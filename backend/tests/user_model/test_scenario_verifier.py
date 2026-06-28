"""The live verifier resolves open batches against real activity — the honest rules:
a sibling winning is the ONLY refutation; a no-match batch EXPIRES (never a negative);
a confirmed branch emits a real signal; resolution is idempotent and reality-only."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.scenario_verifier import ScenarioVerifier
from pragya_assistant.user_model.scenarios import NewScenario, NewScenarioBatch, ScenarioStore

KEY = "browser_activity"
T0 = dt.datetime(2026, 6, 28, 9, 0)


def _branch(summary: str, checkpoint: str, rank: int, prior: float) -> NewScenario:
    return NewScenario(
        summary=summary,
        checkpoints=[checkpoint],
        prior=prior,
        rank=rank,
        deadline_at=T0 + dt.timedelta(hours=24),
    )


async def _seed_search(
    events: BrowserActivityEventStore, query: str, *, cid: str, ts: dt.datetime
) -> None:
    await events.add_events(
        KEY, [IngestedEvent(client_id=cid, event_type="search", ts=ts, data={"query": query})]
    )


async def test_case_a_confirms_winner_refutes_sibling_emits_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(
            branches=[
                _branch("books Kyoto lodging", "kyoto ryokan booking", rank=1, prior=0.6),
                _branch("reads the Raft paper", "raft consensus paper", rank=2, prior=0.4),
            ],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    # Reality: the user read the Raft paper (the rank-2 branch) — we mis-ranked.
    await _seed_search(events, "raft consensus paper pdf", cid="a1", ts=T0 + dt.timedelta(hours=1))

    result = await ScenarioVerifier(store, events).verify(now=T0 + dt.timedelta(hours=2))
    assert result.confirmed == 1
    assert result.refuted == 1
    assert result.expired == 0
    assert result.resolved_batches  # Case A → reconciler input

    batch = (await store.track_record())[0]
    assert batch.status == "resolved"
    by_summary = {b.summary: b for b in batch.branches}
    assert by_summary["reads the Raft paper"].status == "confirmed"
    assert by_summary["books Kyoto lodging"].status == "refuted"
    assert by_summary["books Kyoto lodging"].outcome["signal"] == "mis_ranked_competitor"
    # A real signal was emitted for the confirmed branch (the one-way valve).
    sig = (await events.recent(KEY, types=["scenario_outcome"]))[0]
    assert sig.source == "scenario"
    assert sig.data["status"] == "confirmed"


async def test_case_b_no_match_expires_without_signal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(
            branches=[_branch("books Kyoto lodging", "kyoto ryokan booking", 1, 1.0)],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    # Unrelated activity only — nothing corroborates the branch.
    await _seed_search(events, "weather tomorrow", cid="b1", ts=T0 + dt.timedelta(hours=1))

    # Past due → expire (a weak signal, NOT a negative; absence ≠ refutation).
    result = await ScenarioVerifier(store, events).verify(now=T0 + dt.timedelta(hours=25))
    assert result.expired == 1
    assert result.confirmed == 0
    assert result.refuted == 0
    assert result.resolved_batches == []  # not Case A → reconciler ignores it

    batch = (await store.track_record())[0]
    assert batch.status == "expired"
    assert batch.branches[0].status == "expired"
    assert await events.recent(KEY, types=["scenario_outcome"]) == []  # no signal emitted


async def test_not_yet_due_no_match_stays_open(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(
            branches=[_branch("books Kyoto lodging", "kyoto ryokan booking", 1, 1.0)],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    result = await ScenarioVerifier(store, events).verify(now=T0 + dt.timedelta(hours=1))
    assert (result.confirmed, result.refuted, result.expired) == (0, 0, 0)
    assert len(await store.open_batches()) == 1  # still open — horizon hasn't elapsed


async def test_verify_is_idempotent(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(
            branches=[_branch("books Kyoto lodging", "kyoto ryokan booking", 1, 1.0)],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    await _seed_search(events, "kyoto ryokan booking", cid="c1", ts=T0 + dt.timedelta(hours=1))
    verifier = ScenarioVerifier(store, events)
    first = await verifier.verify(now=T0 + dt.timedelta(hours=2))
    second = await verifier.verify(now=T0 + dt.timedelta(hours=3))  # nothing open now
    assert first.confirmed == 1
    assert second.confirmed == 0
    # Exactly ONE outcome event despite two passes (deterministic client_id upsert).
    assert len(await events.recent(KEY, types=["scenario_outcome"])) == 1


async def test_reality_only_ignores_system_signals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    await store.add_batch(
        NewScenarioBatch(
            branches=[_branch("books Kyoto lodging", "kyoto ryokan booking", 1, 1.0)],
            due_at=T0 + dt.timedelta(hours=24),
            created_at=T0,
        )
    )
    # A prior system-emitted signal whose text would "match" must NOT corroborate.
    await events.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="prev",
                event_type="scenario_outcome",
                ts=T0 + dt.timedelta(hours=1),
                source="scenario",
                data={"summary": "kyoto ryokan booking"},
            )
        ],
    )
    result = await ScenarioVerifier(store, events).verify(now=T0 + dt.timedelta(hours=2))
    assert result.confirmed == 0  # system signal excluded from ground truth
    assert len(await store.open_batches()) == 1  # still open (not due, no real match)
