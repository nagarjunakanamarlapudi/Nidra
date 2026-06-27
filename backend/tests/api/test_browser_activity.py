"""Browser-activity ingest + dream sit behind the global app bearer token."""

from __future__ import annotations

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.memory.db import create_session_factory
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

KEY = "browser_activity"
AUTH = {"Authorization": "Bearer token"}  # build_test_app sets api_auth_token="token"


async def test_ingest_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/connectors/browser_activity/ingest",
            json={"events": [{"type": "search", "id": "1", "data": {"query": "x"}}]},
        )
    assert resp.status_code == 401


async def test_ingest_rejects_bad_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/connectors/browser_activity/ingest",
            json={"events": []},
            headers={"Authorization": "Bearer wrong"},
        )
    assert resp.status_code == 401


async def test_ingest_stores_events(engine: AsyncEngine, build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/connectors/browser_activity/ingest",
            json={
                "events": [
                    {"type": "search", "id": "1", "ts": 1782000000000, "data": {"query": "raft"}},
                    {"type": "reading", "id": "2", "source": "medium", "data": {"title": "X"}},
                ]
            },
            headers=AUTH,
        )
    assert resp.status_code == 200
    assert resp.json()["ingested"] == 2
    store = BrowserActivityEventStore(create_session_factory(engine))
    assert await store.count(KEY) == 2


async def test_ingest_persists_engagement_metrics(
    engine: AsyncEngine, build_test_app: AppBuilder
) -> None:
    """The extension's measured dwell/scroll survives the ingest boundary (was dropped)."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/connectors/browser_activity/ingest",
            json={
                "events": [
                    {
                        "type": "reading",
                        "id": "r1",
                        "data": {"title": "Deep read"},
                        "metrics": {"dwellMs": 360000, "scrollPct": 0.95, "readPct": 0.95},
                    }
                ]
            },
            headers=AUTH,
        )
    assert resp.status_code == 200
    store = BrowserActivityEventStore(create_session_factory(engine))
    row = (await store.recent(KEY))[0]
    assert row.metrics == {"dwellMs": 360000, "scrollPct": 0.95, "readPct": 0.95}


async def test_ingest_persists_context_id_and_new_types(
    engine: AsyncEngine, build_test_app: AppBuilder
) -> None:
    """interaction/impression/action events with a context_id ingest and persist."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/connectors/browser_activity/ingest",
            json={
                "events": [
                    {
                        "type": "interaction",
                        "id": "x1",
                        "context_id": "ctx-9",
                        "data": {"action": "toggle_on", "control": "toggle", "label": "Add-on"},
                    }
                ]
            },
            headers=AUTH,
        )
    assert resp.status_code == 200
    store = BrowserActivityEventStore(create_session_factory(engine))
    row = (await store.recent(KEY, types=["interaction"]))[0]
    assert row.context_id == "ctx-9"
    assert row.data == {"action": "toggle_on", "control": "toggle", "label": "Add-on"}


async def test_dream_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/connectors/browser_activity/dream")
    assert resp.status_code == 401
