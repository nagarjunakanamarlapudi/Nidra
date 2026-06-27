"""Telegram webhook → agent adapter.

Thin route over :func:`process_telegram_update` (shared with the long-polling
worker). Only chat IDs in ``telegram_allowed_chat_ids`` are served; everything
else is ignored with a 200 (Telegram expects 2xx). A future hardening step is
verifying the ``X-Telegram-Bot-Api-Secret-Token``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.api.deps import get_agent, get_conversations, get_settings_dep, get_telegram
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.channels.telegram.handler import process_telegram_update
from pragya_assistant.config import Settings
from pragya_assistant.memory.conversations import ConversationStore

router = APIRouter(tags=["telegram"])


@router.post("/telegram/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    agent: Annotated[AgentEngine, Depends(get_agent)],
    conversations: Annotated[ConversationStore, Depends(get_conversations)],
    telegram: Annotated[TelegramClient | None, Depends(get_telegram)],
) -> dict[str, str]:
    status = await process_telegram_update(
        update,
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
        agent=agent,
        conversations=conversations,
        telegram=telegram,
    )
    return {"status": status}
