"""ConnectorInstanceStore (encrypted config) + OAuthFlowStore."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)
from pragya_assistant.memory.models import ConnectorAppCredential

KEY = "unit-test-secret-key"


async def test_config_encrypt_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    inst = await store.upsert_config(
        "demo", {"token": "supersecret"}, enabled=True, status="connected"
    )
    assert store.decrypt_config(inst) == {"token": "supersecret"}


async def test_stored_config_is_ciphertext(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("demo", {"token": "supersecret"}, enabled=True, status="connected")
    got = await store.get("demo")
    assert got is not None
    assert got.config != ""
    assert "supersecret" not in got.config  # encrypted at rest


async def test_list_enabled_filters(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("on", {}, enabled=True, status="connected")
    await store.upsert_config("off", {}, enabled=False, status="disabled")
    assert [i.connector_key for i in await store.list_enabled()] == ["on"]


async def test_patch_config_merges(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("demo", {"a": "1", "b": "2"}, enabled=True, status="connected")
    inst = await store.patch_config("demo", {"b": "3", "c": "4"})
    assert inst is not None
    assert store.decrypt_config(inst) == {"a": "1", "b": "3", "c": "4"}


async def test_set_status_and_last_sync(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("demo", {}, enabled=True, status="connected")
    await store.set_status("demo", "error", last_error="boom")
    inst = await store.get("demo")
    assert inst is not None
    assert inst.status == "error"
    assert inst.last_error == "boom"
    when = dt.datetime(2026, 6, 23, 8, 0)
    await store.set_last_sync("demo", when)
    inst = await store.get("demo")
    assert inst is not None
    assert inst.last_sync_at == when


async def test_upsert_updates_existing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("demo", {"v": "1"}, enabled=True, status="connected")
    inst = await store.upsert_config(
        "demo", {"v": "2"}, enabled=True, status="connected", granted_scopes=["s"]
    )
    assert store.decrypt_config(inst) == {"v": "2"}
    assert inst.granted_scopes == ["s"]
    assert len(await store.list_all()) == 1


async def test_delete(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = ConnectorInstanceStore(session_factory, KEY)
    await store.upsert_config("demo", {}, enabled=True, status="connected")
    await store.delete("demo")
    assert await store.get("demo") is None


async def test_oauth_flow_create_then_pop_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    flows = OAuthFlowStore(session_factory)
    await flows.create("state1", "demo", "verifier1")
    got = await flows.pop("state1")
    assert got is not None
    assert got.connector_key == "demo"
    assert got.code_verifier == "verifier1"
    assert await flows.pop("state1") is None  # single-use


async def test_app_credential_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AppCredentialStore(session_factory, KEY)
    assert await store.get("google") is None
    await store.set("google", {"client_id": "CID", "client_secret": "SEC"})
    assert await store.get("google") == {"client_id": "CID", "client_secret": "SEC"}


async def test_app_credential_is_ciphertext(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AppCredentialStore(session_factory, KEY)
    await store.set("google", {"client_id": "CID", "client_secret": "SUPERSECRET"})
    async with session_factory() as s:
        row = await s.get(ConnectorAppCredential, "google")
    assert row is not None
    assert "SUPERSECRET" not in row.config


async def test_app_credential_update_and_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = AppCredentialStore(session_factory, KEY)
    await store.set("google", {"client_id": "A", "client_secret": "1"})
    await store.set("google", {"client_id": "B", "client_secret": "2"})
    updated = await store.get("google")
    assert updated is not None
    assert updated["client_id"] == "B"
    await store.delete("google")
    assert await store.get("google") is None
