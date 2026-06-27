import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.service import MemoryService
from tests.fakes import FakeEmbeddingProvider


def _service(
    session_factory: async_sessionmaker[AsyncSession], *, dim: int = 1536
) -> MemoryService:
    return MemoryService(
        session_factory=session_factory,
        embedder=FakeEmbeddingProvider(dim=dim),
        embedding_model="fake",
        embedding_dim=1536,
    )


async def test_set_preference_upserts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    await svc.set_preference("tone", "concise")
    await svc.set_preference("tone", "warm")  # overwrite, not duplicate
    assert await svc.get_preferences() == {"tone": "warm"}


async def test_remember_note_embeds_and_stores(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    note = await svc.remember_note("liked the pasta place downtown")
    assert note.id is not None
    assert note.embedding is not None
    assert len(note.embedding) == 1536


async def test_semantic_search_ranks_by_overlap(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    await svc.remember_note("I love the pasta place downtown")
    await svc.remember_note("meeting notes about quarterly taxes")
    results = await svc.semantic_search("pasta place", k=2)
    assert results[0][0].text == "I love the pasta place downtown"
    assert results[0][1] <= results[1][1]  # smallest distance first


async def test_upcoming_birthdays_within_window(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    today = dt.date(2026, 6, 20)
    await svc.remember_person("Sister", relationship="sister", birthday=dt.date(1990, 6, 25))
    await svc.remember_person("Cousin", relationship="cousin", birthday=dt.date(1992, 1, 1))
    soon = await svc.upcoming_birthdays(within_days=10, today=today)
    assert [p.name for p in soon] == ["Sister"]


async def test_find_people_by_partial_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    await svc.remember_person("Alice Johnson")
    await svc.remember_person("Bob Smith")
    found = await svc.find_people("alice")
    assert [p.name for p in found] == ["Alice Johnson"]


async def test_remember_person_upserts_by_name(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    await svc.remember_person("Sister", birthday=dt.date(1990, 7, 4))
    # Same person again (different case, partial fields) must update, not duplicate.
    await svc.remember_person("sister", relationship="sister")

    people = await svc.find_people("sister")
    assert len(people) == 1
    assert people[0].relationship == "sister"
    assert people[0].birthday == dt.date(1990, 7, 4)  # preserved, not wiped by None


async def test_embedding_dimension_mismatch_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory, dim=8)  # embedder returns wrong-size vectors
    with pytest.raises(ValueError, match="dimension"):
        await svc.remember_note("x")
