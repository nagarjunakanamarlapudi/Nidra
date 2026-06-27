import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.channels.telegram.poller import run_poller
from pragya_assistant.llm.types import Effort, Message
from pragya_assistant.memory.conversations import ConversationStore


class _FakeAgent:
    def __init__(self, reply: str = "hello!") -> None:
        self.reply = reply

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        return self.reply, []


class _FakeTelegram:
    """Returns scripted update batches, then sets ``stop`` and returns empty."""

    def __init__(self, batches: list[list[dict[str, Any]]], stop: asyncio.Event) -> None:
        self._batches = list(batches)
        self._stop = stop
        self.sent: list[tuple[int, str]] = []
        self.offsets: list[int | None] = []

    async def get_updates(
        self, offset: int | None = None, *, poll_timeout: int = 25, allowed_updates: Any = None
    ) -> list[dict[str, Any]]:
        self.offsets.append(offset)
        if self._batches:
            return self._batches.pop(0)
        self._stop.set()
        return []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def _msg(update_id: int, chat_id: int, text: str) -> dict[str, Any]:
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


async def test_poller_processes_and_advances_offset(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    stop = asyncio.Event()
    tg = _FakeTelegram([[_msg(5, 111, "hi")]], stop)
    agent = _FakeAgent("hello!")
    await run_poller(
        telegram=tg,  # type: ignore[arg-type]
        get_agent=lambda: agent,  # type: ignore[arg-type, return-value]
        conversations=ConversationStore(session_factory),
        allowed_chat_ids=[111],
        stop=stop,
    )
    assert tg.sent == [(111, "hello!")]
    assert 6 in tg.offsets  # advanced past update 5


async def test_poller_ignores_non_allowlisted(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    stop = asyncio.Event()
    tg = _FakeTelegram([[_msg(9, 999, "hi")]], stop)
    agent = _FakeAgent("nope")
    await run_poller(
        telegram=tg,  # type: ignore[arg-type]
        get_agent=lambda: agent,  # type: ignore[arg-type, return-value]
        conversations=ConversationStore(session_factory),
        allowed_chat_ids=[111],
        stop=stop,
    )
    assert tg.sent == []
