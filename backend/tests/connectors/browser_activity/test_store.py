"""The browser-activity store persists, upserts by client_id, and reads back."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)

KEY = "browser_activity"


async def test_add_events_and_read_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = BrowserActivityEventStore(session_factory)
    n = await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="a",
                event_type="search",
                ts=dt.datetime(2026, 6, 28, 9),
                data={"query": "raft consensus"},
            )
        ],
    )
    assert n == 1
    assert await store.count(KEY) == 1
    recent = await store.recent(KEY)
    assert recent[0].data == {"query": "raft consensus"}


async def test_add_events_upserts_by_client_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="x", event_type="reading", ts=dt.datetime(2026, 6, 28, 9), title="v1"
            )
        ],
    )
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="x", event_type="reading", ts=dt.datetime(2026, 6, 28, 10), title="v2"
            )
        ],
    )
    assert await store.count(KEY) == 1  # same client_id collapses
    assert (await store.recent(KEY))[0].title == "v2"
