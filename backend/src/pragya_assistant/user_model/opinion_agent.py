"""The opinion-maker as a tool-using agent.

We do NOT write a loop: the configured engine (ClaudeCodeEngine via MCP, or
LoopEngine via native tool-calls) runs the model<->tool loop. We provide the query
TOOLS (wrapping the facts.py collectors), an EvidenceLedger that records every
fact a tool returns (the citable universe), and -- in Task E -- the prompt + a thin
runner + the final parse."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.completion import extract_json
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.user_model.facts import (
    Fact,
    PreferenceReader,
    collect_browser_facts,
    collect_calendar_facts,
    collect_email_facts,
    collect_memory_facts,
)
from pragya_assistant.user_model.opinion_workflow import ProposedOpinion


class EvidenceLedger:
    """Accumulates every Fact the tools return this run, numbered f1..fn -- the
    universe an opinion may cite. Validation resolves citations against it."""

    def __init__(self) -> None:
        self._facts: list[Fact] = []

    def record(self, facts: list[Fact]) -> list[Fact]:
        for f in facts:
            f.id = f"f{len(self._facts) + 1}"
            self._facts.append(f)
        return facts

    @property
    def facts(self) -> list[Fact]:
        return self._facts


def _observe(facts: list[Fact]) -> str:
    if not facts:
        return "(no matching facts)"
    return "\n".join(f"- {f.id} [{f.source}/{f.kind}]: {f.summary}" for f in facts)


def build_query_tools(
    ledger: EvidenceLedger,
    *,
    browser: BrowserActivityEventStore | None = None,
    calendar: CalendarEventStore | None = None,
    email: Any | None = None,
    prefs: PreferenceReader | None = None,
    tasks: Any | None = None,
    now: dt.datetime,
    browser_key: str = "browser_activity",
    calendar_key: str = "google_calendar",
) -> list[Tool]:
    tools: list[Tool] = []

    if browser is not None:
        async def query_browsing(args: dict[str, Any]) -> str:
            days = max(1, int(args.get("days", 30)))
            rows = await browser.recent(
                browser_key,
                types=["search", "reading", "interaction", "action"],
                since=now - dt.timedelta(days=days),
                limit=300,
            )
            return _observe(ledger.record(collect_browser_facts(rows)))

        tools.append(Tool(
            name="query_browsing",
            description=(
                "The user's recent browsing: searches, reading, choices, actions. "
                "arg: days (int)."
            ),
            input_schema={"type": "object", "properties": {"days": {"type": "integer"}},
                          "required": [], "additionalProperties": False},
            handler=query_browsing,
        ))

    if calendar is not None:
        async def query_calendar(args: dict[str, Any]) -> str:
            back = max(0, int(args.get("days_back", 90)))
            ahead = max(0, int(args.get("days_ahead", 60)))
            events = await calendar.events_between(
                calendar_key, now - dt.timedelta(days=back), now + dt.timedelta(days=ahead)
            )
            return _observe(ledger.record(collect_calendar_facts(events)))

        tools.append(Tool(
            name="query_calendar",
            description=(
                "The user's calendar -- past routines and upcoming commitments. "
                "args: days_back, days_ahead (int)."
            ),
            input_schema={"type": "object", "properties": {
                "days_back": {"type": "integer"}, "days_ahead": {"type": "integer"}},
                "required": [], "additionalProperties": False},
            handler=query_calendar,
        ))

    if email is not None:
        async def query_email(args: dict[str, Any]) -> str:
            n = max(1, int(args.get("n", 20)))
            return _observe(ledger.record(collect_email_facts(await email.list_recent(n))))

        tools.append(Tool(
            name="query_email",
            description="The user's recent email (sender + subject). arg: n (int).",
            input_schema={"type": "object", "properties": {"n": {"type": "integer"}},
                          "required": [], "additionalProperties": False},
            handler=query_email,
        ))

    if prefs is not None or tasks is not None:
        async def query_memory(_args: dict[str, Any]) -> str:
            p = await prefs.get_preferences() if prefs is not None else {}
            t = await tasks.list_tasks() if tasks is not None else []
            return _observe(ledger.record(collect_memory_facts(p, t)))

        tools.append(Tool(
            name="query_memory",
            description="What the user explicitly told the assistant: preferences and open tasks.",
            input_schema={"type": "object", "properties": {}, "required": [],
                          "additionalProperties": False},
            handler=query_memory,
        ))

    return tools


# ---------------------------------------------------------------------------
# Task E: the opinion-maker prompt + final parse + a thin runner. We write NO
# loop -- the engine runs the model<->tool loop itself; the tools fill the ledger.
# ---------------------------------------------------------------------------

OPINION_SYSTEM = (
    "You are Nidra's opinion-maker. Investigate the user with the query tools "
    "(query_browsing, query_calendar, query_email, query_memory) -- pull what you need, "
    "including calendar history AND upcoming events. Then state durable, HIGH-CONFIDENCE "
    "opinions the evidence DIRECTLY supports. Each opinion MUST cite the fact ids "
    "(e.g. f3) the tools returned. State nothing the facts don't support. NO speculation "
    "or future-guessing -- that's the dreamer's job. Prefer interest:<topic>, preference:<x>, "
    "routine:<x>, intent:<x>. When done, output ONLY JSON: "
    '{"opinions": [{"trait": "interest:travel", "value": "...", "confidence": 0.0, '
    '"evidence_fact_ids": ["f1"]}]}'
)

_KICKOFF = (
    "Form grounded opinions about the user. Investigate with the tools, then output "
    "the final JSON."
)


def parse_proposed_opinions(text: str) -> list[ProposedOpinion]:
    """Parse the agent's final JSON into proposed opinions, tolerating garbage.

    Drops malformed entries (empty trait, missing/empty value); clamps confidence
    to [0, 1]; keeps only string/int fact ids. Citation resolution against the
    ledger happens later in ``validate_citations`` (the anti-hallucination gate)."""
    parsed = extract_json(text)
    out: list[ProposedOpinion] = []
    for raw in parsed.get("opinions", []) if isinstance(parsed, dict) else []:
        if not isinstance(raw, dict):
            continue
        trait = str(raw.get("trait") or "").strip()
        value = raw.get("value")
        if not trait or value is None or (isinstance(value, str) and not value.strip()):
            continue
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        ids = [str(i) for i in raw.get("evidence_fact_ids", []) if isinstance(i, str | int)]
        out.append(ProposedOpinion(trait, value, conf, ids))
    return out


async def run_opinion_agent(engine: AgentEngine) -> str:
    """Drive the engine -- its OWN tool loop populates the ledger via the query
    tools -- and return the agent's final text (the opinions JSON to parse)."""
    reply, _ = await engine.respond([], _KICKOFF)
    return reply
