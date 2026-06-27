"""Model-facing tools that read ingested events from the store (no live calls)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.memory.models import CalendarEvent


def build_calendar_tools(
    store: CalendarEventStore, connector_key: str, *, today: Callable[[], dt.date] | None = None
) -> list[Tool]:
    _today = today or dt.date.today

    async def agenda(args: dict[str, Any]) -> str:
        day = _parse_date(args.get("date")) or _today()
        start = dt.datetime.combine(day, dt.time.min)
        events = await store.events_between(connector_key, start, start + dt.timedelta(days=1))
        if not events:
            return f"Nothing on the calendar for {day.isoformat()}."
        return _render(events)

    async def upcoming(args: dict[str, Any]) -> str:
        days = int(args.get("days", 7))
        start = dt.datetime.combine(_today(), dt.time.min)
        events = await store.events_between(connector_key, start, start + dt.timedelta(days=days))
        if not events:
            return f"Nothing on the calendar in the next {days} days."
        return _render(events)

    return [
        Tool(
            name="gcal_agenda",
            description="Show Google Calendar events for a day (default today).",
            input_schema=_object({"date": _string("Day as YYYY-MM-DD (default today)")}),
            handler=agenda,
        ),
        Tool(
            name="gcal_upcoming",
            description="List Google Calendar events over the next N days.",
            input_schema=_object({"days": _integer("How many days ahead (default 7)")}),
            handler=upcoming,
        ),
    ]


def _render(events: list[CalendarEvent]) -> str:
    # Tag each line with its account only when events span more than one account.
    multi = len({e.account_label for e in events if e.account_label}) > 1
    return "\n".join(_format(e, show_account=multi) for e in events)


def _format(event: CalendarEvent, *, show_account: bool = False) -> str:
    if event.all_day:
        when = event.start.strftime("%a %b %d") + " (all day)"
    else:
        when = event.start.strftime("%a %b %d %H:%M")
    location = f" @ {event.location}" if event.location else ""
    tag = f"[{event.account_label}] " if show_account and event.account_label else ""
    return f"- {tag}{when} — {event.summary}{location}"


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value))


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": [],
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
