"""ConnectorManager: catalog, enable/disable, OAuth orchestration, tools, sync."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import (
    ConnectorContext,
    ConnectorDeps,
    Health,
    RegisteredConnector,
    SyncResult,
)
from pragya_assistant.connectors.manager import (
    ConnectorError,
    ConnectorManager,
    UnknownConnectorError,
)
from pragya_assistant.connectors.oauth import OAuthToken
from pragya_assistant.connectors.registry import ConnectorRegistry
from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)
from pragya_assistant.connectors.store import AppCredentialStore, ConnectorInstanceStore


class _SecretConn:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        ok = ctx.config.get("api_key") != "BAD"
        return Health(ok=ok, detail=None if ok else "bad key")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        async def _h(args: dict[str, Any]) -> str:
            return "ok"

        return [
            Tool(
                name="demo_tool",
                description="d",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=_h,
            )
        ]


class _OAuthConn:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        if ctx.access_token is not None:
            await ctx.access_token()  # exercise refresh path
        return SyncResult(items=5)


SECRET_SPEC = ConnectorSpec(
    key="secret_demo",
    name="Secret Demo",
    category="X",
    pitch="p",
    icon="🔑",
    auth=AuthStrategy(kind="secret"),
    capabilities=frozenset({Capability.TOOLS}),
    config_schema=(Field(key="api_key", label="API key", type="secret"),),
)

OAUTH_SPEC = ConnectorSpec(
    key="oauth_demo",
    name="OAuth Demo",
    category="X",
    pitch="p",
    icon="🔐",
    auth=AuthStrategy(
        kind="oauth2",
        oauth=OAuthConfig(
            authorize_url="https://a/au",
            token_url="https://a/tok",
            scopes=("s.read",),
            provider="demo",
        ),
    ),
    capabilities=frozenset({Capability.INGEST}),
    config_schema=(
        Field(key="client_id", label="Client ID"),
        Field(key="client_secret", label="Secret", type="secret"),
    ),
)


class _FakeOAuth:
    def __init__(self) -> None:
        self.fail_exchange = False

    async def start(self, spec: ConnectorSpec, config: dict[str, Any]) -> str:
        return "https://auth/redirect?state=ST"

    async def exchange(
        self, spec: ConnectorSpec, config: dict[str, Any], *, code: str, state: str
    ) -> OAuthToken:
        if self.fail_exchange:
            raise ValueError("bad code")
        return OAuthToken(access_token="AT", refresh_token="RT", expires_at=None, scope="s.read")

    async def access_token_for(
        self, spec: ConnectorSpec, config: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        return config.get("access_token", "AT"), config


def _registry() -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(RegisteredConnector(spec=SECRET_SPEC, build=lambda deps: _SecretConn()))
    reg.register(RegisteredConnector(spec=OAUTH_SPEC, build=lambda deps: _OAuthConn()))
    return reg


def _manager(
    session_factory: async_sessionmaker[AsyncSession],
    server_oauth_clients: dict[str, dict[str, str]] | None = None,
) -> tuple[ConnectorManager, list[Any], list[Any]]:
    applied: list[Any] = []
    built: list[Any] = []

    def rebuild(tools: list[Tool], native_tools: tuple[str, ...] = ()) -> Any:
        built.append(tools)
        return ("ENGINE", tools, native_tools)

    def apply(engine: Any) -> None:
        applied.append(engine)

    mgr = ConnectorManager(
        registry=_registry(),
        instance_store=ConnectorInstanceStore(session_factory, "key"),
        oauth=_FakeOAuth(),  # type: ignore[arg-type]
        deps=ConnectorDeps(session_factory=session_factory, settings=None),  # type: ignore[arg-type]
        rebuild_engine=rebuild,
        apply_engine=apply,
        app_credential_store=AppCredentialStore(session_factory, "key"),
        server_oauth_clients=server_oauth_clients,
    )
    return mgr, applied, built


async def test_catalog_lists_specs_with_status(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    entries = {e.key: e for e in await mgr.catalog()}
    assert set(entries) == {"secret_demo", "oauth_demo"}
    assert entries["secret_demo"].status == "available"
    assert entries["secret_demo"].enabled is False
    assert "tools" in entries["secret_demo"].capabilities
    assert entries["oauth_demo"].auth_kind == "oauth2"


async def test_enable_secret_connects_and_resolves_tools(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, applied, built = _manager(session_factory)
    entry = await mgr.enable_secret("secret_demo", {"api_key": "K"})
    assert entry.status == "connected"
    assert entry.enabled is True
    assert entry.configured_fields == ["api_key"]
    assert applied  # the engine was rebuilt + applied (no restart)
    assert any(t.name == "demo_tool" for t in built[-1])


async def test_enable_secret_missing_required_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    with pytest.raises(ValueError, match="api_key"):
        await mgr.enable_secret("secret_demo", {})


async def test_enable_secret_rejects_unknown_field(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    with pytest.raises(ValueError, match="unknown"):
        await mgr.enable_secret("secret_demo", {"api_key": "K", "bogus": "x"})


async def test_enable_unknown_connector(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    with pytest.raises(UnknownConnectorError):
        await mgr.enable_secret("nope", {})


async def test_failed_health_marks_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    entry = await mgr.enable_secret("secret_demo", {"api_key": "BAD"})
    assert entry.status == "error"
    assert entry.last_error == "bad key"


async def test_disable_and_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    await mgr.enable_secret("secret_demo", {"api_key": "K"})
    disabled = await mgr.disable("secret_demo")
    assert disabled.enabled is False
    assert disabled.status == "disabled"
    await mgr.delete("secret_demo")
    assert (await mgr.detail("secret_demo")).status == "available"


async def test_connector_tools_only_for_enabled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    assert await mgr.connector_tools() == []
    await mgr.enable_secret("secret_demo", {"api_key": "K"})
    assert [t.name for t in await mgr.connector_tools()] == ["demo_tool"]


async def test_start_oauth_stores_client_and_returns_url(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    url = await mgr.start_oauth("oauth_demo", {"client_id": "CID", "client_secret": "SEC"})
    assert url == "https://auth/redirect?state=ST"
    entry = await mgr.detail("oauth_demo")
    assert entry is not None
    assert entry.status == "connecting"
    assert set(entry.configured_fields) == {"client_id", "client_secret"}


async def test_complete_oauth_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, applied, _ = _manager(session_factory)
    await mgr.start_oauth("oauth_demo", {"client_id": "CID", "client_secret": "SEC"})
    entry = await mgr.complete_oauth("oauth_demo", code="CODE", state="ST")
    assert entry.status == "connected"
    assert entry.enabled is True
    assert entry.granted_scopes == ["s.read"]


async def test_complete_oauth_failure_marks_needs_reconnect(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    mgr._oauth.fail_exchange = True  # type: ignore[attr-defined]
    await mgr.start_oauth("oauth_demo", {"client_id": "CID", "client_secret": "SEC"})
    with pytest.raises(ConnectorError):
        await mgr.complete_oauth("oauth_demo", code="CODE", state="ST")
    entry = await mgr.detail("oauth_demo")
    assert entry is not None
    assert entry.status == "needs_reconnect"


async def test_sync_runs_and_records_last_sync(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    await mgr.start_oauth("oauth_demo", {"client_id": "CID", "client_secret": "SEC"})
    await mgr.complete_oauth("oauth_demo", code="C", state="ST")
    result = await mgr.sync("oauth_demo")
    assert result.items == 5
    entry = await mgr.detail("oauth_demo")
    assert entry is not None
    assert entry.last_sync_at is not None


async def test_sync_on_non_ingest_connector_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    await mgr.enable_secret("secret_demo", {"api_key": "K"})
    with pytest.raises(ConnectorError):
        await mgr.sync("secret_demo")


async def test_startup_refreshes_engine(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, applied, _ = _manager(session_factory)
    await mgr.startup()
    assert applied


async def test_server_oauth_client_hides_client_fields(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(
        session_factory,
        server_oauth_clients={"demo": {"client_id": "ENVID", "client_secret": "ENVSEC"}},
    )
    entry = await mgr.detail("oauth_demo")
    assert entry is not None
    assert entry.oauth_server_configured is True
    keys = [f.key for f in entry.config_schema]
    assert "client_id" not in keys
    assert "client_secret" not in keys


async def test_start_oauth_uses_server_client_without_user_input(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(
        session_factory,
        server_oauth_clients={"demo": {"client_id": "ENVID", "client_secret": "ENVSEC"}},
    )
    url = await mgr.start_oauth("oauth_demo", {})  # UI sends no client creds
    assert url == "https://auth/redirect?state=ST"
    inst = await mgr._store.get("oauth_demo")
    assert inst is not None
    assert mgr._store.decrypt_config(inst)["client_id"] == "ENVID"


async def test_without_server_client_fields_are_shown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    entry = await mgr.detail("oauth_demo")
    assert entry is not None
    assert entry.oauth_server_configured is False
    assert "client_id" in [f.key for f in entry.config_schema]


async def test_set_app_credentials_enables_one_click(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    # Before: not configured, client fields visible.
    before = await mgr.detail("oauth_demo")
    assert before is not None
    assert before.oauth_server_configured is False
    # Save the app creds once via the UI path.
    entry = await mgr.set_app_credentials(
        "oauth_demo", {"client_id": "UIID", "client_secret": "UISEC"}
    )
    assert entry.oauth_server_configured is True
    assert "client_id" not in [f.key for f in entry.config_schema]


async def test_set_app_credentials_requires_both(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    with pytest.raises(ValueError, match="client_secret"):
        await mgr.set_app_credentials("oauth_demo", {"client_id": "only"})


async def test_start_oauth_uses_saved_app_credentials(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr, *_ = _manager(session_factory)
    await mgr.set_app_credentials("oauth_demo", {"client_id": "SAVEDID", "client_secret": "S"})
    await mgr.start_oauth("oauth_demo", {})  # no client creds from the UI
    inst = await mgr._store.get("oauth_demo")
    assert inst is not None
    assert mgr._store.decrypt_config(inst)["client_id"] == "SAVEDID"
