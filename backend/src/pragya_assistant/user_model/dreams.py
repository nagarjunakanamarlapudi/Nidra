"""Persistence for Dreams — the dreamer's speculative hypotheses.

Dreams are written here ONLY (never ``user_model_snapshots``). They surface,
get resolved by a real outcome, and the resolved set is the recursive
self-improvement track record (Phase-1 exemplars / Phase-2 training data).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Dream

ACTIVE = ("proposed", "surfaced")
RESOLVED = ("confirmed", "refuted")


@dataclass(frozen=True)
class NewDream:
    hypothesis: str
    kind: str = "foresight"
    confidence: float = 0.0
    provenance: list[str] = field(default_factory=list)
    expires_at: dt.datetime | None = None


class DreamStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, dreams: list[NewDream]) -> int:
        if not dreams:
            return 0
        async with self._sf() as s:
            for d in dreams:
                s.add(
                    Dream(
                        hypothesis=d.hypothesis,
                        kind=d.kind,
                        confidence=d.confidence,
                        provenance=list(d.provenance),
                        status="proposed",
                        expires_at=d.expires_at,
                    )
                )
            await s.commit()
        return len(dreams)

    async def active(self, *, limit: int = 50) -> list[Dream]:
        """Unresolved dreams (proposed/surfaced) — what can be surfaced and what
        feeds the next dreaming cycle's context."""
        async with self._sf() as s:
            stmt = (
                select(Dream)
                .where(Dream.status.in_(ACTIVE))
                .order_by(Dream.confidence.desc(), Dream.created_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def mark_surfaced(self, ids: list[int]) -> None:
        """proposed → surfaced (it was shown to the user). Lets us tell a dream the
        user saw-and-ignored from one never surfaced."""
        if not ids:
            return
        async with self._sf() as s:
            rows = (await s.execute(select(Dream).where(Dream.id.in_(ids)))).scalars().all()
            for d in rows:
                if d.status == "proposed":
                    d.status = "surfaced"
            await s.commit()

    async def hypothesis_of(self, dream_id: int) -> str | None:
        async with self._sf() as s:
            return (
                await s.execute(select(Dream.hypothesis).where(Dream.id == dream_id))
            ).scalar_one_or_none()

    async def resolve(
        self,
        dream_id: int,
        *,
        status: str,
        signal: str,
        evidence: list[str] | None = None,
        at: dt.datetime | None = None,
    ) -> None:
        """Resolve a dream with its real outcome. ``status`` ∈ confirmed|refuted|expired;
        ``signal`` ∈ acted|corroborated|dismissed|snoozed|ignored."""
        async with self._sf() as s:
            dream = (
                await s.execute(select(Dream).where(Dream.id == dream_id))
            ).scalar_one()
            dream.status = status
            dream.outcome = {"signal": signal, "evidence": evidence or []}
            dream.resolved_at = at
            await s.commit()

    async def track_record(self, *, limit: int = 100) -> list[Dream]:
        """Resolved dreams (confirmed/refuted), newest first — the RSI exemplars."""
        async with self._sf() as s:
            stmt = (
                select(Dream)
                .where(Dream.status.in_(RESOLVED))
                .order_by(Dream.resolved_at.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())
