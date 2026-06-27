"""GoogleCalendarClient — parsing + pagination + request shape (respx)."""

from __future__ import annotations

import datetime as dt

import httpx
import respx

from pragya_assistant.connectors.google_calendar.client import GoogleCalendarClient

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


@respx.mock
async def test_parses_timed_and_all_day_and_skips_cancelled() -> None:
    respx.get(EVENTS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "1",
                        "summary": "Standup",
                        "location": "Zoom",
                        "start": {"dateTime": "2026-06-24T09:00:00+00:00"},
                        "end": {"dateTime": "2026-06-24T09:30:00+00:00"},
                    },
                    {
                        "id": "2",
                        "summary": "Holiday",
                        "start": {"date": "2026-06-25"},
                        "end": {"date": "2026-06-26"},
                    },
                    {
                        "id": "3",
                        "status": "cancelled",
                        "start": {"dateTime": "2026-06-24T10:00:00Z"},
                    },
                ]
            },
        )
    )
    events = await GoogleCalendarClient().list_events(
        "TOKEN", time_min=dt.datetime(2026, 6, 23), time_max=dt.datetime(2026, 7, 23)
    )
    assert [e.uid for e in events] == ["1", "2"]
    assert events[0].all_day is False
    assert events[0].summary == "Standup"
    assert events[0].location == "Zoom"
    assert events[0].start == dt.datetime(2026, 6, 24, 9, 0)
    assert events[1].all_day is True
    assert events[1].start == dt.datetime(2026, 6, 25, 0, 0)


@respx.mock
async def test_paginates_through_pages() -> None:
    respx.get(EVENTS_URL).side_effect = [
        httpx.Response(
            200,
            json={
                "items": [
                    {"id": "1", "summary": "A", "start": {"dateTime": "2026-06-24T09:00:00Z"}}
                ],
                "nextPageToken": "P2",
            },
        ),
        httpx.Response(
            200,
            json={
                "items": [
                    {"id": "2", "summary": "B", "start": {"dateTime": "2026-06-24T10:00:00Z"}}
                ]
            },
        ),
    ]
    events = await GoogleCalendarClient().list_events(
        "TOKEN", time_min=dt.datetime(2026, 6, 23), time_max=dt.datetime(2026, 7, 23)
    )
    assert [e.uid for e in events] == ["1", "2"]


@respx.mock
async def test_sends_bearer_and_params() -> None:
    route = respx.get(EVENTS_URL).mock(return_value=httpx.Response(200, json={"items": []}))
    await GoogleCalendarClient().list_events(
        "TOKEN", time_min=dt.datetime(2026, 6, 23, 0, 0), time_max=dt.datetime(2026, 7, 23, 0, 0)
    )
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer TOKEN"
    assert req.url.params["singleEvents"] == "true"
    assert req.url.params["timeMin"] == "2026-06-23T00:00:00Z"
