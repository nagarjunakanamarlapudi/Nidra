"""The reconciler learns ONLY from mis-ranked batches (right distribution, wrong
ranking): it hypothesizes the missing context (hedged), persists a low-weight
decaying lesson, and triggers ΔState opinion re-derivation. It ignores batches
where the top branch won and never touches expired batches. lessons_for_prompt
decays + caps + hedges so one miss can't bias the agent."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import ScenarioLesson
from pragya_assistant.user_model.scenario_reconciler import (
    ScenarioReconciler,
    lessons_for_prompt,
)
from pragya_assistant.user_model.scenarios import (
    LessonStore,
    NewScenario,
    NewScenarioBatch,
    ScenarioStore,
)

T0 = dt.datetime(2026, 6, 28, 9, 0)
T = dt.datetime(2026, 6, 28, 11, 0)


def _ns(summary: str, prior: float, rank: int) -> NewScenario:
    return NewScenario(summary=summary, checkpoints=["c"], prior=prior, rank=rank, deadline_at=T)


async def _mis_ranked_batch(store: ScenarioStore) -> int:
    """A resolved batch where rank-1 was refuted and rank-2 confirmed (a mis-rank)."""
    bid = await store.add_batch(
        NewScenarioBatch(
            branches=[_ns("books Kyoto lodging", 0.6, 1), _ns("reads the Raft paper", 0.4, 2)],
            due_at=T,
            created_at=T0,
        )
    )
    branches = (await store.open_batches())[0].branches
    rank1 = next(b for b in branches if b.rank == 1)
    rank2 = next(b for b in branches if b.rank == 2)
    await store.resolve_branch(rank1.id, status="refuted", signal="mis_ranked_competitor", at=T)
    await store.resolve_branch(
        rank2.id, status="confirmed", signal="corroborated", matched_text="raft paper pdf", at=T
    )
    await store.resolve_batch(bid, status="resolved", at=T)
    return bid


async def test_mis_rank_diagnoses_learns_and_refreshes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    lessons = LessonStore(session_factory)
    bid = await _mis_ranked_batch(store)

    prompts: list[str] = []
    refreshed: list[bool] = []

    async def diagnose_fn(prompt: str) -> str:
        prompts.append(prompt)
        return (
            '{"what_we_missed": "ranked travel over study", '
            '"hypothesized_missing_context": "user had an exam Thursday", "confidence": 0.6}'
        )

    async def refresh_fn() -> None:
        refreshed.append(True)

    result = await ScenarioReconciler(
        store, lessons, diagnose_fn=diagnose_fn, refresh_opinions_fn=refresh_fn
    ).reconcile([bid])

    assert result.diagnosed == 1
    assert result.lessons == 1
    assert result.opinions_refreshed is True
    assert len(refreshed) == 1  # ΔState triggered exactly once (debounced)
    # The diagnosis prompt fences the untrusted outcome and names the real winner.
    assert "UNTRUSTED" in prompts[0]
    assert "reads the Raft paper" in prompts[0]
    # Diagnosis persisted on the batch; lesson persisted (hedged hypothesis).
    batch = await store.get_batch(bid)
    assert batch is not None
    assert batch.diagnosis["hypothesized_missing_context"] == "user had an exam Thursday"
    persisted = await lessons.recent()
    assert len(persisted) == 1
    assert persisted[0].hypothesized_missing_context == "user had an exam Thursday"
    assert persisted[0].confidence == 0.6


async def test_top_branch_correct_is_not_reconciled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    lessons = LessonStore(session_factory)
    bid = await store.add_batch(
        NewScenarioBatch(
            branches=[_ns("A", 0.6, 1), _ns("B", 0.4, 2)],
            due_at=T,
            created_at=T0,
        )
    )
    branches = (await store.open_batches())[0].branches
    rank1 = next(b for b in branches if b.rank == 1)
    rank2 = next(b for b in branches if b.rank == 2)
    await store.resolve_branch(rank1.id, status="confirmed", signal="corroborated", at=T)
    await store.resolve_branch(rank2.id, status="refuted", signal="mis_ranked_competitor", at=T)
    await store.resolve_batch(bid, status="resolved", at=T)

    called: list[str] = []

    async def diagnose_fn(prompt: str) -> str:
        called.append(prompt)
        return "{}"

    result = await ScenarioReconciler(store, lessons, diagnose_fn=diagnose_fn).reconcile([bid])
    assert result == result.__class__()  # all zeros — we ranked the winner first
    assert called == []  # the diagnoser was never invoked
    assert await lessons.recent() == []


async def test_expired_batch_is_never_reconciled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    lessons = LessonStore(session_factory)
    bid = await store.add_batch(
        NewScenarioBatch(branches=[_ns("A", 1.0, 1)], due_at=T, created_at=T0)
    )
    branch_id = (await store.open_batches())[0].branches[0].id
    await store.resolve_branch(branch_id, status="expired", signal="no_match", at=T)
    await store.resolve_batch(bid, status="expired", at=T)

    async def diagnose_fn(_prompt: str) -> str:
        raise AssertionError("expired batches must never be diagnosed")

    result = await ScenarioReconciler(store, lessons, diagnose_fn=diagnose_fn).reconcile([bid])
    assert result.diagnosed == 0
    assert await lessons.recent() == []


def _lesson(ctx: str, created_at: dt.datetime, base_weight: float = 1.0) -> ScenarioLesson:
    return ScenarioLesson(
        batch_id=1,
        predicted_branches=[],
        what_happened={},
        hypothesized_missing_context=ctx,
        confidence=0.5,
        base_weight=base_weight,
        created_at=created_at,
    )


def test_lessons_for_prompt_decays_caps_and_hedges() -> None:
    now = dt.datetime(2026, 6, 28, 12, 0)
    fresh = [_lesson(f"ctx{i}", now - dt.timedelta(days=i)) for i in range(4)]  # ages 0..3 days
    stale = _lesson("ancient", now - dt.timedelta(days=120))  # decays far below epsilon

    out = lessons_for_prompt(fresh + [stale], now=now)
    assert len(out) == 3  # capped at MAX_LESSONS
    assert all("ancient" not in line for line in out)  # stale lesson dropped
    assert all("exploration hint" in line for line in out)  # hedged framing, never a rule
    assert "ctx0" in out[0]  # freshest (highest decayed weight) first


def test_lessons_for_prompt_skips_empty_context() -> None:
    now = dt.datetime(2026, 6, 28, 12, 0)
    assert lessons_for_prompt([_lesson("   ", now)], now=now) == []
