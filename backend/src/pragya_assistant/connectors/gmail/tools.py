"""Read-only Gmail tools — live calls, aggregated across all linked accounts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import ConnectorContext
from pragya_assistant.connectors.gmail.client import EmailMessage, GmailClient

_TokenGetter = Callable[[], Awaitable[str]]


def _account_list(ctx: ConnectorContext) -> list[tuple[str, _TokenGetter]]:
    """(label, token-getter) per connected account. Falls back to the single
    ctx.access_token (back-compat / single-account)."""
    if ctx.accounts:
        return [(a.label, a.access_token) for a in ctx.accounts]
    if ctx.access_token is not None:
        return [("", ctx.access_token)]
    return []


def build_gmail_tools(client: GmailClient, ctx: ConnectorContext) -> list[Tool]:
    accounts = _account_list(ctx)

    async def _gather(query: str, n: int, empty: str) -> str:
        if not accounts:
            return "No Gmail accounts connected."
        multi = len(accounts) > 1
        blocks: list[str] = []
        for label, get_token in accounts:
            msgs = await client.recent(await get_token(), query=query, max_results=n)
            if not msgs:
                continue
            body = _format_list(msgs)
            blocks.append(f"▸ {label}\n{body}" if multi and label else body)
        return "\n\n".join(blocks) if blocks else empty

    async def list_recent(args: dict[str, Any]) -> str:
        return await _gather("", int(args.get("n", 10)), "No recent emails.")

    async def search(args: dict[str, Any]) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "Provide a search query (Gmail search syntax, e.g. 'from:bank newer_than:7d')."
        return await _gather(query, int(args.get("n", 10)), f"No emails match {query!r}.")

    async def unread(args: dict[str, Any]) -> str:
        return await _gather("is:unread", int(args.get("n", 10)), "No unread emails.")

    async def read(args: dict[str, Any]) -> str:
        message_id = str(args.get("id", "")).strip()
        if not message_id:
            return "Provide a message id (the id:… from a list/search result)."
        # The id is per-mailbox; try each connected account until one has it.
        for _label, get_token in accounts:
            try:
                msg = await client.read(await get_token(), message_id)
            except Exception:  # noqa: BLE001, S112 — wrong account 404s; try the next
                continue
            return _format_full(msg)
        return "Message not found in any connected account."

    return [
        Tool(
            name="gmail_list_recent",
            description="List recent emails across all connected Google accounts (read-only).",
            input_schema=_object({"n": _integer("How many per account (default 10)")}),
            handler=list_recent,
        ),
        Tool(
            name="gmail_search",
            description="Search all connected inboxes with Gmail query syntax (read-only).",
            input_schema=_object(
                {
                    "query": _string("Gmail search, e.g. 'from:bank newer_than:7d'"),
                    "n": _integer("Max results per account"),
                },
                required=["query"],
            ),
            handler=search,
        ),
        Tool(
            name="gmail_unread",
            description="List unread emails across all connected accounts (read-only).",
            input_schema=_object({"n": _integer("How many per account (default 10)")}),
            handler=unread,
        ),
        Tool(
            name="gmail_read",
            description="Read one email's full body by id (read-only; searches all accounts).",
            input_schema=_object(
                {"id": _string("Message id from a list/search result")}, required=["id"]
            ),
            handler=read,
        ),
    ]


def _format_list(msgs: list[EmailMessage]) -> str:
    lines = []
    for m in msgs:
        lines.append(f"- {m.sender} — {m.subject}  ·  {m.date}  ·  id:{m.id}")
        if m.snippet:
            lines.append(f"    {m.snippet}")
    return "\n".join(lines)


def _format_full(m: EmailMessage) -> str:
    return (
        f"From: {m.sender}\nSubject: {m.subject}\nDate: {m.date}\n\n{m.body or m.snippet}".strip()
    )


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
