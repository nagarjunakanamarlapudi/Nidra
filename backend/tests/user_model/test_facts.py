"""The fact digest builder gathers cited facts from every source except finance."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.facts import FactDigestBuilder, collect_browser_facts

KEY = "browser_activity"


def test_collect_browser_facts_shapes_searches_and_choices() -> None:
    rows = [
        SimpleNamespace(id=1, event_type="search", data={"query": "flights to tokyo"},
                        title=None, domain="google.com", metrics=None),
        SimpleNamespace(id=2, event_type="reading", data={}, title="Best ryokans in Kyoto",
                        domain="medium.com", metrics={"dwellMs": 840000, "readPct": 95}),
        SimpleNamespace(id=3, event_type="interaction",
                        data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
                        title=None, domain="sixt.com", metrics=None),
        SimpleNamespace(id=4, event_type="action", title=None, domain="shop.com",
                        metrics=None, data={"milestone": "reached_checkout", "funnel": "purchase"}),
    ]
    facts = collect_browser_facts(rows)
    kinds = {f.kind for f in facts}
    assert {"search", "reading", "choice"} <= kinds
    assert "action" in kinds
    search = next(f for f in facts if f.kind == "search")
    assert "flights to tokyo" in search.summary and search.event_ids == [1]
    assert search.source == "browser"


async def test_builder_assigns_ids_and_merges_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search", ts=dt.datetime(2026, 6, 20, 9),
                       data={"query": "tokyo"})],
    )
    builder = FactDigestBuilder(
        browser=events, calendar=None, email=None, prefs=None, tasks=None,
        now=dt.datetime(2026, 6, 27, 12),
    )
    facts = await builder.build()
    assert facts and facts[0].id == "f1"
    assert all(f.id.startswith("f") for f in facts)
    assert any("tokyo" in f.summary for f in facts)
