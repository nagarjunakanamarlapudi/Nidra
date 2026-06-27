import pathlib


def test_email_module_has_no_send_or_delete_primitives() -> None:
    pkg = pathlib.Path(__file__).resolve().parents[2] / "src/pragya_assistant/email_inbox"
    source = "\n".join(p.read_text() for p in pkg.glob("*.py"))
    for forbidden in ("smtplib", "expunge", "EXPUNGE", "\\Deleted"):
        assert forbidden not in source, f"email_inbox must never reference {forbidden!r}"
