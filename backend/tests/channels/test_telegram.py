import json
from typing import Any

import httpx
import respx
from httpx import ASGITransport

from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.llm.types import ChatResult
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

SEND_URL = "https://api.telegram.org/bottok/sendMessage"
GET_UPDATES_URL = "https://api.telegram.org/bottok/getUpdates"


def _stop(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=(), finish_reason="stop", usage={})


def _update(chat_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": chat_id, "type": "private"}, "text": text},
    }


async def _post(app: Any, update: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post("/telegram/webhook", json=update)


@respx.mock
async def test_allowed_chat_invokes_agent_and_replies(build_test_app: AppBuilder) -> None:
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    provider = ScriptedChatProvider([_stop("Hi from Pragya")])
    app = build_test_app(provider, telegram=TelegramClient("tok"), allowed_chat_ids=[111])

    resp = await _post(app, _update(111, "hello"))

    assert resp.status_code == 200
    assert len(provider.calls) == 1  # agent was invoked
    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": 111, "text": "Hi from Pragya"}


@respx.mock
async def test_disallowed_chat_is_ignored(build_test_app: AppBuilder) -> None:
    route = respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    provider = ScriptedChatProvider([_stop("should not happen")])
    app = build_test_app(provider, telegram=TelegramClient("tok"), allowed_chat_ids=[111])

    resp = await _post(app, _update(999, "hello"))

    assert resp.status_code == 200
    assert provider.calls == []  # agent NOT invoked
    assert not route.called  # no reply sent


@respx.mock
async def test_non_message_update_is_ignored(build_test_app: AppBuilder) -> None:
    respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    provider = ScriptedChatProvider([])
    app = build_test_app(provider, telegram=TelegramClient("tok"), allowed_chat_ids=[111])

    resp = await _post(app, {"update_id": 2, "edited_message": {"chat": {"id": 111}}})

    assert resp.status_code == 200
    assert provider.calls == []


@respx.mock
async def test_unconfigured_telegram_does_not_crash(build_test_app: AppBuilder) -> None:
    respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    provider = ScriptedChatProvider([_stop("x")])
    app = build_test_app(provider, telegram=None, allowed_chat_ids=[111])

    resp = await _post(app, _update(111, "hi"))

    assert resp.status_code == 200
    assert provider.calls == []  # returns before invoking the agent


@respx.mock
async def test_get_updates_returns_results() -> None:
    respx.post(GET_UPDATES_URL).mock(
        return_value=httpx.Response(
            200, json={"ok": True, "result": [{"update_id": 7, "message": {"text": "hi"}}]}
        )
    )
    updates = await TelegramClient("tok").get_updates(offset=5, poll_timeout=0)
    assert updates == [{"update_id": 7, "message": {"text": "hi"}}]
