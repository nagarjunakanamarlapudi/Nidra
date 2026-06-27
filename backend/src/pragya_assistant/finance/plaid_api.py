"""Concrete Plaid SDK adapter. Read-only products only (no transfer endpoints).

Verify exact request/response model imports against the installed plaid-python;
the Sandbox integration test exercises every method.
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.institutions_get_by_id_request_options import InstitutionsGetByIdRequestOptions
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import InvestmentsTransactionsGetRequest
from plaid.model.investments_transactions_get_request_options import (
    InvestmentsTransactionsGetRequestOptions,
)
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.liabilities_get_request import LiabilitiesGetRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from pragya_assistant.finance.client import (
    LinkResult,
    RawAccount,
    RawHolding,
    RawInvestmentTxn,
    RawLiability,
    RawTxn,
    SyncPage,
)

_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def _dec(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class PlaidApiClient:
    def __init__(self, *, client_id: str, secret: str, env: str) -> None:
        configuration = plaid.Configuration(
            host=_HOSTS[env], api_key={"clientId": client_id, "secret": secret}
        )
        self._api = plaid_api.PlaidApi(plaid.ApiClient(configuration))

    def create_link_token(self) -> str:
        # `transactions` is the broadly-supported base product. investments +
        # liabilities are OPTIONAL — fetched when the institution has them, but
        # never *required* (so a pure-investment broker like Fidelity, with no
        # liability accounts, isn't blocked with "No liability accounts").
        req = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="pragya-user"),
            client_name="Pragya",
            products=[Products("transactions")],
            optional_products=[Products("investments"), Products("liabilities")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        return self._api.link_token_create(req).link_token  # type: ignore[no-any-return]

    def exchange_public_token(self, public_token: str) -> LinkResult:
        resp = self._api.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        access_token: str = resp.access_token
        item_id: str = resp.item_id
        return LinkResult(
            access_token=access_token, item_id=item_id, institution_name="Connected bank"
        )

    def get_institution(self, access_token: str) -> tuple[str, str | None, str | None]:
        """Fetch institution name, logo (base64 PNG), and primary_color for the item's institution.

        Returns ("Connected bank", None, None) on any error so callers always get a usable name.
        Logo and color may be None even on success if Plaid doesn't have them for this institution.
        Empty strings from Plaid (e.g. Chase logo) are normalized to None.
        """
        try:
            item_resp = self._api.item_get(ItemGetRequest(access_token=access_token))
            institution_id = item_resp.item.institution_id
            if institution_id:
                inst_resp = self._api.institutions_get_by_id(
                    InstitutionsGetByIdRequest(
                        institution_id=institution_id,
                        country_codes=[CountryCode("US")],
                        options=InstitutionsGetByIdRequestOptions(
                            include_optional_metadata=True,
                        ),
                    )
                )
                inst = inst_resp.institution
                inst_dict = inst.to_dict() if hasattr(inst, "to_dict") else {}
                raw_logo: str | None = inst_dict.get("logo") or getattr(inst, "logo", None)
                raw_color: str | None = inst_dict.get("primary_color") or getattr(
                    inst, "primary_color", None
                )
                logo = raw_logo if raw_logo else None
                color = raw_color if raw_color else None
                return inst.name, logo, color
        except Exception:  # noqa: BLE001, S110 — best-effort logo fetch; failures are non-fatal
            pass
        return "Connected bank", None, None

    def get_accounts(self, access_token: str) -> list[RawAccount]:
        resp = self._api.accounts_balance_get(AccountsBalanceGetRequest(access_token=access_token))
        out = []
        for a in resp.accounts:
            out.append(
                RawAccount(
                    plaid_account_id=a.account_id,
                    name=a.name,
                    official_name=a.official_name,
                    type=str(a.type),
                    subtype=(None if a.subtype is None else str(a.subtype)),
                    mask=a.mask,
                    current_balance=_dec(a.balances.current),
                    available_balance=_dec(a.balances.available),
                    iso_currency=a.balances.iso_currency_code,
                )
            )
        return out

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        req = TransactionsSyncRequest(access_token=access_token)
        if cursor is not None:
            req.cursor = cursor
        resp = self._api.transactions_sync(req)

        def conv(t: object) -> RawTxn:
            return RawTxn(
                plaid_txn_id=t.transaction_id,  # type: ignore[attr-defined]
                account_plaid_id=t.account_id,  # type: ignore[attr-defined]
                date=t.date if isinstance(t.date, dt.date) else dt.date.fromisoformat(str(t.date)),  # type: ignore[attr-defined]
                name=t.name,  # type: ignore[attr-defined]
                merchant_name=t.merchant_name,  # type: ignore[attr-defined]
                amount=Decimal(str(t.amount)),  # type: ignore[attr-defined]
                category=(
                    t.personal_finance_category.primary  # type: ignore[attr-defined]
                    if t.personal_finance_category  # type: ignore[attr-defined]
                    else None
                ),
                pending=bool(t.pending),  # type: ignore[attr-defined]
            )

        return SyncPage(
            added=[conv(t) for t in resp.added],
            modified=[conv(t) for t in resp.modified],
            removed=[r.transaction_id for r in resp.removed],
            next_cursor=resp.next_cursor,
            has_more=resp.has_more,
        )

    def get_holdings(self, access_token: str) -> list[RawHolding]:
        try:
            resp = self._api.investments_holdings_get(
                InvestmentsHoldingsGetRequest(access_token=access_token)
            )
        except plaid.ApiException:
            return []  # product not available for this item
        secs = {s.security_id: s for s in resp.securities}
        out = []
        for h in resp.holdings:
            sec = secs.get(h.security_id)
            # cost_basis
            h_dict = h.to_dict() if hasattr(h, "to_dict") else {}
            cost_basis = _dec(h_dict.get("cost_basis") or getattr(h, "cost_basis", None))
            # tax_lots
            raw_lots = h_dict.get("tax_lots") or getattr(h, "tax_lots", None)
            if raw_lots:
                built_lots: list[dict[str, Any]] = []
                for lot in raw_lots:
                    if hasattr(lot, "to_dict"):
                        lot_d = lot.to_dict()
                    elif isinstance(lot, dict):
                        lot_d = lot
                    else:
                        lot_d = {}
                    q = lot_d.get("quantity")
                    cb = lot_d.get("cost_basis")
                    ad = lot_d.get("acquired_date")
                    if ad is not None and hasattr(ad, "isoformat"):
                        ad_str: str | None = ad.isoformat()
                    elif ad is not None:
                        ad_str = str(ad)
                    else:
                        ad_str = None
                    built_lots.append(
                        {
                            "quantity": str(q) if q is not None else None,
                            "cost_basis": str(cb) if cb is not None else None,
                            "acquired_date": ad_str,
                        }
                    )
                lots: list[dict[str, Any]] | None = built_lots
            else:
                lots = None
            out.append(
                RawHolding(
                    account_plaid_id=h.account_id,
                    security_name=(
                        (sec.name if sec and sec.name else (sec.ticker_symbol if sec else "")) or ""
                    ),
                    ticker=(sec.ticker_symbol if sec else None),
                    quantity=Decimal(str(h.quantity)),
                    price=_dec(h.institution_price),
                    value=_dec(h.institution_value),
                    iso_currency=h.iso_currency_code,
                    cost_basis=cost_basis,
                    lots=lots,
                    security_id=h.security_id,
                )
            )
        return out

    def get_liabilities(self, access_token: str) -> list[RawLiability]:
        try:
            resp = self._api.liabilities_get(LiabilitiesGetRequest(access_token=access_token))
        except plaid.ApiException:
            return []
        out: list[RawLiability] = []
        liabilities = resp.liabilities
        for m in liabilities.mortgage or []:
            out.append(
                RawLiability(
                    account_plaid_id=m.account_id,
                    kind="mortgage",
                    apr=_dec(getattr(m.interest_rate, "percentage", None)),
                    next_payment_due=_date(m.next_payment_due_date),
                    next_payment_amount=_dec(m.next_monthly_payment),
                    balance=None,
                )
            )
        for c in liabilities.credit or []:
            out.append(
                RawLiability(
                    account_plaid_id=c.account_id,
                    kind="credit",
                    apr=None,
                    next_payment_due=_date(c.next_payment_due_date),
                    next_payment_amount=_dec(c.minimum_payment_amount),
                    balance=None,
                )
            )
        return out

    def remove_item(self, access_token: str) -> None:
        """Revoke the Plaid Item. Best-effort: errors are logged and swallowed.

        Local deletion must proceed even if Plaid revocation fails (expired
        token, network error, etc.).
        """
        try:
            self._api.item_remove(ItemRemoveRequest(access_token=access_token))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).warning(
                "item/remove failed for token %s…; proceeding with local deletion",
                access_token[:8],
            )

    def get_investment_transactions(
        self,
        access_token: str,
        start_date: dt.date,
        end_date: dt.date,
    ) -> list[RawInvestmentTxn]:
        """Fetch all investment transactions in [start_date, end_date].

        Uses offset pagination (max 500 per page). Returns [] if the
        Investments product is not available for this item.
        """
        try:
            MAX_COUNT = 500
            all_txns: list[RawInvestmentTxn] = []
            offset = 0

            # First call — get total and first page
            options = InvestmentsTransactionsGetRequestOptions(
                count=MAX_COUNT,
                offset=offset,
            )
            req = InvestmentsTransactionsGetRequest(
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                options=options,
            )
            resp = self._api.investments_transactions_get(req)
            total: int = resp.total_investment_transactions
            secs = {s.security_id: s for s in resp.securities}

            def _conv(t: object, secs: dict) -> RawInvestmentTxn:  # type: ignore[type-arg]
                sec = secs.get(getattr(t, "security_id", None))
                ticker: str | None = sec.ticker_symbol if sec else None
                raw_type = getattr(t, "type", None)
                raw_subtype = getattr(t, "subtype", None)
                return RawInvestmentTxn(
                    account_plaid_id=t.account_id,  # type: ignore[attr-defined]
                    plaid_investment_txn_id=t.investment_transaction_id,  # type: ignore[attr-defined]
                    security_id=getattr(t, "security_id", None),
                    ticker=ticker,
                    name=t.name,  # type: ignore[attr-defined]
                    type=str(raw_type) if raw_type is not None else "",
                    subtype=str(raw_subtype) if raw_subtype is not None else None,
                    quantity=_dec(getattr(t, "quantity", None)) or Decimal("0"),
                    price=_dec(getattr(t, "price", None)),
                    amount=_dec(getattr(t, "amount", None)) or Decimal("0"),
                    fees=_dec(getattr(t, "fees", None)),
                    date=(
                        t.date  # type: ignore[attr-defined]
                        if isinstance(t.date, dt.date)  # type: ignore[attr-defined]
                        else dt.date.fromisoformat(str(t.date))  # type: ignore[attr-defined]
                    ),
                )

            all_txns.extend(_conv(t, secs) for t in resp.investment_transactions)
            offset += len(resp.investment_transactions)

            # Paginate until we have everything
            while offset < total:
                options = InvestmentsTransactionsGetRequestOptions(
                    count=MAX_COUNT,
                    offset=offset,
                )
                req = InvestmentsTransactionsGetRequest(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options=options,
                )
                resp = self._api.investments_transactions_get(req)
                secs.update({s.security_id: s for s in resp.securities})
                all_txns.extend(_conv(t, secs) for t in resp.investment_transactions)
                offset += len(resp.investment_transactions)
                if not resp.investment_transactions:
                    break  # safety: avoid infinite loop

            return all_txns
        except plaid.ApiException:
            return []  # product not ready / unsupported for this item

    def sandbox_public_token(self) -> str:
        """Sandbox-only: mint a public_token without the Link UI (for tests)."""
        from plaid.model.sandbox_public_token_create_request import (
            SandboxPublicTokenCreateRequest,
        )

        req = SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",
            initial_products=[
                Products("transactions"),
                Products("investments"),
                Products("liabilities"),
            ],
        )
        return self._api.sandbox_public_token_create(req).public_token  # type: ignore[no-any-return]


def _date(value: object) -> dt.date | None:
    if value is None:
        return None
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
