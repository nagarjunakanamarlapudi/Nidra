"""The user-model deriver turns stored decision events into persisted traits."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.derive import UserModelDeriver
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.store import UserModelStore

KEY = "browser_activity"


async def _seed(store: BrowserActivityEventStore) -> None:
    await store.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="i1", event_type="interaction", ts=dt.datetime(2026, 6, 28, 9),
                data={"action": "toggle_on", "group": "Add-ons", "label": "Toll pass"},
                metrics={"latencyMs": 900},
            ),
            IngestedEvent(
                client_id="i2", event_type="interaction", ts=dt.datetime(2026, 6, 28, 9, 1),
                data={"action": "choose", "group": "Payment methods", "label": "Apple Pay", "value": "Apple Pay"},
                metrics={"latencyMs": 1100},
            ),
            IngestedEvent(
                client_id="a1", event_type="action", ts=dt.datetime(2026, 6, 28, 9, 2),
                data={"milestone": "reached_checkout", "funnel": "checkout"},
            ),
            IngestedEvent(
                client_id="a2", event_type="action", ts=dt.datetime(2026, 6, 28, 9, 3),
                data={"milestone": "abandoned", "funnel": "checkout"},
            ),
        ],
    )


async def test_derive_persists_traits(session_factory: async_sessionmaker[AsyncSession]) -> None:
    events = BrowserActivityEventStore(session_factory)
    model = UserModelStore(session_factory)
    await _seed(events)

    snapshots = await UserModelDeriver(events, model).derive()
    assert snapshots, "derivation produced trait snapshots"

    current = await model.current_model()
    traits = {s.trait: s for s in current}
    assert "decisiveness" in traits
    assert "preference:payment" in traits
    assert traits["preference:payment"].value == "Apple Pay"
    # provenance is recorded for auditability
    assert traits["decisiveness"].provenance
