"""Dreams API — read active dreams (digest + read-only popup) and capture outcomes.

Behind the app's global bearer token, like the browser-activity ingest. Outcomes
resolve the dream and emit a real signal (see DreamFeedbackService); the dreamer
never writes Opinions directly.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.completion import ollama_completion_fn
from pragya_assistant.agent.factory import build_confined_completion_fn, build_opinion_engine
from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_session_factory, get_settings_dep
from pragya_assistant.config import Settings
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.user_model.dreamer import DreamerService
from pragya_assistant.user_model.dreams import DreamStore
from pragya_assistant.user_model.facts import PreferenceReader
from pragya_assistant.user_model.feedback import DreamFeedbackService
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, build_query_tools
from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow
from pragya_assistant.user_model.store import UserModelStore

router = APIRouter(tags=["dreams"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


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
    outcome_status = await DreamFeedbackService(dreams, events).record(
        dream_id, signal=payload.signal
    )
    return OutcomeOut(ok=True, status=outcome_status)


@router.post("/opinions/refresh")
async def refresh_opinions(
    settings: AppSettings, session_factory: SessionFactory
) -> dict[str, Any]:
    """Form fact-grounded opinions via the tool-using opinion agent (investigate ->
    validate -> review -> persist). The agent pulls browser+calendar+email+memory
    through read-only query tools that fill an evidence ledger; finance is Phase 2.
    Runs on a CONFINED engine (no web/file/bash, output-scrubbed) — never the
    web-enabled chat engine — so the untrusted ingested facts can't drive tool use
    or exfiltrate. Manual + hourly via cron."""
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    ledger = EvidenceLedger()
    tools = build_query_tools(
        ledger,
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        now=now,
    )
    engine = build_opinion_engine(settings, tools=tools)
    if settings.agent_engine == "ollama":
        review_fn = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
    else:
        review_fn = build_confined_completion_fn(settings)
    model = UserModelStore(session_factory)
    workflow = OpinionWorkflow(model, engine=engine, review_fn=review_fn, ledger=ledger)
    try:
        formed = await workflow.run()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Opinion workflow unavailable: {exc}",
        ) from exc
    return {"ok": True, "traits": len(formed), "facts": len(ledger.facts)}


@router.post("/dreams/run")
async def run_dreams(settings: AppSettings, session_factory: SessionFactory) -> dict[str, Any]:
    """Dream on top of the current Opinions and write the dreams store. Runs on a
    CONFINED engine (no tools, no web, no file/bash) built for this background job
    — never the web-enabled chat engine — so ingested data can't drive tool use or
    exfiltrate. Falls back to on-device Ollama only when AGENT_ENGINE=ollama (also
    confined/no-tools). Invoked manually and nightly by cron."""
    model = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)
    if settings.agent_engine == "ollama":
        complete = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
        engine_label = f"ollama:{settings.dream_model}"
    else:
        complete = build_confined_completion_fn(settings)
        engine_label = settings.agent_engine
    dreamer = DreamerService(model, dreams, complete, engine_label=engine_label)
    try:
        created = await dreamer.dream()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Dreamer unavailable: {exc}",
        ) from exc
    return {
        "ok": True,
        "dreams": [
            {"id": d.id, "hypothesis": d.hypothesis, "kind": d.kind, "confidence": d.confidence}
            for d in created
        ],
    }
