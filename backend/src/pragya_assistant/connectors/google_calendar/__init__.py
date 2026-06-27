"""The Google Calendar connector — the vertical slice proving the platform.

OAuth 2.0 (read-only), ingests events into its own ``calendar_events`` store,
and exposes ``gcal_agenda`` / ``gcal_upcoming`` tools that read from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_google_calendar(registry: ConnectorRegistry) -> None:
    """Register Google Calendar into a registry (deferred imports avoid a cycle)."""
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.google_calendar.connector import GoogleCalendarConnector
    from pragya_assistant.connectors.google_calendar.spec import GOOGLE_CALENDAR_SPEC

    registry.register(
        RegisteredConnector(
            spec=GOOGLE_CALENDAR_SPEC,
            build=lambda deps: GoogleCalendarConnector(deps.session_factory),
        )
    )
