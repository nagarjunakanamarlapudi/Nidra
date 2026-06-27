"""Finance tools — model-facing, read-only. No transfer/sync tool exists."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.memory.models import Account


def build_finance_tools(service: FinanceService) -> list[Tool]:
    async def account_balances(args: dict[str, Any]) -> str:
        rows = await service.accounts_with_institution()
        if not rows:
            return "No connected accounts."
        return "\n".join(_fmt_account(a, institution) for a, institution, _logo, _color in rows)

    async def spending_summary(args: dict[str, Any]) -> str:
        start = dt.date.fromisoformat(str(args["start"]))
        end = dt.date.fromisoformat(str(args["end"]))
        totals = await service.spending_by_category(start, end)
        if not totals:
            return "No spending in that range."
        lines = [f"- {cat}: {amt}" for cat, amt in sorted(totals.items(), key=lambda kv: -kv[1])]
        return f"Spending {start}–{end}:\n" + "\n".join(lines)

    async def search_transactions(args: dict[str, Any]) -> str:
        start = dt.date.fromisoformat(str(args["start"])) if args.get("start") else None
        end = dt.date.fromisoformat(str(args["end"])) if args.get("end") else None
        txns = await service.search_transactions(
            args.get("text"), start, end, int(args.get("limit", 25))
        )
        if not txns:
            return "No matching transactions."
        return "\n".join(f"- {t.date} {t.name}: {t.amount} ({t.category or '—'})" for t in txns)

    async def net_worth(args: dict[str, Any]) -> str:
        total = await service.net_worth()
        return f"Estimated net worth (total account balances minus credit/loan debts): {total}"

    async def holdings(args: dict[str, Any]) -> str:
        rows = await service.holdings()
        if not rows:
            return "No investment holdings."
        return "\n".join(
            f"- {h.ticker or h.security_name}: {h.quantity} @ {h.price} = {h.value}" for h in rows
        )

    async def upcoming_bills(args: dict[str, Any]) -> str:
        rows = await service.liabilities()
        due = [liab for liab in rows if liab.next_payment_due is not None]
        if not due:
            return "No upcoming bills on record."
        due.sort(key=lambda x: x.next_payment_due)  # type: ignore[arg-type,return-value]
        return "\n".join(
            f"- {liab.kind}: {liab.next_payment_amount} due {liab.next_payment_due}"
            + (f" (APR {liab.apr}%)" if liab.apr is not None else "")
            for liab in due
        )

    return [
        Tool(
            name="account_balances",
            description="Show balances across all connected accounts.",
            input_schema=_object({}, []),
            handler=account_balances,
        ),
        Tool(
            name="spending_summary",
            description="Total spending by category for a date range.",
            input_schema=_object(
                {"start": _string("Start date YYYY-MM-DD"), "end": _string("End date YYYY-MM-DD")},
                ["start", "end"],
            ),
            handler=spending_summary,
        ),
        Tool(
            name="search_transactions",
            description="Search transactions by text and/or date range.",
            input_schema=_object(
                {
                    "text": _string("Merchant/description substring"),
                    "start": _string("Start date YYYY-MM-DD"),
                    "end": _string("End date YYYY-MM-DD"),
                    "limit": _integer("Max results (default 25)"),
                },
                [],
            ),
            handler=search_transactions,
        ),
        Tool(
            name="net_worth",
            description=(
                "Estimate net worth: total account balances minus credit/loan debts"
                " (investment-account balances already include holdings;"
                " use 'holdings' for the breakdown)."
            ),
            input_schema=_object({}, []),
            handler=net_worth,
        ),
        Tool(
            name="holdings",
            description="List investment holdings/positions.",
            input_schema=_object({}, []),
            handler=holdings,
        ),
        Tool(
            name="upcoming_bills",
            description="List upcoming liability/loan/mortgage payments and due dates.",
            input_schema=_object({}, []),
            handler=upcoming_bills,
        ),
    ]


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _fmt_account(a: Account, institution: str) -> str:
    currency = f" {a.iso_currency}" if a.iso_currency else ""
    return f"- {institution} · {a.name} ({a.subtype or a.type}): {a.current_balance}{currency}"
