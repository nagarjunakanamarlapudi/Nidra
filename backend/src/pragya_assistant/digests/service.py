"""Generate, store, and deliver the daily digest."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

import structlog

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.prompts import build_digest_prompt, build_dream_surfacing_block
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.digests.store import DigestStore
from pragya_assistant.memory.models import Digest
from pragya_assistant.user_model.dreams import DreamStore

log = structlog.get_logger(__name__)


class DigestService:
    """Composes the digest via the engine, stores it, and pushes it to Telegram."""

    def __init__(
        self,
        *,
        engine: AgentEngine,
        store: DigestStore,
        telegram: TelegramClient | None = None,
        allowed_chat_ids: list[int] | None = None,
        timezone: str = "UTC",
        dreams: DreamStore | None = None,
    ) -> None:
        self._engine = engine
        self._store = store
        self._telegram = telegram
        self._allowed_chat_ids = allowed_chat_ids or []
        self._timezone = timezone
        self._dreams = dreams

    async def run(self, prompt_builder: Callable[[str], str] = build_digest_prompt) -> Digest:
        today = dt.datetime.now(ZoneInfo(self._timezone)).strftime("%A, %B %d, %Y")
        prompt = prompt_builder(today)
        # Surface active dreams (the digest is the primary action surface): weave
        # them into the prompt and mark them shown so we can later tell acted /
        # ignored. Dreams are suggestions, never asserted as fact.
        if self._dreams is not None:
            active = await self._dreams.active(limit=5)
            if active:
                prompt += build_dream_surfacing_block([d.hypothesis for d in active])
                await self._dreams.mark_surfaced([d.id for d in active])
        reply, _ = await self._engine.respond([], prompt)

        delivered = "stored"
        if self._telegram is not None and self._allowed_chat_ids:
            # Per-chat delivery: one failing chat must not blank the others.
            sent = 0
            for chat_id in self._allowed_chat_ids:
                try:
                    await self._telegram.send_message(chat_id, reply)
                    sent += 1
                except Exception:
                    log.exception("digest_delivery_failed", chat_id=chat_id)
            if sent:
                delivered = "telegram"

        digest = await self._store.add(reply, delivered=delivered)
        log.info("digest_generated", length=len(reply), delivered=delivered)
        return digest

    async def recent(self, limit: int = 20) -> list[Digest]:
        return await self._store.recent(limit)
