"""The Gmail connector — OAuth 2.0, read-only, **live tool calls only**.

Deliberately has no ``ingest`` capability: nothing is stored locally. Its tools
query the Gmail API on demand using the OAuth token. Shares the Google OAuth app
(``provider="google"``) with the Google Calendar connector.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_gmail(registry: ConnectorRegistry) -> None:
    """Register Gmail into a registry (deferred imports avoid a cycle)."""
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.gmail.connector import GmailConnector
    from pragya_assistant.connectors.gmail.spec import GMAIL_SPEC

    registry.register(RegisteredConnector(spec=GMAIL_SPEC, build=lambda deps: GmailConnector()))
