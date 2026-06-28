"""Persistence for Scenarios — competing, falsifiable predictions of the user's
next actions, auto-verified against real activity.

A :class:`ScenarioBatch` groups the branches generated from one point-in-time
context snapshot; the verifier resolves each branch (``confirmed`` | ``refuted``
| ``expired``) and the reconciler learns from mis-ranked batches. Scenarios are
written here ONLY — never ``user_model_snapshots`` (the one-way valve, as with
dreams). Resolved/expired batches are the recursive-self-improvement track record.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Scenario, ScenarioBatch, ScenarioLesson

# Batch lifecycle: OPEN -> (resolved | expired). "resolved" = reality spoke
# on-platform (Case A: a branch confirmed); "expired" = horizon passed with no
# branch matched (Case B: weak signal, never a negative).
OPEN: tuple[str, ...] = ("open",)
RESOLVED: tuple[str, ...] = ("resolved", "expired")


@dataclass(frozen=True)
class NewScenario:
    """One proposed branch before it is persisted."""

    summary: str
    checkpoints: list[str]
    prior: float
    rank: int
    deadline_at: dt.datetime
    derivation: dict[str, Any] | None = None


@dataclass(frozen=True)
class NewScenarioBatch:
    branches: list[NewScenario]
    due_at: dt.datetime
    context_snapshot: dict[str, Any] | None = None
    lessons_used: int = 0
    # The generation time; the verifier's point-in-time anchor (activity is read
    # strictly after it). Defaults to the DB ``now()``; set explicitly for replay.
    created_at: dt.datetime | None = None


class ScenarioStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add_batch(self, batch: NewScenarioBatch) -> int:
        """Persist a batch and its branches in one transaction; return the batch id."""
        async with self._sf() as s:
            row = ScenarioBatch(
                context_snapshot=batch.context_snapshot,
                status="open",
                due_at=batch.due_at,
                lessons_used=batch.lessons_used,
            )
            if batch.created_at is not None:
                row.created_at = batch.created_at
            row.branches = [
                Scenario(
                    summary=b.summary,
                    checkpoints=list(b.checkpoints),
                    prior=b.prior,
                    rank=b.rank,
                    deadline_at=b.deadline_at,
                    status="open",
                    derivation=b.derivation,
                )
                for b in batch.branches
            ]
            s.add(row)
            await s.commit()
            return row.id

    async def open_batches(self, *, limit: int = 50) -> list[ScenarioBatch]:
        """Open batches (branches eager-loaded), newest first — powers ``GET
        /scenarios`` and the next generation's "open scenarios" context."""
        async with self._sf() as s:
            stmt = (
                select(ScenarioBatch)
                .where(ScenarioBatch.status.in_(OPEN))
                .order_by(ScenarioBatch.created_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def all_open_batches(self, *, limit: int = 200) -> list[ScenarioBatch]:
        """Every open batch, soonest-due first — the verifier's sweep input. The
        resolution algorithm decides per batch whether it confirms now, expires
        (past due), or stays open."""
        async with self._sf() as s:
            stmt = (
                select(ScenarioBatch)
                .where(ScenarioBatch.status.in_(OPEN))
                .order_by(ScenarioBatch.due_at.asc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def track_record(self, *, limit: int = 100) -> list[ScenarioBatch]:
        """Resolved/expired batches (branches eager-loaded), newest first — the RSI
        exemplars fed back into the next generation prompt."""
        async with self._sf() as s:
            stmt = (
                select(ScenarioBatch)
                .where(ScenarioBatch.status.in_(RESOLVED))
                .order_by(ScenarioBatch.resolved_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def all_batches(self) -> list[ScenarioBatch]:
        """Every batch (branches eager-loaded) — used by the scorecard aggregator."""
        async with self._sf() as s:
            stmt = select(ScenarioBatch).order_by(ScenarioBatch.created_at.desc())
            return list((await s.execute(stmt)).scalars().all())

    async def get_batch(self, batch_id: int) -> ScenarioBatch | None:
        """One batch (branches eager-loaded) — the reconciler's per-batch fetch."""
        async with self._sf() as s:
            return (
                await s.execute(select(ScenarioBatch).where(ScenarioBatch.id == batch_id))
            ).scalar_one_or_none()

    async def set_diagnosis(self, batch_id: int, diagnosis: dict[str, Any]) -> None:
        """Attach the reconciler's gap diagnosis without touching the batch's
        terminal status/timestamps (unlike :meth:`resolve_batch`)."""
        async with self._sf() as s:
            batch = (
                await s.execute(select(ScenarioBatch).where(ScenarioBatch.id == batch_id))
            ).scalar_one()
            batch.diagnosis = diagnosis
            await s.commit()

    async def resolve_branch(
        self,
        branch_id: int,
        *,
        status: str,
        signal: str,
        matched_event_ids: list[int] | None = None,
        matched_text: str | None = None,
        score: float | None = None,
        at: dt.datetime | None = None,
    ) -> bool:
        """Resolve a branch under ``WHERE status='open'`` (the idempotency guard:
        a repeat/overlapping verify pass cannot double-resolve). ``status`` ∈
        confirmed|refuted|expired; ``signal`` ∈ corroborated|mis_ranked_competitor|
        no_match. Returns True iff this call performed the resolution."""
        async with self._sf() as s:
            branch = (
                await s.execute(select(Scenario).where(Scenario.id == branch_id))
            ).scalar_one()
            if branch.status != "open":
                return False
            branch.status = status
            branch.outcome = {
                "signal": signal,
                "matched_event_ids": matched_event_ids or [],
                "matched_text": matched_text,
                "score": score,
                "at": at.isoformat() if at is not None else None,
            }
            branch.resolved_at = at
            await s.commit()
            return True

    async def resolve_batch(
        self,
        batch_id: int,
        *,
        status: str,
        diagnosis: dict[str, Any] | None = None,
        at: dt.datetime | None = None,
    ) -> None:
        """Mark a batch terminal (``resolved`` | ``expired``); optionally attach the
        reconciler's gap ``diagnosis``."""
        async with self._sf() as s:
            batch = (
                await s.execute(select(ScenarioBatch).where(ScenarioBatch.id == batch_id))
            ).scalar_one()
            batch.status = status
            if diagnosis is not None:
                batch.diagnosis = diagnosis
            batch.resolved_at = at
            await s.commit()


class LessonStore:
    """Persistence for the reconciler's low-weight, decaying policy lessons."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(
        self,
        *,
        batch_id: int,
        predicted_branches: list[dict[str, Any]],
        what_happened: dict[str, Any],
        hypothesized_missing_context: str,
        confidence: float,
        base_weight: float = 1.0,
    ) -> int:
        async with self._sf() as s:
            row = ScenarioLesson(
                batch_id=batch_id,
                predicted_branches=predicted_branches,
                what_happened=what_happened,
                hypothesized_missing_context=hypothesized_missing_context,
                confidence=confidence,
                base_weight=base_weight,
            )
            s.add(row)
            await s.commit()
            return row.id

    async def recent(self, *, limit: int = 50) -> list[ScenarioLesson]:
        """Most-recent lessons, newest first. The generation prompt builder decays
        and caps these before injecting — this is just the raw pull."""
        async with self._sf() as s:
            stmt = (
                select(ScenarioLesson)
                .order_by(ScenarioLesson.created_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())
