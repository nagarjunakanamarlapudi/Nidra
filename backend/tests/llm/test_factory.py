from typing import Any

import pytest

from pragya_assistant.config import Settings
from pragya_assistant.llm.anthropic_provider import AnthropicChatProvider
from pragya_assistant.llm.factory import build_chat_provider, build_embedding_provider
from pragya_assistant.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider
from pragya_assistant.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Settings:
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    base: dict[str, Any] = {
        "app_secret_key": "s",
        "api_auth_token": "t",
        "database_url": "postgresql+asyncpg://pragya:pragya@localhost/pragya",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_build_anthropic_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, anthropic_api_key="k")
    assert isinstance(build_chat_provider(s, "anthropic"), AnthropicChatProvider)


def test_build_openai_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, openai_api_key="k")
    assert isinstance(build_chat_provider(s, "openai"), OpenAIChatProvider)


def test_build_ollama_chat_needs_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert isinstance(build_chat_provider(s, "ollama"), OllamaChatProvider)


def test_anthropic_chat_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_chat_provider(s, "anthropic")


def test_build_openai_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, llm_embedding_provider="openai", openai_api_key="k")
    assert isinstance(build_embedding_provider(s), OpenAIEmbeddingProvider)


def test_build_ollama_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, llm_embedding_provider="ollama")
    assert isinstance(build_embedding_provider(s), OllamaEmbeddingProvider)


def test_openai_embedding_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, llm_embedding_provider="openai")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embedding_provider(s)


def test_unknown_chat_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, anthropic_api_key="k")
    with pytest.raises(ValueError, match="Unknown chat provider"):
        build_chat_provider(s, "bogus")  # type: ignore[arg-type]
