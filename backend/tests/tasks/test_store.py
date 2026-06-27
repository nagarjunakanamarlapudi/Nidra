import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.tasks.store import TaskStore


async def test_add_and_list_excludes_done(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = TaskStore(session_factory)
    a = await store.add("buy milk")
    b = await store.add("pay rent", due_date=dt.date(2026, 6, 25))

    assert [t.title for t in await store.list_tasks()] == ["buy milk", "pay rent"]
    assert a.done is False
    assert b.due_date == dt.date(2026, 6, 25)

    await store.complete(a.id)
    assert [t.title for t in await store.list_tasks()] == ["pay rent"]
    assert {t.title for t in await store.list_tasks(include_done=True)} == {"buy milk", "pay rent"}


async def test_complete_missing_returns_none(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    assert await TaskStore(session_factory).complete(999) is None


async def test_due_includes_overdue_and_today_only(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = TaskStore(session_factory)
    today = dt.date(2026, 6, 20)
    await store.add("overdue", due_date=dt.date(2026, 6, 18))
    await store.add("due today", due_date=today)
    await store.add("future", due_date=dt.date(2026, 6, 25))
    await store.add("someday")  # no due date
    done = await store.add("done one", due_date=dt.date(2026, 6, 19))
    await store.complete(done.id)

    assert [t.title for t in await store.due(within_days=0, today=today)] == [
        "overdue",
        "due today",
    ]
    assert [t.title for t in await store.due(within_days=7, today=today)] == [
        "overdue",
        "due today",
        "future",
    ]
