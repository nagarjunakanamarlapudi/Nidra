"""MemoryService — the memory layer's public API.

Owns the unit of work (a session per operation), runs embeddings through the
pluggable provider, and exposes both exact and semantic recall.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.llm.base import EmbeddingProvider
from pragya_assistant.memory.birthdays import days_until_next_birthday
from pragya_assistant.memory.models import Note, Person, Preference
from pragya_assistant.memory.repositories import (
    NoteRepository,
    PeopleRepository,
    PreferenceRepository,
)


class MemoryService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: EmbeddingProvider,
        embedding_model: str,
        embedding_dim: int,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim

    async def remember_note(self, text: str) -> Note:
        embedding = await self._embed(text)
        async with self._session_factory() as session:
            note = await NoteRepository(session).add(text, embedding)
            await session.commit()
            await session.refresh(note)
            return note

    async def remember_person(
        self,
        name: str,
        relationship: str | None = None,
        birthday: dt.date | None = None,
        notes: str | None = None,
    ) -> Person:
        async with self._session_factory() as session:
            repo = PeopleRepository(session)
            existing = await repo.find_one_by_name(name)
            if existing is not None:
                person = await repo.update_fields(existing, relationship, birthday, notes)
            else:
                person = await repo.add(name, relationship, birthday, notes)
            await session.commit()
            await session.refresh(person)
            return person

    async def set_preference(self, key: str, value: str) -> Preference:
        async with self._session_factory() as session:
            pref = await PreferenceRepository(session).upsert(key, value)
            await session.commit()
            await session.refresh(pref)
            return pref

    async def get_preferences(self) -> dict[str, str]:
        async with self._session_factory() as session:
            return await PreferenceRepository(session).all_as_dict()

    async def find_people(self, query: str) -> list[Person]:
        async with self._session_factory() as session:
            return await PeopleRepository(session).find_by_name(query)

    async def semantic_search(self, query: str, k: int = 5) -> list[tuple[Note, float]]:
        embedding = await self._embed(query)
        async with self._session_factory() as session:
            return await NoteRepository(session).semantic_search(embedding, k)

    async def upcoming_birthdays(
        self, within_days: int, today: dt.date | None = None
    ) -> list[Person]:
        reference = today or dt.date.today()
        async with self._session_factory() as session:
            people = await PeopleRepository(session).with_birthdays()

        scored: list[tuple[int, Person]] = []
        for person in people:
            if person.birthday is None:
                continue
            days = days_until_next_birthday(person.birthday, reference)
            if days <= within_days:
                scored.append((days, person))
        scored.sort(key=lambda item: item[0])
        return [person for _, person in scored]

    async def _embed(self, text: str) -> list[float]:
        [embedding] = await self._embedder.embed([text], model=self._embedding_model)
        if len(embedding) != self._embedding_dim:
            raise ValueError(
                f"Embedding dimension {len(embedding)} does not match the configured "
                f"dimension {self._embedding_dim}"
            )
        return embedding
