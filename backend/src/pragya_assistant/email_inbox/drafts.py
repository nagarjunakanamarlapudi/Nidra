"""Build a reply MIME (bytes) for saving as a draft. No sending happens here."""

from __future__ import annotations

from email.message import EmailMessage


def build_reply(
    *,
    from_addr: str,
    to_addr: str,
    orig_subject: str,
    orig_message_id: str,
    orig_references: str,
    reply_text: str,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    subject = orig_subject or ""
    msg["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    if orig_message_id:
        msg["In-Reply-To"] = orig_message_id
        msg["References"] = " ".join(p for p in (orig_references, orig_message_id) if p)
    msg.set_content(reply_text)
    return msg.as_bytes()


def build_new(*, from_addr: str, to_addr: str, subject: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    return msg.as_bytes()
