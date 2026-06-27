"""gcal_agenda / gcal_upcoming tools read from the ingest store."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.google_calendar.store import CalendarEventStore, RawEvent
from pragya_assistant.connectors.google_calendar.tools import build_calendar_tools


def _tools(store: CalendarEventStore) -> dict[str, object]:
    built = build_calendar_tools(store, "google_calendar", today=lambda: dt.date(2026, 6, 24))
    return {t.name: t for t in built}


async def test_agenda_lists_todays_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for(
        "google_calendar",
        [
            RawEvent(
                uid="1",
                summary="Standup",
                location="Zoom",
                start=dt.datetime(2026, 6, 24, 9, 0),
                end=None,
                all_day=False,
                calendar_id="primary",
            )
        ],
    )
    out = await _tools(store)["gcal_agenda"].handler({})  # type: ignore[attr-defined]
    assert "Standup" in out
    assert "Zoom" in out


async def test_agenda_empty(session_factory: async_sessionmaker[AsyncSession]) -> None:
    out = await _tools(CalendarEventStore(session_factory))["gcal_agenda"].handler({})  # type: ignore[attr-defined]
    assert "Nothing" in out


async def test_upcoming_lists_future_events(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for(
        "google_calendar",
        [
            RawEvent(
                uid="1",
                summary="Future",
                location=None,
                start=dt.datetime(2026, 6, 26, 9, 0),
                end=None,
                all_day=False,
                calendar_id="primary",
            )
        ],
    )
    out = await _tools(store)["gcal_upcoming"].handler({"days": 7})  # type: ignore[attr-defined]
    assert "Future" in out
