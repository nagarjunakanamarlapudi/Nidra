import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pragya_assistant.memory.models import (
    EMBEDDING_DIM,
    Conversation,
    ConversationMessage,
    Note,
    Person,
    Preference,
)


async def test_person_roundtrip(session: AsyncSession) -> None:
    session.add(Person(name="Sister", relationship="sister", birthday=dt.date(1990, 3, 3)))
    await session.commit()

    got = (await session.execute(select(Person))).scalar_one()
    assert got.id is not None
    assert got.name == "Sister"
    assert got.relationship == "sister"
    assert got.birthday == dt.date(1990, 3, 3)
    assert got.created_at is not None


async def test_note_stores_embedding(session: AsyncSession) -> None:
    session.add(Note(text="liked the pasta place", embedding=[0.1] * EMBEDDING_DIM))
    await session.commit()

    got = (await session.execute(select(Note))).scalar_one()
    assert got.text == "liked the pasta place"
    assert got.embedding is not None
    assert len(got.embedding) == EMBEDDING_DIM


async def test_preference_unique_key(session: AsyncSession) -> None:
    session.add(Preference(key="tone", value="concise"))
    await session.commit()

    got = (await session.execute(select(Preference).where(Preference.key == "tone"))).scalar_one()
    assert got.value == "concise"


async def test_conversation_with_messages(session: AsyncSession) -> None:
    conv = Conversation(channel="telegram", external_id="chat-123")
    conv.messages.append(ConversationMessage(role="user", content="hi"))
    conv.messages.append(ConversationMessage(role="assistant", content="hello"))
    session.add(conv)
    await session.commit()

    stored = (await session.execute(select(Conversation))).scalar_one()
    msgs = (
        (
            await session.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversation_id == stored.id)
                .order_by(ConversationMessage.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(m.role, m.content) for m in msgs] == [("user", "hi"), ("assistant", "hello")]
