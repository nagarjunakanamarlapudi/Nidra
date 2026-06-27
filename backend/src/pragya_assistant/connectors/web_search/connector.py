"""Web Search connector: no in-process tools — its value is the native toggle."""

from __future__ import annotations

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import ConnectorContext, Health


class WebSearchConnector:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True, detail="Built-in web search is available when enabled.")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        # No in-process Tools; the capability is engine-native (WebSearch/WebFetch),
        # declared via spec.native_engine_tools and wired in on engine rebuild.
        return []
