import datetime as dt

from pragya_assistant.agent.tools import ToolHandler
from pragya_assistant.email_inbox.models import Attachment, InboxMessage
from pragya_assistant.email_inbox.service import EmailService
from pragya_assistant.email_inbox.tools import build_email_tools


class FakeInbox:
    """In-memory InboxClient — read + record drafts; never sends/deletes."""

    def __init__(self, messages: list[InboxMessage]) -> None:
        self._messages = {m.message_id: m for m in messages}
        self.drafts: list[bytes] = []

    def list_recent(self, n: int) -> list[InboxMessage]:
        return list(self._messages.values())[:n]

    def search(self, query: str, n: int) -> list[InboxMessage]:
        q = query.lower()
        hits = [
            m
            for m in self._messages.values()
            if q in (m.subject + " " + m.from_ + " " + m.text).lower()
        ]
        return hits[:n]

    def unread(self, n: int) -> list[InboxMessage]:
        return list(self._messages.values())[:n]

    def get(self, message_id: str) -> InboxMessage | None:
        return self._messages.get(message_id)

    def create_draft(self, raw: bytes) -> None:
        self.drafts.append(raw)


def _msg(
    uid: str,
    frm: str = "Alice <a@x.com>",
    subject: str = "Hi",
    text: str = "hello",
    attachments: tuple[Attachment, ...] = (),
) -> InboxMessage:
    return InboxMessage(
        uid=uid,
        from_=frm,
        subject=subject,
        date=dt.datetime(2026, 6, 22, 10, 0),
        message_id=f"<{uid}@x.com>",
        references="",
        text=text,
        attachments=attachments,
    )


def _handler(tools: list, name: str) -> ToolHandler:
    return next(t for t in tools if t.name == name).handler


async def test_list_and_read() -> None:
    inbox = FakeInbox([_msg("5", subject="Lunch?", text="lunch tomorrow")])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))

    listed = await _handler(tools, "list_emails")({})
    assert "<5@x.com>" in listed and "Lunch?" in listed

    read = await _handler(tools, "read_email")({"message_id": "<5@x.com>"})
    assert "lunch tomorrow" in read


async def test_read_email_includes_attachment_text() -> None:
    bill = Attachment(filename="bill.pdf", content_type="application/pdf", text="Amount due: $500")
    inbox = FakeInbox([_msg("9", subject="Your bill", attachments=(bill,))])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))
    read = await _handler(tools, "read_email")({"message_id": "<9@x.com>"})
    assert "bill.pdf" in read and "Amount due: $500" in read


async def test_draft_reply_saves_draft_never_sends() -> None:
    inbox = FakeInbox([_msg("5", frm="Alice <a@x.com>", subject="Lunch?")])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))

    out = await _handler(tools, "draft_reply")(
        {"message_id": "<5@x.com>", "reply_text": "Sure, noon works"}
    )
    assert "Draft" in out and len(inbox.drafts) == 1
    raw = inbox.drafts[0].decode()
    assert "Re: Lunch?" in raw and "Sure, noon works" in raw and "a@x.com" in raw


async def test_draft_reply_missing_message() -> None:
    inbox = FakeInbox([])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))
    out = await _handler(tools, "draft_reply")({"message_id": "<404@x.com>", "reply_text": "x"})
    assert "No email" in out and inbox.drafts == []


async def test_search_emails() -> None:
    inbox = FakeInbox(
        [_msg("5", subject="Invoice #42", text="payment due"), _msg("6", subject="Hi")]
    )
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))
    out = await _handler(tools, "search_emails")({"query": "invoice"})
    assert "Invoice #42" in out and "<6@x.com>" not in out


async def test_unread_emails() -> None:
    inbox = FakeInbox([_msg("5", subject="Unseen")])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))
    assert "Unseen" in await _handler(tools, "unread_emails")({})


async def test_draft_email_new_message() -> None:
    inbox = FakeInbox([])
    tools = build_email_tools(EmailService(inbox, address="me@x.com"))
    out = await _handler(tools, "draft_email")(
        {"to": "bob@x.com", "subject": "Hello", "body": "Just saying hi"}
    )
    assert "Draft" in out and len(inbox.drafts) == 1
    raw = inbox.drafts[0].decode()
    assert "To: bob@x.com" in raw and "Subject: Hello" in raw and "Just saying hi" in raw


def test_only_read_and_draft_tools_exist() -> None:
    tools = build_email_tools(EmailService(FakeInbox([]), address="me@x.com"))
    names = {t.name for t in tools}
    assert names == {
        "list_emails",
        "search_emails",
        "unread_emails",
        "read_email",
        "draft_reply",
        "draft_email",
    }
    assert not any(("send" in n) or ("delete" in n) for n in names)
