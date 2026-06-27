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


def test_build_digest_surfaces_engagement() -> None:
    """A deep read and a bounce must look different so the dreamer can weigh them."""
    events = [
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="deep",
            event_type="reading",
            ts=dt.datetime(2026, 6, 28, 9),
            source="medium",
            data={"title": "Engaged article"},
            metrics={"dwellMs": 360000, "readPct": 0.95},
        ),
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="bounce",
            event_type="reading",
            ts=dt.datetime(2026, 6, 28, 10),
            source="web",
            data={"title": "Bounced article"},
            metrics={"dwellMs": 4000, "readPct": 0.0},
        ),
    ]
    digest = build_digest(events)
    deep_line = next(line for line in digest.splitlines() if "Engaged article" in line)
    bounce_line = next(line for line in digest.splitlines() if "Bounced article" in line)
    assert "6m" in deep_line and "95%" in deep_line
    assert "4s" in bounce_line


def test_build_digest_summarizes_decisions() -> None:
    """interaction + action events surface as a DECISIONS section the LLM can read."""
    events = [
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="i1",
            event_type="interaction",
            ts=dt.datetime(2026, 6, 28, 9),
            domain="example.com",
            data={"action": "choose", "control": "radio", "label": "Annual",
                  "group": "Subscription", "value": "annual"},
        ),
        BrowserActivityEvent(
            connector_key=KEY,
            client_id="a1",
            event_type="action",
            ts=dt.datetime(2026, 6, 28, 9, 1),
            domain="example.com",
            data={"milestone": "abandoned", "funnel": "checkout", "step": 3, "of": 4},
        ),
    ]
    digest = build_digest(events)
    assert "DECISIONS:" in digest
    assert "Subscription" in digest and "annual" in digest
    assert "abandoned" in digest


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
