import datetime as dt
from decimal import Decimal

from pragya_assistant.finance.client import LinkResult, RawAccount, RawTxn, SyncPage


def test_value_types_construct() -> None:
    link = LinkResult(access_token="enc", item_id="it", institution_name="Chase")
    acct = RawAccount(
        plaid_account_id="ac",
        name="Checking",
        official_name=None,
        type="depository",
        subtype="checking",
        mask="1234",
        current_balance=Decimal("10"),
        available_balance=None,
        iso_currency="USD",
    )
    page = SyncPage(
        added=[
            RawTxn("tx", "ac", dt.date(2026, 6, 1), "Coffee", None, Decimal("4"), "Food", False),
        ],
        modified=[],
        removed=[],
        next_cursor="c1",
        has_more=False,
    )
    assert link.institution_name == "Chase"
    assert acct.current_balance == Decimal("10")
    assert page.added[0].name == "Coffee"
