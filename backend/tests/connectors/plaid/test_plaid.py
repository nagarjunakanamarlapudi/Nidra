"""Plaid (Finance) connector — managed_widget wrapper over FinanceService."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.base import ConnectorContext, ConnectorDeps
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.plaid.connector import PlaidConnector
from pragya_assistant.connectors.plaid.spec import PLAID_SPEC
from pragya_assistant.connectors.registry import build_default_registry
from pragya_assistant.connectors.spec import Capability
from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)

_CTX = ConnectorContext(key="plaid", config={})


class _FakeFinance:
    """Enough of FinanceService for the connector + build_finance_tools()."""

    def __init__(self, *, accounts: list[Any] | None = None, synced: int = 3) -> None:
        self._accounts = accounts or []
        self._synced = synced

    async def account_balances(self) -> list[Any]:
        return self._accounts

    async def sync(self) -> int:
        return self._synced


# --- connector unit tests --------------------------------------------------


def test_spec_is_managed_widget_ingest_tools() -> None:
    assert PLAID_SPEC.auth.kind == "managed_widget"
    assert PLAID_SPEC.auth.widget == "plaid"
    assert PLAID_SPEC.capabilities == frozenset({Capability.INGEST, Capability.TOOLS})


async def test_not_configured_when_finance_missing() -> None:
    conn = PlaidConnector(finance=None)
    assert (await conn.test_connection(_CTX)).ok is False
    assert (await conn.sync(_CTX)).items == 0
    assert conn.build_tools(_CTX) == []


async def test_test_connection_reports_linked_accounts() -> None:
    conn = PlaidConnector(finance=_FakeFinance(accounts=[object(), object()]))  # type: ignore[arg-type]
    health = await conn.test_connection(_CTX)
    assert health.ok is True
    assert "2 account" in (health.detail or "")


async def test_test_connection_no_banks_is_not_ok() -> None:
    conn = PlaidConnector(finance=_FakeFinance(accounts=[]))  # type: ignore[arg-type]
    assert (await conn.test_connection(_CTX)).ok is False


async def test_sync_delegates_to_finance() -> None:
    conn = PlaidConnector(finance=_FakeFinance(synced=5))  # type: ignore[arg-type]
    result = await conn.sync(_CTX)
    assert result.items == 5


def test_build_tools_exposes_finance_tools() -> None:
    conn = PlaidConnector(finance=_FakeFinance())  # type: ignore[arg-type]
    names = {t.name for t in conn.build_tools(_CTX)}
    assert {"account_balances", "net_worth", "spending_summary"} <= names


def test_registered_in_default_registry() -> None:
    reg = build_default_registry(ConnectorDeps(session_factory=None, settings=None))  # type: ignore[arg-type]
    assert "plaid" in reg


# --- manager: managed_widget enable + seeding ------------------------------


def _manager(sf: async_sessionmaker[AsyncSession], finance: Any, settings: Any) -> ConnectorManager:
    deps = ConnectorDeps(session_factory=sf, settings=settings, finance=finance)
    return ConnectorManager(
        registry=build_default_registry(deps),
        instance_store=ConnectorInstanceStore(sf, "key"),
        oauth=OAuthService(OAuthFlowStore(sf), redirect_base_url="http://x"),
        deps=deps,
        rebuild_engine=lambda tools, native=(): ("ENGINE", tools, native),
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(sf, "key"),
    )


async def test_enable_secret_accepts_managed_widget(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr = _manager(session_factory, _FakeFinance(accounts=[object()]), settings=None)
    entry = await mgr.enable_secret("plaid", {})  # managed_widget → allowed, empty config
    assert entry.enabled is True
    # finance tools now flow through the connector
    assert any(t.name == "account_balances" for t in await mgr.connector_tools())


async def test_seed_from_env_seeds_plaid_when_configured(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, "key")
    settings = SimpleNamespace(web_search_enabled=False, telegram_bot_token=None)
    mgr = _manager(session_factory, _FakeFinance(), settings)
    await mgr.seed_from_env()
    inst = await store.get("plaid")
    assert inst is not None and inst.enabled is True


async def test_seed_skips_plaid_when_finance_unconfigured(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, "key")
    settings = SimpleNamespace(web_search_enabled=False, telegram_bot_token=None)
    mgr = _manager(session_factory, None, settings)
    await mgr.seed_from_env()
    assert await store.get("plaid") is None
