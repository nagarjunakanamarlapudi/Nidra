"""The Google Calendar connector spec — OAuth 2.0, read-only.

The scope is deliberately read-only (``calendar.readonly``); a safety test
asserts no write scope or mutating endpoint ever creeps in (mirrors the email
connector's no-send guarantee).
"""

from __future__ import annotations

from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)

CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"

GOOGLE_CALENDAR_SPEC = ConnectorSpec(
    key="google_calendar",
    name="Google Calendar",
    category="Calendar",
    pitch="Your agenda and upcoming events — read-only, with a line in the daily digest.",
    icon="📅",
    auth=AuthStrategy(
        kind="oauth2",
        oauth=OAuthConfig(
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # noqa: S106 — OAuth endpoint URL, not a secret
            scopes=(CALENDAR_READONLY_SCOPE,),
            extra_authorize_params={"access_type": "offline", "prompt": "consent"},
            provider="google",
        ),
    ),
    capabilities=frozenset({Capability.INGEST, Capability.TOOLS}),
    config_schema=(
        Field(
            key="client_id",
            label="OAuth Client ID",
            help="From a Google Cloud OAuth client (Web application) you create once.",
        ),
        Field(key="client_secret", label="OAuth Client Secret", type="secret"),
        Field(
            key="calendar_id",
            label="Calendar ID",
            required=False,
            default="primary",
            placeholder="primary",
            help="Which calendar to sync (default: your primary calendar).",
        ),
        Field(
            key="sync_days_ahead",
            label="Days to sync ahead",
            type="number",
            required=False,
            default=30,
        ),
    ),
    docs_url="https://developers.google.com/calendar/api/guides/auth",
)
