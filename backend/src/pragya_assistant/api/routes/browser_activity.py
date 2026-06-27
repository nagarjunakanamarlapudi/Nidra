"""Browser Activity ingest + dream API.

Both endpoints sit behind the app's global bearer token (``require_token``) — the
same token the extension already holds — so there is no separate per-connector
secret to manage. Ingest stores pushed events; dream runs the on-device LLM
"Sleep" pass over them.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_session_factory, get_settings_dep
from pragya_assistant.config import Settings
from pragya_assistant.connectors.browser_activity.dreamer import DreamerService, ollama_dream_fn
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)

CONNECTOR_KEY = "browser_activity"

router = APIRouter(tags=["browser-activity"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


class ActivityEventIn(BaseModel):
    id: str | None = None
    type: str = "pageview"
    ts: int | None = None  # epoch milliseconds
    url: str | None = None
    domain: str | None = None
    title: str | None = None
    source: str | None = None
    data: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None  # engagement: dwellMs, scrollPct, readPct, latencyMs
    context_id: str | None = None  # correlates impression -> interaction -> action
    redacted: bool = False


class IngestIn(BaseModel):
    events: list[ActivityEventIn] = Field(default_factory=list)


class IngestOut(BaseModel):
    ok: bool
    ingested: int


class DreamOut(BaseModel):
    generated_from: int
    persona: str | None
    connected_insights: list[dict[str, Any]]
    beliefs: list[dict[str, Any]]
    next_needs: list[str]
    engine: str


def _to_ingested(event: ActivityEventIn, index: int) -> IngestedEvent:
    if event.ts is not None:
        ts = dt.datetime.fromtimestamp(event.ts / 1000, tz=dt.UTC).replace(tzinfo=None)
    else:
        ts = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    client_id = event.id or f"{int(ts.timestamp() * 1000)}-{index}"
    return IngestedEvent(
        client_id=client_id,
        event_type=event.type,
        ts=ts,
        source=event.source,
        domain=event.domain,
        url=event.url,
        title=event.title,
        data=event.data,
        metrics=event.metrics,
        context_id=event.context_id,
        redacted=event.redacted,
    )


@router.post("/connectors/browser_activity/ingest", response_model=IngestOut)
async def ingest(payload: IngestIn, session_factory: SessionFactory) -> IngestOut:
    store = BrowserActivityEventStore(session_factory)
    count = await store.add_events(
        CONNECTOR_KEY, [_to_ingested(e, i) for i, e in enumerate(payload.events)]
    )
    return IngestOut(ok=True, ingested=count)


@router.post("/connectors/browser_activity/dream", response_model=DreamOut)
async def dream(settings: AppSettings, session_factory: SessionFactory) -> DreamOut:
    store = BrowserActivityEventStore(session_factory)
    service = DreamerService(
        store,
        ollama_dream_fn(settings.ollama_base_url, settings.dream_model),
        engine_label=f"ollama:{settings.dream_model}",
    )
    try:
        result = await service.dream()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dreamer (Ollama) unavailable: {exc}",
        ) from exc
    return DreamOut(
        generated_from=result.generated_from,
        persona=result.persona,
        connected_insights=result.connected_insights,
        beliefs=result.beliefs,
        next_needs=result.next_needs,
        engine=result.engine,
    )
