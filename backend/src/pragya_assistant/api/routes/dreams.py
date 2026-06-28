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

from pragya_assistant.agent.completion import engine_completion_fn, ollama_completion_fn
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_agent, get_session_factory, get_settings_dep
from pragya_assistant.config import Settings
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.user_model.dreamer import DreamerService
from pragya_assistant.user_model.dreams import DreamStore
from pragya_assistant.user_model.facts import FactDigestBuilder, PreferenceReader
from pragya_assistant.user_model.feedback import DreamFeedbackService
from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow
from pragya_assistant.user_model.store import UserModelStore

router = APIRouter(tags=["dreams"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
Agent = Annotated[AgentEngine, Depends(get_agent)]


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
    settings: AppSettings, session_factory: SessionFactory, agent: Agent
) -> dict[str, Any]:
    """Form fact-grounded opinions via the workflow (digest -> group -> form ->
    validate -> review -> persist). Browser+calendar+email+memory; finance is
    Phase 2. Same engine selection as the dreamer. Manual + hourly via cron."""
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    facts = await FactDigestBuilder(
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        now=now,
    ).build()
    if settings.agent_engine == "ollama":
        fn = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
    else:
        fn = engine_completion_fn(agent)
    model = UserModelStore(session_factory)
    workflow = OpinionWorkflow(model, group_fn=fn, form_fn=fn, review_fn=fn)
    try:
        formed = await workflow.run(facts)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Opinion workflow unavailable: {exc}",
        ) from exc
    return {"ok": True, "traits": len(formed), "facts": len(facts)}


@router.post("/dreams/run")
async def run_dreams(
    settings: AppSettings, session_factory: SessionFactory, agent: Agent
) -> dict[str, Any]:
    """Dream on top of the current Opinions and write the dreams store. Uses the
    configured agent brain (claude-code by default); falls back to on-device
    Ollama only when AGENT_ENGINE=ollama. Invoked manually and nightly by cron."""
    model = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)
    if settings.agent_engine == "ollama":
        complete = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
        engine_label = f"ollama:{settings.dream_model}"
    else:
        complete = engine_completion_fn(agent)
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
