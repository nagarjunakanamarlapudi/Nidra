"""Anthropic chat provider — maps the llm contract onto the Messages API.

Uses adaptive thinking and never sends sampling parameters (``temperature`` /
``top_p`` / ``budget_tokens`` are rejected on Opus 4.7+).
"""

from __future__ import annotations

from typing import Any, cast

import anthropic
from anthropic.types import Message as AnthropicMessage
from anthropic.types import TextBlock, ToolUseBlock

from pragya_assistant.llm.types import ChatResult, Effort, FinishReason, Message, ToolCall, ToolSpec

_DEFAULT_MAX_TOKENS = 4096


class AnthropicChatProvider:
    """``ChatProvider`` backed by Anthropic's Messages API."""

    def __init__(
        self, api_key: str, default_model: str, *, max_tokens: int = _DEFAULT_MAX_TOKENS
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self._max_tokens = max_tokens

    async def chat(
        self,
        *,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        model: str | None = None,
        effort: Effort | None = None,
    ) -> ChatResult:
        system, mapped = _map_messages(messages)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": self._max_tokens,
            "messages": mapped,
            "thinking": {"type": "adaptive"},
        }
        if effort:
            # extra_body so this works across SDK versions that don't yet type
            # output_config as a first-class parameter.
            params["extra_body"] = {"output_config": {"effort": effort}}
        if system:
            params["system"] = system
        if tools:
            params["tools"] = [_map_tool(t) for t in tools]

        response = cast(AnthropicMessage, await self._client.messages.create(**params))
        return _parse_response(response)


def _map_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _map_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Split system text out; map the rest to Anthropic message dicts.

    Consecutive ``tool`` results are merged into one user message, matching
    Anthropic's expectation that all tool_result blocks for an assistant turn
    arrive in a single following user turn.
    """
    system_parts: list[str] = []
    mapped: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            if msg.content:
                system_parts.append(msg.content)
        elif msg.role == "user":
            mapped.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            mapped.append({"role": "assistant", "content": _assistant_content(msg)})
        elif msg.role == "tool":
            block: dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id,
                "content": msg.content,
            }
            last = mapped[-1] if mapped else None
            if last is not None and last["role"] == "user" and isinstance(last["content"], list):
                last["content"].append(block)
            else:
                mapped.append({"role": "user", "content": [block]})

    return "\n".join(system_parts), mapped


def _assistant_content(msg: Message) -> str | list[dict[str, Any]]:
    if not msg.tool_calls:
        return msg.content
    blocks: list[dict[str, Any]] = []
    if msg.content:
        blocks.append({"type": "text", "text": msg.content})
    blocks.extend(
        {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
        for call in msg.tool_calls
    )
    return blocks


def _parse_response(response: AnthropicMessage) -> ChatResult:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in response.content:
        if isinstance(block, TextBlock):
            text_parts.append(block.text)
        elif isinstance(block, ToolUseBlock):
            tool_calls.append(
                ToolCall(id=block.id, name=block.name, arguments=cast(dict[str, Any], block.input))
            )
        elif getattr(block, "type", None) == "thinking":
            reasoning_parts.append(getattr(block, "thinking", "") or "")
    finish: FinishReason = "tool_calls" if response.stop_reason == "tool_use" else "stop"
    return ChatResult(
        text="".join(text_parts),
        tool_calls=tuple(tool_calls),
        finish_reason=finish,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        reasoning="\n".join(p for p in reasoning_parts if p),
    )
