"""Telegram channel connector + the manager's channel-worker lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

import httpx
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.base import (
    ConnectorContext,
    ConnectorDeps,
    Health,
    RegisteredConnector,
)
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.registry import ConnectorRegistry, build_default_registry
from pragya_assistant.connectors.spec import AuthStrategy, Capability, ConnectorSpec
from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)
from pragya_assistant.connectors.telegram.connector import TelegramConnector, parse_chat_ids
from pragya_assistant.connectors.telegram.spec import TELEGRAM_SPEC

# --- connector unit tests --------------------------------------------------


def test_spec_is_secret_channel() -> None:
    assert TELEGRAM_SPEC.auth.kind == "secret"
    assert TELEGRAM_SPEC.capabilities == frozenset({Capability.CHANNEL})
    assert {f.key for f in TELEGRAM_SPEC.config_schema} == {"bot_token", "allowed_chat_ids"}


def test_parse_chat_ids() -> None:
    assert parse_chat_ids("111, -456 , junk, 789") == [111, -456, 789]
    assert parse_chat_ids("") == []
    assert parse_chat_ids(None) == []


@respx.mock
async def test_test_connection_calls_getme() -> None:
    respx.get("https://api.telegram.org/botTOK/getMe").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"username": "pragya_bot"}})
    )
    conn = TelegramConnector(get_agent=None, conversations=None)
    health = await conn.test_connection(
        ConnectorContext(key="telegram", config={"bot_token": "TOK"})
    )
    assert health.ok is True
    assert "pragya_bot" in (health.detail or "")


async def test_test_connection_missing_token() -> None:
    conn = TelegramConnector(get_agent=None, conversations=None)
    health = await conn.test_connection(ConnectorContext(key="telegram", config={}))
    assert health.ok is False


def test_registered_in_default_registry() -> None:
    reg = build_default_registry(ConnectorDeps(session_factory=None, settings=None))  # type: ignore[arg-type]
    assert "telegram" in reg


# --- manager channel lifecycle (generic, via a fake channel connector) -----


class _FakeChannelConn:
    def __init__(self, started: asyncio.Event) -> None:
        self._started = started

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)

    async def channel_worker(self, ctx: ConnectorContext) -> None:
        self._started.set()
        await asyncio.Event().wait()  # block until the manager cancels us


def _channel_registry(started: asyncio.Event) -> ConnectorRegistry:
    reg = ConnectorRegistry()
    spec = ConnectorSpec(
        key="fakechan",
        name="Fake Channel",
        category="X",
        pitch="",
        icon="",
        auth=AuthStrategy(kind="none"),
        capabilities=frozenset({Capability.CHANNEL}),
    )
    reg.register(RegisteredConnector(spec=spec, build=lambda deps: _FakeChannelConn(started)))
    return reg


def _manager(registry: ConnectorRegistry, sf: async_sessionmaker[AsyncSession]) -> ConnectorManager:
    deps = ConnectorDeps(session_factory=sf, settings=None)  # type: ignore[arg-type]
    return ConnectorManager(
        registry=registry,
        instance_store=ConnectorInstanceStore(sf, "key"),
        oauth=OAuthService(OAuthFlowStore(sf), redirect_base_url="http://x"),
        deps=deps,
        rebuild_engine=lambda tools, native=(): object(),
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(sf, "key"),
    )


async def test_worker_starts_on_enable_idempotent_refresh_and_stops_on_disable(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    started = asyncio.Event()
    mgr = _manager(_channel_registry(started), session_factory)

    await mgr.enable_secret("fakechan", {})
    task = mgr._channel_tasks["fakechan"]
    assert not task.done()
    await asyncio.wait_for(started.wait(), timeout=1)  # worker actually ran

    await mgr.refresh()  # idempotent: same task, not a second worker
    assert mgr._channel_tasks["fakechan"] is task

    await mgr.disable("fakechan")
    assert "fakechan" not in mgr._channel_tasks
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test_shutdown_cancels_workers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    started = asyncio.Event()
    mgr = _manager(_channel_registry(started), session_factory)
    await mgr.enable_secret("fakechan", {})
    task = mgr._channel_tasks["fakechan"]
    await asyncio.wait_for(started.wait(), timeout=1)

    await mgr.shutdown()
    assert mgr._channel_tasks == {}
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test_seed_from_env_seeds_telegram(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, "key")
    deps = ConnectorDeps(
        session_factory=session_factory,
        settings=SimpleNamespace(  # type: ignore[arg-type]
            telegram_bot_token="TOK",
            telegram_allowed_chat_ids=[111, -22],
            web_search_enabled=False,
        ),
    )
    mgr = ConnectorManager(
        registry=build_default_registry(deps),
        instance_store=store,
        oauth=OAuthService(OAuthFlowStore(session_factory), redirect_base_url="http://x"),
        deps=deps,
        rebuild_engine=lambda tools, native=(): object(),
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(session_factory, "key"),
    )
    await mgr.seed_from_env()
    inst = await store.get("telegram")
    assert inst is not None and inst.enabled is True
    cfg = store.decrypt_config(inst)
    assert cfg["bot_token"] == "TOK"
    assert cfg["allowed_chat_ids"] == "111,-22"
