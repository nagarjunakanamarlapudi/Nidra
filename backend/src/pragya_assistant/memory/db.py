"""Async engine / session factories and schema helpers.

Factory functions (not module globals) so callers — the API lifespan, tests —
own the engine lifecycle and can point at different databases.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pragya_assistant.memory.models import Base


def create_engine(database_url: str) -> AsyncEngine:
    """Create an async engine for the given URL (asyncpg driver)."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def ensure_vector_extension(engine: AsyncEngine) -> None:
    """Idempotently enable the pgvector extension."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def create_all(engine: AsyncEngine) -> None:
    """Create all tables (dev/test convenience; production uses migrations)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
