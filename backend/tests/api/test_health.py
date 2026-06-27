import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.api.deps import get_engine
from pragya_assistant.api.routes.health import database_ready
from pragya_assistant.memory.db import create_engine
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

_UNREACHABLE_DB = "postgresql+asyncpg://pragya:pragya@localhost:1/pragya"


async def test_health(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_pings_db(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready"}


async def test_database_ready_true(engine: AsyncEngine) -> None:
    assert await database_ready(engine) is True


async def test_database_ready_false_on_unreachable_db() -> None:
    bad = create_engine(_UNREACHABLE_DB)
    try:
        assert await database_ready(bad) is False
    finally:
        await bad.dispose()


async def test_ready_returns_503_when_db_down(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    bad = create_engine(_UNREACHABLE_DB)
    app.dependency_overrides[get_engine] = lambda: bad
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/ready")
    finally:
        await bad.dispose()
    assert resp.status_code == 503
