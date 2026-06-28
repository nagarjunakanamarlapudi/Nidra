# src/pragya_assistant/user_model/facts.py
"""Stage 0 of the opinion workflow: gather cited FACTS from every source except
finance (browser, calendar, email, explicit memory). Pure per-source collectors
(testable without IO) that the query tools wrap, plus a light preferences reader.
No conclusions — just grounded facts, each tagged with its source ids."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


class PreferenceReader:
    """Light read-only preferences accessor (no embedder needed, unlike
    MemoryService) so it can be wired from a session factory alone — the query
    tools use it to read explicit preferences without spinning up MemoryService."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_preferences(self) -> dict[str, str]:
        async with self._sf() as s:
            return await PreferenceRepository(s).all_as_dict()
