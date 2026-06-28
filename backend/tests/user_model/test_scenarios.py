"""The scenarios store: a batch of competing branches, resolved by the verifier;
resolved/expired batches are the RSI track record. Scenarios never write Opinions."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.user_model.scenarios import (
    LessonStore,
    NewScenario,
    NewScenarioBatch,
    ScenarioStore,
)

T0 = dt.datetime(2026, 6, 28, 9, 0)


def _branch(summary: str, prior: float, rank: int) -> NewScenario:
    return NewScenario(
        summary=summary,
        checkpoints=[summary],
        prior=prior,
        rank=rank,
        deadline_at=T0 + dt.timedelta(hours=24),
    )


async def test_add_batch_and_open(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = ScenarioStore(session_factory)
    bid = await store.add_batch(
        NewScenarioBatch(
            branches=[_branch("books Kyoto lodging", 0.6, 1), _branch("reads Raft paper", 0.4, 2)],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    assert bid > 0
    batches = await store.open_batches()
    assert len(batches) == 1
    batch = batches[0]
    assert batch.status == "open"
    assert [br.rank for br in batch.branches] == [1, 2]  # ordered by rank
    assert batch.branches[0].summary == "books Kyoto lodging"


async def test_resolve_branch_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(branches=[_branch("x", 1.0, 1)], due_at=T0, created_at=T0)
    )
    branch_id = (await store.open_batches())[0].branches[0].id

    first = await store.resolve_branch(branch_id, status="confirmed", signal="corroborated", at=T0)
    second = await store.resolve_branch(
        branch_id, status="refuted", signal="mis_ranked_competitor", at=T0
    )
    assert first is True  # this call resolved it
    assert second is False  # guarded by WHERE status='open' — a no-op


async def test_track_record_only_terminal_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(branches=[_branch("a", 1.0, 1)], due_at=T0, created_at=T0)
    )
    await store.add_batch(
        NewScenarioBatch(branches=[_branch("b", 1.0, 1)], due_at=T0, created_at=T0)
    )
    open_batches = await store.open_batches()
    await store.resolve_batch(
        open_batches[0].id, status="resolved", at=dt.datetime(2026, 6, 28, 10)
    )
    await store.resolve_batch(
        open_batches[1].id, status="expired", at=dt.datetime(2026, 6, 28, 11)
    )

    record = await store.track_record()
    assert [b.status for b in record] == ["expired", "resolved"]  # newest resolved_at first
    assert await store.open_batches() == []  # both terminal now


async def test_lesson_store_add_and_recent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    bid = await store.add_batch(
        NewScenarioBatch(branches=[_branch("a", 1.0, 1)], due_at=T0, created_at=T0)
    )
    lessons = LessonStore(session_factory)
    lid = await lessons.add(
        batch_id=bid,
        predicted_branches=[{"summary": "a", "prior": 1.0, "rank": 1}],
        what_happened={"winner_summary": "b"},
        hypothesized_missing_context="user had an exam deadline",
        confidence=0.5,
    )
    assert lid > 0
    got = await lessons.recent()
    assert len(got) == 1
    assert got[0].hypothesized_missing_context == "user had an exam deadline"
    assert got[0].base_weight == 1.0
