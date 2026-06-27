import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.finance.client import RawAccount, RawInvestmentTxn, RawTxn
from pragya_assistant.finance.store import FinanceStore
from pragya_assistant.memory.models import Transaction


def _acct(pid: str, name: str, bal: str, type_: str = "depository") -> RawAccount:
    return RawAccount(pid, name, None, type_, None, None, Decimal(bal), None, "USD")


def _txn(tid: str, acct: str, amount: str, cat: str, day: int) -> RawTxn:
    return RawTxn(tid, acct, dt.date(2026, 6, day), tid, None, Decimal(amount), cat, False)


async def test_upsert_accounts_and_balances(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100.00")])
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "150.00")])  # update, not dup
    balances = await store.account_balances()
    assert len(balances) == 1 and balances[0].current_balance == Decimal("150.00")


async def test_txn_sync_and_spending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100")])
    await store.apply_txn_sync(
        item_id,
        added=[
            _txn("t1", "ac1", "4.00", "Food", 1),
            _txn("t2", "ac1", "6.00", "Food", 2),
            _txn("t3", "ac1", "20.00", "Transport", 3),
        ],
        modified=[],
        removed=[],
    )
    spend = await store.spending_by_category(dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert spend["Food"] == Decimal("10.00") and spend["Transport"] == Decimal("20.00")
    await store.apply_txn_sync(item_id, added=[], modified=[], removed=["t1"])
    spend2 = await store.spending_by_category(dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert spend2["Food"] == Decimal("6.00")


async def test_get_cursor_missing_returns_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """get_cursor on a non-existent item_id must return None, not raise AttributeError."""
    store = FinanceStore(session_factory)
    result = await store.get_cursor(99999)
    assert result is None


async def test_net_worth_subtracts_debts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(
        item_id,
        [
            _acct("ac1", "Checking", "1000.00", "depository"),
            _acct("ac2", "Visa", "200.00", "credit"),
        ],
    )
    assert await store.net_worth() == Decimal("800")


async def test_apply_txn_sync_modified_updates(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100")])
    # Insert original transaction
    await store.apply_txn_sync(
        item_id,
        added=[_txn("t1", "ac1", "10.00", "Food", 1)],
        modified=[],
        removed=[],
    )
    # Modify same plaid_txn_id — should update, not duplicate
    await store.apply_txn_sync(
        item_id,
        added=[],
        modified=[_txn("t1", "ac1", "25.00", "Dining", 1)],
        removed=[],
    )
    txns = await store.search_transactions(None, None, None, limit=10)
    assert len(txns) == 1
    assert txns[0].amount == Decimal("25.00")
    assert txns[0].category == "Dining"


async def test_save_item_idempotent_on_relink(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Re-linking the same institution (same item_id) must NOT raise IntegrityError.

    Plaid returns the same item_id when a user re-links the same institution.
    save_item must be get-or-create by item_id: on collision, update access_token
    and return the existing row's id.
    """
    store = FinanceStore(session_factory)
    first_id = await store.save_item("Chase", "enc1", "it_1")
    # Second call: same item_id, new encrypted token — must not raise
    second_id = await store.save_item("Chase", "enc2", "it_1")

    assert first_id == second_id, "re-link must return the same DB id"
    items = await store.list_items()
    assert len(items) == 1, "re-link must not insert a duplicate row"
    assert items[0].access_token == "enc2", "access_token must be updated to the new value"


async def test_set_institution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Connected bank", "enc", "it_1")
    await store.set_institution(item_id, "Chase", "abc123base64logo", None)
    items = await store.list_items()
    assert items[0].institution_name == "Chase"
    assert items[0].institution_logo == "abc123base64logo"
    assert items[0].institution_color is None


async def test_set_institution_clears_logo_when_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Connected bank", "enc", "it_1")
    await store.set_institution(item_id, "Chase", None, None)
    items = await store.list_items()
    assert items[0].institution_name == "Chase"
    assert items[0].institution_logo is None


async def test_set_institution_stores_color(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Connected bank", "enc", "it_1")
    await store.set_institution(item_id, "Chase", None, "#095aa6")
    items = await store.list_items()
    assert items[0].institution_name == "Chase"
    assert items[0].institution_color == "#095aa6"


async def test_accounts_with_institution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """accounts_with_institution returns each account paired with institution name, logo, and color."""  # noqa: E501
    store = FinanceStore(session_factory)
    chase_id = await store.save_item("Chase", "enc1", "it_chase")
    bofa_id = await store.save_item("Bank of America", "enc2", "it_bofa")
    await store.set_institution(chase_id, "Chase", "chase_logo_b64", "#012169")
    await store.set_institution(bofa_id, "Bank of America", None, None)
    await store.upsert_accounts(chase_id, [_acct("ac1", "Checking", "610.92")])
    await store.upsert_accounts(bofa_id, [_acct("ac2", "Savings", "1000.00")])

    rows = await store.accounts_with_institution()
    assert len(rows) == 2

    # ordered by institution name, then account name: "Bank of America" < "Chase"
    (acct_bofa, inst_bofa, logo_bofa, color_bofa) = rows[0]
    (acct_chase, inst_chase, logo_chase, color_chase) = rows[1]

    assert inst_bofa == "Bank of America"
    assert logo_bofa is None
    assert color_bofa is None
    assert acct_bofa.name == "Savings"
    assert inst_chase == "Chase"
    assert logo_chase == "chase_logo_b64"
    assert color_chase == "#012169"
    assert acct_chase.name == "Checking"


async def test_delete_item_cascades(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """delete_item removes the PlaidItem and all child rows via DB cascade."""
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100")])
    await store.apply_txn_sync(
        item_id,
        added=[_txn("t1", "ac1", "4.00", "Food", 1)],
        modified=[],
        removed=[],
    )

    await store.delete_item(item_id)

    # PlaidItem gone
    assert await store.list_items() == []
    # Accounts gone
    assert await store.account_balances() == []
    # Transactions gone (DB cascade)
    async with session_factory() as s:
        txns = (await s.execute(select(Transaction))).scalars().all()
        assert list(txns) == []


async def test_transactions_for_account(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100")])
    await store.apply_txn_sync(
        item_id,
        added=[
            _txn("t1", "ac1", "4.00", "Food", 1),
            _txn("t2", "ac1", "6.00", "Food", 2),
            _txn("t3", "ac1", "20.00", "Transport", 3),
        ],
        modified=[],
        removed=[],
    )
    # get account PK
    accounts = await store.account_balances()
    acct_pk = accounts[0].id

    txns = await store.transactions_for_account(acct_pk, limit=100)
    # newest first
    assert len(txns) == 3
    assert txns[0].date == dt.date(2026, 6, 3)  # day=3 is newest
    assert txns[2].date == dt.date(2026, 6, 1)

    # limit respected
    top1 = await store.transactions_for_account(acct_pk, limit=1)
    assert len(top1) == 1
    assert top1[0].plaid_txn_id == "t3"


def _inv_txn(
    inv_txn_id: str,
    acct_plaid_id: str,
    security_id: str | None,
    ticker: str | None,
    amount: str,
    day: int,
) -> RawInvestmentTxn:
    return RawInvestmentTxn(
        account_plaid_id=acct_plaid_id,
        plaid_investment_txn_id=inv_txn_id,
        security_id=security_id,
        ticker=ticker,
        name=f"Trade {inv_txn_id}",
        type="buy",
        subtype=None,
        quantity=Decimal("1.000000"),
        price=Decimal(amount),
        amount=Decimal(amount),
        fees=None,
        date=dt.date(2026, 6, day),
    )


async def test_replace_investment_transactions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Fidelity", "enc", "it_fid")
    await store.upsert_accounts(item_id, [_acct("inv1", "Brokerage", "10000", "investment")])

    txns = [
        _inv_txn("it1", "inv1", "sec_AAPL", "AAPL", "185.00", 1),
        _inv_txn("it2", "inv1", "sec_MSFT", "MSFT", "420.00", 3),
    ]
    await store.replace_investment_transactions(item_id, txns)

    # per-account query — newest first (day=3 before day=1)
    accounts = await store.account_balances()
    acct_pk = accounts[0].id
    result = await store.investment_transactions_for_account(acct_pk)
    assert len(result) == 2
    assert result[0].date == dt.date(2026, 6, 3)  # newest first
    assert result[1].date == dt.date(2026, 6, 1)
    assert result[0].ticker == "MSFT"

    # per-security query
    sec_txns = await store.investment_transactions_for_security("sec_AAPL")
    assert len(sec_txns) == 1
    assert sec_txns[0].ticker == "AAPL"

    # replace is idempotent — re-inserting same data should not duplicate
    await store.replace_investment_transactions(item_id, txns)
    result2 = await store.investment_transactions_for_account(acct_pk)
    assert len(result2) == 2


async def test_investment_transactions_for_security_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    result = await store.investment_transactions_for_security("sec_UNKNOWN")
    assert result == []


async def test_replace_holdings_cost_basis_and_lots(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """cost_basis and lots round-trip through replace_holdings to the DB."""
    from pragya_assistant.finance.client import RawHolding

    store = FinanceStore(session_factory)
    item_id = await store.save_item("Fidelity", "enc", "it_fid")
    await store.upsert_accounts(item_id, [_acct("inv1", "Brokerage", "10000", "investment")])

    lots_data = [
        {"quantity": "5", "cost_basis": "100.00", "acquired_date": "2024-01-15"},
        {"quantity": "5", "cost_basis": "120.00", "acquired_date": None},
    ]
    holding = RawHolding(
        account_plaid_id="inv1",
        security_name="Apple Inc.",
        ticker="AAPL",
        quantity=Decimal("10"),
        price=Decimal("185.00"),
        value=Decimal("1850.00"),
        iso_currency="USD",
        cost_basis=Decimal("1100.00"),
        lots=lots_data,
    )
    await store.replace_holdings(item_id, [holding])

    all_h = await store.all_holdings()
    assert len(all_h) == 1
    h = all_h[0]
    assert h.cost_basis == Decimal("1100.00")
    assert h.lots is not None
    assert len(h.lots) == 2
    assert h.lots[0]["cost_basis"] == "100.00"
    assert h.lots[1]["acquired_date"] is None
