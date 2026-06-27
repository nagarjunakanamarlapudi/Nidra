from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.mcp_memory import create_memory_server, memory_mcp_tools


def _tool(name: str) -> Tool:
    async def handler(args: dict[str, Any]) -> str:
        return "ok"

    return Tool(
        name=name,
        description="d",
        input_schema={"type": "object", "properties": {}},
        handler=handler,
    )


def test_memory_mcp_tools_conversion() -> None:
    mcp_tools = memory_mcp_tools([_tool("remember_note"), _tool("recall_notes")])
    assert [t.name for t in mcp_tools] == ["remember_note", "recall_notes"]
    assert mcp_tools[0].inputSchema == {"type": "object", "properties": {}}
    assert mcp_tools[0].description == "d"


def test_create_memory_server_builds() -> None:
    server = create_memory_server([_tool("remember_note")])
    assert server.name == "pragya"
