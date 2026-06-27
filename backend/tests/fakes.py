"""Test doubles shared across suites (importable as ``tests.fakes``)."""

from __future__ import annotations

import hashlib
from typing import Any

from pragya_assistant.llm.types import ChatResult, Effort, Message, ToolSpec


class ScriptedChatProvider:
    """A ChatProvider that returns pre-scripted results and records its calls."""

    def __init__(self, results: list[ChatResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> ChatResult:
        self.calls.append({"messages": list(messages), "tools": tools, "effort": effort})
        if not self._results:
            raise AssertionError("ScriptedChatProvider ran out of scripted results")
        return self._results.pop(0)


class FakeEmbeddingProvider:
    """Deterministic bag-of-words embeddings — no network.

    Each word maps to a fixed component, so texts that share words get
    overlapping nonzero components and a smaller cosine distance. Enough to test
    ranking without a real embedding model.
    """

    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for word in text.lower().split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self._dim  # noqa: S324 — deterministic fake, not cryptographic
            vec[idx] = 1.0
        return vec
