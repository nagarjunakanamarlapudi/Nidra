"""Email tools — model-facing. Read + draft only; no send/delete tool exists."""

from __future__ import annotations

from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.email_inbox.models import InboxMessage
from pragya_assistant.email_inbox.service import EmailService


def build_email_tools(service: EmailService) -> list[Tool]:
    async def list_emails(args: dict[str, Any]) -> str:
        messages = await service.list_recent(int(args.get("limit", 10)))
        if not messages:
            return "Inbox is empty."
        return "\n".join(_line(m) for m in messages)

    async def read_email(args: dict[str, Any]) -> str:
        message = await service.get(str(args["message_id"]))
        if message is None:
            return f"No email found with id {args['message_id']}."
        parts = [
            f"From: {message.from_}\nSubject: {message.subject}\n"
            f"Date: {message.date}\n\n{message.text}"
        ]
        for att in message.attachments:
            parts.append(f"\n--- Attachment: {att.filename} ({att.content_type}) ---\n{att.text}")
        return "\n".join(parts)

    async def search_emails(args: dict[str, Any]) -> str:
        messages = await service.search(str(args["query"]), int(args.get("limit", 10)))
        if not messages:
            return "No matching emails."
        return "\n".join(_line(m) for m in messages)

    async def unread_emails(args: dict[str, Any]) -> str:
        messages = await service.unread(int(args.get("limit", 10)))
        if not messages:
            return "No unread emails."
        return "\n".join(_line(m) for m in messages)

    async def draft_reply(args: dict[str, Any]) -> str:
        original = await service.draft_reply(str(args["message_id"]), str(args["reply_text"]))
        if original is None:
            return f"No email found with id {args['message_id']}."
        return f"Draft reply saved to '{original.subject}' (not sent — review it in Gmail Drafts)."

    async def draft_email(args: dict[str, Any]) -> str:
        await service.draft_new(str(args["to"]), str(args["subject"]), str(args["body"]))
        return f"Draft to {args['to']} saved (not sent — review it in Gmail Drafts)."

    return [
        Tool(
            name="list_emails",
            description="List recent inbox emails: id (Message-ID), sender, subject, snippet.",
            input_schema=_object({"limit": _integer("How many (default 10)")}, []),
            handler=list_emails,
        ),
        Tool(
            name="search_emails",
            description=(
                "Search all mail with a Gmail query (e.g. 'from:bank subject:statement', "
                "'newer_than:7d invoice', 'has:attachment')."
            ),
            input_schema=_object(
                {
                    "query": _string("Gmail search query"),
                    "limit": _integer("Max results (default 10)"),
                },
                ["query"],
            ),
            handler=search_emails,
        ),
        Tool(
            name="unread_emails",
            description="List recent UNREAD inbox emails (reading does not mark them read).",
            input_schema=_object({"limit": _integer("How many (default 10)")}, []),
            handler=unread_emails,
        ),
        Tool(
            name="read_email",
            description=(
                "Read one email's full body AND any attachment text (PDF/Word/Excel/CSV) "
                "by its id (the Message-ID from list/search)."
            ),
            input_schema=_object(
                {"message_id": _string("The email's Message-ID from list/search")},
                ["message_id"],
            ),
            handler=read_email,
        ),
        Tool(
            name="draft_reply",
            description="Save a DRAFT reply (never sends). Give the message_id + reply body.",
            input_schema=_object(
                {
                    "message_id": _string("The email's Message-ID from list/search"),
                    "reply_text": _string("Your reply body"),
                },
                ["message_id", "reply_text"],
            ),
            handler=draft_reply,
        ),
        Tool(
            name="draft_email",
            description="Compose a NEW draft email (never sends). Give to, subject, body.",
            input_schema=_object(
                {
                    "to": _string("Recipient address"),
                    "subject": _string("Subject"),
                    "body": _string("Email body"),
                },
                ["to", "subject", "body"],
            ),
            handler=draft_email,
        ),
    ]


def _line(m: InboxMessage) -> str:
    return f"- [{m.message_id}] {m.from_} — {m.subject} · {m.snippet}"


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
