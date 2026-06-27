"""Data-access layer — one repository per aggregate.

Repositories ``flush`` but never ``commit``; the unit-of-work boundary belongs
to the caller (the service).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pragya_assistant.memory.models import Note, Person, Preference


class PeopleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        name: str,
        relationship: str | None = None,
        birthday: dt.date | None = None,
        notes: str | None = None,
    ) -> Person:
        person = Person(name=name, relationship=relationship, birthday=birthday, notes=notes)
        self._session.add(person)
        await self._session.flush()
        return person

    async def with_birthdays(self) -> list[Person]:
        result = await self._session.execute(select(Person).where(Person.birthday.is_not(None)))
        return list(result.scalars().all())

    async def find_by_name(self, query: str) -> list[Person]:
        stmt = select(Person).where(Person.name.ilike(f"%{query}%")).order_by(Person.name)
        return list((await self._session.execute(stmt)).scalars().all())

    async def find_one_by_name(self, name: str) -> Person | None:
        stmt = select(Person).where(func.lower(Person.name) == name.lower())
        return (await self._session.execute(stmt)).scalars().first()

    async def update_fields(
        self,
        person: Person,
        relationship: str | None = None,
        birthday: dt.date | None = None,
        notes: str | None = None,
    ) -> Person:
        """Update only the fields that are provided (never wipe with None)."""
        if relationship is not None:
            person.relationship = relationship
        if birthday is not None:
            person.birthday = birthday
        if notes is not None:
            person.notes = notes
        await self._session.flush()
        return person


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, text: str, embedding: list[float]) -> Note:
        note = Note(text=text, embedding=embedding)
        self._session.add(note)
        await self._session.flush()
        return note

    async def semantic_search(
        self, query_embedding: list[float], k: int
    ) -> list[tuple[Note, float]]:
        distance = Note.embedding.cosine_distance(query_embedding)
        stmt = (
            select(Note, distance.label("distance"))
            .where(Note.embedding.is_not(None))
            .order_by(distance)
            .limit(k)
        )
        rows = (await self._session.execute(stmt)).all()
        return [(row[0], float(row[1])) for row in rows]


class PreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, key: str, value: str) -> Preference:
        existing = (
            await self._session.execute(select(Preference).where(Preference.key == key))
        ).scalar_one_or_none()
        if existing is not None:
            existing.value = value
            await self._session.flush()
            return existing
        pref = Preference(key=key, value=value)
        self._session.add(pref)
        await self._session.flush()
        return pref

    async def all_as_dict(self) -> dict[str, str]:
        rows = (await self._session.execute(select(Preference))).scalars().all()
        return {p.key: p.value for p in rows}
