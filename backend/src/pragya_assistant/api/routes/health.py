"""Liveness and readiness endpoints (unauthenticated)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.api.deps import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def database_ready(engine: AsyncEngine) -> bool:
    """True if the database accepts a trivial query; never raises."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


@router.get("/ready")
async def ready(engine: Annotated[AsyncEngine, Depends(get_engine)]) -> dict[str, str]:
    if not await database_ready(engine):
        raise HTTPException(status_code=503, detail="database not ready")
    return {"status": "ready"}
