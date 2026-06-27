"""CalendarEventStore — the Google Calendar connector's bespoke ingest store."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.google_calendar.store import CalendarEventStore, RawEvent


def _ev(uid: str, start: dt.datetime, summary: str = "E") -> RawEvent:
    return RawEvent(
        uid=uid,
        summary=summary,
        location=None,
        start=start,
        end=None,
        all_day=False,
        calendar_id="primary",
    )


async def test_replace_and_query_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for(
        "google_calendar",
        [_ev("a", dt.datetime(2026, 6, 24, 9, 0)), _ev("b", dt.datetime(2026, 6, 25, 10, 0))],
    )
    events = await store.events_between(
        "google_calendar", dt.datetime(2026, 6, 24, 0, 0), dt.datetime(2026, 6, 25, 0, 0)
    )
    assert [e.uid for e in events] == ["a"]
    assert await store.count("google_calendar") == 2


async def test_replace_overwrites_previous(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for("google_calendar", [_ev("a", dt.datetime(2026, 6, 24, 9, 0))])
    await store.replace_for("google_calendar", [_ev("c", dt.datetime(2026, 6, 26, 9, 0))])
    assert await store.count("google_calendar") == 1
    everything = await store.events_between(
        "google_calendar", dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1)
    )
    assert [e.uid for e in everything] == ["c"]


async def test_per_account_replace_is_isolated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-syncing one account must not wipe another account's events."""
    store = CalendarEventStore(session_factory)
    await store.replace_for(
        "google_calendar",
        [_ev("w1", dt.datetime(2026, 6, 24, 9, 0), "Standup")],
        account_label="work@x.com",
    )
    await store.replace_for(
        "google_calendar",
        [_ev("h1", dt.datetime(2026, 6, 24, 18, 0), "Dinner")],
        account_label="home@x.com",
    )
    everything = await store.events_between(
        "google_calendar", dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1)
    )
    by_label = {e.account_label: e.uid for e in everything}
    assert by_label == {"work@x.com": "w1", "home@x.com": "h1"}

    # re-sync work only → home untouched
    await store.replace_for(
        "google_calendar",
        [_ev("w2", dt.datetime(2026, 6, 25, 9, 0), "Review")],
        account_label="work@x.com",
    )
    everything = await store.events_between(
        "google_calendar", dt.datetime(2026, 1, 1), dt.datetime(2027, 1, 1)
    )
    by_label = {e.account_label: e.uid for e in everything}
    assert by_label == {"work@x.com": "w2", "home@x.com": "h1"}


async def test_dedups_within_batch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for(
        "google_calendar",
        [_ev("a", dt.datetime(2026, 6, 24, 9, 0)), _ev("a", dt.datetime(2026, 6, 24, 9, 0))],
    )
    assert await store.count("google_calendar") == 1


async def test_isolated_by_connector(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = CalendarEventStore(session_factory)
    await store.replace_for("google_calendar", [_ev("a", dt.datetime(2026, 6, 24, 9, 0))])
    await store.replace_for("other", [_ev("z", dt.datetime(2026, 6, 24, 9, 0))])
    rows = await store.events_between(
        "google_calendar", dt.datetime(2026, 6, 1), dt.datetime(2026, 7, 1)
    )
    assert [e.uid for e in rows] == ["a"]
