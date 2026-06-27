"""OpenAI providers — map the llm contract onto the Chat Completions and
Embeddings APIs.

Keeps the rest of the system free of vendor types: our :class:`Message` /
:class:`ToolSpec` go in, our :class:`ChatResult` / plain float lists come out.
"""

from __future__ import annotations

import json
from typing import Any, cast

import openai
from openai.types.chat import ChatCompletion

from pragya_assistant.llm.types import ChatResult, Effort, FinishReason, Message, ToolCall, ToolSpec


class OpenAIChatProvider:
    """``ChatProvider`` backed by OpenAI's Chat Completions API."""

    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> ChatResult:
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": [_map_message(m) for m in messages],
        }
        if effort:
            params["extra_body"] = {"reasoning_effort": effort}
        if tools:
            params["tools"] = [_map_tool(t) for t in tools]

        response = cast(ChatCompletion, await self._client.chat.completions.create(**params))
        return _parse_response(response)


class OpenAIEmbeddingProvider:
    """``EmbeddingProvider`` backed by OpenAI's Embeddings API."""

    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=model or self._default_model, input=texts
        )
        return [d.embedding for d in response.data]


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
    if msg.role == "system":
        return {"role": "system", "content": msg.content}
    if msg.role == "user":
        return {"role": "user", "content": msg.content}
    if msg.role == "assistant":
        if msg.tool_calls:
            return {
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ],
            }
        return {"role": "assistant", "content": msg.content}
    return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content}


def _parse_response(response: ChatCompletion) -> ChatResult:
    message = response.choices[0].message
    tool_calls: list[ToolCall] = []
    for call in message.tool_calls or []:
        if call.type != "function":  # ignore custom tool calls; we only define function tools
            continue
        tool_calls.append(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=cast(dict[str, Any], json.loads(call.function.arguments)),
            )
        )
    finish: FinishReason = "tool_calls" if tool_calls else "stop"
    return ChatResult(
        text=message.content or "",
        tool_calls=tuple(tool_calls),
        finish_reason=finish,
        usage={
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
        },
    )
