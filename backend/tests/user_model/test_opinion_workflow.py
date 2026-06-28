"""The opinion workflow: group facts -> form cited opinions (LLM stages are
injected fns returning canned JSON, so the test is deterministic)."""

from __future__ import annotations

from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.opinion_workflow import (
    ProposedOpinion,
    Theme,
    calibrate,
    form_opinions,
    group_facts,
    validate_citations,
)


async def test_group_facts_parses_themes() -> None:
    facts = [Fact("browser", "search", "searched 'tokyo'", event_ids=[1], id="f1")]

    async def fake(_prompt: str) -> str:
        return '{"themes": [{"label": "travel to Tokyo", "fact_ids": ["f1"]}]}'

    themes = await group_facts(facts, fake)
    assert themes == [Theme(label="travel to Tokyo", fact_ids=["f1"])]


async def test_group_facts_falls_back_to_single_theme_on_garbage() -> None:
    facts = [Fact("browser", "search", "x", event_ids=[1], id="f1")]

    async def fake(_prompt: str) -> str:
        return "not json"

    themes = await group_facts(facts, fake)
    assert len(themes) == 1 and themes[0].fact_ids == ["f1"]


async def test_form_opinions_parses_cited_opinions() -> None:
    facts = [Fact("browser", "search", "searched 'tokyo'", event_ids=[1], id="f1")]
    themes = [Theme(label="travel", fact_ids=["f1"])]

    async def fake(_prompt: str) -> str:
        return (
            '{"opinions": [{"trait": "intent:travel", "value": "planning a Tokyo trip", '
            '"confidence": 0.9, "evidence_fact_ids": ["f1"]}]}'
        )

    ops = await form_opinions(themes, facts, fake)
    assert ops == [
        ProposedOpinion(
            trait="intent:travel", value="planning a Tokyo trip",
            confidence=0.9, evidence_fact_ids=["f1"],
        )
    ]


async def test_form_opinions_tolerates_garbage_fields() -> None:
    facts = [Fact("browser", "search", "x", event_ids=[1], id="f1")]
    themes = [Theme(label="t", fact_ids=["f1"])]

    async def fake(_prompt: str) -> str:
        return (
            '{"opinions": ['
            '{"trait": "", "value": 1, "confidence": "high", "evidence_fact_ids": ["f1"]},'
            '{"trait": "intent:x", "value": 1, "confidence": null}'
            ']}'
        )

    ops = await form_opinions(themes, facts, fake)
    assert len(ops) == 1
    assert ops[0].trait == "intent:x"
    assert ops[0].confidence == 0.0
    assert ops[0].evidence_fact_ids == []


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
