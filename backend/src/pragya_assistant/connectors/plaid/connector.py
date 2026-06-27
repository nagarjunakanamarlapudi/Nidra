"""Plaid connector: delegates to the existing FinanceService (sync + tools)."""

from __future__ import annotations

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import ConnectorContext, Health, SyncResult
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.tools import build_finance_tools

_NOT_CONFIGURED = "Plaid isn't configured — set PLAID_CLIENT_ID / PLAID_SECRET."


class PlaidConnector:
    def __init__(self, *, finance: FinanceService | None) -> None:
        self._finance = finance

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        if self._finance is None:
            return Health(ok=False, detail=_NOT_CONFIGURED)
        accounts = await self._finance.account_balances()
        if accounts:
            return Health(ok=True, detail=f"{len(accounts)} account(s) linked")
        return Health(ok=False, detail="No banks linked yet — use Connect.")

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        if self._finance is None:
            return SyncResult(items=0, detail=_NOT_CONFIGURED)
        count = await self._finance.sync()
        return SyncResult(items=count, detail=f"synced {count} item(s)")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        if self._finance is None:
            return []
        return build_finance_tools(self._finance)
