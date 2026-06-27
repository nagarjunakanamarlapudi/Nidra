"""The dreamer builds a digest, parses model JSON, and connects the dots."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.dreamer import (
    DreamerService,
    build_digest,
    extract_json,
)
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.memory.models import BrowserActivityEvent

KEY = "browser_activity"


def test_extract_json_handles_fences_and_noise() -> None:
    assert extract_json('```json\n{"a": 1}\n```')["a"] == 1
    assert extract_json('noise {"b": 2} tail')["b"] == 2
    assert extract_json("not json at all") == {}


def test_build_digest_groups_by_type() -> None:
    events = [
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="1",
            event_type="search",
            ts=dt.datetime(2026, 6, 28, 9),
            data={"query": "flights to tokyo"},
        ),
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="2",
            event_type="reading",
            ts=dt.datetime(2026, 6, 28, 9),
            source="medium",
            domain="medium.com",
            data={"title": "Best ryokans in Kyoto", "tags": ["japan", "travel"]},
        ),
    ]
    digest = build_digest(events)
    assert "SEARCHES:" in digest and "flights to tokyo" in digest
    assert "READING:" in digest and "ryokans" in digest


async def test_dreamer_connects_signals_with_injected_engine(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = BrowserActivityEventStore(session_factory)
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="1",
                event_type="search",
                ts=dt.datetime(2026, 6, 28, 9),
                data={"query": "flights to tokyo"},
            )
        ],
    )
    canned = (
        '{"connectedInsights": [{"insight": "Planning a trip to Japan", '
        '"fromSignals": ["flights"], "confidence": 0.9}], "persona": "A traveler", '
        '"beliefs": [{"statement": "interested in Japan", "confidence": 0.8}], '
        '"nextNeeds": ["draft a Tokyo itinerary"]}'
    )

    async def fake_engine(_digest: str) -> str:
        return canned

    result = await DreamerService(store, fake_engine).dream()
    assert result.generated_from == 1
    assert result.persona == "A traveler"
    assert result.connected_insights[0]["insight"] == "Planning a trip to Japan"
    assert result.beliefs[0]["statement"] == "interested in Japan"
    assert result.next_needs == ["draft a Tokyo itinerary"]
