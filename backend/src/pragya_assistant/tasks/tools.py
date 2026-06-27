"""Task tools — thin, model-facing wrappers over :class:`TaskStore`."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.memory.models import Task
from pragya_assistant.tasks.store import TaskStore


def build_task_tools(store: TaskStore) -> list[Tool]:
    async def add_task(args: dict[str, Any]) -> str:
        task = await store.add(str(args["title"]), due_date=_parse_date(args.get("due_date")))
        return f"Added task #{task.id}: {_describe(task)}"

    async def list_tasks(args: dict[str, Any]) -> str:
        tasks = await store.list_tasks()
        return "\n".join(f"- #{t.id} {_describe(t)}" for t in tasks) if tasks else "No open tasks."

    async def complete_task(args: dict[str, Any]) -> str:
        task = await store.complete(int(args["id"]))
        return f"Completed task #{task.id}: {task.title}" if task else f"No task #{args['id']}."

    async def due_tasks(args: dict[str, Any]) -> str:
        tasks = await store.due(within_days=int(args.get("within_days", 0)))
        return "\n".join(f"- #{t.id} {_describe(t)}" for t in tasks) if tasks else "No tasks due."

    return [
        Tool(
            name="add_task",
            description="Add a task to the user's to-do list, optionally with a due date.",
            input_schema=_object(
                {"title": _string("What needs doing"), "due_date": _string("Due date YYYY-MM-DD")},
                ["title"],
            ),
            handler=add_task,
        ),
        Tool(
            name="list_tasks",
            description="List the user's open (not-done) tasks with their ids.",
            input_schema=_object({}, []),
            handler=list_tasks,
        ),
        Tool(
            name="complete_task",
            description="Mark a task done by its id.",
            input_schema=_object({"id": _integer("The task id to complete")}, ["id"]),
            handler=complete_task,
        ),
        Tool(
            name="due_tasks",
            description="List tasks due within N days, including overdue (default today only).",
            input_schema=_object(
                {"within_days": _integer("Days ahead to include (default 0)")}, []
            ),
            handler=due_tasks,
        ),
    ]


def _describe(task: Task) -> str:
    return task.title + (f" (due {task.due_date.isoformat()})" if task.due_date else "")


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value))


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
