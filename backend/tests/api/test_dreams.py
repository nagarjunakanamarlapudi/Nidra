"""Dreams API: read active dreams + capture an outcome (which resolves the dream)."""

from __future__ import annotations

import httpx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.memory.db import create_session_factory
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


async def test_dreams_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/dreams")).status_code == 401


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
