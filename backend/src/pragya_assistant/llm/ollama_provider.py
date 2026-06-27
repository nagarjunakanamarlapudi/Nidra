"""Ollama chat + embedding providers — maps the llm contract onto Ollama's REST API.

Ollama runs as a local server, so these talk to it over plain HTTP with
``httpx`` (no SDK). Each call opens and closes its own ``AsyncClient`` so there
is no long-lived connection to manage or leak.
"""

from __future__ import annotations

from typing import Any

import httpx

from pragya_assistant.llm.types import ChatResult, Effort, FinishReason, Message, ToolCall, ToolSpec


class OllamaChatProvider:
    """``ChatProvider`` backed by Ollama's ``/api/chat`` endpoint."""

    def __init__(self, base_url: str, default_model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> ChatResult:
        # effort is accepted for protocol conformance; Ollama's thinking toggle is
        # model-specific and left to the model's own defaults.
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [_map_message(m) for m in messages],
            "stream": False,
        }
        if tools:
            body["tools"] = [_map_tool(t) for t in tools]

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self._base_url}/api/chat", json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        return _parse_chat_response(data)


class OllamaEmbeddingProvider:
    """``EmbeddingProvider`` backed by Ollama's ``/api/embed`` endpoint."""

    def __init__(self, base_url: str, default_model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "input": texts,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self._base_url}/api/embed", json=body)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
        embeddings: list[list[float]] = data["embeddings"]
        return embeddings


def _map_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _map_message(msg: Message) -> dict[str, Any]:
    """Map one contract ``Message`` to an Ollama message dict.

    Ollama tool calls carry an arguments *object* (not a JSON string), and tool
    results are plain ``role="tool"`` messages with no id reference.
    """
    if msg.role == "assistant" and msg.tool_calls:
        return {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"function": {"name": call.name, "arguments": call.arguments}}
                for call in msg.tool_calls
            ],
        }
    return {"role": msg.role, "content": msg.content}


def _parse_chat_response(data: dict[str, Any]) -> ChatResult:
    message: dict[str, Any] = data.get("message", {})
    raw_tool_calls: list[dict[str, Any]] = message.get("tool_calls") or []

    tool_calls: list[ToolCall] = []
    for i, raw in enumerate(raw_tool_calls):
        fn = raw["function"]
        tool_calls.append(ToolCall(id=f"call_{i}", name=fn["name"], arguments=fn["arguments"]))

    finish: FinishReason = "tool_calls" if tool_calls else "stop"
    return ChatResult(
        text=message.get("content", ""),
        tool_calls=tuple(tool_calls),
        finish_reason=finish,
        usage={
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
        },
    )
