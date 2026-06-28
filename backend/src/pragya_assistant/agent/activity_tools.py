"""Agent tools exposing captured activity + the user model to the chat agent.

Closes the loop: signals flow into Opinions/Dreams, and these tools let the
assistant the user *talks to* actually read their browsing and what Nidra has
concluded — answering "what did I browse today?" and "what do you know about me?".
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.user_model.dreams import DreamStore
from pragya_assistant.user_model.store import UserModelStore

KEY = "browser_activity"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _format_trait(s: Any) -> str:
    base = (
        f"- {s.trait}: {s.value} "
        f"(confidence {s.confidence}, from {', '.join(s.provenance or [])})"
    )
    d = s.derivation or {}
    formula = d.get("formula") if isinstance(d, dict) else None
    n = len(d.get("event_ids", [])) if isinstance(d, dict) else 0
    if formula:
        base += f"\n    └ derived by: {formula}" + (f" ({n} signals)" if n else "")
    return base


def build_activity_tools(session_factory: async_sessionmaker[AsyncSession]) -> list[Tool]:
    events = BrowserActivityEventStore(session_factory)
    user_model = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)

    async def recent_browsing(args: dict[str, Any]) -> str:
        days = max(1, int(args.get("days", 1)))
        since = _now() - dt.timedelta(days=days)
        rows = await events.recent(
            KEY, types=["reading", "search", "pageview"], since=since, limit=100
        )
        if not rows:
            return f"No browsing captured in the last {days} day(s)."
        searches = [str((r.data or {}).get("query")) for r in rows if r.event_type == "search"]
        searches = [q for q in searches if q and q != "None"]
        reading = [r for r in rows if r.event_type == "reading"]
        domains: dict[str, int] = {}
        for r in rows:
            if r.domain:
                domains[r.domain] = domains.get(r.domain, 0) + 1
        lines = [f"Browsing in the last {days} day(s):"]
        if searches:
            lines.append("Searches: " + "; ".join(searches[:15]))
        if reading:
            titles = [
                r.title or (r.data or {}).get("title") or r.domain or "(page)" for r in reading
            ]
            lines.append("Read: " + "; ".join(str(t) for t in titles[:15]))
        if domains:
            top = sorted(domains, key=lambda d: domains[d], reverse=True)[:8]
            lines.append("Top sites: " + ", ".join(top))
        return "\n".join(lines)

    async def about_me(_args: dict[str, Any]) -> str:
        model = await user_model.current_model()
        active = await dreams.active(limit=10)
        if not model and not active:
            return (
                "I don't have a model of you yet — capture some activity, then run "
                "an opinions refresh and a dream."
            )
        parts: list[str] = []
        if model:
            parts.append(
                "What I know about you (grounded in your activity):\n"
                + "\n".join(_format_trait(s) for s in model)
            )
        if active:
            parts.append(
                "Current hunches I'm tracking (dreams, not yet confirmed):\n"
                + "\n".join(f"- {d.hypothesis}" for d in active)
            )
        return "\n\n".join(parts)

    return [
        Tool(
            name="recent_browsing",
            description=(
                "Look at what the user recently browsed, read, and searched for "
                "(from ambient capture). Use for questions like 'what did I browse "
                "today?' or 'what have I been reading about?'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "How many days back to look (default 1 = today).",
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=recent_browsing,
        ),
        Tool(
            name="about_me",
            description=(
                "Read Nidra's model of the user — the durable opinions/traits it has "
                "formed from their activity, plus current dream hunches. Use for "
                "'what do you know about me?', 'what are my interests/habits?'."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            handler=about_me,
        ),
    ]
