"""Live Gmail/IMAP adapter (sync; wrap in a thread). Read-only + draft-only.

INBOX is opened read-only (EXAMINE) and every fetch passes ``mark_seen=False`` —
two independent guarantees that reading never mutates the mailbox. The only write
is saving a ``\\Draft`` to Drafts; it never deletes/moves messages and never
sends mail.
"""

from __future__ import annotations

from typing import Any

from imap_tools import AND, MailBox, MailMessageFlags

from pragya_assistant.email_inbox.attachments import extract_attachment
from pragya_assistant.email_inbox.models import Attachment, InboxMessage
from pragya_assistant.email_inbox.parse import html_to_text

_DRAFTS = "[Gmail]/Drafts"


class ImapToolsClient:
    def __init__(self, *, host: str, address: str, app_password: str) -> None:
        self._host = host
        self._address = address
        self._password = app_password

    def _box(self) -> Any:
        return MailBox(self._host).login(self._address, self._password)

    def list_recent(self, n: int) -> list[InboxMessage]:
        with self._box() as box:
            box.folder.set("INBOX", readonly=True)
            return [
                _to_message(m) for m in box.fetch(reverse=True, limit=n, mark_seen=False, bulk=True)
            ]

    def search(self, query: str, n: int) -> list[InboxMessage]:
        # Gmail's native search (X-GM-RAW) over All Mail, opened read-only.
        safe = query.replace('"', " ").strip()
        with self._box() as box:
            box.folder.set("[Gmail]/All Mail", readonly=True)
            criteria = f'X-GM-RAW "{safe}"'
            return [
                _to_message(m)
                for m in box.fetch(criteria, reverse=True, limit=n, mark_seen=False, bulk=True)
            ]

    def unread(self, n: int) -> list[InboxMessage]:
        with self._box() as box:
            box.folder.set("INBOX", readonly=True)
            return [
                _to_message(m)
                for m in box.fetch(
                    AND(seen=False), reverse=True, limit=n, mark_seen=False, bulk=True
                )
            ]

    def get(self, message_id: str) -> InboxMessage | None:
        # Find by RFC822 Message-ID across ALL mail (folder-agnostic), so an email
        # surfaced by search/list is readable wherever it lives. Read attachments.
        mid = message_id.strip().strip("<>").replace('"', " ")
        with self._box() as box:
            box.folder.set("[Gmail]/All Mail", readonly=True)
            found = list(box.fetch(f'X-GM-RAW "rfc822msgid:{mid}"', mark_seen=False, limit=1))
            return _to_message(found[0], with_attachments=True) if found else None

    def create_draft(self, raw: bytes) -> None:
        with self._box() as box:
            box.append(raw, _DRAFTS, flag_set=[MailMessageFlags.DRAFT])


def _to_message(m: Any, *, with_attachments: bool = False) -> InboxMessage:
    text = (m.text or "").strip() or html_to_text(m.html or "")

    def header(name: str) -> str:
        value = m.headers.get(name)
        return value[0] if isinstance(value, tuple) and value else ""

    attachments: tuple[Attachment, ...] = ()
    if with_attachments:
        attachments = tuple(
            Attachment(
                filename=a.filename or "",
                content_type=a.content_type or "",
                text=extract_attachment(a.filename or "", a.content_type or "", a.payload),
            )
            for a in (m.attachments or [])
        )

    return InboxMessage(
        uid=str(m.uid or ""),
        from_=m.from_ or "",
        subject=m.subject or "",
        date=m.date,
        message_id=header("message-id"),
        references=header("references"),
        text=text,
        attachments=attachments,
    )
