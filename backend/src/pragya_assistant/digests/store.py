"""Storage for generated digests."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Digest


class DigestStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, content: str, delivered: str = "stored") -> Digest:
        async with self._session_factory() as session:
            digest = Digest(content=content, delivered=delivered)
            session.add(digest)
            await session.commit()
            await session.refresh(digest)
            return digest

    async def recent(self, limit: int = 20) -> list[Digest]:
        async with self._session_factory() as session:
            rows = (
                (await session.execute(select(Digest).order_by(Digest.id.desc()).limit(limit)))
                .scalars()
                .all()
            )
            return list(rows)
