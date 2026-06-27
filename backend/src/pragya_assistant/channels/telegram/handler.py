"""Route a single Telegram update through the agent and reply.

Shared by the webhook route and the long-polling worker so both behave
identically. Only chat IDs in ``allowed_chat_ids`` are served (the caller supplies
the allow-list — from settings for the webhook, from connector config for the
channel worker).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.memory.conversations import ConversationStore


async def process_telegram_update(
    update: dict[str, Any],
    *,
    allowed_chat_ids: Sequence[int],
    agent: AgentEngine,
    conversations: ConversationStore,
    telegram: TelegramClient | None,
) -> str:
    message = update.get("message")
    if not isinstance(message, dict):
        return "ignored"

    chat_id = (message.get("chat") or {}).get("id")
    text = message.get("text")
    if not isinstance(chat_id, int) or not isinstance(text, str) or not text:
        return "ignored"

    if chat_id not in allowed_chat_ids:
        return "ignored"
    if telegram is None:
        return "unconfigured"

    conversation_id = await conversations.get_or_create_by_external("telegram", str(chat_id))
    history = await conversations.history(conversation_id)
    reply, _ = await agent.respond(history, text)
    await conversations.append(conversation_id, "user", text)
    await conversations.append(conversation_id, "assistant", reply)
    await telegram.send_message(chat_id, reply)
    return "ok"
