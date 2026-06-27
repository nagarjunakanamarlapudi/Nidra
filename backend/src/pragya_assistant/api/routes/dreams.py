"""Dreams API — read active dreams (digest + read-only popup) and capture outcomes.

Behind the app's global bearer token, like the browser-activity ingest. Outcomes
resolve the dream and emit a real signal (see DreamFeedbackService); the dreamer
never writes Opinions directly.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_session_factory
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.user_model.dreams import DreamStore
from pragya_assistant.user_model.feedback import DreamFeedbackService

router = APIRouter(tags=["dreams"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


class OutcomeIn(BaseModel):
    signal: str  # acted | corroborated | dismissed | snoozed | ignored


class OutcomeOut(BaseModel):
    ok: bool
    status: str | None  # confirmed | refuted | None (snoozed/ignored — unresolved)


@router.get("/dreams")
async def list_dreams(session_factory: SessionFactory) -> dict[str, list[dict[str, Any]]]:
    rows = await DreamStore(session_factory).active()
    return {
        "dreams": [
            {
                "id": d.id,
                "hypothesis": d.hypothesis,
                "kind": d.kind,
                "confidence": d.confidence,
                "provenance": d.provenance,
                "status": d.status,
            }
            for d in rows
        ]
    }


@router.post("/dreams/{dream_id}/outcome", response_model=OutcomeOut)
async def record_outcome(
    dream_id: int, payload: OutcomeIn, session_factory: SessionFactory
) -> OutcomeOut:
    dreams = DreamStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    status = await DreamFeedbackService(dreams, events).record(dream_id, signal=payload.signal)
    return OutcomeOut(ok=True, status=status)
