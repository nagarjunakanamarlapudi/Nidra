"""Persistence for the distilled, durable user model.

Where the event store holds raw substrate, this holds what the derivation /
dreamer pass *concluded* — trait/preference snapshots. Append-only: each pass
writes fresh rows so a trait's evolution is queryable; the "current model" is
the latest snapshot per trait.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import UserModelSnapshot


@dataclass(frozen=True)
class TraitSnapshot:
    """One derived trait/preference at a point in time."""

    trait: str
    value: Any
    confidence: float = 0.0
    evidence: int = 0
    provenance: list[str] = field(default_factory=list)
    computed_at: dt.datetime | None = None


class UserModelStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def write(self, snapshots: list[TraitSnapshot]) -> int:
        """Append snapshots (history is never overwritten)."""
        if not snapshots:
            return 0
        async with self._sf() as s:
            for snap in snapshots:
                row = UserModelSnapshot(
                    trait=snap.trait,
                    value=snap.value,
                    confidence=snap.confidence,
                    evidence=snap.evidence,
                    provenance=list(snap.provenance),
                )
                if snap.computed_at is not None:
                    row.computed_at = snap.computed_at
                s.add(row)
            await s.commit()
        return len(snapshots)

    async def current_model(self) -> list[UserModelSnapshot]:
        """The latest snapshot per trait — the user model as it stands now."""
        async with self._sf() as s:
            stmt = (
                select(UserModelSnapshot)
                .distinct(UserModelSnapshot.trait)  # Postgres DISTINCT ON (trait)
                .order_by(UserModelSnapshot.trait, UserModelSnapshot.computed_at.desc())
            )
            return list((await s.execute(stmt)).scalars().all())

    async def history(self, trait: str) -> list[UserModelSnapshot]:
        """All snapshots for one trait, oldest → newest."""
        async with self._sf() as s:
            stmt = (
                select(UserModelSnapshot)
                .where(UserModelSnapshot.trait == trait)
                .order_by(UserModelSnapshot.computed_at.asc())
            )
            return list((await s.execute(stmt)).scalars().all())
