import json

import httpx
import respx

from pragya_assistant.llm.ollama_provider import OllamaChatProvider, OllamaEmbeddingProvider
from pragya_assistant.llm.types import Message, ToolCall, ToolSpec

BASE_URL = "http://localhost:11434"
CHAT_URL = f"{BASE_URL}/api/chat"
EMBED_URL = f"{BASE_URL}/api/embed"


def _chat_provider() -> OllamaChatProvider:
    return OllamaChatProvider(base_url=BASE_URL, default_model="llama3.1")


def _embed_provider() -> OllamaEmbeddingProvider:
    return OllamaEmbeddingProvider(base_url=BASE_URL, default_model="nomic-embed-text")


@respx.mock
async def test_text_response_parsed() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "Hello!"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 10,
                "eval_count": 3,
            },
        )
    )

    result = await _chat_provider().chat(messages=[Message(role="user", content="hi")])

    assert result.text == "Hello!"
    assert result.finish_reason == "stop"
    assert result.tool_calls == ()
    assert result.usage == {"input_tokens": 10, "output_tokens": 3}

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "llama3.1"
    assert body["stream"] is False
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert "tools" not in body


@respx.mock
async def test_tool_call_response_parsed() -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"function": {"name": "remember", "arguments": {"text": "x"}}}],
                },
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 20,
                "eval_count": 8,
            },
        )
    )
    tools = [ToolSpec(name="remember", description="store a fact", input_schema={"type": "object"})]

    result = await _chat_provider().chat(
        messages=[Message(role="user", content="remember x")], tools=tools
    )

    assert result.finish_reason == "tool_calls"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert (tc.id, tc.name, tc.arguments) == ("call_0", "remember", {"text": "x"})


@respx.mock
async def test_message_and_tool_mapping_round_trip() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "llama3.1",
                "message": {"role": "assistant", "content": "done"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 1,
                "eval_count": 1,
            },
        )
    )
    messages = [
        Message(role="system", content="You are Pragya."),
        Message(role="user", content="remember x"),
        Message(
            role="assistant",
            tool_calls=(ToolCall(id="call_0", name="remember", arguments={"text": "x"}),),
        ),
        Message(role="tool", content="stored", tool_call_id="call_0"),
    ]
    tools = [ToolSpec(name="remember", description="d", input_schema={"type": "object"})]

    await _chat_provider().chat(messages=messages, tools=tools)

    body = json.loads(route.calls.last.request.content)
    assert body["messages"] == [
        {"role": "system", "content": "You are Pragya."},
        {"role": "user", "content": "remember x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "remember", "arguments": {"text": "x"}}}],
        },
        {"role": "tool", "content": "stored"},
    ]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {"name": "remember", "description": "d", "parameters": {"type": "object"}},
        }
    ]


@respx.mock
async def test_embeddings() -> None:
    route = respx.post(EMBED_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "nomic-embed-text",
                "embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            },
        )
    )

    result = await _embed_provider().embed(["a", "b"])

    assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    body = json.loads(route.calls.last.request.content)
    assert body["model"] == "nomic-embed-text"
    assert body["input"] == ["a", "b"]
