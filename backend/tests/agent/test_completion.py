"""Neutral LLM-completion helpers shared by the opinion-maker and the dreamer
(neither subsystem imports the other)."""

from __future__ import annotations

from pragya_assistant.agent.completion import engine_completion_fn, extract_json


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
