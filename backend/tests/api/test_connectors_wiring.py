"""End-to-end wiring: enabling a connector re-wires the live agent (no restart)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.guard import GuardedEngine
from pragya_assistant.api.deps import build_components
from pragya_assistant.config import Settings
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.store import ConnectorInstanceStore
from pragya_assistant.memory.db import create_session_factory
from tests.conftest import TEST_DATABASE_URL


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="local",
        app_secret_key="secretkey-secretkey",
        api_auth_token="token",
        database_url=TEST_DATABASE_URL,
        agent_engine="ollama",
        llm_embedding_provider="ollama",
        llm_embedding_model="custom-embed",
        llm_embedding_dim=1536,
    )


async def test_build_components_wires_manager(engine: AsyncEngine) -> None:
    components = build_components(_settings())
    try:
        assert isinstance(components.connectors, ConnectorManager)
    finally:
        await components.engine.dispose()


async def test_enabling_google_calendar_rewires_agent_tools(engine: AsyncEngine) -> None:
    settings = _settings()
    components = build_components(settings)
    try:
        # Enable Google Calendar directly in the vault (skip the live OAuth dance).
        store = ConnectorInstanceStore(create_session_factory(engine), settings.app_secret_key)
        await store.upsert_config(
            "google_calendar",
            {
                "client_id": "c",
                "client_secret": "s",
                "calendar_id": "primary",
                "sync_days_ahead": 30,
                "access_token": "AT",
                "refresh_token": "RT",
            },
            enabled=True,
            status="connected",
            granted_scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        assert components.connectors is not None
        await components.connectors.refresh()

        # The chat agent is guard-wrapped; unwrap to the loop brain that got the
        # newly-enabled calendar tools.
        assert isinstance(components.agent, GuardedEngine)
        chat_brain = components.agent._inner
        assert isinstance(chat_brain, LoopEngine)
        tool_names = {spec.name for spec in chat_brain._registry.specs()}
        assert "gcal_agenda" in tool_names
        assert "gcal_upcoming" in tool_names

        # Security win: the digest runs on a CONFINED engine, NOT the re-wired
        # chat agent — so it never inherits the connector (calendar/web) tools.
        assert components.digests._engine is not components.agent
        digest_brain = components.digests._engine
        assert isinstance(digest_brain, GuardedEngine)
        assert isinstance(digest_brain._inner, LoopEngine)
        digest_tools = {spec.name for spec in digest_brain._inner._registry.specs()}
        assert "gcal_agenda" not in digest_tools and digest_tools == set()
    finally:
        await components.engine.dispose()
