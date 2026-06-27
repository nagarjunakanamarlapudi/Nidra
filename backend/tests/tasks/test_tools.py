import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import ToolHandler
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.tasks.tools import build_task_tools


def _handler(tools: list, name: str) -> ToolHandler:
    return next(t for t in tools if t.name == name).handler


async def test_add_list_complete(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = TaskStore(session_factory)
    tools = build_task_tools(store)

    out = await _handler(tools, "add_task")({"title": "pay rent", "due_date": "2026-06-25"})
    assert "Added task #" in out and "pay rent" in out and "2026-06-25" in out
    assert "pay rent" in await _handler(tools, "list_tasks")({})

    tid = (await store.list_tasks())[0].id
    assert f"Completed task #{tid}" in await _handler(tools, "complete_task")({"id": tid})
    assert await _handler(tools, "list_tasks")({}) == "No open tasks."


async def test_complete_missing(session_factory: async_sessionmaker[AsyncSession]) -> None:
    tools = build_task_tools(TaskStore(session_factory))
    assert "No task #999" in await _handler(tools, "complete_task")({"id": 999})


async def test_due_tasks_tool(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = TaskStore(session_factory)
    await store.add("overdue thing", due_date=dt.date.today() - dt.timedelta(days=1))
    out = await _handler(build_task_tools(store), "due_tasks")({"within_days": 0})
    assert "overdue thing" in out
