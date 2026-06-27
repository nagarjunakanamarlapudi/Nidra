"""Root test fixtures.

Database fixtures are shared across suites (memory, agent, api, channels). They
are *integration* fixtures against a real Postgres+pgvector — point them at one
with ``TEST_DATABASE_URL`` (defaults to the Compose database). Tests that don't
request a db fixture never open a connection.

``build_test_app`` wires a FastAPI app to the test DB and a scripted (fake) LLM,
so route/channel tests run without real model calls.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import ToolRegistry
from pragya_assistant.api.app import create_app
from pragya_assistant.api.deps import AppComponents
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.config import Settings
from pragya_assistant.digests.service import DigestService
from pragya_assistant.digests.store import DigestStore
from pragya_assistant.memory.conversations import ConversationStore
from pragya_assistant.memory.db import create_engine, create_session_factory
from pragya_assistant.memory.models import Base
from tests.fakes import ScriptedChatProvider

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test"
)


async def _ensure_database(url: str) -> None:
    """Create the target database if it doesn't exist (tests use a separate DB
    from dev/smoke data, so the suite never wipes real data)."""
    base, _, target = url.rpartition("/")
    admin = create_async_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{target}"'))
    finally:
        await admin.dispose()


AppBuilder = Callable[..., FastAPI]

_APP_ENV_VARS = (
    "APP_ENV",
    "LOG_LEVEL",
    "APP_SECRET_KEY",
    "API_AUTH_TOKEN",
    "APP_BASE_URL",
    "OAUTH_REDIRECT_BASE_URL",
    "DATABASE_URL",
    "LLM_CHAT_PROVIDER",
    "LLM_CHAT_MODEL",
    "LLM_EMBEDDING_PROVIDER",
    "LLM_EMBEDDING_MODEL",
    "LLM_EMBEDDING_DIM",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OLLAMA_BASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_CHAT_IDS",
    "CORS_ALLOW_ORIGINS",
    "PLAID_CLIENT_ID",
    "PLAID_SECRET",
    "PLAID_ENV",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "FINANCE_WEEKLY_ENABLED",
    "FINANCE_WEEKLY_DAY",
)


@pytest.fixture(autouse=True)
def _clean_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic: ambient app config (a dev's shell, an exported .env)
    must never override what a test sets. TEST_DATABASE_URL is kept on purpose."""
    for key in _APP_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    await _ensure_database(TEST_DATABASE_URL)
    eng = create_engine(TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(engine)


@pytest_asyncio.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as db_session:
        yield db_session


@pytest.fixture
def build_test_app(engine: AsyncEngine) -> AppBuilder:
    def _build(
        provider: ScriptedChatProvider,
        *,
        telegram: TelegramClient | None = None,
        allowed_chat_ids: list[int] | None = None,
    ) -> FastAPI:
        settings = Settings(
            _env_file=None,
            app_secret_key="s",
            api_auth_token="token",
            database_url=TEST_DATABASE_URL,
            telegram_allowed_chat_ids=allowed_chat_ids or [],
            digest_enabled=False,
        )
        agent = LoopEngine(provider=provider, registry=ToolRegistry([]), system_prompt="SYS")
        session_factory = create_session_factory(engine)
        components = AppComponents(
            settings=settings,
            engine=engine,
            agent=agent,
            conversations=ConversationStore(session_factory),
            digests=DigestService(
                engine=agent,
                store=DigestStore(session_factory),
                telegram=telegram,
                allowed_chat_ids=allowed_chat_ids or [],
            ),
            telegram=telegram,
        )
        return create_app(settings, components=components)

    return _build
