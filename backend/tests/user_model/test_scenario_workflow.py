"""The scenario workflow: the tool-using agent investigates (engine loop fills the
ledger), then validate (cite-or-omit) -> calibrate (renormalize + exploration cap +
rank) -> review -> persist one batch. Branches are predictions, never Opinions."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import ToolRegistry
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.llm.types import ChatResult, ToolCall
from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.opinion_agent import EvidenceLedger
from pragya_assistant.user_model.scenario_agent import build_scenario_tools
from pragya_assistant.user_model.scenario_workflow import (
    ProposedBranch,
    ScenarioWorkflow,
    _Branch,
    calibrate_priors,
    review_branches,
    validate_branch_citations,
)
from pragya_assistant.user_model.scenarios import ScenarioStore
from tests.fakes import ScriptedChatProvider

KEY = "browser_activity"
NOW = dt.datetime(2026, 6, 28, 12, 0)


def _vb(summary: str, prior: float, horizon: float = 24.0) -> _Branch:
    return _Branch(
        summary=summary,
        checkpoints=[f"{summary} checkpoint"],
        prior=prior,
        horizon_hours=horizon,
        derivation={"method": "scenario-workflow", "fact_summaries": []},
    )


def test_validate_drops_uncited_and_unresolvable() -> None:
    facts = [Fact("browser", "search", "searched 'tokyo'", event_ids=[1], id="f1")]
    proposed = [
        ProposedBranch("books a Tokyo hotel", ["searches hotels"], 24.0, 0.6, ["f1"]),  # ok
        ProposedBranch("buys a car", ["dealer visit"], 24.0, 0.4, []),  # uncited -> drop
        ProposedBranch("ghost", ["x"], 24.0, 0.5, ["f99"]),  # bad id -> drop
    ]
    out = validate_branch_citations(proposed, facts)
    assert [b.summary for b in out] == ["books a Tokyo hotel"]
    assert out[0].derivation["event_ids"] == [1]
    assert out[0].derivation["evidence_fact_ids"] == ["f1"]
    assert out[0].derivation["method"] == "scenario-workflow"


def test_calibrate_normalizes_and_caps_for_exploration() -> None:
    # The model returns a near-certain branch — the cap must preserve exploration.
    out = calibrate_priors([_vb("A", 0.95), _vb("B", 0.05)], now=NOW)
    by = {b.summary: b for b in out}
    assert by["A"].prior <= 0.8  # capped — never collapses onto one branch
    assert by["B"].prior >= 0.2  # received the redistributed mass
    assert abs(sum(b.prior for b in out) - 1.0) < 1e-6  # still a distribution
    assert by["A"].rank == 1 and by["B"].rank == 2  # ranked by prior, frozen
    assert by["A"].deadline_at == NOW + dt.timedelta(hours=24)


def test_calibrate_single_branch_keeps_full_mass() -> None:
    out = calibrate_priors([_vb("only", 0.9)], now=NOW)
    assert out[0].prior == 1.0  # nothing to redistribute to
    assert out[0].rank == 1


async def test_review_drops_non_distinct_branch() -> None:
    async def fake(_prompt: str) -> str:
        return '{"reviews": [{"summary": "B", "keep": false}]}'

    kept = await review_branches([_vb("A", 0.5), _vb("B", 0.5)], fake)
    assert [b.summary for b in kept] == ["A"]


async def test_workflow_run_persists_batch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="s1",
                event_type="search",
                ts=dt.datetime(2026, 6, 20, 9),
                data={"query": "flights to tokyo"},
            )
        ],
    )
    ledger = EvidenceLedger()
    tools = build_scenario_tools(ledger, browser=events, now=dt.datetime(2026, 6, 27, 12))

    branches_json = (
        '{"branches": [{"summary": "books a Tokyo hotel", '
        '"checkpoints": ["searches hotels in tokyo"], "horizon_hours": 48, "prior": 0.9, '
        '"evidence_fact_ids": ["f1"]}, {"summary": "reads more CS papers", '
        '"checkpoints": ["opens arxiv"], "horizon_hours": 24, "prior": 0.1, '
        '"evidence_fact_ids": ["f1"]}]}'
    )
    provider = ScriptedChatProvider(
        [
            ChatResult(
                text="",
                tool_calls=(ToolCall(id="c1", name="query_browsing", arguments={"days": 30}),),
                finish_reason="tool_calls",
                usage={},
            ),
            ChatResult(text=branches_json, tool_calls=(), finish_reason="stop", usage={}),
        ]
    )
    engine = LoopEngine(provider=provider, registry=ToolRegistry(tools), system_prompt="SYS")
    scenarios = ScenarioStore(session_factory)
    run = await ScenarioWorkflow(
        scenarios, engine=engine, ledger=ledger, now=dt.datetime(2026, 6, 27, 12)
    ).run()

    assert run.batch_id > 0
    assert len(run.branches) == 2
    top = min(run.branches, key=lambda b: b.rank)
    assert top.summary == "books a Tokyo hotel"
    assert top.prior <= 0.8  # the near-certain prior was capped
    batch = (await scenarios.open_batches())[0]
    assert batch.branches[0].derivation["evidence_fact_ids"] == ["f1"]
    assert batch.branches[0].derivation["event_ids"] == [1]
    # due_at is the latest deadline (the 48h branch)
    assert batch.due_at == dt.datetime(2026, 6, 27, 12) + dt.timedelta(hours=48)


async def test_workflow_run_no_cited_branches_is_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ledger = EvidenceLedger()
    provider = ScriptedChatProvider(
        [
            ChatResult(
                text=(
                    '{"branches": [{"summary": "x", "checkpoints": ["y"], "prior": 1.0, '
                    '"evidence_fact_ids": ["f404"]}]}'
                ),
                tool_calls=(),
                finish_reason="stop",
                usage={},
            )
        ]
    )
    engine = LoopEngine(provider=provider, registry=ToolRegistry([]), system_prompt="SYS")
    run = await ScenarioWorkflow(
        ScenarioStore(session_factory), engine=engine, ledger=ledger, now=NOW
    ).run()
    assert run.batch_id == 0
    assert run.branches == []
