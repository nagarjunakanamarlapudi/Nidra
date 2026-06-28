"""Opinions API: refresh forms fact-grounded, cited opinions via the confined,
tool-using opinion agent (never the web-enabled chat engine)."""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import Tool, ToolRegistry
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.llm.types import ChatResult, ToolCall
from pragya_assistant.memory.db import create_session_factory
from pragya_assistant.user_model.store import UserModelStore
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}
KEY = "browser_activity"


async def test_opinions_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/opinions/refresh")).status_code == 401


async def test_opinions_refresh_runs_workflow(
    engine: AsyncEngine, build_test_app: AppBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refresh forms a fact-grounded, cited opinion. The opinion-maker is a
    tool-using agent on a CONFINED engine (``build_opinion_engine``): it calls the
    query tools (which fill the ledger), then emits the opinions JSON; the skeptical
    review runs on a CONFINED completion (``build_confined_completion_fn``). Neither
    touches the web-enabled chat agent, so its provider must stay untouched."""
    from pragya_assistant.api.routes import opinions as opinions_route

    sf = create_session_factory(engine)
    await BrowserActivityEventStore(sf).add_events(
        KEY,
        [
            IngestedEvent(
                client_id="s1",
                event_type="search",
                ts=dt.datetime(2026, 6, 28, 9),
                data={"query": "flights to tokyo"},
            )
        ],
    )
    form = (
        '{"opinions": [{"trait": "intent:travel", "value": "planning a Tokyo trip", '
        '"confidence": 0.9, "evidence_fact_ids": ["f1"]}]}'
    )
    review = '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": 0}]}'

    # The opinion engine: a confined brain that investigates via the real query
    # tools (bound to the route's ledger) then emits the opinions JSON citing f1.
    def fake_opinion_engine(_settings: object, *, tools: list[Tool]) -> object:
        return LoopEngine(
            provider=ScriptedChatProvider([
                ChatResult(
                    text="",
                    tool_calls=(ToolCall(id="c1", name="query_browsing",
                                         arguments={"days": 30}),),
                    finish_reason="tool_calls",
                    usage={},
                ),
                ChatResult(text=form, tool_calls=(), finish_reason="stop", usage={}),
            ]),
            registry=ToolRegistry(tools),
            system_prompt="SYS",
        )

    def fake_confined(_settings: object) -> object:
        async def _complete(_prompt: str) -> str:
            return review

        return _complete

    monkeypatch.setattr(opinions_route, "build_opinion_engine", fake_opinion_engine)
    monkeypatch.setattr(opinions_route, "build_confined_completion_fn", fake_confined)

    provider = ScriptedChatProvider([])  # the web-enabled chat engine must NOT run
    app = build_test_app(provider)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/opinions/refresh", headers=AUTH)
    assert resp.status_code == 200 and resp.json()["traits"] == 1

    current = {s.trait: s for s in await UserModelStore(sf).current_model()}
    assert "intent:travel" in current
    assert current["intent:travel"].derivation["event_ids"] == [1]
    assert provider.calls == []  # the confined opinion agent ran it, not chat
