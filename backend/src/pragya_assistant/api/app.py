"""FastAPI application factory."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pragya_assistant.api.deps import AppComponents, build_components
from pragya_assistant.api.routes import (
    browser_activity,
    chat,
    connectors,
    conversations,
    digests,
    dreams,
    finance,
    health,
    opinions,
    scenarios,
)
from pragya_assistant.channels.telegram import webhook as telegram_webhook
from pragya_assistant.config import Settings
from pragya_assistant.logging_config import configure_logging


def create_app(settings: Settings, *, components: AppComponents | None = None) -> FastAPI:
    """Build the app. Pass ``components`` to inject wiring (tests); otherwise
    the composition root builds it from settings."""
    configure_logging(settings.log_level)
    resolved = components or build_components(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved.connectors is not None:
            await resolved.connectors.startup()
        try:
            yield
        finally:
            if resolved.connectors is not None:
                await resolved.connectors.shutdown()
            await resolved.engine.dispose()

    app = FastAPI(title="Pragya", version="0.1.0", lifespan=lifespan)
    app.state.components = resolved

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def bind_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=str(uuid.uuid4()))
        return await call_next(request)

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(conversations.router)
    app.include_router(digests.router)
    app.include_router(finance.router)
    app.include_router(connectors.router)
    app.include_router(connectors.oauth_router)
    app.include_router(browser_activity.router)
    app.include_router(dreams.router)
    app.include_router(opinions.router)
    app.include_router(scenarios.router)
    app.include_router(telegram_webhook.router)
    return app
