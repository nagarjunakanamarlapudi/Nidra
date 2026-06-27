from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.conversations import ConversationStore


async def test_create_then_empty_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    cid = await store.create("web")
    assert isinstance(cid, int)
    assert await store.history(cid) == []
    assert await store.exists(cid) is True


async def test_append_and_history(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    cid = await store.create("web")
    await store.append(cid, "user", "hi")
    await store.append(cid, "assistant", "hello")
    history = await store.history(cid)
    assert [(m.role, m.content) for m in history] == [("user", "hi"), ("assistant", "hello")]


async def test_get_or_create_by_external_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    first = await store.get_or_create_by_external("telegram", "123")
    again = await store.get_or_create_by_external("telegram", "123")
    other = await store.get_or_create_by_external("telegram", "456")
    assert first == again
    assert other != first


async def test_exists_false_for_unknown(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    assert await store.exists(987654) is False


async def test_list_conversations_titles_and_recency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    a = await store.create("web")
    await store.append(a, "user", "first chat about coffee")
    await store.append(a, "assistant", "ok")
    b = await store.create("web")
    await store.append(b, "user", "second chat")

    summaries = await store.list_conversations()
    assert [s.id for s in summaries] == [b, a]  # most recent first
    assert summaries[0].title == "second chat"
    assert summaries[1].title == "first chat about coffee"


async def test_list_conversations_skips_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    empty = await store.create("web")  # e.g. a failed turn left this with no messages
    full = await store.create("web")
    await store.append(full, "user", "hello")
    ids = [s.id for s in await store.list_conversations()]
    assert full in ids
    assert empty not in ids


async def test_list_conversations_filters_to_channel(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = ConversationStore(session_factory)
    web = await store.create("web")
    await store.append(web, "user", "web msg")
    tg = await store.get_or_create_by_external("telegram", "1")
    await store.append(tg, "user", "tg msg")
    ids = [s.id for s in await store.list_conversations()]  # defaults to web
    assert web in ids
    assert tg not in ids
