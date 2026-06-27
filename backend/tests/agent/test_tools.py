from typing import Any

from pragya_assistant.agent.tools import Tool, ToolRegistry
from pragya_assistant.llm.types import ToolCall


def _echo_tool() -> Tool:
    async def handler(args: dict[str, Any]) -> str:
        return f"echo: {args['value']}"

    return Tool(
        name="echo",
        description="Echo the value",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
        handler=handler,
    )


async def test_registry_runs_tool_and_returns_tool_message() -> None:
    registry = ToolRegistry([_echo_tool()])
    msg = await registry.run(ToolCall(id="c1", name="echo", arguments={"value": "hi"}))
    assert msg.role == "tool"
    assert msg.tool_call_id == "c1"
    assert msg.content == "echo: hi"


async def test_specs_lists_registered_tools() -> None:
    registry = ToolRegistry([_echo_tool()])
    assert [s.name for s in registry.specs()] == ["echo"]


async def test_unknown_tool_returns_error_message() -> None:
    registry = ToolRegistry([])
    msg = await registry.run(ToolCall(id="c1", name="missing", arguments={}))
    assert msg.role == "tool"
    assert msg.tool_call_id == "c1"
    assert "unknown tool" in msg.content.lower()


async def test_tool_exception_is_surfaced_as_error() -> None:
    async def boom(args: dict[str, Any]) -> str:
        raise RuntimeError("kaboom")

    registry = ToolRegistry(
        [Tool(name="boom", description="d", input_schema={"type": "object"}, handler=boom)]
    )
    msg = await registry.run(ToolCall(id="c2", name="boom", arguments={}))
    assert msg.tool_call_id == "c2"
    assert "kaboom" in msg.content
