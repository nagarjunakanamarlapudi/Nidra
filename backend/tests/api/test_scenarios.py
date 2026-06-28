"""Scenarios API: /scenarios/run generates competing branches via the confined,
tool-using scenario agent (never the web-enabled chat engine); GET /scenarios lists
open batches with their branches."""

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
from pragya_assistant.user_model.scenarios import NewScenario, NewScenarioBatch, ScenarioStore
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}
KEY = "browser_activity"


async def test_scenarios_requires_token(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/scenarios/run")).status_code == 401
        assert (await c.get("/scenarios")).status_code == 401


async def test_scenarios_run_uses_confined_engine_not_chat(
    engine: AsyncEngine, build_test_app: AppBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/scenarios/run runs the tool-using agent on a CONFINED engine and the review
    on a CONFINED completion — never the web-enabled chat agent, whose provider must
    stay untouched."""
    from pragya_assistant.api.routes import scenarios as scenarios_route

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
    branches_json = (
        '{"branches": [{"summary": "books a Tokyo hotel", "checkpoints": ["searches hotels"], '
        '"horizon_hours": 48, "prior": 0.7, "evidence_fact_ids": ["f1"]}]}'
    )

    def fake_scenario_engine(_settings: object, *, tools: list[Tool]) -> object:
        return LoopEngine(
            provider=ScriptedChatProvider(
                [
                    ChatResult(
                        text="",
                        tool_calls=(
                            ToolCall(id="c1", name="query_browsing", arguments={"days": 30}),
                        ),
                        finish_reason="tool_calls",
                        usage={},
                    ),
                    ChatResult(text=branches_json, tool_calls=(), finish_reason="stop", usage={}),
                ]
            ),
            registry=ToolRegistry(tools),
            system_prompt="SYS",
        )

    def fake_confined(_settings: object) -> object:
        async def _complete(_prompt: str) -> str:
            return '{"reviews": []}'  # keep all

        return _complete

    monkeypatch.setattr(scenarios_route, "build_scenario_engine", fake_scenario_engine)
    monkeypatch.setattr(scenarios_route, "build_confined_completion_fn", fake_confined)

    provider = ScriptedChatProvider([])  # the web-enabled chat engine must NOT run
    app = build_test_app(provider)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/scenarios/run", headers=AUTH)

    assert resp.status_code == 200
    assert resp.json()["branches"] == 1
    assert provider.calls == []  # the confined scenario agent ran it, not chat

    batches = await ScenarioStore(sf).open_batches()
    assert len(batches) == 1
    assert batches[0].branches[0].summary == "books a Tokyo hotel"
    assert batches[0].branches[0].derivation["event_ids"] == [1]


async def test_list_scenarios(engine: AsyncEngine, build_test_app: AppBuilder) -> None:
    sf = create_session_factory(engine)
    await ScenarioStore(sf).add_batch(
        NewScenarioBatch(
            branches=[
                NewScenario(
                    summary="books a hotel",
                    checkpoints=["searches hotels"],
                    prior=0.6,
                    rank=1,
                    deadline_at=dt.datetime(2026, 6, 29, 12),
                )
            ],
            due_at=dt.datetime(2026, 6, 29, 12),
            created_at=dt.datetime(2026, 6, 28, 12),
        )
    )
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        data = (await c.get("/scenarios", headers=AUTH)).json()

    assert len(data["batches"]) == 1
    branch = data["batches"][0]["branches"][0]
    assert branch["summary"] == "books a hotel"
    assert branch["rank"] == 1
    assert branch["status"] == "open"


async def test_verify_resolves_and_reconciles(
    engine: AsyncEngine, build_test_app: AppBuilder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/scenarios/verify confirms the matching branch, refutes the sibling, then the
    reconciler diagnoses the mis-rank and triggers ΔState opinion re-derivation."""
    from pragya_assistant.api.routes import scenarios as scenarios_route

    sf = create_session_factory(engine)
    # Seed relative to real now so the verifier's (created_at, now] window holds.
    base = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    await ScenarioStore(sf).add_batch(
        NewScenarioBatch(
            branches=[
                NewScenario(
                    summary="books Kyoto lodging",
                    checkpoints=["kyoto ryokan booking"],
                    prior=0.6,
                    rank=1,
                    deadline_at=base + dt.timedelta(hours=24),
                ),
                NewScenario(
                    summary="reads the Raft paper",
                    checkpoints=["raft consensus paper"],
                    prior=0.4,
                    rank=2,
                    deadline_at=base + dt.timedelta(hours=24),
                ),
            ],
            due_at=base + dt.timedelta(hours=24),
            created_at=base - dt.timedelta(hours=2),
        )
    )
    await BrowserActivityEventStore(sf).add_events(
        KEY,
        [
            IngestedEvent(
                client_id="a1",
                event_type="search",
                ts=base - dt.timedelta(hours=1),
                data={"query": "raft consensus paper pdf"},
            )
        ],
    )

    refreshed: list[bool] = []

    def fake_confined(_settings: object) -> object:
        async def _complete(_prompt: str) -> str:
            return (
                '{"what_we_missed": "x", "hypothesized_missing_context": "exam Thursday", '
                '"confidence": 0.5}'
            )

        return _complete

    async def fake_form_opinions(_settings: object, _sf: object) -> tuple[int, int]:
        refreshed.append(True)
        return (0, 0)

    monkeypatch.setattr(scenarios_route, "build_confined_completion_fn", fake_confined)
    monkeypatch.setattr(scenarios_route, "form_opinions", fake_form_opinions)

    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = (await c.post("/scenarios/verify", headers=AUTH)).json()

    assert body["confirmed"] == 1
    assert body["refuted"] == 1
    assert body["diagnosed"] == 1
    assert body["lessons"] == 1
    assert body["opinions_refreshed"] is True
    assert refreshed == [True]  # ΔState triggered once


async def test_scorecard(engine: AsyncEngine, build_test_app: AppBuilder) -> None:
    sf = create_session_factory(engine)
    store = ScenarioStore(sf)
    base = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    bid = await store.add_batch(
        NewScenarioBatch(
            branches=[
                NewScenario(summary="A", checkpoints=["c"], prior=0.6, rank=1, deadline_at=base),
                NewScenario(summary="B", checkpoints=["c"], prior=0.4, rank=2, deadline_at=base),
            ],
            due_at=base,
            created_at=base - dt.timedelta(hours=1),
        )
    )
    branches = (await store.open_batches())[0].branches
    rank1 = next(b for b in branches if b.rank == 1)
    rank2 = next(b for b in branches if b.rank == 2)
    await store.resolve_branch(rank1.id, status="confirmed", signal="corroborated", at=base)
    await store.resolve_branch(rank2.id, status="refuted", signal="mis_ranked_competitor", at=base)
    await store.resolve_batch(bid, status="resolved", at=base)

    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        card = (await c.get("/scenarios/scorecard", headers=AUTH)).json()

    assert card["hit_rate"] == 0.5  # 1 confirmed / (1 confirmed + 1 refuted)
    assert card["top_branch_accuracy"] == 1.0  # rank-1 branch won
    assert card["branches"]["confirmed"] == 1
    assert card["branches"]["refuted"] == 1
    assert "rsi" in card
    assert "expired_rate" in card
