"""Composition root + FastAPI dependencies.

``build_components`` is the single place the app is wired together. Request
handlers depend on small getters that read the wired components off ``app.state``
(so tests can construct components with fakes and skip ``build_components``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.factory import build_engine
from pragya_assistant.agent.tools import Tool
from pragya_assistant.calendars.service import CalendarService
from pragya_assistant.channels.telegram.client import TelegramClient
from pragya_assistant.config import Settings
from pragya_assistant.connectors.base import ConnectorDeps
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.registry import build_default_registry
from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)
from pragya_assistant.digests.service import DigestService
from pragya_assistant.digests.store import DigestStore
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.finance.fx import FxService
from pragya_assistant.finance.service import FinanceService, build_finance_service
from pragya_assistant.llm.factory import build_embedding_provider
from pragya_assistant.memory.conversations import ConversationStore
from pragya_assistant.memory.db import create_engine, create_session_factory
from pragya_assistant.memory.models import EMBEDDING_DIM
from pragya_assistant.memory.service import MemoryService
from pragya_assistant.tasks.store import TaskStore


@dataclass
class AppComponents:
    settings: Settings
    engine: AsyncEngine
    agent: AgentEngine
    conversations: ConversationStore
    digests: DigestService
    telegram: TelegramClient | None = None
    finance: FinanceService | None = None
    fx: FxService | None = None
    connectors: ConnectorManager | None = None


def build_components(settings: Settings) -> AppComponents:
    if settings.llm_embedding_dim != EMBEDDING_DIM:
        raise ValueError(
            f"settings.llm_embedding_dim ({settings.llm_embedding_dim}) must match the schema "
            f"embedding dimension ({EMBEDDING_DIM}). Change the model and regenerate the migration."
        )
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    memory = MemoryService(
        session_factory=session_factory,
        embedder=build_embedding_provider(settings),
        embedding_model=settings.llm_embedding_model,
        embedding_dim=settings.llm_embedding_dim,
    )
    task_store = TaskStore(session_factory)
    calendar_service = (
        CalendarService(settings.calendar_ics_url) if settings.calendar_ics_url else None
    )
    email_service = build_email_service(settings)
    finance = build_finance_service(settings, session_factory)
    agent = build_engine(settings, memory, task_store, calendar_service, email_service)
    telegram = TelegramClient(settings.telegram_bot_token) if settings.telegram_bot_token else None
    digests = DigestService(
        engine=agent,
        store=DigestStore(session_factory),
        telegram=telegram,
        allowed_chat_ids=settings.telegram_allowed_chat_ids,
        timezone=settings.digest_timezone,
    )
    components = AppComponents(
        settings=settings,
        engine=engine,
        agent=agent,
        conversations=ConversationStore(session_factory),
        digests=digests,
        telegram=telegram,
        finance=finance,
        fx=FxService(),
    )

    # --- Connectors platform: registry + encrypted vault + OAuth + manager ---
    # get_agent resolves the *live* engine (rebuilt on connector changes); used by
    # channel connectors (Telegram) so their long-poll worker stays current.
    conn_deps = ConnectorDeps(
        session_factory=session_factory,
        settings=settings,
        get_agent=lambda: components.agent,
        conversations=components.conversations,
        finance=finance,
    )
    registry = build_default_registry(conn_deps)
    oauth = OAuthService(
        OAuthFlowStore(session_factory),
        redirect_base_url=settings.oauth_redirect_base_url or settings.app_base_url,
    )
    instance_store = ConnectorInstanceStore(session_factory, settings.app_secret_key)

    def _rebuild_engine(connector_tools: list[Tool], native_tools: tuple[str, ...]) -> AgentEngine:
        return build_engine(
            settings,
            memory,
            task_store,
            calendar_service,
            email_service,
            connector_tools=connector_tools,
            native_tools=native_tools,
        )

    def _apply_engine(new_engine: AgentEngine) -> None:
        components.agent = new_engine
        components.digests.set_engine(new_engine)

    # Env-provided OAuth app creds, keyed by provider (take precedence over the
    # DB-stored app creds set from the UI).
    server_oauth_clients: dict[str, dict[str, str]] = {}
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        server_oauth_clients["google"] = {
            "client_id": settings.google_oauth_client_id,
            "client_secret": settings.google_oauth_client_secret,
        }

    components.connectors = ConnectorManager(
        registry=registry,
        instance_store=instance_store,
        oauth=oauth,
        deps=conn_deps,
        rebuild_engine=_rebuild_engine,
        apply_engine=_apply_engine,
        app_credential_store=AppCredentialStore(session_factory, settings.app_secret_key),
        server_oauth_clients=server_oauth_clients,
    )
    return components


def get_components(request: Request) -> AppComponents:
    return cast(AppComponents, request.app.state.components)


def get_settings_dep(request: Request) -> Settings:
    return get_components(request).settings


def get_agent(request: Request) -> AgentEngine:
    return get_components(request).agent


def get_conversations(request: Request) -> ConversationStore:
    return get_components(request).conversations


def get_engine(request: Request) -> AsyncEngine:
    return get_components(request).engine


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """A session factory bound to the app's engine — for connector stores that
    own their sessions (browser-activity ingest + dreamer)."""
    return create_session_factory(get_engine(request))


def get_telegram(request: Request) -> TelegramClient | None:
    return get_components(request).telegram


def get_digests(request: Request) -> DigestService:
    return get_components(request).digests


def get_finance(request: Request) -> FinanceService:
    finance = get_components(request).finance
    if finance is None:
        raise HTTPException(status_code=503, detail="Finance not configured")
    return finance


def get_fx(request: Request) -> FxService:
    fx = get_components(request).fx
    if fx is None:
        raise HTTPException(status_code=503, detail="FX service not available")
    return fx


def get_connectors(request: Request) -> ConnectorManager:
    manager = get_components(request).connectors
    if manager is None:
        raise HTTPException(status_code=503, detail="Connectors not available")
    return manager
