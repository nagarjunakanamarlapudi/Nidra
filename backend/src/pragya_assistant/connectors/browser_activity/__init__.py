"""Browser Activity connector — ambient capture pushed from the Nidra extension.

Auth ``secret``: a per-connector ingest token. Events are PUSHED to the ingest
endpoint (not pulled), stored in the connector's own table, and the dreamer
consolidates them into higher-level intent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_browser_activity(registry: ConnectorRegistry) -> None:
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.browser_activity.connector import BrowserActivityConnector
    from pragya_assistant.connectors.browser_activity.spec import BROWSER_ACTIVITY_SPEC

    registry.register(
        RegisteredConnector(
            spec=BROWSER_ACTIVITY_SPEC,
            build=lambda deps: BrowserActivityConnector(deps.session_factory),
        )
    )
