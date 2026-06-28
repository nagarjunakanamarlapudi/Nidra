"""Assemble the full agent tool set: memory + tasks + calendar + email.

One place that composes the tool families, reused by the engine factory
(in-process engines) and the Codex stdio MCP server — so every engine sees the
same tools (§10).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.activity_tools import build_activity_tools
from pragya_assistant.agent.memory_tools import build_memory_tools
from pragya_assistant.agent.tools import Tool
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.calendars.tools import build_calendar_tools
from pragya_assistant.email_inbox.service import EmailService
from pragya_assistant.email_inbox.tools import build_email_tools
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.tools import build_finance_tools
from pragya_assistant.memory.service import MemoryService
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.tasks.tools import build_task_tools


def build_agent_tools(
    memory: MemoryService,
    task_store: TaskStore | None = None,
    calendar_service: CalendarService | None = None,
    email_service: EmailService | None = None,
    finance_service: FinanceService | None = None,
    connector_tools: list[Tool] | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> list[Tool]:
    tools = build_memory_tools(memory)
    if session_factory is not None:
        # Browser-activity + user-model (Opinions/Dreams) read tools.
        tools += build_activity_tools(session_factory)
    if task_store is not None:
        tools += build_task_tools(task_store)
    if calendar_service is not None:
        tools += build_calendar_tools(calendar_service)
    if email_service is not None:
        tools += build_email_tools(email_service)
    if finance_service is not None:
        tools += build_finance_tools(finance_service)
    if connector_tools:
        tools += connector_tools
    return tools
