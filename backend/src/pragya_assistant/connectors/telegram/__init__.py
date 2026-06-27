"""The Telegram connector — a `channel`: an interaction surface, not ingestion.

Wraps the existing long-polling worker. The manager runs `channel_worker` as a
background task while the connector is enabled and cancels it on disable. The
worker uses the live agent engine (via `deps.get_agent`), so Telegram replies
have the full connected toolset (Gmail, Calendar, web search, …).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pragya_assistant.connectors.registry import ConnectorRegistry


def register_telegram(registry: ConnectorRegistry) -> None:
    from pragya_assistant.connectors.base import RegisteredConnector
    from pragya_assistant.connectors.telegram.connector import TelegramConnector
    from pragya_assistant.connectors.telegram.spec import TELEGRAM_SPEC

    registry.register(
        RegisteredConnector(
            spec=TELEGRAM_SPEC,
            build=lambda deps: TelegramConnector(
                get_agent=deps.get_agent, conversations=deps.conversations
            ),
        )
    )
