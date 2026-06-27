"""Stdio MCP server exposing Pragya's memory tools.

Run as: ``python -m pragya_assistant.mcp_memory``

Lets external coding agents (Codex) call the same memory tools the loop and
Claude Code engines use. It reuses ``build_memory_tools`` + ``ToolRegistry`` as
the single source of truth, backed by ``MemoryService`` (Postgres). Settings
(DB URL, embedding config) come from the environment the parent passes in.
"""

from __future__ import annotations

import asyncio
from typing import Any

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from pragya_assistant.agent.tools import Tool, ToolRegistry
from pragya_assistant.agent.toolset import build_agent_tools
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.config import get_settings
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.finance.service import build_finance_service
from pragya_assistant.llm.factory import build_embedding_provider
from pragya_assistant.llm.types import ToolCall
from pragya_assistant.memory.db import create_engine, create_session_factory
from pragya_assistant.memory.service import MemoryService
from pragya_assistant.tasks.store import TaskStore

SERVER_NAME = "pragya"


def memory_mcp_tools(tools: list[Tool]) -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(name=t.name, description=t.description, inputSchema=t.input_schema)
        for t in tools
    ]


def create_memory_server(tools: list[Tool]) -> Server[Any, Any]:
    server: Server[Any, Any] = Server(SERVER_NAME)
    registry = ToolRegistry(tools)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return memory_mcp_tools(tools)

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
        message = await registry.run(ToolCall(id="mcp", name=name, arguments=arguments))
        return [mcp_types.TextContent(type="text", text=message.content)]

    return server


async def serve() -> None:
    settings = get_settings()
    db = create_engine(settings.database_url)
    session_factory = create_session_factory(db)
    memory = MemoryService(
        session_factory=session_factory,
        embedder=build_embedding_provider(settings),
        embedding_model=settings.llm_embedding_model,
        embedding_dim=settings.llm_embedding_dim,
    )
    task_store = TaskStore(session_factory)
    calendar_service = (
        CalendarService(settings.calendar_ics_url) if settings.calendar_ics_url else None
    )
    email_service = build_email_service(settings)
    finance_service = build_finance_service(settings, session_factory)
    server = create_memory_server(
        build_agent_tools(memory, task_store, calendar_service, email_service, finance_service)
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
