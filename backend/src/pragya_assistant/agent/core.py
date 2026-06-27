"""The agent loop: assemble context, call the model, run tools, repeat."""

from __future__ import annotations

import structlog

from pragya_assistant.agent.tools import ToolRegistry
from pragya_assistant.llm.base import ChatProvider
from pragya_assistant.llm.types import Effort, Message

log = structlog.get_logger(__name__)


class LoopEngine:
    """Provider-agnostic tool-calling engine (our own agent loop).

    ``respond`` prepends the system prompt and prior history, drives the
    model↔tool loop until the model stops calling tools (or ``max_steps`` is
    hit), and returns the final text plus the messages produced this turn (the
    system prompt is sent to the model but excluded from the stored turn).
    """

    def __init__(
        self,
        *,
        provider: ChatProvider,
        registry: ToolRegistry,
        system_prompt: str,
        max_steps: int = 6,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt
        self._max_steps = max_steps

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        user_message = Message(role="user", content=user_text)
        conversation: list[Message] = [
            Message(role="system", content=self._system_prompt),
            *history,
            user_message,
        ]
        produced: list[Message] = [user_message]
        final_text = ""
        usage_total: dict[str, int] = {}
        reasoning = ""

        for _ in range(self._max_steps):
            result = await self._provider.chat(
                messages=conversation, tools=self._registry.specs(), effort=effort
            )
            final_text = result.text
            if result.reasoning:
                reasoning = result.reasoning
            for key, value in (result.usage or {}).items():
                if isinstance(value, int):
                    usage_total[key] = usage_total.get(key, 0) + value
            assistant_message = Message(
                role="assistant", content=result.text, tool_calls=result.tool_calls
            )
            conversation.append(assistant_message)
            produced.append(assistant_message)

            if result.finish_reason != "tool_calls" or not result.tool_calls:
                break

            for call in result.tool_calls:
                tool_message = await self._registry.run(call)
                conversation.append(tool_message)
                produced.append(tool_message)

        if reasoning:
            log.info("engine_reasoning", engine="loop", reasoning=reasoning[:2000])
        log.info("engine_usage", engine="loop", usage=usage_total)
        return final_text, produced
