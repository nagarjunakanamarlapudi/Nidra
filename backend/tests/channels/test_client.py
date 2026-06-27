import json

import httpx
import respx

from pragya_assistant.channels.telegram.client import TelegramClient


@respx.mock
async def test_send_message_posts_to_telegram() -> None:
    route = respx.post("https://api.telegram.org/bottest-token/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    await TelegramClient("test-token").send_message(12345, "hello")

    assert route.called
    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": 12345, "text": "hello"}
