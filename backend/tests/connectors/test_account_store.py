"""ConnectorAccountStore: identity-keyed multi-account CRUD."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.store import ConnectorAccountStore


async def test_upsert_creates_then_updates_by_identity(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorAccountStore(session_factory, "key")
    a1 = await store.upsert_by_identity(
        "gmail",
        "work@x.com",
        label="Work",
        config={"access_token": "T1"},
        granted_scopes=["s.read"],
    )
    assert store.decrypt_config(a1)["access_token"] == "T1"
    # same (connector, identity) → update in place, not a duplicate
    a2 = await store.upsert_by_identity(
        "gmail", "work@x.com", label="Work (renamed)", config={"access_token": "T2"}
    )
    assert a2.id == a1.id
    assert a2.label == "Work (renamed)"
    assert store.decrypt_config(a2)["access_token"] == "T2"
    assert len(await store.list_for_connector("gmail")) == 1


async def test_multiple_accounts_per_connector(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorAccountStore(session_factory, "key")
    await store.upsert_by_identity(
        "gmail", "work@x.com", label="Work", config={"access_token": "A"}
    )
    await store.upsert_by_identity(
        "gmail", "home@x.com", label="Home", config={"access_token": "B"}
    )
    accounts = await store.list_for_connector("gmail")
    assert len(accounts) == 2
    assert {a.external_account_id for a in accounts} == {"work@x.com", "home@x.com"}


async def test_list_all_across_connectors(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorAccountStore(session_factory, "key")
    await store.upsert_by_identity("gmail", "a@x.com", label="A", config={})
    await store.upsert_by_identity("google_calendar", "a@x.com", label="A", config={})
    assert len(await store.list_all()) == 2


async def test_set_status_update_config_delete(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConnectorAccountStore(session_factory, "key")
    a = await store.upsert_by_identity(
        "gmail", "x@x.com", label="X", config={"access_token": "OLD"}
    )

    await store.update_config(a.id, {"access_token": "NEW", "refresh_token": "R"})
    await store.set_status(a.id, "needs_reconnect", last_error="expired")
    got = await store.get(a.id)
    assert got is not None
    assert got.status == "needs_reconnect"
    assert got.last_error == "expired"
    assert store.decrypt_config(got) == {"access_token": "NEW", "refresh_token": "R"}

    await store.delete(a.id)
    assert await store.get(a.id) is None
