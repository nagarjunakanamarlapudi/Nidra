import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import ToolHandler
from pragya_assistant.finance.client import RawAccount, RawTxn
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.store import FinanceStore


class _NoClient:  # tools never call the client; sync isn't exercised here
    def create_link_token(self) -> str: ...
    def exchange_public_token(self, public_token: str): ...
    def get_accounts(self, access_token: str):
        return []

    def sync_transactions(self, access_token: str, cursor): ...
    def get_holdings(self, access_token: str):
        return []

    def get_liabilities(self, access_token: str):
        return []


def _handler(tools: list, name: str) -> ToolHandler:
    return next(t for t in tools if t.name == name).handler


async def _seeded(session_factory: async_sessionmaker[AsyncSession]) -> FinanceService:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(
        item_id,
        [
            RawAccount(
                "ac1", "Checking", None, "depository", "checking", "1", Decimal("500"), None, "USD"
            ),
        ],
    )
    await store.apply_txn_sync(
        item_id,
        added=[
            RawTxn("t1", "ac1", dt.date(2026, 6, 1), "Cafe", None, Decimal("4"), "Food", False),
        ],
        modified=[],
        removed=[],
    )
    return FinanceService(_NoClient(), store, app_secret_key="x" * 16)


async def test_balances_and_net_worth(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools

    tools = build_finance_tools(await _seeded(session_factory))
    bal = await _handler(tools, "account_balances")({})
    assert "Chase" in bal and "Checking" in bal and "500" in bal
    nw = await _handler(tools, "net_worth")({})
    assert "500" in nw


async def test_spending_summary(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools

    tools = build_finance_tools(await _seeded(session_factory))
    out = await _handler(tools, "spending_summary")({"start": "2026-06-01", "end": "2026-06-30"})
    assert "Food" in out and "4" in out


async def test_no_transfer_or_sync_tool(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools

    # build with a throwaway service object is fine; only names are inspected
    svc = await _seeded(session_factory)
    names = {t.name for t in build_finance_tools(svc)}
    assert names == {
        "account_balances",
        "spending_summary",
        "search_transactions",
        "net_worth",
        "holdings",
        "upcoming_bills",
    }
    assert not any(("transfer" in n) or ("pay" in n) or ("sync" in n) for n in names)
