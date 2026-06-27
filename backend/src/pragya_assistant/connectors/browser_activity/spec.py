"""Browser Activity connector spec — ambient capture pushed from the extension.

Auth ``none``: pushes are authenticated by the app's global bearer token (the
same one the extension already uses to trigger dreams), so there's no separate
secret to manage. Declares ``INGEST``; events arrive at the ingest endpoint
rather than being pulled, and the dreamer runs on top of the stored events.
"""

from __future__ import annotations

from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
)

BROWSER_ACTIVITY_SPEC = ConnectorSpec(
    key="browser_activity",
    name="Browser Activity",
    category="Ambient",
    pitch="Learns from what you read and search, then dreams on it to connect the dots.",
    icon="🌙",
    auth=AuthStrategy(kind="none"),
    capabilities=frozenset({Capability.INGEST}),
)
