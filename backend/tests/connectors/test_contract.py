"""The connector contract: declarative spec + runtime capability protocols."""

from __future__ import annotations

import dataclasses

import pytest

from pragya_assistant.connectors.base import (
    Connector,
    ConnectorContext,
    Health,
    SupportsIngest,
    SupportsTools,
    SyncResult,
)
from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)


def _spec(**kw: object) -> ConnectorSpec:
    defaults: dict[str, object] = {
        "key": "demo",
        "name": "Demo",
        "category": "Misc",
        "pitch": "A demo connector.",
        "icon": "🔌",
        "auth": AuthStrategy(kind="none"),
        "capabilities": frozenset({Capability.TOOLS}),
    }
    defaults.update(kw)
    return ConnectorSpec(**defaults)  # type: ignore[arg-type]


def test_field_defaults() -> None:
    f = Field(key="token", label="API token")
    assert f.type == "text"
    assert f.required is True
    assert f.options == ()


def test_capabilities_membership() -> None:
    spec = _spec(capabilities=frozenset({Capability.INGEST, Capability.TOOLS}))
    assert Capability.INGEST in spec.capabilities
    assert Capability.CHANNEL not in spec.capabilities


def test_oauth_strategy_carries_config() -> None:
    oauth = OAuthConfig(
        authorize_url="https://auth.example/authorize",
        token_url="https://auth.example/token",
        scopes=("read",),
    )
    spec = _spec(auth=AuthStrategy(kind="oauth2", oauth=oauth))
    assert spec.auth.kind == "oauth2"
    assert spec.auth.oauth is not None
    assert spec.auth.oauth.scopes == ("read",)
    assert spec.auth.oauth.user_provided_client is True


def test_spec_is_frozen() -> None:
    spec = _spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.key = "other"  # type: ignore[misc]


class _IngestOnly:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        return SyncResult(items=3)


def test_capability_protocols_are_structural() -> None:
    conn = _IngestOnly()
    assert isinstance(conn, Connector)
    assert isinstance(conn, SupportsIngest)
    assert not isinstance(conn, SupportsTools)


def test_connector_context_holds_decrypted_config() -> None:
    ctx = ConnectorContext(key="demo", config={"token": "secret"})
    assert ctx.config["token"] == "secret"
    assert ctx.granted_scopes == ()
    assert ctx.access_token is None
