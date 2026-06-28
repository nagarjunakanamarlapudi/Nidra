"""Neutral LLM-completion helpers shared by the opinion-maker and the dreamer
(neither subsystem imports the other)."""

from __future__ import annotations

import json

import httpx
import pytest

from pragya_assistant.agent import completion as completion_mod
from pragya_assistant.agent.completion import (
    engine_completion_fn,
    extract_json,
    ollama_completion_fn,
)


def test_extract_json_strips_fences_and_salvages() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise {"b": 2} trailing') == {"b": 2}
    assert extract_json("not json") == {}


class _FakeEngine:
    async def respond(self, history, user_text, *, effort=None):  # type: ignore[no-untyped-def]
        return f"echo:{user_text}", []


async def test_engine_completion_fn_calls_respond() -> None:
    fn = engine_completion_fn(_FakeEngine())  # type: ignore[arg-type]
    assert await fn("hi") == "echo:hi"


async def test_ollama_completion_fn_forces_json_and_low_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Faithful to the original: /api/chat, forced JSON, temperature 0.3, prompt as
    the user message; parses message.content."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": '{"ok": 1}'}})

    real_client = httpx.AsyncClient

    def fake_client(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(completion_mod.httpx, "AsyncClient", fake_client)

    out = await ollama_completion_fn("http://host:11434", "gemma")("PROMPT")
    assert out == '{"ok": 1}'
    assert str(captured["url"]).endswith("/api/chat")
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["format"] == "json"
    assert body["options"] == {"temperature": 0.3}
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
