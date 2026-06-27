"""Plaid (Finance) connector spec — managed-widget auth (Plaid Link)."""

from __future__ import annotations

from pragya_assistant.connectors.spec import AuthStrategy, Capability, ConnectorSpec

PLAID_SPEC = ConnectorSpec(
    key="plaid",
    name="Finance",
    category="Finance",
    pitch="Link your bank & brokerage via Plaid — balances, spending, net worth, holdings.",
    icon="🏦",
    # Plaid Link is a client-side widget: no fields to paste, the platform creds
    # (PLAID_CLIENT_ID / PLAID_SECRET) live in env. The frontend opens Plaid Link
    # for `widget="plaid"`.
    auth=AuthStrategy(kind="managed_widget", widget="plaid"),
    capabilities=frozenset({Capability.INGEST, Capability.TOOLS}),
    docs_url="https://plaid.com/",
)
