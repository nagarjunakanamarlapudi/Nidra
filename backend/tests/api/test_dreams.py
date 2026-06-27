"""Dreams API: read active dreams + capture an outcome (which resolves the dream)."""

from __future__ import annotations

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.memory.db import create_session_factory
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.store import UserModelStore
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}
KEY = "browser_activity"


async def test_dreams_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/dreams")).status_code == 401
        assert (await c.post("/dreams/run")).status_code == 401
        assert (await c.post("/opinions/refresh")).status_code == 401


async def test_opinions_refresh_forms_grounded_opinions(
    engine: AsyncEngine, build_test_app: AppBuilder
) -> None:
    """Deterministic: refresh runs the OpinionFormer over real browser signals."""
    events = BrowserActivityEventStore(create_session_factory(engine))
    await events.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="i1", event_type="interaction", ts=__import__("datetime").datetime(2026, 6, 28, 9),
                data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
                metrics={"latencyMs": 800},
            )
        ],
    )
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/opinions/refresh", headers=AUTH)
    assert resp.status_code == 200 and resp.json()["traits"] >= 1

    model = UserModelStore(create_session_factory(engine))
    traits = {s.trait for s in await model.current_model()}
    assert "preference:payment" in traits  # grounded opinion, written by the former


async def test_list_and_record_outcome(engine: AsyncEngine, build_test_app: AppBuilder) -> None:
    dreams = DreamStore(create_session_factory(engine))
    await dreams.add([NewDream(hypothesis="Planning a Japan trip", kind="foresight", confidence=0.6)])

    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        listed = (await c.get("/dreams", headers=AUTH)).json()["dreams"]
        assert len(listed) == 1 and "Japan trip" in listed[0]["hypothesis"]
        did = listed[0]["id"]

        resp = await c.post(f"/dreams/{did}/outcome", json={"signal": "acted"}, headers=AUTH)
        assert resp.status_code == 200 and resp.json()["status"] == "confirmed"

    # confirmed → off the active list
    assert await dreams.active() == []
    assert (await dreams.track_record())[0].status == "confirmed"
