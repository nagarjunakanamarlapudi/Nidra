"""Calendar tools — thin, model-facing wrappers over :class:`CalendarService`."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.calendars.service import CalendarService, CalEvent


def build_calendar_tools(
    service: CalendarService, *, today: Callable[[], dt.date] | None = None
) -> list[Tool]:
    _today = today or dt.date.today

    async def agenda(args: dict[str, Any]) -> str:
        day = _parse_date(args.get("date")) or _today()
        events = await service.events_on(day)
        if not events:
            return f"Nothing on the calendar for {day.isoformat()}."
        return "\n".join(_format(e) for e in events)

    async def upcoming_events(args: dict[str, Any]) -> str:
        days = int(args.get("days", 7))
        start = _today()
        events = await service.events_between(start, start + dt.timedelta(days=days))
        if not events:
            return f"Nothing on the calendar in the next {days} days."
        return "\n".join(_format(e) for e in events)

    return [
        Tool(
            name="agenda",
            description="Show the user's calendar events for a day (default today).",
            input_schema=_object({"date": _string("Day as YYYY-MM-DD (default today)")}, []),
            handler=agenda,
        ),
        Tool(
            name="upcoming_events",
            description="List the user's calendar events over the next N days.",
            input_schema=_object({"days": _integer("How many days ahead (default 7)")}, []),
            handler=upcoming_events,
        ),
    ]


def _format(event: CalEvent) -> str:
    if isinstance(event.start, dt.datetime):
        when = event.start.strftime("%a %b %d %H:%M")
    else:
        when = event.start.strftime("%a %b %d") + " (all day)"
    location = f" @ {event.location}" if event.location else ""
    return f"- {when} — {event.summary}{location}"


def _parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    return dt.date.fromisoformat(str(value))


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
