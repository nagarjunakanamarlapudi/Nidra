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
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.engine import AgentEngine
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
    # Finance tools are intentionally NOT wired here: for in-process engines they
    # arrive via the Plaid connector (so they're owned by the marketplace). The
    # Codex MCP server still wires them directly (it has no connector runtime).
    engine = settings.agent_engine
    tools = build_agent_tools(
        memory,
        task_store,
        calendar_service,
        email_service,
        connector_tools=connector_tools,
        session_factory=session_factory,
    )
    if engine in _LOOP_PROVIDERS:
        provider = build_chat_provider(settings, _LOOP_PROVIDERS[engine])
        return LoopEngine(
            provider=provider,
            registry=ToolRegistry(tools),
            system_prompt=build_system_prompt(),
        )
    if engine == "codex":
        return CodexEngine(
            model=settings.codex_model,
            system_prompt=build_system_prompt(),
            mcp_command=[sys.executable, "-m", "pragya_assistant.mcp_memory"],
            mcp_env=_codex_mcp_env(settings),
            bypass_sandbox=True,
        )
    if engine == "claude-code":
        # ``builtin_tools`` are the SDK built-ins this engine may use (e.g.
        # ``WebSearch``/``WebFetch``). They are NOT hardcoded here: like finance
        # tools via Plaid, web built-ins arrive through the web_search connector
        # (seeded from ``settings.web_search_enabled``) and are threaded in by the
        # connector manager. Background-job builders pass nothing → () → no
        # built-ins, so only chat keeps web. Everything else stays confined.
        return ClaudeCodeEngine(
            tools=tools,
            system_prompt=build_system_prompt(),
            model=settings.claude_code_model,
            builtin_tools=builtin_tools,
        )
    raise ValueError(f"Unknown agent engine: {engine!r}")
