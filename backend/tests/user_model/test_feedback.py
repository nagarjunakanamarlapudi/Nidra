"""Dream outcome capture: surfacing marks dreams shown; a user outcome resolves
the dream AND emits a real activity signal (so a confirmed dream can later ground
an Opinion through the normal grounded path — never written as an Opinion directly)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.feedback import DreamFeedbackService

KEY = "browser_activity"


async def _one_dream(dreams: DreamStore) -> int:
    await dreams.add([NewDream(hypothesis="Planning a Japan trip", kind="foresight", confidence=0.6)])
    return (await dreams.active())[0].id


async def test_mark_surfaced(session_factory: async_sessionmaker[AsyncSession]) -> None:
    dreams = DreamStore(session_factory)
    did = await _one_dream(dreams)
    await dreams.mark_surfaced([did])
    assert (await dreams.active())[0].status == "surfaced"


async def test_acted_confirms_and_emits_real_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dreams = DreamStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    did = await _one_dream(dreams)

    await DreamFeedbackService(dreams, events).record(
        did, signal="acted", at=dt.datetime(2026, 6, 28)
    )

    # dream resolved as confirmed, off the active list
    assert await dreams.active() == []
    assert (await dreams.track_record())[0].status == "confirmed"
    # a real signal was emitted for the grounded path (not an Opinion write)
    sig = (await events.recent(KEY, types=["dream_outcome"]))[0]
    assert sig.source == "dream"
    assert sig.data["dream_id"] == did and sig.data["signal"] == "acted"


async def test_dismissed_refutes_snoozed_stays_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    dreams = DreamStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    svc = DreamFeedbackService(dreams, events)

    d1 = await _one_dream(dreams)
    await svc.record(d1, signal="dismissed", at=dt.datetime(2026, 6, 28))
    assert (await dreams.track_record())[0].status == "refuted"

    await dreams.add([NewDream(hypothesis="Wants a new laptop", kind="need")])
    d2 = [d.id for d in await dreams.active()][0]
    await svc.record(d2, signal="snoozed", at=dt.datetime(2026, 6, 28))
    assert any(d.id == d2 for d in await dreams.active())  # snoozed → still active, not resolved
