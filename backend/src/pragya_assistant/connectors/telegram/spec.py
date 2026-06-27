"""Telegram connector spec — secret auth (bot token), channel capability."""

from __future__ import annotations

from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
)

TELEGRAM_SPEC = ConnectorSpec(
    key="telegram",
    name="Telegram",
    category="Messaging",
    pitch="Chat with Pragya from Telegram — it answers with your full connected toolset.",
    icon="💬",
    auth=AuthStrategy(kind="secret"),
    capabilities=frozenset({Capability.CHANNEL}),
    config_schema=(
        Field(
            key="bot_token",
            label="Bot Token",
            type="secret",
            help="Create a bot with @BotFather and paste its token.",
        ),
        Field(
            key="allowed_chat_ids",
            label="Allowed Chat IDs",
            required=False,
            help="Comma-separated chat IDs allowed to message the bot (groups are negative).",
        ),
    ),
    docs_url="https://core.telegram.org/bots/features#botfather",
)
