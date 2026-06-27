"""A thin async Gmail REST client — read-only (list / get / profile)."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


@dataclass(frozen=True)
class EmailMessage:
    id: str
    sender: str
    subject: str
    date: str
    snippet: str
    body: str | None = None


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _header(headers: list[dict[str, Any]], name: str) -> str:
    for h in headers:
        if str(h.get("name", "")).lower() == name.lower():
            return str(h.get("value", ""))
    return ""


def _decode_b64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body(payload: dict[str, Any]) -> str:
    """Best-effort plain-text body from a Gmail payload (recurse into parts)."""
    if payload.get("mimeType", "").startswith("text/plain"):
        data = payload.get("body", {}).get("data")
        if data:
            return _decode_b64url(data)
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def _to_message(data: dict[str, Any], *, with_body: bool) -> EmailMessage:
    payload = data.get("payload", {})
    headers = payload.get("headers", [])
    return EmailMessage(
        id=str(data.get("id", "")),
        sender=_header(headers, "From"),
        subject=_header(headers, "Subject") or "(no subject)",
        date=_header(headers, "Date"),
        snippet=str(data.get("snippet", "")),
        body=_extract_body(payload) if with_body else None,
    )


class GmailClient:
    async def _get(
        self, token: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{_BASE}{path}", headers=_auth(token), params=params)
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            return payload

    async def list_ids(self, token: str, *, query: str, max_results: int) -> list[str]:
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        data = await self._get(token, "/messages", params)
        return [str(m["id"]) for m in data.get("messages", [])]

    async def recent(self, token: str, *, query: str, max_results: int) -> list[EmailMessage]:
        ids = await self.list_ids(token, query=query, max_results=max_results)
        out: list[EmailMessage] = []
        for message_id in ids:
            data = await self._get(
                token,
                f"/messages/{message_id}",
                {"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            out.append(_to_message(data, with_body=False))
        return out

    async def read(self, token: str, message_id: str) -> EmailMessage:
        data = await self._get(token, f"/messages/{message_id}", {"format": "full"})
        return _to_message(data, with_body=True)

    async def profile_email(self, token: str) -> str:
        data = await self._get(token, "/profile")
        return str(data.get("emailAddress", ""))
