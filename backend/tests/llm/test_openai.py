import json

import httpx
import respx

from pragya_assistant.llm.openai_provider import OpenAIChatProvider, OpenAIEmbeddingProvider
from pragya_assistant.llm.types import Message, ToolCall, ToolSpec

CHAT_URL = "https://api.openai.com/v1/chat/completions"
EMBED_URL = "https://api.openai.com/v1/embeddings"


def _chat_provider() -> OpenAIChatProvider:
    return OpenAIChatProvider(api_key="test-key", default_model="gpt-4o")


def _embed_provider() -> OpenAIEmbeddingProvider:
    return OpenAIEmbeddingProvider(api_key="test-key", default_model="text-embedding-3-small")


@respx.mock
async def test_text_response_parsed() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Hello!", "tool_calls": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )
    )
    tools = [ToolSpec(name="remember", description="store a fact", input_schema={"type": "object"})]

    result = await _chat_provider().chat(messages=[Message(role="user", content="hi")], tools=tools)

    assert result.text == "Hello!"
    assert result.finish_reason == "stop"
    assert result.tool_calls == ()
    assert result.usage == {"input_tokens": 10, "output_tokens": 3}

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "gpt-4o"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "remember",
                "description": "store a fact",
                "parameters": {"type": "object"},
            },
        }
    ]


@respx.mock
async def test_effort_sent_as_reasoning_effort() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-y",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok", "tool_calls": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )

    await _chat_provider().chat(messages=[Message(role="user", content="hi")], effort="high")

    body = json.loads(route.calls.last.request.content)
    assert body["reasoning_effort"] == "high"


@respx.mock
async def test_tool_call_response_parsed() -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "remember",
                                        "arguments": '{"text":"x"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
            },
        )
    )

    result = await _chat_provider().chat(messages=[Message(role="user", content="remember x")])

    assert result.finish_reason == "tool_calls"
    assert result.text == ""
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert (tc.id, tc.name, tc.arguments) == ("call_1", "remember", {"text": "x"})


@respx.mock
async def test_message_mapping_round_trip() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "created": 0,
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "done", "tool_calls": None},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    messages = [
        Message(role="system", content="You are Pragya."),
        Message(role="user", content="remember x"),
        Message(
            role="assistant",
            tool_calls=(ToolCall(id="call_1", name="remember", arguments={"text": "x"}),),
        ),
        Message(role="tool", content="stored", tool_call_id="call_1"),
    ]

    await _chat_provider().chat(messages=messages)

    body = json.loads(route.calls.last.request.content)
    assert body["messages"] == [
        {"role": "system", "content": "You are Pragya."},
        {"role": "user", "content": "remember x"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "remember", "arguments": '{"text": "x"}'},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "stored"},
    ]
    assert "tools" not in body


@respx.mock
async def test_embeddings_returns_vectors() -> None:
    respx.post(EMBED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2]},
                    {"object": "embedding", "index": 1, "embedding": [0.3, 0.4]},
                ],
                "model": "text-embedding-3-small",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )
    )

    vectors = await _embed_provider().embed(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
