"""Opinions API — refresh the user model by forming fact-grounded opinions.

Behind the app's global bearer token, like the browser-activity ingest. The
opinion-maker is a confined, tool-using agent (``build_opinion_engine``): it pulls
browser+calendar+email+memory through read-only query tools that fill an evidence
ledger, forms cited opinions, has them skeptically reviewed, then persists them —
never the web-enabled chat engine, so the untrusted ingested facts can't drive
tool use or exfiltrate.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
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
from pragya_assistant.user_model.facts import PreferenceReader
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, build_query_tools
from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow
from pragya_assistant.user_model.store import UserModelStore

router = APIRouter(tags=["opinions"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


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
