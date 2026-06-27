import httpx
from httpx import ASGITransport

from pragya_assistant.llm.types import ChatResult
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


def _stop(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=(), finish_reason="stop", usage={})


async def test_digests_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/digests")
    assert resp.status_code == 401


async def test_run_then_list(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("Good morning! No birthdays this week.")]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        run = await c.post("/digests/run", headers=AUTH)
        listed = await c.get("/digests", headers=AUTH)

    assert run.status_code == 200
    body = run.json()
    assert "Good morning" in body["content"]
    assert body["delivered"] == "stored"  # no Telegram configured in tests

    items = listed.json()
    assert items and items[0]["content"] == body["content"]


async def test_run_weekly_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/digests/run-weekly")
    assert resp.status_code == 401


async def test_run_weekly_stores_digest(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("Weekly finance: all green.")]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        run = await c.post("/digests/run-weekly", headers=AUTH)

    assert run.status_code == 200
    body = run.json()
    assert "Weekly finance" in body["content"]
    assert body["delivered"] == "stored"
