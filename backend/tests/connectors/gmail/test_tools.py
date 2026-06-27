"""Gmail tools call the live API with the OAuth token (respx)."""

from __future__ import annotations

import httpx
import respx

from pragya_assistant.connectors.base import AccountAuth, ConnectorContext
from pragya_assistant.connectors.gmail.connector import GmailConnector

MSGS = "https://gmail.googleapis.com/gmail/v1/users/me/messages"


def _ctx() -> ConnectorContext:
    async def _token() -> str:
        return "TOKEN"

    return ConnectorContext(key="gmail", config={}, access_token=_token)


def _tools() -> dict[str, object]:
    return {t.name: t for t in GmailConnector().build_tools(_ctx())}


@respx.mock
async def test_unread_lists_messages() -> None:
    respx.get(MSGS).mock(return_value=httpx.Response(200, json={"messages": [{"id": "m1"}]}))
    respx.get(f"{MSGS}/m1").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m1",
                "snippet": "ping",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "boss@x.com"},
                        {"name": "Subject", "value": "Standup"},
                    ]
                },
            },
        )
    )
    out = await _tools()["gmail_unread"].handler({})  # type: ignore[attr-defined]
    assert "boss@x.com" in out
    assert "Standup" in out
    assert "id:m1" in out


async def test_search_requires_query() -> None:
    out = await _tools()["gmail_search"].handler({})  # type: ignore[attr-defined]
    assert "query" in out.lower()


@respx.mock
async def test_read_returns_body() -> None:
    import base64

    body = base64.urlsafe_b64encode(b"the full message").decode().rstrip("=")
    respx.get(f"{MSGS}/m9").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "m9",
                "snippet": "...",
                "payload": {
                    "headers": [{"name": "Subject", "value": "Report"}],
                    "parts": [{"mimeType": "text/plain", "body": {"data": body}}],
                },
            },
        )
    )
    out = await _tools()["gmail_read"].handler({"id": "m9"})  # type: ignore[attr-defined]
    assert "Report" in out
    assert "the full message" in out


@respx.mock
async def test_unread_aggregates_across_accounts() -> None:
    """Two linked accounts → merged results, each block labeled by account."""

    def list_by_token(request: httpx.Request) -> httpx.Response:
        mid = "w1" if "WORK" in request.headers["Authorization"] else "h1"
        return httpx.Response(200, json={"messages": [{"id": mid}]})

    def get_by_id(request: httpx.Request) -> httpx.Response:
        mid = request.url.path.rsplit("/", 1)[-1]
        sender = "boss@work.com" if mid == "w1" else "mom@home.com"
        return httpx.Response(
            200,
            json={
                "id": mid,
                "snippet": "hi",
                "payload": {"headers": [{"name": "From", "value": sender}]},
            },
        )

    respx.get(MSGS).mock(side_effect=list_by_token)
    respx.route(method="GET", url__regex=r".*/messages/\w+").mock(side_effect=get_by_id)

    async def work_token() -> str:
        return "TOK-WORK"

    async def home_token() -> str:
        return "TOK-HOME"

    ctx = ConnectorContext(
        key="gmail",
        config={},
        accounts=(
            AccountAuth(account_id=1, label="work@x.com", access_token=work_token),
            AccountAuth(account_id=2, label="home@x.com", access_token=home_token),
        ),
    )
    tools = {t.name: t for t in GmailConnector().build_tools(ctx)}
    out = await tools["gmail_unread"].handler({})  # type: ignore[attr-defined]
    assert "▸ work@x.com" in out and "▸ home@x.com" in out
    assert "boss@work.com" in out and "mom@home.com" in out
