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


async def test_add_events_persists_engagement_metrics(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dwell time + scroll depth (the engagement signal) round-trip into storage."""
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="m",
                event_type="reading",
                ts=dt.datetime(2026, 6, 28, 9),
                title="A long read",
                metrics={"dwellMs": 360000, "scrollPct": 0.95, "readPct": 0.95},
            )
        ],
    )
    recent = await store.recent(KEY)
    assert recent[0].metrics == {"dwellMs": 360000, "scrollPct": 0.95, "readPct": 0.95}


async def test_add_events_persists_context_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """context_id correlates impression -> interaction -> action on one page load."""
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="i1",
                event_type="interaction",
                ts=dt.datetime(2026, 6, 28, 9),
                context_id="ctx-abc",
                data={"action": "toggle_on", "control": "toggle", "label": "X"},
            )
        ],
    )
    assert (await store.recent(KEY))[0].context_id == "ctx-abc"


async def test_recent_filters_by_type_so_new_events_dont_evict_reading(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The dreamer's reading/search window must survive a flood of interactions."""
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="read-1",
                event_type="reading",
                ts=dt.datetime(2026, 6, 28, 8),
                title="An article",
            ),
            *[
                IngestedEvent(
                    client_id=f"int-{n}",
                    event_type="interaction",
                    ts=dt.datetime(2026, 6, 28, 9, n % 60),
                    data={"action": "select"},
                )
                for n in range(50)
            ],
        ],
    )
    reading = await store.recent(KEY, types=["reading"], limit=10)
    assert len(reading) == 1 and reading[0].title == "An article"


async def test_recent_time_window_for_pointintime_replay(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """before/since windows enable backtesting without look-ahead leakage."""
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(client_id="p1", event_type="search", ts=dt.datetime(2026, 6, 1)),
            IngestedEvent(client_id="p2", event_type="search", ts=dt.datetime(2026, 6, 10)),
            IngestedEvent(client_id="f1", event_type="search", ts=dt.datetime(2026, 6, 20)),
        ],
    )
    T = dt.datetime(2026, 6, 15)
    before = await store.recent(KEY, before=T)
    after = await store.recent(KEY, since=T)
    assert {e.client_id for e in before} == {"p1", "p2"}  # strictly before T
    assert {e.client_id for e in after} == {"f1"}  # at/after T


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
