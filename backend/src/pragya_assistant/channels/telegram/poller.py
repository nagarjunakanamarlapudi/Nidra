"""Long-polling worker: pull Telegram updates and route them through the agent.

Outbound only (``getUpdates``), so it needs no public URL — it runs anywhere the
laptop can reach the Telegram API. Each update goes through the same
:func:`process_telegram_update` the webhook uses.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

import structlog

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.channels.telegram.handler import process_telegram_update
from pragya_assistant.memory.conversations import ConversationStore

log = structlog.get_logger(__name__)


async def run_poller(
    *,
    telegram: TelegramClient,
    get_agent: Callable[[], AgentEngine],
    conversations: ConversationStore,
    allowed_chat_ids: Sequence[int],
    stop: asyncio.Event | None = None,
    poll_timeout: int = 25,
    error_backoff: float = 3.0,
) -> None:
    # ``get_agent`` is resolved per update so the worker always uses the current
    # engine — connector toggles rebuild it without restarting this loop (which
    # would lose the in-memory offset and risk reprocessing the last batch).
    offset: int | None = None
    log.info("telegram_poller_started", allowed_chats=len(allowed_chat_ids))
    while stop is None or not stop.is_set():
        try:
            updates = await telegram.get_updates(
                offset, poll_timeout=poll_timeout, allowed_updates=["message"]
            )
        except Exception:
            log.exception("telegram_getupdates_failed")
            await asyncio.sleep(error_backoff)
            continue

        for update in updates:
            update_id = update.get("update_id")
            try:
                status = await process_telegram_update(
                    update,
                    allowed_chat_ids=allowed_chat_ids,
                    agent=get_agent(),
                    conversations=conversations,
                    telegram=telegram,
                )
                log.info("telegram_update_processed", update_id=update_id, status=status)
            except Exception:
                log.exception("telegram_update_failed", update_id=update_id)
            if isinstance(update_id, int):
                offset = update_id + 1
