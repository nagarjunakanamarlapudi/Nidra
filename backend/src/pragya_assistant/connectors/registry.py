"""The connector registry — the in-memory catalog of *available* connectors.

This holds what Pragya *can* connect to. What the user has actually enabled lives
in the database (``ConnectorInstance``); the manager joins the two.
"""

from __future__ import annotations

from pragya_assistant.connectors.base import ConnectorDeps, RegisteredConnector
from pragya_assistant.connectors.spec import ConnectorSpec


class ConnectorRegistry:
    """A keyed set of registered connectors, listed for the marketplace."""

    def __init__(self) -> None:
        self._items: dict[str, RegisteredConnector] = {}

    def register(self, rc: RegisteredConnector) -> None:
        """Register (or replace, by key) a connector."""
        self._items[rc.spec.key] = rc

    def get(self, key: str) -> RegisteredConnector | None:
        return self._items.get(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._items

    def all_specs(self) -> list[ConnectorSpec]:
        """All catalog entries, sorted by display name (stable UI ordering)."""
        return [rc.spec for rc in sorted(self._items.values(), key=lambda rc: rc.spec.name)]


def build_default_registry(deps: ConnectorDeps) -> ConnectorRegistry:
    """The registry the app boots with. Connectors register themselves here as
    they land (Google Calendar in the vertical slice). ``deps`` is threaded for
    connectors whose registration depends on settings."""
    registry = ConnectorRegistry()
    from pragya_assistant.connectors.browser_activity import register_browser_activity
    from pragya_assistant.connectors.gmail import register_gmail
    from pragya_assistant.connectors.google_calendar import register_google_calendar
    from pragya_assistant.connectors.plaid import register_plaid
    from pragya_assistant.connectors.telegram import register_telegram
    from pragya_assistant.connectors.web_search import register_web_search

    register_google_calendar(registry)
    register_gmail(registry)
    register_web_search(registry)
    register_telegram(registry)
    register_plaid(registry)
    register_browser_activity(registry)
    return registry
