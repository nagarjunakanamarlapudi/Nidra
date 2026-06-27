"""GoogleCalendarConnector — sync ingests, test_connection probes (respx)."""

from __future__ import annotations

import datetime as dt

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.base import ConnectorContext
from pragya_assistant.connectors.google_calendar.connector import GoogleCalendarConnector
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def _ctx() -> ConnectorContext:
    async def _token() -> str:
        return "TOKEN"

    return ConnectorContext(
        key="google_calendar",
        config={"calendar_id": "primary", "sync_days_ahead": 30},
        access_token=_token,
    )


@respx.mock
async def test_sync_ingests_events(session_factory: async_sessionmaker[AsyncSession]) -> None:
    respx.get(EVENTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "1",
                        "summary": "Standup",
                        "start": {"dateTime": "2026-06-24T09:00:00Z"},
                        "end": {"dateTime": "2026-06-24T09:30:00Z"},
                    }
                ]
            },
        )
    )
    conn = GoogleCalendarConnector(session_factory, now=lambda: dt.datetime(2026, 6, 24, 8, 0))
    result = await conn.sync(_ctx())
    assert result.items == 1
    assert await CalendarEventStore(session_factory).count("google_calendar") == 1


@respx.mock
async def test_test_connection_ok(session_factory: async_sessionmaker[AsyncSession]) -> None:
    respx.get(EVENTS_URL).mock(return_value=httpx.Response(200, json={"items": []}))
    conn = GoogleCalendarConnector(session_factory, now=lambda: dt.datetime(2026, 6, 24, 8, 0))
    assert (await conn.test_connection(_ctx())).ok is True


@respx.mock
async def test_test_connection_failure(session_factory: async_sessionmaker[AsyncSession]) -> None:
    respx.get(EVENTS_URL).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
    conn = GoogleCalendarConnector(session_factory, now=lambda: dt.datetime(2026, 6, 24, 8, 0))
    assert (await conn.test_connection(_ctx())).ok is False
