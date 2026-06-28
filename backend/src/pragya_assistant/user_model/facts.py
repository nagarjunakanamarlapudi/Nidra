# src/pragya_assistant/user_model/facts.py
"""Stage 0 of the opinion workflow: gather cited FACTS from every source except
finance (browser, calendar, email, explicit memory). Pure per-source collectors
(testable without IO) + a builder that fetches, runs them, and numbers the facts.
No conclusions — just grounded facts, each tagged with its source ids."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.memory.repositories import PreferenceRepository


@dataclass
class Fact:
    """One grounded fact, tagged with its source ids (ints for browser/calendar
    rows, strings for gmail message ids / memory rows)."""

    source: str
    kind: str
    summary: str
    event_ids: list[int] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    id: str = ""  # assigned by the builder, e.g. "f1"


def _dwell_min(metrics: dict[str, Any] | None) -> int | None:
    ms = (metrics or {}).get("dwellMs")
    return round(ms / 60000) if isinstance(ms, int | float) and ms > 0 else None


def collect_browser_facts(rows: Sequence[Any]) -> list[Fact]:
    facts: list[Fact] = []
    for r in rows:
        d = r.data or {}
        if r.event_type == "search" and d.get("query"):
            facts.append(Fact("browser", "search", f"searched '{d['query']}'", event_ids=[r.id]))
        elif r.event_type == "reading" and (r.title or d.get("title")):
            title = r.title or d.get("title")
            mins = _dwell_min(r.metrics)
            pct = (r.metrics or {}).get("readPct")
            extra = f" ({mins}m, {pct}%)" if mins and pct else (f" ({mins}m)" if mins else "")
            facts.append(Fact("browser", "reading", f"read '{title}'{extra}", event_ids=[r.id]))
        elif r.event_type == "interaction" and d.get("action") == "choose" and d.get("value"):
            grp = d.get("group") or "option"
            facts.append(
                Fact("browser", "choice", f"chose {d['value']} for {grp}", event_ids=[r.id])
            )
        elif r.event_type == "action" and d.get("milestone"):
            funnel = d.get("funnel") or "flow"
            facts.append(
                Fact("browser", "action", f"{d['milestone']} in {funnel}", event_ids=[r.id])
            )
    return facts


def collect_calendar_facts(events: Sequence[Any], *, cap: int = 40) -> list[Fact]:
    facts: list[Fact] = []
    for e in events[:cap]:
        when = e.start.strftime("%a") if getattr(e, "start", None) else "?"
        facts.append(
            Fact("calendar", "event", f"calendar: '{e.summary}' ({when})", event_ids=[e.id])
        )
    return facts


def collect_email_facts(messages: Sequence[Any], *, cap: int = 20) -> list[Fact]:
    facts: list[Fact] = []
    for m in messages[:cap]:
        facts.append(
            Fact("email", "email", f"email from {m.from_} — {m.subject}", refs=[m.message_id])
        )
    return facts


def collect_memory_facts(
    preferences: dict[str, str], tasks: Sequence[Any]
) -> list[Fact]:
    facts: list[Fact] = []
    for k, v in preferences.items():
        facts.append(Fact("memory", "preference", f"preference {k}: {v}", refs=[f"pref:{k}"]))
    for t in tasks:
        facts.append(Fact("memory", "task", f"open task: {t.title}", refs=[f"task:{t.id}"]))
    return facts


class _PrefsSource(Protocol):
    async def get_preferences(self) -> dict[str, str]: ...


class _TasksSource(Protocol):
    async def list_tasks(self, include_done: bool = False) -> list[Any]: ...


class _EmailSource(Protocol):
    async def list_recent(self, n: int = 10) -> list[Any]: ...


class PreferenceReader:
    """Light read-only preferences accessor (no embedder needed, unlike
    MemoryService) so the builder can be wired from a session factory alone."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_preferences(self) -> dict[str, str]:
        async with self._sf() as s:
            return await PreferenceRepository(s).all_as_dict()


class FactDigestBuilder:
    """Gathers facts from whatever sources are available (skips any that are
    None / empty) and numbers them f1..fn for citation."""

    def __init__(
        self,
        *,
        browser: BrowserActivityEventStore | None = None,
        calendar: CalendarEventStore | None = None,
        email: _EmailSource | None = None,
        prefs: _PrefsSource | None = None,
        tasks: _TasksSource | None = None,
        now: dt.datetime,
        window_days: int = 30,
        browser_key: str = "browser_activity",
        calendar_key: str = "google_calendar",
    ) -> None:
        self._browser = browser
        self._calendar = calendar
        self._email = email
        self._prefs = prefs
        self._tasks = tasks
        self._now = now
        self._window = window_days
        self._browser_key = browser_key
        self._calendar_key = calendar_key

    async def build(self) -> list[Fact]:
        collected: list[Fact] = []
        if self._browser is not None:
            rows = await self._browser.recent(
                self._browser_key,
                types=["search", "reading", "interaction", "action"],
                since=self._now - dt.timedelta(days=self._window),
                limit=300,
            )
            collected += collect_browser_facts(rows)
        if self._calendar is not None:
            # Calendar events are FORWARD-looking (upcoming meetings/bookings = intent),
            # so look ahead — unlike browsing history, which is in the past.
            events = await self._calendar.events_between(
                self._calendar_key,
                self._now - dt.timedelta(days=1),
                self._now + dt.timedelta(days=self._window),
            )
            collected += collect_calendar_facts(events)
        if self._email is not None:
            collected += collect_email_facts(await self._email.list_recent(20))
        prefs = await self._prefs.get_preferences() if self._prefs is not None else {}
        tasks = await self._tasks.list_tasks() if self._tasks is not None else []
        if prefs or tasks:
            collected += collect_memory_facts(prefs, tasks)
        for i, f in enumerate(collected, start=1):
            f.id = f"f{i}"
        return collected
