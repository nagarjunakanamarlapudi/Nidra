"""Conversation transcript storage.

Persists the visible turn (user + assistant text) per conversation and rebuilds
it as ``llm.types.Message`` history for the agent. Intermediate tool turns are
handled in-memory by the agent loop and are intentionally not persisted.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.llm.types import Message, Role
from pragya_assistant.memory.models import Conversation, ConversationMessage

_TITLE_MAX = 60


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    id: int
    title: str
    created_at: dt.datetime


class ConversationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create(self, channel: str, external_id: str | None = None) -> int:
        async with self._session_factory() as session:
            conversation = Conversation(channel=channel, external_id=external_id)
            session.add(conversation)
            await session.commit()
            return conversation.id

    async def get_or_create_by_external(self, channel: str, external_id: str) -> int:
        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(Conversation).where(
                        Conversation.channel == channel,
                        Conversation.external_id == external_id,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            conversation = Conversation(channel=channel, external_id=external_id)
            session.add(conversation)
            await session.commit()
            return conversation.id

    async def exists(self, conversation_id: int) -> bool:
        async with self._session_factory() as session:
            return await session.get(Conversation, conversation_id) is not None

    async def history(self, conversation_id: int) -> list[Message]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(ConversationMessage)
                        .where(ConversationMessage.conversation_id == conversation_id)
                        .order_by(ConversationMessage.id)
                    )
                )
                .scalars()
                .all()
            )
            return [Message(role=_role(row.role), content=row.content) for row in rows]

    async def list_conversations(
        self, channel: str = "web", limit: int = 50
    ) -> list[ConversationSummary]:
        """Conversations for a channel, newest first, titled by their first user
        message. Conversations with no messages (e.g. a failed turn) are skipped."""
        async with self._session_factory() as session:
            conversations = (
                (
                    await session.execute(
                        select(Conversation)
                        .where(Conversation.channel == channel)
                        .order_by(Conversation.id.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            summaries: list[ConversationSummary] = []
            for conversation in conversations:
                first_user = (
                    await session.execute(
                        select(ConversationMessage.content)
                        .where(
                            ConversationMessage.conversation_id == conversation.id,
                            ConversationMessage.role == "user",
                        )
                        .order_by(ConversationMessage.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if first_user is None:
                    continue
                summaries.append(
                    ConversationSummary(
                        id=conversation.id,
                        title=_title(first_user),
                        created_at=conversation.created_at,
                    )
                )
            return summaries

    async def append(self, conversation_id: int, role: str, content: str) -> None:
        async with self._session_factory() as session:
            session.add(
                ConversationMessage(conversation_id=conversation_id, role=role, content=content)
            )
            await session.commit()


def _role(value: str) -> Role:
    return "assistant" if value == "assistant" else "user"


def _title(content: str, max_len: int = _TITLE_MAX) -> str:
    stripped = content.strip()
    if not stripped:
        return "New conversation"
    first_line = stripped.splitlines()[0]
    return first_line[:max_len] + ("…" if len(first_line) > max_len else "")
