"""The Gmail connector spec — OAuth 2.0, read-only, tools-only (no ingest).

Scope is strictly ``gmail.readonly``; a safety test asserts no send/modify scope
or mutating endpoint ever creeps in. Shares the Google app via ``provider="google"``.
"""

from __future__ import annotations

from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"

GMAIL_SPEC = ConnectorSpec(
    key="gmail",
    name="Gmail",
    category="Email",
    pitch="Search and read your inbox on demand — read-only, nothing stored locally.",
    icon="📧",
    auth=AuthStrategy(
        kind="oauth2",
        oauth=OAuthConfig(
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",  # noqa: S106 — OAuth endpoint URL
            scopes=(GMAIL_READONLY_SCOPE,),
            extra_authorize_params={"access_type": "offline", "prompt": "consent"},
            provider="google",
        ),
    ),
    capabilities=frozenset({Capability.TOOLS}),
    config_schema=(
        Field(
            key="client_id",
            label="OAuth Client ID",
            help="Shared with Google Calendar — set once via `make google-oauth`.",
        ),
        Field(key="client_secret", label="OAuth Client Secret", type="secret"),
    ),
    docs_url="https://developers.google.com/gmail/api/guides",
)
