"""The opinion workflow: group facts -> form cited opinions (LLM stages are
injected fns returning canned JSON, so the test is deterministic)."""

from __future__ import annotations

from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.opinion_workflow import (
    ProposedOpinion,
    Theme,
    form_opinions,
    group_facts,
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
