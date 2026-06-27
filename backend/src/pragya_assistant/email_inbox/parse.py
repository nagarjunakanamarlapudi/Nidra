"""Parse raw RFC822 bytes into an InboxMessage (stdlib email, modern policy)."""

from __future__ import annotations

import datetime as dt
import email
import re
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from pragya_assistant.email_inbox.models import InboxMessage


def parse_eml(raw: bytes, *, uid: str = "") -> InboxMessage:
    msg = email.message_from_bytes(raw, policy=policy.default)
    return InboxMessage(
        uid=uid,
        from_=str(msg.get("From", "")),
        subject=str(msg.get("Subject", "")),
        date=_parse_date(msg.get("Date")),
        message_id=str(msg.get("Message-ID", "")),
        references=str(msg.get("References", "")),
        text=_body_text(msg),
    )


def html_to_text(html: str) -> str:
    """Crude HTML→text: drop script/style, strip tags, collapse whitespace."""
    no_blocks = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"<[^>]+>", " ", no_blocks).strip()


def _body_text(msg: EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content: str = body.get_content()
    if body.get_content_type() == "text/html":
        return html_to_text(content)
    return content.strip()


def _parse_date(value: object) -> dt.datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
