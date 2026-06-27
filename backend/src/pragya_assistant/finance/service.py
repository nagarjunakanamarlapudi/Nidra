"""Async finance service: orchestrates Plaid client + store. Read-only + sync."""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal
from typing import TYPE_CHECKING

from pragya_assistant.config import Settings
from pragya_assistant.crypto import decrypt_secret, encrypt_secret
from pragya_assistant.finance.client import PlaidClient
from pragya_assistant.finance.store import FinanceStore
from pragya_assistant.memory.models import (
    Account,
    Holding,
    InvestmentTransaction,
    Liability,
    PlaidItem,
    Transaction,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class FinanceService:
    def __init__(self, client: PlaidClient, store: FinanceStore, *, app_secret_key: str) -> None:
        self._client = client
        self._store = store
        self._key = app_secret_key

    async def create_link_token(self) -> str:
        return await asyncio.to_thread(self._client.create_link_token)

    async def link(self, public_token: str) -> str:
        result = await asyncio.to_thread(self._client.exchange_public_token, public_token)
        encrypted = encrypt_secret(result.access_token, self._key)
        item_id = await self._store.save_item(result.institution_name, encrypted, result.item_id)
        # Fetch name+logo+color via separate get_institution call (exchange does not return these).
        name, logo, color = await asyncio.to_thread(
            self._client.get_institution, result.access_token
        )
        await self._store.set_institution(item_id, name, logo, color)
        accounts = await asyncio.to_thread(self._client.get_accounts, result.access_token)
        await self._store.upsert_accounts(item_id, accounts)
        # Auto-sync: pull transactions, holdings, liabilities immediately after linking.
        items = await self._store.list_items()
        item = next(i for i in items if i.id == item_id)
        await self._sync_item(item)
        return name

    async def _sync_item(self, item: PlaidItem) -> None:
        """Pull latest data for one PlaidItem from Plaid and persist it."""
        token = decrypt_secret(item.access_token, self._key)
        accounts = await asyncio.to_thread(self._client.get_accounts, token)
        await self._store.upsert_accounts(item.id, accounts)

        cursor = item.transactions_cursor
        while True:
            page = await asyncio.to_thread(self._client.sync_transactions, token, cursor)
            await self._store.apply_txn_sync(item.id, page.added, page.modified, page.removed)
            cursor = page.next_cursor
            if not page.has_more:
                break
        await self._store.set_cursor(item.id, cursor)

        await self._store.replace_holdings(
            item.id, await asyncio.to_thread(self._client.get_holdings, token)
        )
        await self._store.replace_liabilities(
            item.id, await asyncio.to_thread(self._client.get_liabilities, token)
        )
        start_date = dt.date.today() - dt.timedelta(days=365 * 5)
        end_date = dt.date.today()
        inv_txns = await asyncio.to_thread(
            self._client.get_investment_transactions, token, start_date, end_date
        )
        await self._store.replace_investment_transactions(item.id, inv_txns)

    async def sync(self) -> int:
        items = await self._store.list_items()
        for item in items:
            await self._sync_item(item)
        return len(items)

    # --- query passthroughs (used by tools + digest) ---
    async def account_balances(self) -> list[Account]:
        return await self._store.account_balances()

    async def accounts_with_institution(self) -> list[tuple[Account, str, str | None, str | None]]:
        return await self._store.accounts_with_institution()

    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]:
        return await self._store.spending_by_category(start, end)

    async def search_transactions(
        self, text: str | None, start: dt.date | None, end: dt.date | None, limit: int = 25
    ) -> list[Transaction]:
        return await self._store.search_transactions(text, start, end, limit)

    async def holdings(self) -> list[Holding]:
        return await self._store.all_holdings()

    async def all_holdings(self) -> list[Holding]:
        return await self._store.all_holdings()

    async def liabilities(self) -> list[Liability]:
        return await self._store.all_liabilities()

    async def net_worth(self) -> Decimal:
        return await self._store.net_worth()

    async def transactions_for_account(
        self, account_id: int, limit: int = 100
    ) -> list[Transaction]:
        return await self._store.transactions_for_account(account_id, limit)

    async def investment_transactions_for_account(
        self, account_id: int, limit: int = 100
    ) -> list[InvestmentTransaction]:
        return await self._store.investment_transactions_for_account(account_id, limit)

    async def investment_transactions_for_security(
        self, security_id: str, limit: int = 100
    ) -> list[InvestmentTransaction]:
        return await self._store.investment_transactions_for_security(security_id, limit)

    async def backfill_institutions(self) -> int:
        items = await self._store.list_items()
        count = 0
        for item in items:
            if not item.institution_name or item.institution_name == "Connected bank":
                token = decrypt_secret(item.access_token, self._key)
                name, logo, color = await asyncio.to_thread(self._client.get_institution, token)
                await self._store.set_institution(item.id, name, logo, color)
                count += 1
        return count

    async def remove_item(self, item_id: int) -> bool:
        """Revoke the Plaid Item and delete all local data for it.

        Plaid revocation is best-effort — local deletion always proceeds.
        Returns True if the item existed and was deleted, False if not found.
        """
        items = await self._store.list_items()
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            return False
        token = decrypt_secret(item.access_token, self._key)
        await asyncio.to_thread(self._client.remove_item, token)
        await self._store.delete_item(item_id)
        return True


def build_finance_service(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> FinanceService | None:
    if not (settings.plaid_client_id and settings.plaid_secret):
        return None
    from pragya_assistant.finance.plaid_api import PlaidApiClient  # Task 11 (lazy import)

    client = PlaidApiClient(
        client_id=settings.plaid_client_id, secret=settings.plaid_secret, env=settings.plaid_env
    )
    store = FinanceStore(session_factory)
    return FinanceService(client, store, app_secret_key=settings.app_secret_key)
