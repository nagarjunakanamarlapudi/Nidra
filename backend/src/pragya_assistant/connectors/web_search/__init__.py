"""Web Search connector — a toggle for the engine's built-in WebSearch/WebFetch.

Auth ``none``: there are no credentials. Enabling it adds the engine-native tools
(declared on the spec as ``native_engine_tools``) on the next engine rebuild.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_web_search(registry: ConnectorRegistry) -> None:
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.web_search.connector import WebSearchConnector
    from pragya_assistant.connectors.web_search.spec import WEB_SEARCH_SPEC

    registry.register(
        RegisteredConnector(spec=WEB_SEARCH_SPEC, build=lambda deps: WebSearchConnector())
    )
