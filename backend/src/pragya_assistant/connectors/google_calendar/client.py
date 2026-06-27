"""A thin async Google Calendar REST client (read-only).

Hits the Calendar v3 ``events.list`` endpoint with a bearer token, expands
recurrences (``singleEvents=true``), paginates, and normalizes each event into a
:class:`~pragya_assistant.connectors.google_calendar.store.RawEvent`. All times
are normalized to naive UTC to match the store's columns.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import httpx

from pragya_assistant.connectors.google_calendar.store import RawEvent

_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{cal}/events"


def _rfc3339(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_node(node: dict[str, Any]) -> tuple[dt.datetime, bool]:
    """Parse a Google ``start``/``end`` node → (naive-UTC datetime, all_day)."""
    if "dateTime" in node:
        parsed = dt.datetime.fromisoformat(str(node["dateTime"]).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
        return parsed, False
    day = dt.date.fromisoformat(str(node["date"]))
    return dt.datetime.combine(day, dt.time.min), True


class GoogleCalendarClient:
    async def list_events(
        self,
        access_token: str,
        *,
        time_min: dt.datetime,
        time_max: dt.datetime,
        calendar_id: str = "primary",
    ) -> list[RawEvent]:
        url = _EVENTS_URL.format(cal=calendar_id)
        headers = {"Authorization": f"Bearer {access_token}"}
        base_params = {
            "timeMin": _rfc3339(time_min),
            "timeMax": _rfc3339(time_max),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "2500",
        }
        events: list[RawEvent] = []
        async with httpx.AsyncClient(timeout=20.0) as client:
            page_token: str | None = None
            while True:
                params = dict(base_params)
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
                for item in payload.get("items", []):
                    event = _to_event(item, calendar_id)
                    if event is not None:
                        events.append(event)
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
        return events

    async def primary_email(self, access_token: str) -> str:
        """The account's email (the primary calendar's id) — used to label accounts."""
        url = "https://www.googleapis.com/calendar/v3/calendars/primary"
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
        return str(data.get("id", ""))


def _to_event(item: dict[str, Any], calendar_id: str) -> RawEvent | None:
    if item.get("status") == "cancelled":
        return None
    start_node = item.get("start") or {}
    if not start_node:
        return None
    start, all_day = _parse_node(start_node)
    end_node = item.get("end")
    end = _parse_node(end_node)[0] if end_node else None
    return RawEvent(
        uid=str(item["id"]),
        summary=item.get("summary") or "(no title)",
        location=item.get("location"),
        start=start,
        end=end,
        all_day=all_day,
        calendar_id=calendar_id,
    )
