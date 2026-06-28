"""Dreams API: read active dreams + capture an outcome (which resolves the dream)."""

from __future__ import annotations

import httpx
import pytest
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
        assert (await c.post("/dreams/run")).status_code == 401


async def test_dreams_run_uses_confined_engine_not_chat(
    build_test_app: AppBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/dreams/run` runs on a CONFINED completion (no tools/web), never the
    web-enabled chat agent. The chat provider is empty here, so if the route ever
    fell back to the chat engine it would error — proving the confined path."""
    from pragya_assistant.api.routes import dreams as dreams_route

    used: dict[str, bool] = {}

    def fake_confined(_settings: object) -> object:
        async def _complete(_prompt: str) -> str:
            used["confined"] = True
            return (
                '{"dreams": [{"hypothesis": "You will plan a spring trip", '
                '"kind": "foresight", "confidence": 0.6}]}'
            )

        return _complete

    monkeypatch.setattr(dreams_route, "build_confined_completion_fn", fake_confined)

    provider = ScriptedChatProvider([])  # the chat engine would raise if invoked
    app = build_test_app(provider)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/dreams/run", headers=AUTH)

    assert resp.status_code == 200
    assert used.get("confined") is True  # the confined engine ran the dreamer
    assert provider.calls == []  # the web-enabled chat engine was never invoked
    assert resp.json()["dreams"][0]["hypothesis"] == "You will plan a spring trip"


async def test_list_and_record_outcome(engine: AsyncEngine, build_test_app: AppBuilder) -> None:
    dreams = DreamStore(create_session_factory(engine))
    await dreams.add(
        [NewDream(hypothesis="Planning a Japan trip", kind="foresight", confidence=0.6)]
    )

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
