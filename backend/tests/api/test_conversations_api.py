import httpx
from httpx import ASGITransport

from pragya_assistant.llm.types import ChatResult
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


def _stop(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=(), finish_reason="stop", usage={})


async def test_list_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/conversations")
    assert resp.status_code == 401


async def test_list_and_get_conversation(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([_stop("Hi there")]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        chat = await c.post("/chat", json={"message": "remember milk"}, headers=AUTH)
        cid = chat.json()["conversation_id"]
        listed = await c.get("/conversations", headers=AUTH)
        detail = await c.get(f"/conversations/{cid}", headers=AUTH)

    assert listed.status_code == 200
    assert any(item["id"] == cid and item["title"] == "remember milk" for item in listed.json())

    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "remember milk"),
        ("assistant", "Hi there"),
    ]


async def test_get_unknown_conversation_returns_404(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/conversations/999999", headers=AUTH)
    assert resp.status_code == 404
