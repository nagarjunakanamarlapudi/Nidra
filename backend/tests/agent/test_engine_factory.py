from typing import Any, Protocol, cast

from pragya_assistant.agent.claude_code_engine import ClaudeCodeEngine
from pragya_assistant.agent.codex_engine import CodexEngine
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.factory import build_engine
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
