"""Plaid value types + the read-only client interface (Protocol).

The concrete SDK adapter (PlaidApiClient) lives below; tests and the service
depend on the Protocol so they run without the SDK or network.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class LinkResult:
    access_token: str
    item_id: str
    institution_name: str


@dataclass(frozen=True)
class RawAccount:
    plaid_account_id: str
    name: str
    official_name: str | None
    type: str
    subtype: str | None
    mask: str | None
    current_balance: Decimal | None
    available_balance: Decimal | None
    iso_currency: str | None


@dataclass(frozen=True)
class RawTxn:
    plaid_txn_id: str
    account_plaid_id: str
    date: dt.date
    name: str
    merchant_name: str | None
    amount: Decimal
    category: str | None
    pending: bool


@dataclass(frozen=True)
class RawHolding:
    account_plaid_id: str
    security_name: str
    ticker: str | None
    quantity: Decimal
    price: Decimal | None
    value: Decimal | None
    iso_currency: str | None
    cost_basis: Decimal | None = None
    lots: list[dict[str, Any]] | None = None
    security_id: str | None = None


@dataclass(frozen=True)
class RawLiability:
    account_plaid_id: str
    kind: str
    apr: Decimal | None
    next_payment_due: dt.date | None
    next_payment_amount: Decimal | None
    balance: Decimal | None


@dataclass(frozen=True)
class SyncPage:
    added: list[RawTxn]
    modified: list[RawTxn]
    removed: list[str]
    next_cursor: str
    has_more: bool


@dataclass(frozen=True)
class RawInvestmentTxn:
    account_plaid_id: str
    plaid_investment_txn_id: str
    security_id: str | None
    ticker: str | None
    name: str
    type: str
    subtype: str | None
    quantity: Decimal
    price: Decimal | None
    amount: Decimal
    fees: Decimal | None
    date: dt.date


class PlaidClient(Protocol):
    def create_link_token(self) -> str: ...
    def exchange_public_token(self, public_token: str) -> LinkResult: ...
    def get_institution(self, access_token: str) -> tuple[str, str | None, str | None]: ...
    def get_accounts(self, access_token: str) -> list[RawAccount]: ...
    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage: ...
    def get_holdings(self, access_token: str) -> list[RawHolding]: ...
    def get_liabilities(self, access_token: str) -> list[RawLiability]: ...
    def remove_item(self, access_token: str) -> None: ...
    def get_investment_transactions(
        self, access_token: str, start_date: dt.date, end_date: dt.date
    ) -> list[RawInvestmentTxn]: ...
