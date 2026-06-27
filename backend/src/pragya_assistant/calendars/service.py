"""Read-only calendar access over an .ics feed (with recurrence expansion)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import icalendar
import recurring_ical_events

Fetcher = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class CalEvent:
    start: dt.datetime | dt.date
    end: dt.datetime | dt.date | None
    summary: str
    location: str | None


class CalendarService:
    """Fetches + parses an .ics feed, expands recurrences, with a short TTL cache.

    ``fetcher`` and ``clock`` are injectable for tests (no network, no real time).
    """

    def __init__(
        self,
        ics_url: str | None,
        *,
        fetcher: Fetcher | None = None,
        clock: Callable[[], dt.datetime] | None = None,
        cache_ttl: float = 300.0,
    ) -> None:
        self._ics_url = ics_url
        self._fetch = fetcher or _http_fetch
        self._clock = clock or (lambda: dt.datetime.now(dt.UTC))
        self._cache_ttl = cache_ttl
        # icalendar is only partially typed; treat parsed objects as Any.
        self._cache: tuple[float, Any] | None = None

    async def events_on(self, day: dt.date) -> list[CalEvent]:
        return await self.events_between(day, day + dt.timedelta(days=1))

    async def events_between(self, start: dt.date, end: dt.date) -> list[CalEvent]:
        calendar = await self._calendar()
        if calendar is None:
            return []
        occurrences = recurring_ical_events.of(calendar).between(start, end)
        return sorted((_to_event(o) for o in occurrences), key=lambda e: _sort_key(e.start))

    async def _calendar(self) -> Any:
        if not self._ics_url:
            return None
        now = self._clock().timestamp()
        if self._cache is not None and now - self._cache[0] < self._cache_ttl:
            return self._cache[1]
        text = await self._fetch(self._ics_url)
        calendar: Any = icalendar.Calendar.from_ical(text)
        self._cache = (now, calendar)
        return calendar


async def _http_fetch(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _to_event(component: Any) -> CalEvent:
    end_prop = component.get("DTEND")
    location = component.get("LOCATION")
    return CalEvent(
        start=component.get("DTSTART").dt,
        end=end_prop.dt if end_prop is not None else None,
        summary=str(component.get("SUMMARY", "(no title)")),
        location=str(location) if location else None,
    )


def _sort_key(start: dt.datetime | dt.date) -> dt.datetime:
    if isinstance(start, dt.datetime):
        return start.replace(tzinfo=None)
    return dt.datetime.combine(start, dt.time.min)
