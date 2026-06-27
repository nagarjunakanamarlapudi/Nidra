"""Email value types + the read/draft-only client interface."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    text: str  # extracted text (PDF/Office/etc.), or a marker if unreadable


@dataclass(frozen=True)
class InboxMessage:
    uid: str
    from_: str
    subject: str
    date: dt.datetime | None
    message_id: str
    references: str
    text: str
    attachments: tuple[Attachment, ...] = ()

    @property
    def snippet(self) -> str:
        return " ".join(self.text.split())[:200]


class InboxClient(Protocol):
    """Read + draft only — deliberately NO send/delete on the interface, so the
    agent (and the type system) cannot send or delete mail."""

    def list_recent(self, n: int) -> list[InboxMessage]: ...

    def search(self, query: str, n: int) -> list[InboxMessage]: ...

    def unread(self, n: int) -> list[InboxMessage]: ...

    def get(self, message_id: str) -> InboxMessage | None: ...

    def create_draft(self, raw: bytes) -> None: ...
