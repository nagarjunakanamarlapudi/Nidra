import pathlib


def test_no_transfer_endpoints() -> None:
    pkg = pathlib.Path(__file__).resolve().parents[2] / "src/pragya_assistant/finance"
    src = "\n".join(p.read_text() for p in pkg.glob("*.py"))
    forbidden_terms = (
        "transfer_create",
        "transfer_authorization",
        "/transfer",
        "payment_initiation",
    )
    for forbidden in forbidden_terms:
        assert forbidden not in src, f"finance must never reference {forbidden!r}"
