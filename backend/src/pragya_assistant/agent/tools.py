"""Tool abstraction and registry for the agent loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pragya_assistant.llm.types import Message, ToolCall, ToolSpec

ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    """A callable the model can invoke: schema + async handler returning text."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name, description=self.description, input_schema=self.input_schema
        )


class ToolRegistry:
    """Holds tools and executes a model's tool calls."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def specs(self) -> list[ToolSpec]:
        return [tool.spec() for tool in self._tools.values()]

    async def run(self, call: ToolCall) -> Message:
        """Execute a tool call, returning a ``role="tool"`` result message.

        Unknown tools and handler exceptions are returned as error text rather
        than raised, so the model can see the failure and adapt.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return Message(
                role="tool", content=f"Error: unknown tool {call.name!r}", tool_call_id=call.id
            )
        try:
            content = await tool.handler(call.arguments)
        except Exception as exc:  # deliberately broad: report failures back to the model
            content = f"Error: {exc}"
        return Message(role="tool", content=content, tool_call_id=call.id)
