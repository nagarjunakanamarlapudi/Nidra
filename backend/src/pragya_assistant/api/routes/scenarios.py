"""Scenarios API — generate competing next-action predictions, verify them against
real activity over time, and report the self-improvement scorecard.

Behind the app's global bearer token, like the opinions/dreams routes. Generation
runs on a CONFINED, tool-using agent (``build_scenario_engine``) — never the
web-enabled chat engine — so untrusted ingested facts can't drive tool use or
exfiltrate. Verification + reconciliation are headless (cron); a scenario is never
written as an Opinion (the one-way valve).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.completion import ollama_completion_fn
from pragya_assistant.agent.factory import build_confined_completion_fn, build_scenario_engine
from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_session_factory, get_settings_dep
from pragya_assistant.api.routes.opinions import form_opinions
from pragya_assistant.config import Settings
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.user_model.facts import PreferenceReader
from pragya_assistant.user_model.opinion_agent import EvidenceLedger
from pragya_assistant.user_model.scenario_agent import build_scenario_tools
from pragya_assistant.user_model.scenario_metrics import scenario_scorecard
from pragya_assistant.user_model.scenario_reconciler import ScenarioReconciler, lessons_for_prompt
from pragya_assistant.user_model.scenario_verifier import ScenarioVerifier
from pragya_assistant.user_model.scenario_workflow import ScenarioWorkflow
from pragya_assistant.user_model.scenarios import LessonStore, ScenarioStore
from pragya_assistant.user_model.store import UserModelStore

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["scenarios"], dependencies=[Depends(require_token)])

SessionFactory = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


@router.post("/scenarios/run")
async def run_scenarios(settings: AppSettings, session_factory: SessionFactory) -> dict[str, Any]:
    """Generate a batch of competing, falsifiable next-action predictions from the
    user's current state via the confined, tool-using scenario agent (investigate ->
    validate -> calibrate -> review -> persist). The resolved track record is fed
    back in as in-context RSI. Manual + every few hours via cron (verify-first)."""
    now = _now()
    ledger = EvidenceLedger()
    tools = build_scenario_tools(
        ledger,
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        opinions=UserModelStore(session_factory),
        now=now,
    )
    engine = build_scenario_engine(settings, tools=tools)
    if settings.agent_engine == "ollama":
        review_fn = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
    else:
        review_fn = build_confined_completion_fn(settings)
    scenarios = ScenarioStore(session_factory)
    track_record = await scenarios.track_record(limit=20)
    # In-context RSI: decayed, capped, hedged lessons from past mis-ranks.
    lesson_texts = lessons_for_prompt(await LessonStore(session_factory).recent(limit=20), now=now)
    workflow = ScenarioWorkflow(
        scenarios,
        engine=engine,
        ledger=ledger,
        now=now,
        review_fn=review_fn,
        track_record=track_record,
        lesson_texts=lesson_texts,
        lessons_used=len(lesson_texts),
    )
    try:
        run = await workflow.run()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Scenario workflow unavailable: {exc}",
        ) from exc
    return {"ok": True, "batch_id": run.batch_id, "branches": len(run.branches)}


@router.post("/scenarios/verify")
async def verify_scenarios(
    settings: AppSettings, session_factory: SessionFactory
) -> dict[str, Any]:
    """Resolve open batches against real activity (the honest rules), then reconcile
    mis-ranked batches: diagnose the missing context, persist a hedged decaying
    lesson, and trigger ΔState opinion re-derivation. Headless; runs every ~15 min
    via cron, before each generation. Idempotent."""
    now = _now()
    scenarios = ScenarioStore(session_factory)
    events = BrowserActivityEventStore(session_factory)
    result = await ScenarioVerifier(scenarios, events).verify(now=now)

    if settings.agent_engine == "ollama":
        diagnose_fn = ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
    else:
        diagnose_fn = build_confined_completion_fn(settings)

    async def refresh_opinions_fn() -> None:
        # ΔState: re-derive Opinions from the new real signals. A failure here must
        # not fail verification — the next hourly opinions cron will catch up.
        try:
            await form_opinions(settings, session_factory)
        except httpx.HTTPError as exc:
            logger.warning("scenario_delta_state_refresh_failed", error=str(exc))

    reconciler = ScenarioReconciler(
        scenarios,
        LessonStore(session_factory),
        diagnose_fn=diagnose_fn,
        refresh_opinions_fn=refresh_opinions_fn,
    )
    rec = await reconciler.reconcile(result.resolved_batches)
    return {
        "ok": True,
        "confirmed": result.confirmed,
        "refuted": result.refuted,
        "expired": result.expired,
        "diagnosed": rec.diagnosed,
        "lessons": rec.lessons,
        "opinions_refreshed": rec.opinions_refreshed,
    }


@router.get("/scenarios/scorecard")
async def scenarios_scorecard(
    session_factory: SessionFactory, window_days: int = 30
) -> dict[str, Any]:
    """The self-improvement scorecard: hit-rate (expired excluded), top-branch
    accuracy, Brier calibration, expired-rate (the observability gap, reported
    separately), and the ΔPolicy-vs-ΔState split."""
    return await scenario_scorecard(ScenarioStore(session_factory), window_days=window_days)


@router.get("/scenarios")
async def list_scenarios(session_factory: SessionFactory) -> dict[str, list[dict[str, Any]]]:
    """Open batches with their competing branches (ordered by rank)."""
    batches = await ScenarioStore(session_factory).open_batches()
    return {
        "batches": [
            {
                "id": b.id,
                "created_at": b.created_at.isoformat(),
                "due_at": b.due_at.isoformat(),
                "status": b.status,
                "branches": [
                    {
                        "id": br.id,
                        "summary": br.summary,
                        "checkpoints": br.checkpoints,
                        "prior": br.prior,
                        "rank": br.rank,
                        "deadline_at": br.deadline_at.isoformat(),
                        "status": br.status,
                    }
                    for br in b.branches
                ],
            }
            for b in batches
        ]
    }
