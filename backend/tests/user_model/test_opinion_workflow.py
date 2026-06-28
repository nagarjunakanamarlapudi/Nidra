"""The opinion workflow: the tool-using agent investigates (engine loop fills the
ledger via query tools), then validate -> review -> persist. The end-to-end run is
driven by a LoopEngine + ScriptedChatProvider so the test is deterministic."""

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
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, build_query_tools
from pragya_assistant.user_model.opinion_workflow import (
    OpinionWorkflow,
    ProposedOpinion,
    calibrate,
    review_opinions,
    validate_citations,
)
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore
from tests.fakes import ScriptedChatProvider

KEY = "browser_activity"


def test_validate_dedups_by_trait_keeping_best() -> None:
    facts = [Fact("browser", "search", "a", event_ids=[1], id="f1"),
             Fact("calendar", "event", "b", event_ids=[2], id="f2")]
    ops = [
        ProposedOpinion("intent:x", "weak", 0.5, ["f1"]),
        ProposedOpinion("intent:x", "strong", 0.9, ["f1", "f2"]),
    ]
    snaps = validate_citations(ops, facts)
    assert len(snaps) == 1 and snaps[0].value == "strong"


def test_validate_drops_uncited_and_unresolvable() -> None:
    facts = [Fact("browser", "search", "searched 'tokyo'", event_ids=[1], id="f1")]
    ops = [
        ProposedOpinion("intent:travel", "Tokyo trip", 0.9, ["f1"]),      # ok
        ProposedOpinion("trait:vibes", "mysterious", 0.9, []),             # uncited -> drop
        ProposedOpinion("trait:ghost", "?", 0.9, ["f99"]),                 # bad id -> drop
    ]
    snaps = validate_citations(ops, facts)
    assert [s.trait for s in snaps] == ["intent:travel"]
    s = snaps[0]
    assert s.derivation is not None
    assert s.derivation["event_ids"] == [1] and s.derivation["evidence_fact_ids"] == ["f1"]
    assert s.derivation["method"] == "opinion-workflow"
    assert s.derivation["fact_summaries"] == ["searched 'tokyo'"]
    assert s.derivation["refs"] == []
    assert s.provenance == ["browser"] and s.evidence == 1


def test_confidence_capped_by_evidence() -> None:
    facts = [
        Fact("browser", "search", "a", event_ids=[1], id="f1"),
        Fact("calendar", "event", "b", event_ids=[2], id="f2"),
    ]
    # One source, one citation -> cap 0.5 even though the LLM said 0.99.
    one = validate_citations([ProposedOpinion("x", "v", 0.99, ["f1"])], facts)[0]
    assert one.confidence == 0.5
    # Two citations across two sources -> 0.5 + 0.15 + 0.15 = 0.8.
    two = validate_citations([ProposedOpinion("y", "v", 0.99, ["f1", "f2"])], facts)[0]
    assert two.confidence == 0.8
    assert set(two.provenance) == {"browser", "calendar"}
    # LLM confidence already below the calibrated floor -> kept unchanged.
    low = validate_citations([ProposedOpinion("z", "v", 0.3, ["f1"])], facts)[0]
    assert low.confidence == 0.3  # min() keeps the LLM's lower confidence


def test_calibrate_curve() -> None:
    assert calibrate(1, 1) == 0.5
    assert calibrate(5, 3) == 0.95


# ---------------------------------------------------------------------------
# Reviewer agent
# ---------------------------------------------------------------------------


def _snap(trait: str) -> TraitSnapshot:
    return TraitSnapshot(trait=trait, value="v", confidence=0.8, evidence=1,
                         provenance=["browser"], derivation={"method": "opinion-workflow"})


async def test_review_drops_and_downgrades() -> None:
    snaps = [_snap("intent:travel"), _snap("trait:overreach"), _snap("interest:rust")]

    async def fake(_prompt: str) -> str:
        # fake review only mentions the first two; "interest:rust" is unreviewed
        return (
            '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": -0.1, '
            '"reason": "well supported"}, {"trait": "trait:overreach", "keep": false, '
            '"reason": "evidence does not support this"}]}'
        )

    kept = await review_opinions(snaps, fake)
    assert [s.trait for s in kept] == ["intent:travel", "interest:rust"]
    travel = next(s for s in kept if s.trait == "intent:travel")
    assert travel.confidence == 0.7  # 0.8 - 0.1
    assert travel.derivation is not None
    assert travel.derivation["review"]["reason"] == "well supported"
    assert travel.derivation["review"]["confidence_adjustment"] == -0.1
    # Unreviewed opinion survives untouched, with no review key recorded.
    rust = next(s for s in kept if s.trait == "interest:rust")
    assert "interest:rust" in [s.trait for s in kept]
    assert "review" not in (rust.derivation or {})  # untouched, kept as-is


async def test_review_positive_adjustment_cannot_raise_confidence() -> None:
    snaps = [_snap("intent:travel")]  # _snap sets confidence 0.8

    async def fake(_p: str) -> str:
        return ('{"reviews": [{"trait": "intent:travel", "keep": true, '
                '"confidence_adjustment": 0.3}]}')

    kept = await review_opinions(snaps, fake)
    assert kept[0].confidence == 0.8  # clamped to 0; never raised to 1.1


# ---------------------------------------------------------------------------
# OpinionWorkflow.run — driven end-to-end by the engine's own tool loop
# ---------------------------------------------------------------------------


async def test_workflow_run_persists_reviewed_opinions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Seed a browser search the agent discovers via the query_browsing tool.
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search",
                       ts=dt.datetime(2026, 6, 20, 9), data={"query": "flights to tokyo"})],
    )
    ledger = EvidenceLedger()
    tools = build_query_tools(ledger, browser=events, now=dt.datetime(2026, 6, 27, 12))

    # Script the engine: turn 1 calls query_browsing (fills the ledger with f1),
    # turn 2 emits the final opinions JSON citing f1.
    provider = ScriptedChatProvider([
        ChatResult(
            text="",
            tool_calls=(ToolCall(id="c1", name="query_browsing", arguments={"days": 30}),),
            finish_reason="tool_calls",
            usage={},
        ),
        ChatResult(
            text=('{"opinions": [{"trait": "intent:travel", "value": "Tokyo trip", '
                  '"confidence": 0.9, "evidence_fact_ids": ["f1"]}]}'),
            tool_calls=(),
            finish_reason="stop",
            usage={},
        ),
    ])
    engine = LoopEngine(provider=provider, registry=ToolRegistry(tools), system_prompt="SYS")

    async def review_fn(_p: str) -> str:
        return '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": 0}]}'

    model = UserModelStore(session_factory)
    wf = OpinionWorkflow(model, engine=engine, review_fn=review_fn, ledger=ledger)
    out = await wf.run()

    assert [s.trait for s in out] == ["intent:travel"]
    current = {s.trait: s for s in await model.current_model()}
    snap = current["intent:travel"]
    assert snap.derivation is not None
    assert snap.derivation["evidence_fact_ids"] == ["f1"]
    assert snap.derivation["fact_summaries"] == ["searched 'flights to tokyo'"]
    assert snap.derivation["method"] == "opinion-workflow"
    assert snap.provenance == ["browser"]
    assert len(snap.derivation["event_ids"]) == 1  # the seeded browser row


async def test_workflow_run_no_opinions_is_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Agent returns no opinions -> nothing to validate -> reviewer never called.
    ledger = EvidenceLedger()
    provider = ScriptedChatProvider(
        [ChatResult(text='{"opinions": []}', tool_calls=(), finish_reason="stop", usage={})]
    )
    engine = LoopEngine(provider=provider, registry=ToolRegistry([]), system_prompt="SYS")
    wf = OpinionWorkflow(
        UserModelStore(session_factory), engine=engine, review_fn=_unused, ledger=ledger,
    )
    assert await wf.run() == []


async def _unused(_p: str) -> str:  # pragma: no cover - must never be called
    raise AssertionError("reviewer should not be called when there are no opinions")
