from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.digests.store import DigestStore


async def test_add_and_recent_newest_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = DigestStore(session_factory)
    await store.add("first")
    await store.add("second", delivered="telegram")

    recent = await store.recent()
    assert [d.content for d in recent] == ["second", "first"]
    assert recent[0].delivered == "telegram"
    assert recent[1].delivered == "stored"


async def test_recent_respects_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = DigestStore(session_factory)
    for i in range(5):
        await store.add(f"d{i}")
    assert len(await store.recent(limit=3)) == 3
