from typing import Any

from pragya_assistant.agent.claude_code_engine import ClaudeCodeEngine
from pragya_assistant.agent.codex_engine import CodexEngine
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.factory import build_engine
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


def test_build_loop_engine_for_anthropic_api() -> None:
    s = _settings(agent_engine="anthropic-api", anthropic_api_key="k")
    assert isinstance(build_engine(s, _memory()), LoopEngine)


def test_build_loop_engine_for_openai_api() -> None:
    s = _settings(agent_engine="openai-api", openai_api_key="k")
    assert isinstance(build_engine(s, _memory()), LoopEngine)


def test_build_loop_engine_for_ollama() -> None:
    s = _settings(agent_engine="ollama")
    assert isinstance(build_engine(s, _memory()), LoopEngine)


def test_build_claude_code_engine() -> None:
    s = _settings(agent_engine="claude-code")
    assert isinstance(build_engine(s, _memory()), ClaudeCodeEngine)


def test_build_codex_engine() -> None:
    s = _settings(agent_engine="codex")
    assert isinstance(build_engine(s, _memory()), CodexEngine)
