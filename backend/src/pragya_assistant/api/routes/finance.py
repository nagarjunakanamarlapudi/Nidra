"""Finance endpoints — Plaid Link flow + manual sync + accounts (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_finance, get_fx
from pragya_assistant.api.schemas import (
    AccountOut,
    ExchangeIn,
    FxOut,
    HoldingOut,
    InvestmentTransactionOut,
    TransactionOut,
)
from pragya_assistant.finance.fx import FxService
from pragya_assistant.finance.service import FinanceService

router = APIRouter(tags=["finance"], dependencies=[Depends(require_token)])


@router.get("/finance/fx", response_model=FxOut)
async def get_fx_rate(fx: Annotated[FxService, Depends(get_fx)]) -> FxOut:
    """Return the current USD→INR exchange rate (cached up to 12 h)."""
    rate, as_of = await fx.get_usd_inr()
    return FxOut(usd_inr=rate, as_of=as_of)


@router.post("/finance/link/token")
async def link_token(finance: Annotated[FinanceService, Depends(get_finance)]) -> dict[str, str]:
    return {"link_token": await finance.create_link_token()}


@router.post("/finance/link/exchange")
async def link_exchange(
    body: ExchangeIn, finance: Annotated[FinanceService, Depends(get_finance)]
) -> dict[str, str]:
    return {"institution": await finance.link(body.public_token)}


@router.post("/finance/sync")
async def sync(finance: Annotated[FinanceService, Depends(get_finance)]) -> dict[str, int]:
    return {"items_synced": await finance.sync()}


@router.get("/finance/accounts", response_model=list[AccountOut])
async def accounts(finance: Annotated[FinanceService, Depends(get_finance)]) -> list[AccountOut]:
    return [
        AccountOut(
            account_id=a.id,
            item_id=a.item_id,
            institution=institution,
            institution_logo=institution_logo,
            institution_color=institution_color,
            name=a.name,
            official_name=a.official_name,
            mask=a.mask,
            type=a.type,
            subtype=a.subtype,
            current_balance=a.current_balance,
            iso_currency=a.iso_currency,
        )
        for a, institution, institution_logo, institution_color in (
            await finance.accounts_with_institution()
        )
    ]


@router.get("/finance/holdings", response_model=list[HoldingOut])
async def get_holdings(
    finance: Annotated[FinanceService, Depends(get_finance)],
) -> list[HoldingOut]:
    holdings = await finance.all_holdings()
    # Sort by value desc, nulls last
    return [
        HoldingOut(
            account_id=h.account_id,
            ticker=h.ticker,
            security_name=h.security_name,
            quantity=h.quantity,
            price=h.price,
            value=h.value,
            iso_currency=h.iso_currency,
            cost_basis=h.cost_basis,
            lots=h.lots,
            security_id=h.security_id,
        )
        for h in sorted(
            holdings,
            key=lambda h: (h.value is None, -(h.value or 0)),
        )
    ]


@router.delete("/finance/items/{item_id}")
async def delete_item(
    item_id: int,
    finance: Annotated[FinanceService, Depends(get_finance)],
) -> dict[str, bool]:
    removed = await finance.remove_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"removed": True}


@router.get("/finance/transactions/{account_id}", response_model=list[TransactionOut])
async def account_transactions(
    account_id: int,
    finance: Annotated[FinanceService, Depends(get_finance)],
    limit: int = 100,
) -> list[TransactionOut]:
    txns = await finance.transactions_for_account(account_id, limit=limit)
    return [
        TransactionOut(
            id=t.id,
            date=t.date,
            name=t.name,
            merchant_name=t.merchant_name,
            amount=t.amount,
            category=t.category,
            pending=t.pending,
        )
        for t in txns
    ]


@router.get(
    "/finance/investment-transactions/{account_id}",
    response_model=list[InvestmentTransactionOut],
)
async def investment_transactions_for_account(
    account_id: int,
    finance: Annotated[FinanceService, Depends(get_finance)],
    limit: int = 100,
) -> list[InvestmentTransactionOut]:
    txns = await finance.investment_transactions_for_account(account_id, limit=limit)
    return [
        InvestmentTransactionOut(
            id=t.id,
            date=t.date,
            name=t.name,
            type=t.type,
            subtype=t.subtype,
            ticker=t.ticker,
            security_id=t.security_id,
            quantity=t.quantity,
            price=t.price,
            amount=t.amount,
            fees=t.fees,
        )
        for t in txns
    ]


@router.get(
    "/finance/holdings/{security_id}/transactions",
    response_model=list[InvestmentTransactionOut],
)
async def investment_transactions_for_security(
    security_id: str,
    finance: Annotated[FinanceService, Depends(get_finance)],
    limit: int = 100,
) -> list[InvestmentTransactionOut]:
    txns = await finance.investment_transactions_for_security(security_id, limit=limit)
    return [
        InvestmentTransactionOut(
            id=t.id,
            date=t.date,
            name=t.name,
            type=t.type,
            subtype=t.subtype,
            ticker=t.ticker,
            security_id=t.security_id,
            quantity=t.quantity,
            price=t.price,
            amount=t.amount,
            fees=t.fees,
        )
        for t in txns
    ]
