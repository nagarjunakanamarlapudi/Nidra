from pragya_assistant.email_inbox.attachments import extract_attachment


def test_extract_csv() -> None:
    out = extract_attachment("bill.csv", "text/csv", b"item,amount\nrent,1500\n")
    assert "rent" in out and "1500" in out


def test_extract_html() -> None:
    out = extract_attachment("invoice.html", "text/html", b"<h1>Invoice</h1><p>Total due: 500</p>")
    assert "Invoice" in out and "500" in out


def test_unreadable_returns_marker_not_crash() -> None:
    # Garbage bytes / unknown type must never raise — extraction is best-effort.
    out = extract_attachment("mystery.xyz", "application/octet-stream", b"\x00\x01\x02not-a-doc")
    assert isinstance(out, str) and out != ""
