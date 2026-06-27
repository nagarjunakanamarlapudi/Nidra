"""Async email service over a (sync) InboxClient. Read + draft only."""

from __future__ import annotations

import asyncio

from pragya_assistant.config import Settings
from pragya_assistant.email_inbox.client import ImapToolsClient
from pragya_assistant.email_inbox.drafts import build_new, build_reply
from pragya_assistant.email_inbox.models import InboxClient, InboxMessage


class EmailService:
    def __init__(self, client: InboxClient, *, address: str) -> None:
        self._client = client
        self._address = address  # the user's own address — the From on drafts

    async def list_recent(self, n: int = 10) -> list[InboxMessage]:
        return await asyncio.to_thread(self._client.list_recent, n)

    async def search(self, query: str, n: int = 10) -> list[InboxMessage]:
        return await asyncio.to_thread(self._client.search, query, n)

    async def unread(self, n: int = 10) -> list[InboxMessage]:
        return await asyncio.to_thread(self._client.unread, n)

    async def get(self, message_id: str) -> InboxMessage | None:
        return await asyncio.to_thread(self._client.get, message_id)

    async def draft_reply(self, message_id: str, reply_text: str) -> InboxMessage | None:
        original = await self.get(message_id)
        if original is None:
            return None
        raw = build_reply(
            from_addr=self._address,
            to_addr=original.from_,
            orig_subject=original.subject,
            orig_message_id=original.message_id,
            orig_references=original.references,
            reply_text=reply_text,
        )
        await asyncio.to_thread(self._client.create_draft, raw)
        return original

    async def draft_new(self, to_addr: str, subject: str, body: str) -> None:
        raw = build_new(from_addr=self._address, to_addr=to_addr, subject=subject, body=body)
        await asyncio.to_thread(self._client.create_draft, raw)


def build_email_service(settings: Settings) -> EmailService | None:
    """Build the live email service, or None when not configured."""
    if not (settings.email_address and settings.email_app_password):
        return None
    client = ImapToolsClient(
        host=settings.email_imap_host,
        address=settings.email_address,
        app_password=settings.email_app_password,
    )
    return EmailService(client, address=settings.email_address)
