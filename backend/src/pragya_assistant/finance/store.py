"""Async persistence + queries for finance data. No Plaid calls here."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.finance.client import (
    RawAccount,
    RawHolding,
    RawInvestmentTxn,
    RawLiability,
    RawTxn,
)
from pragya_assistant.memory.models import (
    Account,
    Holding,
    InvestmentTransaction,
    Liability,
    PlaidItem,
    Transaction,
)


class FinanceStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_item(self, institution_name: str, encrypted_token: str, item_id: str) -> int:
        """Insert a new PlaidItem or update in place on re-link (same item_id).

        Plaid returns the same item_id when the user re-links an already-connected
        institution, so a plain INSERT would raise IntegrityError on the UNIQUE
        constraint.  We do get-or-create by item_id and always update the token.
        """
        async with self._session_factory() as s:
            existing = (
                await s.execute(select(PlaidItem).where(PlaidItem.item_id == item_id))
            ).scalar_one_or_none()
            if existing is not None:
                existing.access_token = encrypted_token
                existing.institution_name = institution_name
                await s.commit()
                return existing.id
            item = PlaidItem(
                institution_name=institution_name, access_token=encrypted_token, item_id=item_id
            )
            s.add(item)
            await s.commit()
            await s.refresh(item)
            return item.id

    async def list_items(self) -> list[PlaidItem]:
        async with self._session_factory() as s:
            return list((await s.execute(select(PlaidItem))).scalars().all())

    async def delete_item(self, item_id: int) -> None:
        """Delete a PlaidItem by PK. FK ondelete=CASCADE removes child rows in DB."""
        async with self._session_factory() as s:
            await s.execute(delete(PlaidItem).where(PlaidItem.id == item_id))
            await s.commit()

    async def set_institution(
        self, item_id: int, name: str, logo: str | None, color: str | None
    ) -> None:
        async with self._session_factory() as s:
            item = await s.get(PlaidItem, item_id)
            if item is not None:
                item.institution_name = name
                item.institution_logo = logo
                item.institution_color = color
                await s.commit()

    async def get_cursor(self, item_id: int) -> str | None:
        async with self._session_factory() as s:
            item = await s.get(PlaidItem, item_id)
            return item.transactions_cursor if item is not None else None

    async def set_cursor(self, item_id: int, cursor: str) -> None:
        async with self._session_factory() as s:
            item = await s.get(PlaidItem, item_id)
            if item is not None:
                item.transactions_cursor = cursor
                item.last_synced_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
                await s.commit()

    async def _account_pk(self, s: AsyncSession, item_id: int, plaid_account_id: str) -> int | None:
        stmt = select(Account.id).where(
            Account.item_id == item_id, Account.plaid_account_id == plaid_account_id
        )
        return (await s.execute(stmt)).scalar_one_or_none()

    async def upsert_accounts(self, item_id: int, accounts: list[RawAccount]) -> None:
        async with self._session_factory() as s:
            for a in accounts:
                existing = (
                    await s.execute(
                        select(Account).where(
                            Account.item_id == item_id,
                            Account.plaid_account_id == a.plaid_account_id,
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    s.add(
                        Account(
                            item_id=item_id,
                            plaid_account_id=a.plaid_account_id,
                            name=a.name,
                            official_name=a.official_name,
                            type=a.type,
                            subtype=a.subtype,
                            mask=a.mask,
                            current_balance=a.current_balance,
                            available_balance=a.available_balance,
                            iso_currency=a.iso_currency,
                        )
                    )
                else:
                    existing.current_balance = a.current_balance
                    existing.available_balance = a.available_balance
                    existing.name = a.name
            await s.commit()

    async def apply_txn_sync(
        self, item_id: int, added: list[RawTxn], modified: list[RawTxn], removed: list[str]
    ) -> None:
        async with self._session_factory() as s:
            for t in [*added, *modified]:
                acct_pk = await self._account_pk(s, item_id, t.account_plaid_id)
                if acct_pk is None:
                    continue
                existing = (
                    await s.execute(
                        select(Transaction).where(Transaction.plaid_txn_id == t.plaid_txn_id)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    s.add(
                        Transaction(
                            account_id=acct_pk,
                            plaid_txn_id=t.plaid_txn_id,
                            date=t.date,
                            name=t.name,
                            merchant_name=t.merchant_name,
                            amount=t.amount,
                            category=t.category,
                            pending=t.pending,
                        )
                    )
                else:
                    existing.amount = t.amount
                    existing.category = t.category
                    existing.pending = t.pending
            if removed:
                await s.execute(delete(Transaction).where(Transaction.plaid_txn_id.in_(removed)))
            await s.commit()

    async def replace_holdings(self, item_id: int, holdings: list[RawHolding]) -> None:
        async with self._session_factory() as s:
            acct_ids = (
                (await s.execute(select(Account.id).where(Account.item_id == item_id)))
                .scalars()
                .all()
            )
            if acct_ids:
                await s.execute(delete(Holding).where(Holding.account_id.in_(acct_ids)))
            for h in holdings:
                pk = await self._account_pk(s, item_id, h.account_plaid_id)
                if pk is not None:
                    s.add(
                        Holding(
                            account_id=pk,
                            security_id=h.security_id,
                            security_name=h.security_name,
                            ticker=h.ticker,
                            quantity=h.quantity,
                            price=h.price,
                            value=h.value,
                            iso_currency=h.iso_currency,
                            cost_basis=h.cost_basis,
                            lots=h.lots,
                        )
                    )
            await s.commit()

    async def replace_liabilities(self, item_id: int, liabilities: list[RawLiability]) -> None:
        async with self._session_factory() as s:
            acct_ids = (
                (await s.execute(select(Account.id).where(Account.item_id == item_id)))
                .scalars()
                .all()
            )
            if acct_ids:
                await s.execute(delete(Liability).where(Liability.account_id.in_(acct_ids)))
            for liab in liabilities:
                pk = await self._account_pk(s, item_id, liab.account_plaid_id)
                if pk is not None:
                    s.add(
                        Liability(
                            account_id=pk,
                            kind=liab.kind,
                            apr=liab.apr,
                            next_payment_due=liab.next_payment_due,
                            next_payment_amount=liab.next_payment_amount,
                            balance=liab.balance,
                        )
                    )
            await s.commit()

    async def account_balances(self) -> list[Account]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Account).order_by(Account.name))).scalars().all())

    async def accounts_with_institution(
        self,
    ) -> list[tuple[Account, str, str | None, str | None]]:
        """Return each Account paired with institution_name, logo, and color.

        Ordered by institution name, then account name.
        """
        async with self._session_factory() as s:
            stmt = (
                select(
                    Account,
                    PlaidItem.institution_name,
                    PlaidItem.institution_logo,
                    PlaidItem.institution_color,
                )
                .join(PlaidItem, Account.item_id == PlaidItem.id)
                .order_by(PlaidItem.institution_name, Account.name)
            )
            rows = (await s.execute(stmt)).all()
            return [
                (acct, institution_name, institution_logo, institution_color)
                for acct, institution_name, institution_logo, institution_color in rows
            ]

    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]:
        async with self._session_factory() as s:
            stmt = select(Transaction).where(
                Transaction.date >= start, Transaction.date <= end, Transaction.amount > 0
            )
            totals: dict[str, Decimal] = {}
            for t in (await s.execute(stmt)).scalars().all():
                key = t.category or "Uncategorized"
                totals[key] = totals.get(key, Decimal("0")) + t.amount
            return totals

    async def search_transactions(
        self, text: str | None, start: dt.date | None, end: dt.date | None, limit: int
    ) -> list[Transaction]:
        async with self._session_factory() as s:
            stmt = select(Transaction).order_by(Transaction.date.desc())
            if text:
                stmt = stmt.where(Transaction.name.ilike(f"%{text}%"))
            if start:
                stmt = stmt.where(Transaction.date >= start)
            if end:
                stmt = stmt.where(Transaction.date <= end)
            return list((await s.execute(stmt.limit(limit))).scalars().all())

    async def transactions_for_account(
        self, account_id: int, limit: int = 100
    ) -> list[Transaction]:
        """Return up to *limit* transactions for *account_id*, newest first."""
        async with self._session_factory() as s:
            stmt = (
                select(Transaction)
                .where(Transaction.account_id == account_id)
                .order_by(Transaction.date.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def all_holdings(self) -> list[Holding]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Holding))).scalars().all())

    async def all_liabilities(self) -> list[Liability]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Liability))).scalars().all())

    async def net_worth(self) -> Decimal:
        # Investment-account balances already include the value of their holdings,
        # so holdings are NOT added separately here (avoids double-counting).
        async with self._session_factory() as s:
            assets = Decimal("0")
            for a in (await s.execute(select(Account))).scalars().all():
                if a.current_balance is None:
                    continue
                # credit/loan are debts (Plaid mortgages have type "loan"); others are assets
                if a.type in {"credit", "loan"}:
                    assets -= a.current_balance
                else:
                    assets += a.current_balance
            return assets

    async def replace_investment_transactions(
        self, item_id: int, txns: list[RawInvestmentTxn]
    ) -> None:
        """Delete existing investment transactions for item's accounts then re-insert."""
        async with self._session_factory() as s:
            acct_ids = (
                (await s.execute(select(Account.id).where(Account.item_id == item_id)))
                .scalars()
                .all()
            )
            if acct_ids:
                await s.execute(
                    delete(InvestmentTransaction).where(
                        InvestmentTransaction.account_id.in_(acct_ids)
                    )
                )
            # Build plaid_account_id → account PK map for this item
            acct_map: dict[str, int] = {}
            for row in (
                await s.execute(
                    select(Account.id, Account.plaid_account_id).where(Account.item_id == item_id)
                )
            ).all():
                acct_map[row.plaid_account_id] = row.id
            for t in txns:
                pk = acct_map.get(t.account_plaid_id)
                if pk is None:
                    continue
                s.add(
                    InvestmentTransaction(
                        account_id=pk,
                        plaid_investment_txn_id=t.plaid_investment_txn_id,
                        security_id=t.security_id,
                        ticker=t.ticker,
                        name=t.name,
                        type=t.type,
                        subtype=t.subtype,
                        quantity=t.quantity,
                        price=t.price,
                        amount=t.amount,
                        fees=t.fees,
                        date=t.date,
                    )
                )
            await s.commit()

    async def investment_transactions_for_account(
        self, account_id: int, limit: int = 100
    ) -> list[InvestmentTransaction]:
        """Return up to *limit* investment transactions for *account_id*, newest first."""
        async with self._session_factory() as s:
            stmt = (
                select(InvestmentTransaction)
                .where(InvestmentTransaction.account_id == account_id)
                .order_by(InvestmentTransaction.date.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())

    async def investment_transactions_for_security(
        self, security_id: str, limit: int = 100
    ) -> list[InvestmentTransaction]:
        """Return up to *limit* investment transactions for *security_id*, newest first."""
        async with self._session_factory() as s:
            stmt = (
                select(InvestmentTransaction)
                .where(InvestmentTransaction.security_id == security_id)
                .order_by(InvestmentTransaction.date.desc())
                .limit(limit)
            )
            return list((await s.execute(stmt)).scalars().all())
