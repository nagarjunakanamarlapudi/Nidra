import json

import httpx
import respx

from pragya_assistant.llm.anthropic_provider import AnthropicChatProvider
from pragya_assistant.llm.types import Message, ToolCall, ToolSpec

URL = "https://api.anthropic.com/v1/messages"


def _provider() -> AnthropicChatProvider:
    return AnthropicChatProvider(api_key="test-key", default_model="claude-opus-4-8")


@respx.mock
async def test_text_response_parsed() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": "Hello!"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )

    result = await _provider().chat(messages=[Message(role="user", content="hi")])

    assert result.text == "Hello!"
    assert result.finish_reason == "stop"
    assert result.tool_calls == ()
    assert result.usage == {"input_tokens": 10, "output_tokens": 3}

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "claude-opus-4-8"
    assert body["max_tokens"] == 4096
    assert body["thinking"] == {"type": "adaptive"}
    assert "temperature" not in body and "top_p" not in body
    assert body["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
async def test_effort_sent_and_reasoning_captured() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_3",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [
                    {"type": "thinking", "thinking": "the answer is 4", "signature": "sig"},
                    {"type": "text", "text": "4"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )
    )

    result = await _provider().chat(messages=[Message(role="user", content="2+2?")], effort="high")

    assert result.text == "4"
    assert "answer is 4" in result.reasoning
    body = json.loads(route.calls.last.request.content)
    assert body["output_config"] == {"effort": "high"}


@respx.mock
async def test_tool_use_response_parsed() -> None:
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "msg_2",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [
                    {"type": "text", "text": "Noting that."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "remember",
                        "input": {"text": "x"},
                    },
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 20, "output_tokens": 8},
            },
        )
    )
    tools = [ToolSpec(name="remember", description="store a fact", input_schema={"type": "object"})]

    result = await _provider().chat(
        messages=[Message(role="user", content="remember x")], tools=tools
    )

    assert result.finish_reason == "tool_calls"
    assert result.text == "Noting that."
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert (tc.id, tc.name, tc.arguments) == ("toolu_1", "remember", {"text": "x"})


@respx.mock
async def test_message_and_tool_mapping_round_trip() -> None:
    route = respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": "done"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )
    messages = [
        Message(role="system", content="You are Pragya."),
        Message(role="user", content="remember x"),
        Message(
            role="assistant",
            tool_calls=(ToolCall(id="toolu_1", name="remember", arguments={"text": "x"}),),
        ),
        Message(role="tool", content="stored", tool_call_id="toolu_1"),
    ]
    tools = [ToolSpec(name="remember", description="d", input_schema={"type": "object"})]

    await _provider().chat(messages=messages, tools=tools)

    body = json.loads(route.calls.last.request.content)
    assert body["system"] == "You are Pragya."
    assert body["messages"] == [
        {"role": "user", "content": "remember x"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_1", "name": "remember", "input": {"text": "x"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "stored"}],
        },
    ]
    assert body["tools"] == [
        {"name": "remember", "description": "d", "input_schema": {"type": "object"}}
    ]
