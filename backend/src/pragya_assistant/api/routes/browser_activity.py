"""Browser Activity ingest API.

The endpoint sits behind the app's global bearer token (``require_token``) — the
same token the extension already holds — so there is no separate per-connector
secret to manage. It stores the activity events the extension pushes. (Dreaming
moved to the multi-source ``/dreams/run``; the legacy on-device dream pass here is
retired.)
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_session_factory
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)

CONNECTOR_KEY = "browser_activity"

router = APIRouter(tags=["browser-activity"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]


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
