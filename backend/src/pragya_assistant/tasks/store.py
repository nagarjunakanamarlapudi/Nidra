"""Storage for tasks."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Task


class TaskStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, title: str, due_date: dt.date | None = None) -> Task:
        async with self._session_factory() as session:
            task = Task(title=title, due_date=due_date)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def list_tasks(self, include_done: bool = False) -> list[Task]:
        async with self._session_factory() as session:
            stmt = select(Task).order_by(Task.id.asc())
            if not include_done:
                stmt = stmt.where(Task.done.is_(False))
            return list((await session.execute(stmt)).scalars().all())

    async def complete(self, task_id: int) -> Task | None:
        async with self._session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None:
                return None
            task.done = True
            await session.commit()
            await session.refresh(task)
            return task

    async def due(self, within_days: int = 0, *, today: dt.date | None = None) -> list[Task]:
        cutoff = (today or dt.date.today()) + dt.timedelta(days=within_days)
        async with self._session_factory() as session:
            stmt = (
                select(Task)
                .where(
                    Task.done.is_(False),
                    Task.due_date.is_not(None),
                    Task.due_date <= cutoff,
                )
                .order_by(Task.due_date.asc(), Task.id.asc())
            )
            return list((await session.execute(stmt)).scalars().all())
