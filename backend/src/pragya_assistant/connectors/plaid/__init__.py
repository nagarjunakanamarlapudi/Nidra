"""The Plaid (Finance) connector — `managed_widget` auth via Plaid Link.

A thin adapter over the existing FinanceService: the widget (Plaid Link, in the
drawer) links a bank, `sync` pulls transactions (ingest), and `build_tools`
exposes the finance tools to in-process engines. The rich Finance page remains
for detailed analysis.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_plaid(registry: ConnectorRegistry) -> None:
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.plaid.connector import PlaidConnector
    from pragya_assistant.connectors.plaid.spec import PLAID_SPEC

    registry.register(
        RegisteredConnector(
            spec=PLAID_SPEC, build=lambda deps: PlaidConnector(finance=deps.finance)
        )
    )
