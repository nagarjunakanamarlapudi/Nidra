"""The declarative half of a connector: what it is, how it authenticates, and
what it can do. A ``ConnectorSpec`` is pure data — no behaviour — so the catalog
can be listed, the config form auto-generated, and the auth flow chosen without
constructing anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

# A typed config field renders to one form control in the marketplace UI.
FieldType = Literal["text", "secret", "url", "select", "bool", "number"]

# How a connector collects credentials when enabled.
AuthKind = Literal["none", "secret", "oauth2", "managed_widget"]


class Capability(StrEnum):
    """What an enabled connector contributes. Composable — a connector may
    declare any combination (e.g. a chat channel that also ingests messages)."""

    INGEST = "ingest"  # downloads data into its own store; feeds the digest
    TOOLS = "tools"  # exposes tools to the agent (native or via MCP)
    CHANNEL = "channel"  # a two-way conversational surface (Telegram, WhatsApp)


@dataclass(frozen=True)
class Field:
    """One configurable value, rendered as a form control and validated on enable."""

    key: str
    label: str
    type: FieldType = "text"
    required: bool = True
    help: str | None = None
    placeholder: str | None = None
    options: tuple[str, ...] = ()  # for ``select``
    default: str | int | bool | None = None


@dataclass(frozen=True)
class OAuthConfig:
    """Per-provider OAuth 2.0 endpoints + scopes. The user supplies their own
    ``client_id``/``client_secret`` (single-user: one OAuth app, registered once)
    via the spec's ``config_schema``, so they are not stored here."""

    authorize_url: str
    token_url: str
    scopes: tuple[str, ...]
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    user_provided_client: bool = True
    # Config fields that carry the OAuth *app* credentials (hidden in the UI when
    # the server already provides them).
    client_field_keys: tuple[str, ...] = ("client_id", "client_secret")
    # Provider key under which the shared OAuth app creds are stored (env or DB),
    # so sibling connectors (e.g. Google Calendar + Gmail) reuse one app.
    provider: str | None = None


@dataclass(frozen=True)
class AuthStrategy:
    kind: AuthKind
    oauth: OAuthConfig | None = None
    widget: str | None = None  # for ``managed_widget`` (e.g. "plaid")


@dataclass(frozen=True)
class ConnectorSpec:
    """The catalog entry for one connector."""

    key: str
    name: str
    category: str
    pitch: str
    icon: str
    auth: AuthStrategy
    capabilities: frozenset[Capability]
    config_schema: tuple[Field, ...] = ()
    docs_url: str | None = None
    # Engine-native tool names this connector lights up when enabled (e.g. the
    # Claude Code built-ins "WebSearch"/"WebFetch"). Collected by the manager and
    # passed into the engine on rebuild — distinct from the in-process `Tool`s a
    # connector builds via SupportsTools.build_tools.
    native_engine_tools: tuple[str, ...] = ()
