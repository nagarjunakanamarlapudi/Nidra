"""Build concrete providers from settings.

Selecting providers happens here and nowhere else; the rest of the app depends
only on the ``ChatProvider`` / ``EmbeddingProvider`` interfaces.
"""

from __future__ import annotations

from pragya_assistant.config import ChatProviderName, Settings
from pragya_assistant.llm.anthropic_provider import AnthropicChatProvider
from pragya_assistant.llm.base import ChatProvider, EmbeddingProvider
from pragya_assistant.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider
from pragya_assistant.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider


def build_chat_provider(settings: Settings, provider: ChatProviderName) -> ChatProvider:
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for the anthropic chat provider")
        return AnthropicChatProvider(settings.anthropic_api_key, settings.llm_chat_model)
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai chat provider")
        return OpenAIChatProvider(settings.openai_api_key, settings.llm_chat_model)
    if provider == "ollama":
        return OllamaChatProvider(settings.ollama_base_url, settings.llm_chat_model)
    raise ValueError(f"Unknown chat provider: {provider!r}")


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.llm_embedding_provider
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for the openai embedding provider")
        return OpenAIEmbeddingProvider(settings.openai_api_key, settings.llm_embedding_model)
    if provider == "ollama":
        return OllamaEmbeddingProvider(settings.ollama_base_url, settings.llm_embedding_model)
    raise ValueError(f"Unknown embedding provider: {provider!r}")
