import dataclasses

import pytest

from pragya_assistant.llm.base import ChatProvider, EmbeddingProvider
from pragya_assistant.llm.types import ChatResult, Message, ToolCall, ToolSpec


def test_message_defaults() -> None:
    m = Message(role="user", content="hi")
    assert m.role == "user"
    assert m.content == "hi"
    assert m.tool_calls == ()
    assert m.tool_call_id is None


def test_message_is_frozen() -> None:
    m = Message(role="user", content="hi")
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.content = "x"  # type: ignore[misc]


def test_tool_call_and_spec() -> None:
    tc = ToolCall(id="t1", name="remember", arguments={"text": "x"})
    assert tc.name == "remember"
    assert tc.arguments == {"text": "x"}
    spec = ToolSpec(name="remember", description="store", input_schema={"type": "object"})
    assert spec.input_schema["type"] == "object"


def test_chat_result() -> None:
    r = ChatResult(text="done", tool_calls=(), finish_reason="stop", usage={})
    assert r.finish_reason == "stop"
    assert r.tool_calls == ()


def test_chat_provider_is_structural() -> None:
    class FakeChat:
        async def chat(
            self,
            *,
            messages: list[Message],
            tools: list[ToolSpec] | None = None,
            model: str | None = None,
        ) -> ChatResult:
            return ChatResult(text="", tool_calls=(), finish_reason="stop", usage={})

    assert isinstance(FakeChat(), ChatProvider)


def test_embedding_provider_is_structural() -> None:
    class FakeEmbed:
        async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
            return [[0.0] for _ in texts]

    assert isinstance(FakeEmbed(), EmbeddingProvider)
