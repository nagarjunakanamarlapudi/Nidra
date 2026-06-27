"""Web Search connector spec — no auth, lights up engine-native search tools."""

from __future__ import annotations

from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
)

# The Claude Code engine exposes these as built-ins; enabling the connector adds
# them to the agent's allowed tools (see ConnectorSpec.native_engine_tools).
WEB_SEARCH_TOOLS = ("WebSearch", "WebFetch")

WEB_SEARCH_SPEC = ConnectorSpec(
    key="web_search",
    name="Web Search",
    category="Knowledge",
    pitch="Let the assistant search the web and fetch pages, live — no setup, no keys.",
    icon="🔎",
    auth=AuthStrategy(kind="none"),
    capabilities=frozenset({Capability.TOOLS}),
    native_engine_tools=WEB_SEARCH_TOOLS,
)
