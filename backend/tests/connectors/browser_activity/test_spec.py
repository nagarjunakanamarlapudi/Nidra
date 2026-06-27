"""The Browser Activity connector registers as a none-auth ingest connector."""

from __future__ import annotations

from pragya_assistant.connectors.browser_activity import register_browser_activity
from pragya_assistant.connectors.registry import ConnectorRegistry
from pragya_assistant.connectors.spec import Capability


def test_browser_activity_is_registered() -> None:
    registry = ConnectorRegistry()
    register_browser_activity(registry)

    assert "browser_activity" in registry
    rc = registry.get("browser_activity")
    assert rc is not None
    assert rc.spec.auth.kind == "none"  # ingest is behind the global app token
    assert Capability.INGEST in rc.spec.capabilities
