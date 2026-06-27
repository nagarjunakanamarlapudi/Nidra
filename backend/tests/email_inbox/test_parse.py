from email.message import EmailMessage

from pragya_assistant.email_inbox.parse import html_to_text, parse_eml


def _plain() -> bytes:
    m = EmailMessage()
    m["From"] = "Alice <alice@example.com>"
    m["To"] = "me@example.com"
    m["Subject"] = "Lunch?"
    m["Date"] = "Mon, 22 Jun 2026 10:00:00 -0700"
    m["Message-ID"] = "<abc@example.com>"
    m.set_content("Hey, lunch tomorrow?\n")
    return m.as_bytes()


def _html_only() -> bytes:
    m = EmailMessage()
    m["From"] = "Bob <bob@example.com>"
    m["Subject"] = "HTML only"
    m.set_content("<html><body><p>Hello <b>world</b></p></body></html>", subtype="html")
    return m.as_bytes()


def test_parse_plain() -> None:
    msg = parse_eml(_plain(), uid="5")
    assert msg.uid == "5"
    assert msg.from_ == "Alice <alice@example.com>"
    assert msg.subject == "Lunch?"
    assert "lunch tomorrow" in msg.text.lower()
    assert msg.message_id == "<abc@example.com>"
    assert msg.date is not None and msg.date.year == 2026


def test_parse_html_only_converts_to_text() -> None:
    msg = parse_eml(_html_only())
    assert "Hello" in msg.text and "world" in msg.text
    assert "<" not in msg.text


def test_html_to_text_strips_tags_and_scripts() -> None:
    out = html_to_text("<p>Hi <b>there</b></p><script>evil()</script>")
    assert "Hi" in out and "there" in out
    assert "evil" not in out and "<" not in out


def test_snippet_truncates() -> None:
    m = EmailMessage()
    m["From"] = "x"
    m["Subject"] = "s"
    m.set_content("word " * 100)
    assert len(parse_eml(m.as_bytes()).snippet) <= 200
