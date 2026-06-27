"""Persistence for ingested browser-activity events (this connector's store)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import BrowserActivityEvent


@dataclass(frozen=True)
class IngestedEvent:
    """A normalized, already-redacted activity event before it becomes a row."""

    client_id: str
    event_type: str
    ts: dt.datetime
    source: str | None = None
    domain: str | None = None
    url: str | None = None
    title: str | None = None
    data: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    context_id: str | None = None
    redacted: bool = False


class BrowserActivityEventStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add_events(self, connector_key: str, events: list[IngestedEvent]) -> int:
        """Upsert events by ``(connector_key, client_id)`` so a page's load + flush
        collapse into one row. Returns the number of events processed."""
        if not events:
            return 0
        async with self._sf() as s:
            for e in events:
                existing = (
                    await s.execute(
                        select(BrowserActivityEvent).where(
                            BrowserActivityEvent.connector_key == connector_key,
                            BrowserActivityEvent.client_id == e.client_id,
                        )
                    )
                ).scalar_one_or_none()
                row = existing or BrowserActivityEvent(
                    connector_key=connector_key, client_id=e.client_id
                )
                row.event_type = e.event_type
                row.ts = e.ts
                row.source = e.source
                row.domain = e.domain
                row.url = e.url
                row.title = e.title
                row.data = e.data
                row.metrics = e.metrics
                row.context_id = e.context_id
                row.redacted = e.redacted
                if existing is None:
                    s.add(row)
            await s.commit()
        return len(events)

    async def recent(
        self,
        connector_key: str,
        *,
        limit: int = 200,
        types: list[str] | None = None,
    ) -> list[BrowserActivityEvent]:
        """Most-recent events, newest first. ``types`` restricts to those
        ``event_type``s — used to give each event family its OWN window, so a
        flood of high-frequency interaction/impression rows can't evict the
        reading/search/email/calendar rows the dreamer's digest depends on."""
        async with self._sf() as s:
            stmt = select(BrowserActivityEvent).where(
                BrowserActivityEvent.connector_key == connector_key
            )
            if types is not None:
                stmt = stmt.where(BrowserActivityEvent.event_type.in_(types))
            stmt = stmt.order_by(BrowserActivityEvent.ts.desc()).limit(limit)
            return list((await s.execute(stmt)).scalars().all())

    async def count(self, connector_key: str) -> int:
        async with self._sf() as s:
            stmt = (
                select(func.count())
                .select_from(BrowserActivityEvent)
                .where(BrowserActivityEvent.connector_key == connector_key)
            )
            return int((await s.execute(stmt)).scalar_one())
