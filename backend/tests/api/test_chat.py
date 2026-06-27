import httpx
import structlog
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.api.deps import get_agent
from pragya_assistant.llm.types import ChatResult, Message
from pragya_assistant.memory.conversations import ConversationStore
from pragya_assistant.memory.db import create_session_factory
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


def _stop(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=(), finish_reason="stop", usage={})


async def test_chat_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("hi")]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/chat", json={"message": "hello"})
    assert resp.status_code == 401


async def test_chat_returns_reply_and_persists(
    engine: AsyncEngine, build_test_app: AppBuilder
) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("Hello there!")]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/chat", json={"message": "hi"}, headers=AUTH)

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Hello there!"
    conversation_id = body["conversation_id"]

    store = ConversationStore(create_session_factory(engine))
    history = await store.history(conversation_id)
    assert [(m.role, m.content) for m in history] == [("user", "hi"), ("assistant", "Hello there!")]


async def test_chat_threads_history_across_turns(build_test_app: AppBuilder) -> None:
    provider = ScriptedChatProvider([_stop("First"), _stop("Second")])
    app = build_test_app(provider)
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/chat", json={"message": "one"}, headers=AUTH)
        cid = first.json()["conversation_id"]
        second = await client.post(
            "/chat", json={"message": "two", "conversation_id": cid}, headers=AUTH
        )

    assert second.json()["reply"] == "Second"
    # the model's 2nd call must have seen the prior turn as history, ending with "two"
    sent = provider.calls[1]["messages"]
    pairs = [(m.role, m.content) for m in sent]
    assert ("user", "one") in pairs
    assert ("assistant", "First") in pairs
    assert pairs[-1] == ("user", "two")


async def test_chat_unknown_conversation_returns_404(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("x")]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/chat", json={"message": "hi", "conversation_id": 999999}, headers=AUTH
        )
    assert resp.status_code == 404


class _FailingEngine:
    async def respond(self, history: list[Message], user_text: str) -> tuple[str, list[Message]]:
        raise RuntimeError("boom")


async def test_chat_returns_502_when_engine_fails(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    app.dependency_overrides[get_agent] = lambda: _FailingEngine()
    with structlog.testing.capture_logs() as logs:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/chat", json={"message": "hi"}, headers=AUTH)
    assert resp.status_code == 502
    assert "engine" in resp.json()["detail"].lower()
    assert any(e["event"] == "chat_engine_failed" for e in logs)


async def test_chat_logs_completion_with_duration(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("ok")]))
    with structlog.testing.capture_logs() as logs:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/chat", json={"message": "hi"}, headers=AUTH)
    done = [e for e in logs if e["event"] == "chat_completed"]
    assert done and "duration_ms" in done[0] and done[0]["engine"] == "LoopEngine"


async def test_chat_forwards_effort_to_engine(build_test_app: AppBuilder) -> None:
    captured: dict[str, str | None] = {}

    class _RecordingEngine:
        async def respond(
            self, history: list[Message], user_text: str, *, effort: str | None = None
        ) -> tuple[str, list[Message]]:
            captured["effort"] = effort
            return "ok", [
                Message(role="user", content=user_text),
                Message(role="assistant", content="ok"),
            ]

    app = build_test_app(ScriptedChatProvider([]))
    app.dependency_overrides[get_agent] = lambda: _RecordingEngine()
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/chat", json={"message": "hi", "effort": "high"}, headers=AUTH)
    assert captured["effort"] == "high"
