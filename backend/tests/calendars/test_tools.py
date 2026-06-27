import datetime as dt

from pragya_assistant.agent.tools import ToolHandler
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.calendars.tools import build_calendar_tools
from tests.calendars.test_service import _fetcher


def _handler(tools: list, name: str) -> ToolHandler:
    return next(t for t in tools if t.name == name).handler


async def test_agenda_default_today() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    tools = build_calendar_tools(svc, today=lambda: dt.date(2026, 6, 20))
    assert "Single meeting" in await _handler(tools, "agenda")({})


async def test_agenda_explicit_date_expands_recurrence() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    tools = build_calendar_tools(svc, today=lambda: dt.date(2026, 6, 1))
    assert "Weekly standup" in await _handler(tools, "agenda")({"date": "2026-06-22"})


async def test_upcoming_events_spans_days() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    tools = build_calendar_tools(svc, today=lambda: dt.date(2026, 6, 20))
    out = await _handler(tools, "upcoming_events")({"days": 7})
    assert "Single meeting" in out and "Weekly standup" in out


async def test_empty_day_message() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    tools = build_calendar_tools(svc, today=lambda: dt.date(2026, 6, 21))  # Sunday, nothing
    assert "Nothing on the calendar" in await _handler(tools, "agenda")({})
