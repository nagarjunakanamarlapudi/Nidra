"""The opinion-maker as a tool-using agent.

We do NOT write a loop: the configured engine (ClaudeCodeEngine via MCP, or
LoopEngine via native tool-calls) runs the model<->tool loop. We provide the query
TOOLS (wrapping the facts.py collectors), an EvidenceLedger that records every
fact a tool returns (the citable universe), and -- in Task E -- the prompt + a thin
runner + the final parse."""

from __future__ import annotations

import datetime as dt
from typing import Any

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
