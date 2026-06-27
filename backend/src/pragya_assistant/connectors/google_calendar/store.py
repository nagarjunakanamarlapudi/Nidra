"""Persistence for ingested Google Calendar events (one connector's own store)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import CalendarEvent


@dataclass(frozen=True)
class RawEvent:
    """A normalized event from the provider, before it becomes a DB row."""

    uid: str
    summary: str
    location: str | None
    start: dt.datetime
    end: dt.datetime | None
    all_day: bool
    calendar_id: str | None


class CalendarEventStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def replace_for(
        self, connector_key: str, events: list[RawEvent], *, account_label: str = ""
    ) -> None:
        """Replace ONE account's events with the freshly synced window; other
        accounts of the same connector are left untouched."""
        seen: set[str] = set()
        deduped: list[RawEvent] = []
        for e in events:
            if e.uid in seen:
                continue
            seen.add(e.uid)
            deduped.append(e)
        async with self._sf() as s:
            await s.execute(
                delete(CalendarEvent).where(
                    CalendarEvent.connector_key == connector_key,
                    CalendarEvent.account_label == account_label,
                )
            )
            for e in deduped:
                s.add(
                    CalendarEvent(
                        connector_key=connector_key,
                        account_label=account_label,
                        uid=e.uid,
                        summary=e.summary,
                        location=e.location,
                        start=e.start,
                        end=e.end,
                        all_day=e.all_day,
                        calendar_id=e.calendar_id,
                    )
                )
            await s.commit()

    async def events_between(
        self, connector_key: str, start: dt.datetime, end: dt.datetime
    ) -> list[CalendarEvent]:
        async with self._sf() as s:
            stmt = (
                select(CalendarEvent)
                .where(
                    CalendarEvent.connector_key == connector_key,
                    CalendarEvent.start >= start,
                    CalendarEvent.start < end,
                )
                .order_by(CalendarEvent.start)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def count(self, connector_key: str) -> int:
        async with self._sf() as s:
            stmt = (
                select(func.count())
                .select_from(CalendarEvent)
                .where(CalendarEvent.connector_key == connector_key)
            )
            return int((await s.execute(stmt)).scalar_one())
