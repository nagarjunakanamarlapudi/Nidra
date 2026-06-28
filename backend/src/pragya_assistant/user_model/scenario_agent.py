"""The scenario-maker as a tool-using agent.

Like the opinion agent, the configured engine runs the model<->tool loop; we
provide the read-only query tools (reused from the opinion agent) plus a
``query_user_model`` tool that surfaces current Opinions as citable facts, and the
prompt + final parse. The agent's job: from the user's CURRENT state, predict a
SMALL DISTRIBUTION of competing next-action branches, each falsifiable and citing
the facts it rests on. The track record + (hedged) policy lessons are injected
into the kickoff as in-context RSI — never as rules.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.completion import extract_json
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.tools import Tool
from pragya_assistant.agent.untrusted import wrap_untrusted
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.memory.models import ScenarioBatch
from pragya_assistant.user_model.facts import Fact, PreferenceReader
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, _observe, build_query_tools
from pragya_assistant.user_model.scenario_workflow import ProposedBranch
from pragya_assistant.user_model.store import UserModelStore

SCENARIO_SYSTEM = (
    "You are Nidra's scenario-maker. From the user's CURRENT state, predict the "
    "user's NEXT actions as a SMALL DISTRIBUTION of COMPETING branches. Investigate "
    "with the query tools (query_browsing, query_calendar, query_email, query_memory, "
    "query_user_model) -- pull what you need to read the current context. Then "
    "enumerate 2-4 DISTINCT, mutually-competing branches (different trajectories, NOT "
    "variations of one). Each branch MUST have: a one-line falsifiable prediction of "
    "an action the user will take; 1-3 action-level checkpoints OBSERVABLE in "
    "on-platform activity (a search, a page read, a choice, a calendar event) -- the "
    "FIRST checkpoint is the core test; a horizon in hours (horizon_hours); a prior "
    "probability; and the fact ids (e.g. f3) it is derived from (cite or it is "
    "dropped). Priors across your branches should sum to about 1. Keep the "
    "distribution DIVERSE -- do NOT collapse to one near-certain branch; reserve "
    "probability for alternatives, because the user may surprise you. The TRACK "
    "RECORD and POLICY LESSONS are HINTS about context you may have missed -- never "
    "rules, and never let one dominate. When done, output ONLY JSON: "
    '{"branches": [{"summary": "...", "checkpoints": ["..."], "horizon_hours": 24, '
    '"prior": 0.4, "evidence_fact_ids": ["f1"]}]}'
)

_KICKOFF = (
    "Predict the user's next actions as competing branches. Investigate the current "
    "state with the tools, then output the final branches JSON."
)


def build_scenario_tools(
    ledger: EvidenceLedger,
    *,
    browser: BrowserActivityEventStore | None = None,
    calendar: CalendarEventStore | None = None,
    email: Any | None = None,
    prefs: PreferenceReader | None = None,
    tasks: Any | None = None,
    opinions: UserModelStore | None = None,
    now: dt.datetime,
) -> list[Tool]:
    """The opinion agent's read-only query tools plus ``query_user_model`` (current
    Opinions as citable facts), all filling the same evidence ledger."""
    tools = build_query_tools(
        ledger, browser=browser, calendar=calendar, email=email, prefs=prefs, tasks=tasks, now=now
    )
    if opinions is not None:
        tools.append(_build_opinion_tool(ledger, opinions))
    return tools


def _build_opinion_tool(ledger: EvidenceLedger, opinions: UserModelStore) -> Tool:
    async def query_user_model(_args: dict[str, Any]) -> str:
        snaps = await opinions.current_model()
        facts = [
            Fact(
                "opinion",
                "trait",
                f"{s.trait} = {s.value} (conf {s.confidence})",
                refs=[f"opinion:{s.trait}"],
            )
            for s in snaps
        ]
        return _observe(ledger.record(facts))  # same fenced rendering as the other tools

    return Tool(
        name="query_user_model",
        description="Nidra's current grounded opinions about the user (citable as fact ids).",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=query_user_model,
    )


def build_scenario_kickoff(track_record: list[ScenarioBatch], lesson_texts: list[str]) -> str:
    """The kickoff message carrying the in-context RSI signal: how past batches
    turned out, and HEDGED policy lessons. Fenced as untrusted history so a crafted
    summary can't pose as an instruction."""
    body: list[str] = []
    if track_record:
        body.append("TRACK RECORD (past batches -- which branch reality confirmed):")
        for batch in track_record:
            if batch.status == "expired":
                body.append(f"- [expired] none of {len(batch.branches)} branches matched")
                continue
            parts = []
            for br in batch.branches:
                mark = {"confirmed": "CONFIRMED", "refuted": "refuted"}.get(br.status, br.status)
                parts.append(f"{br.summary} (p={br.prior}, rank{br.rank}) -> {mark}")
            body.append("- [resolved] " + " | ".join(parts))
    if lesson_texts:
        body.append("")
        body.append(
            "POLICY LESSONS (HYPOTHESES about context you may have missed -- treat as "
            "exploration hints, NEVER rules; never let one dominate your branches):"
        )
        body.extend(f"- {t}" for t in lesson_texts)
    if not body:
        return _KICKOFF
    return f"{_KICKOFF}\n\n{wrap_untrusted('scenario history', chr(10).join(body))}"


async def run_scenario_agent(engine: AgentEngine, kickoff: str) -> str:
    """Drive the engine -- its OWN tool loop fills the ledger via the query tools --
    and return the agent's final text (the branches JSON to parse)."""
    reply, _ = await engine.respond([], kickoff)
    return reply


def parse_proposed_branches(text: str) -> list[ProposedBranch]:
    """Parse the agent's final JSON into proposed branches, tolerating garbage.

    Drops entries with no summary or no checkpoints; clamps ``prior`` to [0, 1];
    coerces ``horizon_hours`` to a positive number (default 24); keeps only
    string/int fact ids. Citation resolution happens later in the workflow."""
    parsed = extract_json(text)
    out: list[ProposedBranch] = []
    for raw in parsed.get("branches", []) if isinstance(parsed, dict) else []:
        if not isinstance(raw, dict):
            continue
        summary = str(raw.get("summary") or "").strip()
        checkpoints = [str(c).strip() for c in raw.get("checkpoints", []) if str(c).strip()]
        if not summary or not checkpoints:
            continue
        try:
            prior = max(0.0, min(1.0, float(raw.get("prior", 0.0))))
        except (TypeError, ValueError):
            prior = 0.0
        try:
            horizon = float(raw.get("horizon_hours", 24.0))
        except (TypeError, ValueError):
            horizon = 24.0
        if horizon <= 0:
            horizon = 24.0
        ids = [str(i) for i in raw.get("evidence_fact_ids", []) if isinstance(i, str | int)]
        out.append(ProposedBranch(summary, checkpoints, horizon, prior, ids))
    return out
