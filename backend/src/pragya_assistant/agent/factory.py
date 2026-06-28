"""Engine (brain) selection — maps the ``AGENT_ENGINE`` selector to an engine.

This is the single place the brain is chosen, spanning all plug categories:
loop-based brains (model API keys / local LLM) wrap a ``ChatProvider`` in the
``LoopEngine``; coding-agent brains (subscriptions) are their own engines.
"""

from __future__ import annotations

import sys

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.claude_code_engine import ClaudeCodeEngine
from pragya_assistant.agent.codex_engine import CodexEngine
from pragya_assistant.agent.completion import CompletionFn, engine_completion_fn
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.guard import guard
from pragya_assistant.agent.hardening import harden
from pragya_assistant.agent.prompts import build_system_prompt
from pragya_assistant.agent.tools import Tool, ToolRegistry
from pragya_assistant.agent.toolset import build_agent_tools
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.config import ChatProviderName, Settings
from pragya_assistant.email_inbox.service import EmailService
from pragya_assistant.llm.factory import build_chat_provider
from pragya_assistant.memory.service import MemoryService
from pragya_assistant.tasks.store import TaskStore

# Loop-based brains resolve to a raw chat provider.
_LOOP_PROVIDERS: dict[str, ChatProviderName] = {
    "anthropic-api": "anthropic",
    "openai-api": "openai",
    "ollama": "ollama",
}


def _codex_mcp_env(settings: Settings) -> dict[str, str]:
    """Env passed to the memory MCP server that codex spawns (it reads settings)."""
    env = {
        "APP_SECRET_KEY": settings.app_secret_key,
        "API_AUTH_TOKEN": settings.api_auth_token,
        "DATABASE_URL": settings.database_url,
        "LLM_EMBEDDING_PROVIDER": settings.llm_embedding_provider,
        "LLM_EMBEDDING_MODEL": settings.llm_embedding_model,
        "LLM_EMBEDDING_DIM": str(settings.llm_embedding_dim),
        "OLLAMA_BASE_URL": settings.ollama_base_url,
    }
    if settings.openai_api_key:
        env["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.calendar_ics_url:
        env["CALENDAR_ICS_URL"] = settings.calendar_ics_url
    if settings.email_address and settings.email_app_password:
        env["EMAIL_ADDRESS"] = settings.email_address
        env["EMAIL_APP_PASSWORD"] = settings.email_app_password
        env["EMAIL_IMAP_HOST"] = settings.email_imap_host
    if settings.plaid_client_id and settings.plaid_secret:
        env["PLAID_CLIENT_ID"] = settings.plaid_client_id
        env["PLAID_SECRET"] = settings.plaid_secret
        env["PLAID_ENV"] = settings.plaid_env
    return env


def _make_engine(
    settings: Settings,
    *,
    tools: list[Tool],
    system_prompt: str,
    builtin_tools: tuple[str, ...] = (),
    allow_codex_bypass: bool = False,
) -> AgentEngine:
    """The single place an engine is constructed — confinement + harden + guard.

    Picks the inner brain per ``settings.agent_engine``, prepends the hardening
    preamble to ``system_prompt`` (idempotent), and wraps the result in
    :func:`guard` so its output is always scrubbed. Confinement is expressed by
    the CALLER: chat passes its full ``tools`` + web ``builtin_tools``; the
    confined builders pass ``tools=[]`` / ``builtin_tools=()`` so the engine can
    reach no file/bash/web tool at all.

    Codex is special: it self-wires its own MCP tools and can bypass the sandbox,
    so the in-process ``tools`` list does not apply to it. ``allow_codex_bypass``
    gates that privilege — it defaults to ``False`` (fail-closed), so only the
    chat path (which passes ``allow_codex_bypass=True``) ever gets the memory MCP
    + sandbox bypass. Every confined caller gets a minimal, read-only Codex.
    """
    engine = settings.agent_engine
    # Soft defense layer: prepend the hardening preamble once, here, so EVERY
    # brain built below (every path) carries it. ``harden`` is idempotent.
    system_prompt = harden(system_prompt)
    # Every engine is wrapped in ``guard`` so its output is always scrubbed of
    # secrets — the single, engine-agnostic chokepoint of the output defense.
    if engine in _LOOP_PROVIDERS:
        provider = build_chat_provider(settings, _LOOP_PROVIDERS[engine])
        return guard(
            LoopEngine(
                provider=provider,
                registry=ToolRegistry(tools),
                system_prompt=system_prompt,
            )
        )
    if engine == "codex":
        return guard(_make_codex_engine(settings, system_prompt, allow_bypass=allow_codex_bypass))
    if engine == "claude-code":
        # ``builtin_tools`` are the SDK built-ins this engine may use (e.g.
        # ``WebSearch``/``WebFetch``). They are NOT hardcoded here: like finance
        # tools via Plaid, web built-ins arrive through the web_search connector
        # (seeded from ``settings.web_search_enabled``) and are threaded in by the
        # connector manager. Background-job builders pass nothing → () → no
        # built-ins, so only chat keeps web. Everything else stays confined.
        return guard(
            ClaudeCodeEngine(
                tools=tools,
                system_prompt=system_prompt,
                model=settings.claude_code_model,
                builtin_tools=builtin_tools,
            )
        )
    raise ValueError(f"Unknown agent engine: {engine!r}")


def _make_codex_engine(
    settings: Settings, system_prompt: str, *, allow_bypass: bool
) -> CodexEngine:
    """Build a Codex brain — privileged (chat) or fail-safe (confined).

    Chat (``allow_bypass=True``): the memory MCP server + ``bypass_sandbox`` (the
    container is the isolation boundary; single-user only). Unchanged behavior.

    Confined (``allow_bypass=False``): NO memory MCP and NO sandbox bypass — a
    read-only Codex with no extra tools. Codex self-wires tools via MCP, so
    omitting the MCP server leaves it with none; the read-only sandbox blocks
    file writes and network. This is the fail-safe for background jobs that must
    never touch secrets, the filesystem, or the web.
    """
    if not allow_bypass:
        return CodexEngine(
            model=settings.codex_model,
            system_prompt=system_prompt,
            sandbox="read-only",
            bypass_sandbox=False,
        )
    return CodexEngine(
        model=settings.codex_model,
        system_prompt=system_prompt,
        mcp_command=[sys.executable, "-m", "pragya_assistant.mcp_memory"],
        mcp_env=_codex_mcp_env(settings),
        bypass_sandbox=True,
    )


def build_engine(
    settings: Settings,
    memory: MemoryService,
    task_store: TaskStore | None = None,
    calendar_service: CalendarService | None = None,
    email_service: EmailService | None = None,
    connector_tools: list[Tool] | None = None,
    builtin_tools: tuple[str, ...] = (),
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> AgentEngine:
    """The interactive chat engine: full agent tools + (optionally) web built-ins.

    Finance tools are intentionally NOT wired here: for in-process engines they
    arrive via the Plaid connector (so they're owned by the marketplace). The
    Codex MCP server still wires them directly (it has no connector runtime).
    Chat is the one privileged caller of Codex (``allow_codex_bypass=True``).
    """
    tools = build_agent_tools(
        memory,
        task_store,
        calendar_service,
        email_service,
        connector_tools=connector_tools,
        session_factory=session_factory,
    )
    return _make_engine(
        settings,
        tools=tools,
        system_prompt=build_system_prompt(),
        builtin_tools=builtin_tools,
        allow_codex_bypass=True,
    )


def build_opinion_engine(settings: Settings, *, tools: list[Tool]) -> AgentEngine:
    """Engine for the opinion-maker job: the configured brain wired with the
    read-only query tools + the opinion-forming prompt, and CONFINED.

    Passes ``builtin_tools=()`` so the agent gets NO web/file/bash — only the
    in-process query tools (``query_browsing``/``query_calendar``/...). Reuses the
    same single engine switch + ``harden`` + ``guard`` as every other engine, so
    the opinion agent is confined and output-scrubbed for free.

    Codex note: like ``build_engine``, Codex ignores the passed ``tools`` — it
    self-wires its own MCP memory tools. With ``allow_codex_bypass`` defaulting to
    ``False`` the confined (read-only, no-MCP) Codex is used, so under Codex the
    opinion agent still runs but without the query tools. The opinion agent
    therefore targets the claude-code / loop brains."""
    from pragya_assistant.user_model.opinion_agent import OPINION_SYSTEM

    return _make_engine(settings, tools=tools, system_prompt=OPINION_SYSTEM, builtin_tools=())


def build_confined_engine(settings: Settings, *, tools: list[Tool] | None = None) -> AgentEngine:
    """A confined engine: NO web built-ins (``builtin_tools=()``) and — for Codex
    — no memory MCP and no sandbox bypass. Hardened + guarded like every engine.

    ``tools`` is empty by default (the dreamer needs none). The digest passes a
    READ-ONLY data subset (see :func:`build_digest_tools`): those let it gather
    info, but they are in-process data tools — never web/file/bash (web is a
    built-in gated by ``builtin_tools=()``; file/bash are SDK built-ins, never in
    this list and explicitly disallowed). So even with tools the engine cannot
    reach the web or filesystem, and a prompt injection has nowhere to exfiltrate."""
    return _make_engine(
        settings,
        tools=tools or [],
        system_prompt=build_system_prompt(),
        builtin_tools=(),
    )


def build_confined_completion_fn(settings: Settings) -> CompletionFn:
    """A one-shot ``prompt -> text`` completion backed by a confined engine.

    For the dreamer: no tools, no web, no file/bash, scrubbed output, hardened
    prompt — confined and guarded by construction."""
    return engine_completion_fn(build_confined_engine(settings))
