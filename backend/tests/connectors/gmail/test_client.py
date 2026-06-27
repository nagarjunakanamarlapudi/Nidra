"""GmailClient — list/parse + body decode + request shape (respx)."""

from __future__ import annotations

import base64

import httpx
import respx

from pragya_assistant.connectors.gmail.client import GmailClient

MSGS = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


@respx.mock
async def test_recent_lists_then_fetches_metadata() -> None:
    respx.get(MSGS).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "m1"}, {"id": "m2"}]})
    )
    respx.get(f"{MSGS}/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "snippet": "hi there",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "a@x.com"},
                        {"name": "Subject", "value": "Hello"},
                        {"name": "Date", "value": "Mon, 23 Jun 2026"},
                    ]
                },
            },
        )
    )
    respx.get(f"{MSGS}/m2").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m2",
                "snippet": "second",
                "payload": {"headers": [{"name": "From", "value": "b@x.com"}]},
            },
        )
    )
    route = respx.calls
    msgs = await GmailClient().recent("TOKEN", query="is:unread", max_results=10)
    assert [m.id for m in msgs] == ["m1", "m2"]
    assert msgs[0].sender == "a@x.com"
    assert msgs[0].subject == "Hello"
    assert msgs[0].snippet == "hi there"
    assert msgs[1].subject == "(no subject)"  # missing Subject header
    # list request carried bearer + query
    first = route[0].request
    assert first.headers["Authorization"] == "Bearer TOKEN"
    assert first.url.params["q"] == "is:unread"


@respx.mock
async def test_read_decodes_plaintext_body() -> None:
    body = base64.urlsafe_b64encode(b"Full body here").decode().rstrip("=")
    respx.get(f"{MSGS}/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "snippet": "...",
                "payload": {
                    "headers": [{"name": "Subject", "value": "Hi"}],
                    "parts": [{"mimeType": "text/plain", "body": {"data": body}}],
                },
            },
        )
    )
    msg = await GmailClient().read("TOKEN", "m1")
    assert "Full body here" in (msg.body or "")


@respx.mock
async def test_profile_email() -> None:
    respx.get("https://gmail.googleapis.com/gmail/v1/users/me/profile").mock(
        return_value=httpx.Response(200, json={"emailAddress": "me@x.com"})
    )
    assert await GmailClient().profile_email("TOKEN") == "me@x.com"
