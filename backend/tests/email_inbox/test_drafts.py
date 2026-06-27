from email import message_from_bytes, policy

from pragya_assistant.email_inbox.drafts import build_new, build_reply


def _parsed(raw: bytes):  # type: ignore[no-untyped-def]
    return message_from_bytes(raw, policy=policy.default)


def test_build_reply_sets_re_and_threading() -> None:
    raw = build_reply(
        from_addr="me@x.com",
        to_addr="alice@x.com",
        orig_subject="Lunch?",
        orig_message_id="<abc@x.com>",
        orig_references="<root@x.com>",
        reply_text="Sure!",
    )
    m = _parsed(raw)
    assert m["Subject"] == "Re: Lunch?"
    assert m["In-Reply-To"] == "<abc@x.com>"
    assert m["References"] == "<root@x.com> <abc@x.com>"
    assert m["To"] == "alice@x.com" and m["From"] == "me@x.com"
    assert "Sure!" in m.get_content()


def test_build_reply_no_double_re_prefix() -> None:
    raw = build_reply(
        from_addr="me",
        to_addr="a",
        orig_subject="Re: Hi",
        orig_message_id="",
        orig_references="",
        reply_text="x",
    )
    assert _parsed(raw)["Subject"] == "Re: Hi"


def test_build_new_message() -> None:
    raw = build_new(from_addr="me@x.com", to_addr="bob@x.com", subject="Hello", body="Hi Bob")
    m = _parsed(raw)
    assert m["To"] == "bob@x.com" and m["Subject"] == "Hello" and m["From"] == "me@x.com"
    assert "In-Reply-To" not in m
    assert "Hi Bob" in m.get_content()
