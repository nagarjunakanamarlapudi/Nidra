"""The dreams store: the dreamer writes hypotheses here (never user_model_snapshots),
they surface, get resolved by real outcomes, and resolved ones become the RSI track record."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.user_model.dreams import DreamStore, NewDream


async def test_add_and_list_active(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = DreamStore(session_factory)
    await store.add(
        [
            NewDream(
                hypothesis="Planning a Japan trip in spring",
                kind="foresight",
                confidence=0.6,
                provenance=["browser", "calendar"],
                expires_at=dt.datetime(2026, 7, 15),
            )
        ]
    )
    active = await store.active()
    assert len(active) == 1
    assert active[0].status == "proposed"
    assert active[0].hypothesis == "Planning a Japan trip in spring"


async def test_resolve_sets_outcome_and_drops_from_active(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = DreamStore(session_factory)
    await store.add([NewDream(hypothesis="Wants a larger car", kind="need", confidence=0.4)])
    dream_id = (await store.active())[0].id

    await store.resolve(
        dream_id,
        status="confirmed",
        signal="corroborated",
        evidence=["plaid: dealership visit charge"],
        at=dt.datetime(2026, 7, 1),
    )

    assert await store.active() == []  # resolved → no longer active/surfaceable
    record = await store.track_record()
    assert len(record) == 1
    assert record[0].status == "confirmed"
    assert record[0].outcome["signal"] == "corroborated"
    assert record[0].resolved_at == dt.datetime(2026, 7, 1)


async def test_track_record_only_resolved_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = DreamStore(session_factory)
    await store.add(
        [
            NewDream(hypothesis="A", kind="foresight", confidence=0.5),
            NewDream(hypothesis="B", kind="foresight", confidence=0.5),
            NewDream(hypothesis="C", kind="foresight", confidence=0.5),  # stays unresolved
        ]
    )
    ids = [d.id for d in await store.active()]
    await store.resolve(ids[0], status="refuted", signal="dismissed", at=dt.datetime(2026, 6, 28))
    await store.resolve(ids[1], status="confirmed", signal="acted", at=dt.datetime(2026, 6, 29))

    record = await store.track_record()
    assert [r.hypothesis for r in record] == ["B", "A"]  # resolved only, newest first
