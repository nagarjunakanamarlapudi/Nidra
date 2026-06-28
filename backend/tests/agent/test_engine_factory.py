from typing import Any, Protocol, cast

from pragya_assistant.agent.claude_code_engine import ClaudeCodeEngine
from pragya_assistant.agent.codex_engine import CodexEngine
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.factory import (
    build_confined_completion_fn,
    build_confined_engine,
    build_engine,
)
from pragya_assistant.agent.guard import GuardedEngine
from pragya_assistant.agent.hardening import HARDENING_PREAMBLE
from pragya_assistant.config import Settings
from pragya_assistant.memory.db import create_engine, create_session_factory
from pragya_assistant.memory.service import MemoryService
from tests.fakes import FakeEmbeddingProvider


def _memory() -> MemoryService:
    # Lazy engine — build_engine never queries, so no DB is needed here.
    factory = create_session_factory(
        create_engine("postgresql+asyncpg://pragya:pragya@localhost/pragya")
    )
    return MemoryService(
        session_factory=factory,
        embedder=FakeEmbeddingProvider(),
        embedding_model="fake",
        embedding_dim=1536,
    )


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "app_secret_key": "s",
        "api_auth_token": "t",
        "database_url": "postgresql+asyncpg://pragya:pragya@localhost/pragya",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


class _HasSystemPrompt(Protocol):
    _system_prompt: str


def _inner(s: Settings) -> object:
    """Build the engine, assert it is guard-wrapped, and return the inner brain.

    Every built engine must be a ``GuardedEngine`` so its output is always
    scrubbed; the per-engine tests then assert the right inner brain was chosen.
    """
    built = build_engine(s, _memory())
    assert isinstance(built, GuardedEngine)
    return built._inner


def _system_prompt(s: Settings) -> str:
    # Every brain stores its prompt as ``_system_prompt``; reach it through the
    # guard exactly as the per-engine tests reach ``_inner``.
    return cast(_HasSystemPrompt, _inner(s))._system_prompt


def test_build_loop_engine_for_anthropic_api() -> None:
    s = _settings(agent_engine="anthropic-api", anthropic_api_key="k")
    assert isinstance(_inner(s), LoopEngine)


def test_build_loop_engine_for_openai_api() -> None:
    s = _settings(agent_engine="openai-api", openai_api_key="k")
    assert isinstance(_inner(s), LoopEngine)


def test_build_loop_engine_for_ollama() -> None:
    s = _settings(agent_engine="ollama")
    assert isinstance(_inner(s), LoopEngine)


def test_build_claude_code_engine() -> None:
    s = _settings(agent_engine="claude-code")
    assert isinstance(_inner(s), ClaudeCodeEngine)


def test_build_codex_engine() -> None:
    s = _settings(agent_engine="codex")
    assert isinstance(_inner(s), CodexEngine)


def test_build_engine_always_guards_output() -> None:
    # The factory's security contract: regardless of which brain is selected, the
    # returned engine is wrapped so its output is scrubbed.
    s = _settings(agent_engine="anthropic-api", anthropic_api_key="k")
    assert isinstance(build_engine(s, _memory()), GuardedEngine)


def test_every_engine_carries_the_hardening_preamble() -> None:
    # Soft defense layer: every built brain -- on every path -- must have the
    # hardening preamble prepended to its system prompt.
    for s in (
        _settings(agent_engine="anthropic-api", anthropic_api_key="k"),
        _settings(agent_engine="openai-api", openai_api_key="k"),
        _settings(agent_engine="ollama"),
        _settings(agent_engine="codex"),
        _settings(agent_engine="claude-code"),
    ):
        assert _system_prompt(s).startswith(HARDENING_PREAMBLE)


def test_preamble_precedes_the_base_prompt() -> None:
    # Prepend, don't replace: the base system prompt survives after the preamble.
    from pragya_assistant.agent.prompts import BASE_SYSTEM_PROMPT

    prompt = _system_prompt(_settings(agent_engine="ollama"))
    assert prompt.startswith(HARDENING_PREAMBLE)
    assert BASE_SYSTEM_PROMPT in prompt


# --- Confined builders (Sec-6): engines for background jobs ------------------
# build_confined_engine / build_confined_completion_fn produce an engine with NO
# file/bash/web tools at all — so the dreamer + digest can never reach the web or
# the filesystem even if an injected prompt tries. Same single switch + guard +
# harden as the chat engine, just with tools=[] / builtin_tools=().


def _confined_inner(s: Settings) -> object:
    """Build the confined engine, assert it is guard-wrapped, return the brain."""
    built = build_confined_engine(s)
    assert isinstance(built, GuardedEngine)
    return built._inner


def test_confined_engine_always_guards_output() -> None:
    s = _settings(agent_engine="anthropic-api", anthropic_api_key="k")
    assert isinstance(build_confined_engine(s), GuardedEngine)


def test_confined_loop_engine_exposes_no_tools() -> None:
    # Loop brains (anthropic/openai/ollama): the tool registry is empty, so the
    # background job cannot call any tool (memory, finance, calendar, ...).
    for s in (
        _settings(agent_engine="anthropic-api", anthropic_api_key="k"),
        _settings(agent_engine="openai-api", openai_api_key="k"),
        _settings(agent_engine="ollama"),
    ):
        inner = _confined_inner(s)
        assert isinstance(inner, LoopEngine)
        assert inner._registry.specs() == []


def test_confined_claude_code_has_no_tools_and_no_web() -> None:
    # claude-code: no MCP tools, no built-ins (so no Read/Bash AND no WebFetch),
    # and the dangerous filesystem/shell built-ins stay explicitly disallowed.
    inner = _confined_inner(_settings(agent_engine="claude-code"))
    assert isinstance(inner, ClaudeCodeEngine)
    assert inner._tools == []
    assert inner._builtin_tools == ()
    opts = inner._options()
    assert opts.tools == []  # availability: zero built-ins (no web, no file, no bash)
    assert "WebFetch" not in opts.allowed_tools and "WebSearch" not in opts.allowed_tools
    for builtin in ("Read", "Bash", "Write"):
        assert builtin in (opts.disallowed_tools or [])


def test_confined_codex_is_fail_safe() -> None:
    # Codex self-wires its own MCP tools + can bypass the sandbox; the confined
    # path must do NEITHER (no memory MCP, no sandbox bypass) — the fail-safe.
    inner = _confined_inner(_settings(agent_engine="codex"))
    assert isinstance(inner, CodexEngine)
    assert inner._bypass_sandbox is False
    assert inner._mcp_command is None


def test_chat_codex_keeps_bypass_and_mcp() -> None:
    # The boundary: only the interactive chat engine gets the privileged Codex
    # (memory MCP + sandbox bypass). This must NOT regress.
    inner = _inner(_settings(agent_engine="codex"))
    assert isinstance(inner, CodexEngine)
    assert inner._bypass_sandbox is True
    assert inner._mcp_command is not None


def test_confined_engine_carries_hardening_preamble() -> None:
    for s in (
        _settings(agent_engine="ollama"),
        _settings(agent_engine="codex"),
        _settings(agent_engine="claude-code"),
    ):
        assert cast(_HasSystemPrompt, _confined_inner(s))._system_prompt.startswith(
            HARDENING_PREAMBLE
        )


def test_build_confined_completion_fn_returns_callable() -> None:
    # The dreamer/digest one-shot completion is backed by a confined engine.
    fn = build_confined_completion_fn(_settings(agent_engine="ollama"))
    assert callable(fn)
