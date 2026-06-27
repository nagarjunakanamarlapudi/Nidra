import datetime as dt
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.digests.service import DigestService
from pragya_assistant.digests.store import DigestStore
from pragya_assistant.llm.types import Effort, Message


class _FakeEngine:
    def __init__(self, reply: str = "Good morning! Aria's birthday is in 3 days.") -> None:
        self.reply = reply
        self.prompts: list[str] = []

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        self.prompts.append(user_text)
        return self.reply, []


class _FakeTelegram:
    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self._fail = fail

    async def send_message(self, chat_id: int, text: str) -> None:
        if self._fail:
            raise RuntimeError("telegram down")
        self.sent.append((chat_id, text))


async def test_run_stores_and_pushes(session_factory: async_sessionmaker[AsyncSession]) -> None:
    engine = _FakeEngine()
    tg = _FakeTelegram()
    store = DigestStore(session_factory)
    svc = DigestService(engine=engine, store=store, telegram=tg, allowed_chat_ids=[111])

    digest = await svc.run()

    assert "Good morning" in digest.content
    assert digest.delivered == "telegram"
    assert tg.sent == [(111, engine.reply)]
    assert (await store.recent())[0].content == engine.reply
    assert "daily digest" in engine.prompts[0].lower()


async def test_run_stores_when_telegram_not_configured(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = DigestService(
        engine=_FakeEngine(), store=DigestStore(session_factory), telegram=None, allowed_chat_ids=[]
    )
    digest = await svc.run()
    assert digest.delivered == "stored"


async def test_run_survives_telegram_failure(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = DigestService(
        engine=_FakeEngine(),
        store=DigestStore(session_factory),
        telegram=_FakeTelegram(fail=True),
        allowed_chat_ids=[111],
    )
    digest = await svc.run()  # must not raise
    assert digest.delivered == "stored"


async def test_partial_telegram_failure_still_marks_delivered(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    class _PartialTelegram:
        def __init__(self) -> None:
            self.sent: list[int] = []

        async def send_message(self, chat_id: int, text: str) -> None:
            if chat_id == 999:
                raise RuntimeError("cannot post to that chat")
            self.sent.append(chat_id)

    tg = _PartialTelegram()
    svc = DigestService(
        engine=_FakeEngine(),
        store=DigestStore(session_factory),
        telegram=tg,  # type: ignore[arg-type]
        allowed_chat_ids=[111, 999],
    )
    digest = await svc.run()
    assert digest.delivered == "telegram"  # 111 succeeded even though 999 failed
    assert tg.sent == [111]


async def test_digest_date_uses_configured_timezone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    engine = _FakeEngine()
    svc = DigestService(
        engine=engine, store=DigestStore(session_factory), timezone="America/Los_Angeles"
    )
    await svc.run()
    expected = dt.datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%A, %B %d, %Y")
    assert expected in engine.prompts[0]


async def test_run_with_custom_prompt_builder(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """run(prompt_builder) uses the supplied builder instead of the default."""
    from pragya_assistant.agent.prompts import build_weekly_finance_prompt

    engine = _FakeEngine(reply="Weekly finance summary: all good.")
    store = DigestStore(session_factory)
    svc = DigestService(engine=engine, store=store)

    digest = await svc.run(build_weekly_finance_prompt)

    assert digest.content == "Weekly finance summary: all good."
    assert "weekly finance" in engine.prompts[0].lower()
    assert (await store.recent())[0].content == digest.content
