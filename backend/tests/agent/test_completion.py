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
from pragya_assistant.agent.hardening import HARDENING_PREAMBLE


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
    """Faithful to the original: /api/chat, forced JSON, temperature 0.3, the
    caller's prompt riding at the end of the (now hardened) user message; parses
    message.content."""
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
    assert body["format"] == "json"  # forced JSON preserved (dream/opinion parsing)
    assert body["options"] == {"temperature": 0.3}
    messages = body["messages"]
    assert isinstance(messages, list) and len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"].endswith("PROMPT")  # caller's prompt is preserved


async def test_ollama_completion_fn_scrubs_output_and_hardens_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The raw ollama path does its own harden + scrub (it skips the engine's
    ``harden``/``guard``): the sent prompt carries the hardening preamble, and a
    secret the model emits is redacted before it leaves the system — keeping the
    spec's always-on output scrubbing true under AGENT_ENGINE=ollama."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        # The on-device model is coaxed into emitting an AWS key inside its JSON.
        return httpx.Response(
            200, json={"message": {"content": '{"leak": "AKIAIOSFODNN7EXAMPLE"}'}}
        )

    real_client = httpx.AsyncClient

    def fake_client(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(completion_mod.httpx, "AsyncClient", fake_client)

    out = await ollama_completion_fn("http://host:11434", "gemma")("PROMPT")
    # Output is scrubbed: the AWS key never leaves, replaced by [REDACTED].
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED]" in out
    assert json.loads(out) == {"leak": "[REDACTED]"}  # still valid, parseable JSON
    # The sent prompt is hardened: the security preamble precedes the caller's text.
    body = captured["body"]
    assert isinstance(body, dict)
    sent = body["messages"][0]["content"]
    assert sent.startswith(HARDENING_PREAMBLE)
    assert sent.endswith("PROMPT")
