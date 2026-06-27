"""Web Search connector: no-auth toggle that lights up engine-native tools."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.base import ConnectorContext, ConnectorDeps
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.registry import build_default_registry
from pragya_assistant.connectors.spec import Capability
from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)
from pragya_assistant.connectors.web_search.connector import WebSearchConnector
from pragya_assistant.connectors.web_search.spec import WEB_SEARCH_SPEC


def test_spec_is_no_auth_tools_with_native() -> None:
    assert WEB_SEARCH_SPEC.auth.kind == "none"
    assert WEB_SEARCH_SPEC.capabilities == frozenset({Capability.TOOLS})
    assert WEB_SEARCH_SPEC.native_engine_tools == ("WebSearch", "WebFetch")
    assert WEB_SEARCH_SPEC.config_schema == ()  # nothing to paste


async def test_connector_has_no_inprocess_tools_but_is_healthy() -> None:
    conn = WebSearchConnector()
    ctx = ConnectorContext(key="web_search", config={})
    assert conn.build_tools(ctx) == []  # native, not in-process
    assert (await conn.test_connection(ctx)).ok is True


def test_registered_in_default_registry() -> None:
    reg = build_default_registry(ConnectorDeps(session_factory=None, settings=None))  # type: ignore[arg-type]
    assert "web_search" in reg


def _manager(sf: async_sessionmaker[AsyncSession], settings: object) -> ConnectorManager:
    deps = ConnectorDeps(session_factory=sf, settings=settings)  # type: ignore[arg-type]
    return ConnectorManager(
        registry=build_default_registry(deps),
        instance_store=ConnectorInstanceStore(sf, "key"),
        oauth=OAuthService(OAuthFlowStore(sf), redirect_base_url="http://localhost:8000"),
        deps=deps,
        rebuild_engine=lambda tools, native=(): ("ENGINE", tools, native),
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(sf, "key"),
    )


async def test_native_engine_tools_collected_only_when_enabled(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr = _manager(session_factory, SimpleNamespace(web_search_enabled=False))
    assert await mgr.native_engine_tools() == ()  # nothing enabled yet
    await mgr.enable_secret("web_search", {})  # none-auth → enables with empty config
    assert await mgr.native_engine_tools() == ("WebSearch", "WebFetch")


async def test_seed_from_env_enables_web_search_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, "key")
    mgr = _manager(session_factory, SimpleNamespace(web_search_enabled=True))

    await mgr.seed_from_env()
    inst = await store.get("web_search")
    assert inst is not None and inst.enabled is True
    assert await mgr.native_engine_tools() == ("WebSearch", "WebFetch")

    # Idempotent: a later disable is never undone by re-seeding.
    await mgr.disable("web_search")
    await mgr.seed_from_env()
    inst = await store.get("web_search")
    assert inst is not None and inst.enabled is False


async def test_seed_from_env_noop_when_disabled_in_env(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, "key")
    mgr = _manager(session_factory, SimpleNamespace(web_search_enabled=False))
    await mgr.seed_from_env()
    assert await store.get("web_search") is None
