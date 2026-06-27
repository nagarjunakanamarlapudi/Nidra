"""Provider interfaces.

Structural (``Protocol``) so any object with the right shape qualifies — no
inheritance required — and ``runtime_checkable`` so dependency wiring can assert
conformance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pragya_assistant.llm.types import ChatResult, Effort, Message, ToolSpec


@runtime_checkable
class ChatProvider(Protocol):
    """A chat-completion backend with tool-calling support."""

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> ChatResult: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A text-embedding backend."""

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...
