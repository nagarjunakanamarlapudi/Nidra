import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.crypto import encrypt_secret
from pragya_assistant.finance.client import (
    LinkResult,
    RawAccount,
    RawHolding,
    RawInvestmentTxn,
    RawTxn,
    SyncPage,
)
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.store import FinanceStore

KEY = "x" * 16


class FakePlaid:
    def __init__(self) -> None:
        self.exchanged: str | None = None
        self._cursors: list[str | None] = []
        self.removed_tokens: list[str] = []
        self.investment_txn_calls: list = []

    def create_link_token(self) -> str:
        return "link-sandbox-tok"

    def exchange_public_token(self, public_token: str) -> LinkResult:
        self.exchanged = public_token
        return LinkResult(access_token="access-sandbox-1", item_id="it_1", institution_name="Chase")

    def get_accounts(self, access_token: str) -> list[RawAccount]:
        return [
            RawAccount(
                "ac1", "Checking", None, "depository", "checking", "1", Decimal("500"), None, "USD"
            )
        ]

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        self._cursors.append(cursor)
        if cursor is None:
            return SyncPage(
                added=[
                    RawTxn(
                        "t1",
                        "ac1",
                        dt.date(2026, 6, 1),
                        "Coffee",
                        None,
                        Decimal("4"),
                        "Food",
                        False,
                    )
                ],
                modified=[],
                removed=[],
                next_cursor="c1",
                has_more=True,
            )
        return SyncPage(added=[], modified=[], removed=[], next_cursor="c2", has_more=False)

    def get_institution(self, access_token: str) -> tuple[str, str | None, str | None]:
        return "Chase", None, None

    def get_holdings(self, access_token: str) -> list[RawHolding]:
        return [
            RawHolding(
                account_plaid_id="ac1",
                security_name="Acme Corp",
                ticker="ACME",
                quantity=Decimal("10"),
                price=Decimal("50"),
                value=Decimal("500"),
                iso_currency="USD",
            )
        ]

    def get_liabilities(self, access_token: str) -> list:
        return []

    def get_investment_transactions(
        self,
        access_token: str,
        start_date,
        end_date,
    ) -> list[RawInvestmentTxn]:
        self.investment_txn_calls.append((access_token, start_date, end_date))
        return [
            RawInvestmentTxn(
                account_plaid_id="ac1",
                plaid_investment_txn_id="inv_t1",
                security_id="sec_ACME",
                ticker="ACME",
                name="Buy ACME",
                type="buy",
                subtype=None,
                quantity=Decimal("10"),
                price=Decimal("50"),
                amount=Decimal("500"),
                fees=None,
                date=dt.date(2026, 1, 15),
            )
        ]

    def remove_item(self, access_token: str) -> None:
        self.removed_tokens.append(access_token)


async def test_backfill_institutions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    await store.save_item("Connected bank", encrypt_secret("access-sandbox-1", KEY), "it_1")
    count = await svc.backfill_institutions()
    assert count == 1
    items = await store.list_items()
    assert items[0].institution_name == "Chase"
    # logo and color are None (FakePlaid returns None) — that is acceptable
    assert items[0].institution_logo is None
    assert items[0].institution_color is None


async def test_link_then_sync(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    name = await svc.link("public-sandbox-tok")
    assert name == "Chase" and fake.exchanged == "public-sandbox-tok"

    # token persisted ENCRYPTED, not in plaintext
    items = await store.list_items()
    assert items[0].access_token != "access-sandbox-1"
    assert items[0].institution_logo is None
    # institution color is None (FakePlaid returns None)
    assert items[0].institution_color is None

    synced = await svc.sync()
    assert synced == 1
    # link() auto-synced: [None, "c1"]; sync() resumes from "c2" (stored cursor): ["c2"]
    assert fake._cursors == [None, "c1", "c2"]
    items_after = await store.list_items()
    assert items_after[0].transactions_cursor == "c2"
    balances = await svc.account_balances()
    assert balances[0].current_balance == Decimal("500")


async def test_link_auto_syncs_holdings_and_transactions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """link() must immediately sync transactions and holdings — no manual sync needed."""
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    await svc.link("public-sandbox-tok")

    # Transactions were synced during link (cursor pages were visited).
    assert fake._cursors == [None, "c1"], "sync_transactions should be called during link"

    # The transaction from FakePlaid should be persisted.
    txns = await store.search_transactions(None, None, None, limit=10)
    assert len(txns) == 1, "transaction should be persisted after link"
    assert txns[0].name == "Coffee"

    # The holding from FakePlaid should be persisted.
    holdings = await store.all_holdings()
    assert len(holdings) == 1, "holding should be persisted after link"
    assert holdings[0].ticker == "ACME"
    assert holdings[0].security_name == "Acme Corp"
    assert holdings[0].value == Decimal("500")


async def test_remove_item_calls_plaid_and_deletes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """remove_item should call Plaid.remove_item AND delete the item from the store."""
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    # Link an item first so there is something to remove.
    await svc.link("public-sandbox-tok")
    items = await store.list_items()
    assert len(items) == 1
    item_id = items[0].id

    result = await svc.remove_item(item_id)

    assert result is True
    # Plaid adapter was called with the (decrypted) access token
    assert len(fake.removed_tokens) == 1
    assert fake.removed_tokens[0] == "access-sandbox-1"
    # Local item is gone
    assert await store.list_items() == []


async def test_remove_item_returns_false_when_not_found(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """remove_item on a non-existent item_id must return False, not raise."""
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    result = await svc.remove_item(99999)

    assert result is False
    assert fake.removed_tokens == []


async def test_sync_item_calls_investment_transactions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """_sync_item (called by link and sync) must call get_investment_transactions."""
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    await svc.link("public-sandbox-tok")

    # get_investment_transactions should have been called once during link
    assert len(fake.investment_txn_calls) == 1
    _, start, end = fake.investment_txn_calls[0]
    # start should be ~5 years ago, end should be today
    import datetime

    today = datetime.date.today()
    assert end == today
    assert (today - start).days > 365 * 4  # at least 4 years back

    # The investment transaction should be persisted
    accounts = await store.account_balances()
    acct_pk = accounts[0].id
    inv_txns = await store.investment_transactions_for_account(acct_pk)
    assert len(inv_txns) == 1
    assert inv_txns[0].ticker == "ACME"
