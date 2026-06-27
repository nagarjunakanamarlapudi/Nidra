"""Telegram channel connector: health probe + the long-polling worker."""

from __future__ import annotations

from collections.abc import Callable

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.channels.telegram.poller import run_poller
from pragya_assistant.connectors.base import ConnectorContext, Health
from pragya_assistant.memory.conversations import ConversationStore


def parse_chat_ids(raw: object) -> list[int]:
    """Parse a comma-separated chat-id string into ints, skipping junk."""
    ids: list[int] = []
    for part in str(raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


class TelegramConnector:
    def __init__(
        self,
        *,
        get_agent: Callable[[], AgentEngine] | None,
        conversations: ConversationStore | None,
    ) -> None:
        self._get_agent = get_agent
        self._conversations = conversations

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        token = str(ctx.config.get("bot_token", ""))
        if not token:
            return Health(ok=False, detail="Missing bot token")
        try:
            me = await TelegramClient(token).get_me()
        except Exception as exc:
            return Health(ok=False, detail=str(exc))
        username = me.get("username")
        return Health(ok=True, detail=f"Connected as @{username}" if username else "Connected")

    async def channel_worker(self, ctx: ConnectorContext) -> None:
        """Long-poll Telegram until cancelled by the manager (on disable)."""
        if self._get_agent is None or self._conversations is None:
            raise RuntimeError("telegram channel worker requires get_agent + conversations deps")
        token = str(ctx.config.get("bot_token", ""))
        await run_poller(
            telegram=TelegramClient(token),
            get_agent=self._get_agent,
            conversations=self._conversations,
            allowed_chat_ids=parse_chat_ids(ctx.config.get("allowed_chat_ids")),
        )
