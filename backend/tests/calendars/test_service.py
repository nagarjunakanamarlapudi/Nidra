import datetime as dt
from collections.abc import Awaitable, Callable

from pragya_assistant.calendars.service import CalendarService

# Single event on Sat 2026-06-20; weekly standup every Monday from 2026-06-15.
SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//pragya//test//EN
BEGIN:VEVENT
UID:single@test
DTSTART:20260620T150000Z
DTEND:20260620T160000Z
SUMMARY:Single meeting
LOCATION:Room 1
END:VEVENT
BEGIN:VEVENT
UID:weekly@test
DTSTART:20260615T100000Z
DTEND:20260615T103000Z
RRULE:FREQ=WEEKLY;BYDAY=MO
SUMMARY:Weekly standup
END:VEVENT
END:VCALENDAR
"""


def _fetcher(calls: list[str] | None = None) -> Callable[[str], Awaitable[str]]:
    async def fetch(url: str) -> str:
        if calls is not None:
            calls.append(url)
        return SAMPLE_ICS

    return fetch


async def test_events_on_single_day() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    events = await svc.events_on(dt.date(2026, 6, 20))
    assert [e.summary for e in events] == ["Single meeting"]
    assert events[0].location == "Room 1"


async def test_recurring_event_expands() -> None:
    svc = CalendarService("http://feed", fetcher=_fetcher())
    events = await svc.events_on(dt.date(2026, 6, 22))  # a Monday after the series start
    assert [e.summary for e in events] == ["Weekly standup"]


async def test_cache_avoids_refetch() -> None:
    calls: list[str] = []
    svc = CalendarService("http://feed", fetcher=_fetcher(calls))
    await svc.events_on(dt.date(2026, 6, 20))
    await svc.events_on(dt.date(2026, 6, 22))
    assert calls == ["http://feed"]  # fetched once, then served from cache


async def test_no_url_returns_empty() -> None:
    svc = CalendarService(None)
    assert await svc.events_on(dt.date(2026, 6, 20)) == []
