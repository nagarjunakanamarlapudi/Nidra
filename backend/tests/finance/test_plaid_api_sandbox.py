"""Live Plaid Sandbox integration test for the PlaidApiClient adapter.

Runs ONLY when a dedicated PLAID_SANDBOX_SECRET is set (separate from the
app's PLAID_SECRET, which may hold production creds). This keeps the test
from running against a production secret with env="sandbox" (which Plaid
rejects). Exercises the real plaid-python API end-to-end against Sandbox.
"""

import os

import pytest

from pragya_assistant.finance.plaid_api import PlaidApiClient

# Capture at collection time — the autouse env-clearing fixture in conftest scrubs
# PLAID_* before each test body runs, so we can't read os.environ inside the test.
_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
_SANDBOX_SECRET = os.getenv("PLAID_SANDBOX_SECRET")

pytestmark = pytest.mark.skipif(
    not (_CLIENT_ID and _SANDBOX_SECRET),
    reason="Plaid Sandbox creds not set (set PLAID_CLIENT_ID + PLAID_SANDBOX_SECRET to run)",
)


def _client() -> PlaidApiClient:
    assert _CLIENT_ID and _SANDBOX_SECRET
    return PlaidApiClient(client_id=_CLIENT_ID, secret=_SANDBOX_SECRET, env="sandbox")


def test_sandbox_link_exchange_accounts_sync() -> None:
    client = _client()

    public_token = client.sandbox_public_token()
    link = client.exchange_public_token(public_token)
    assert link.access_token.startswith("access-sandbox")
    assert link.item_id

    accounts = client.get_accounts(link.access_token)
    assert accounts, "expected at least one account"
    # account.type must be the bare enum value (net_worth keys off it)
    assert accounts[0].type in {"depository", "credit", "loan", "investment", "other"}
    assert any(a.current_balance is not None for a in accounts)

    page = client.sync_transactions(link.access_token, None)
    assert page.next_cursor
    # added transactions (if any) must carry the load-bearing fields
    for txn in page.added:
        assert txn.plaid_txn_id and txn.account_plaid_id
        assert txn.date is not None


def test_sandbox_holdings_and_liabilities_shapes() -> None:
    # These products may be empty for the default institution, but the adapter's
    # parsing paths must not raise on the real response shapes.
    client = _client()
    link = client.exchange_public_token(client.sandbox_public_token())
    assert isinstance(client.get_holdings(link.access_token), list)
    assert isinstance(client.get_liabilities(link.access_token), list)
