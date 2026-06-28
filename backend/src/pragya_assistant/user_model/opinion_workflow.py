# src/pragya_assistant/user_model/opinion_workflow.py
"""The opinion-forming workflow: group -> form -> validate -> review -> persist.

Opinions are LLM-formed but strictly fact-bound: high-confidence, cited, no
imagination (speculation is the dreamer's job). The three LLM stages take an
injected completion fn so tests are deterministic; the deterministic citation
validator is the mechanical anti-hallucination gate, and the reviewer agent is a
skeptical second pass that drops opinions overreaching their evidence."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import structlog

from pragya_assistant.user_model.dreamer import extract_json
from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

logger = structlog.get_logger(__name__)

LlmFn = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class Theme:
    label: str
    fact_ids: list[str]


@dataclass(frozen=True)
class ProposedOpinion:
    trait: str
    value: Any
    confidence: float
    evidence_fact_ids: list[str]


GROUP_SYSTEM = (
    "You are Nidra's fact organizer. Group the given FACTS into a few coherent "
    "themes (e.g. 'evaluating cloud infra', 'travel to Tokyo'). Use ONLY the facts "
    "given; never invent. Keep each fact_id exactly as shown. Respond with ONLY "
    'JSON: {"themes": [{"label": "short label", "fact_ids": ["f1", "f2"]}]}'
)

FORM_SYSTEM = (
    "You are Nidra's opinion former. For each theme, state durable, HIGH-CONFIDENCE "
    "opinions about the user that the facts DIRECTLY support. Each opinion MUST list "
    "the fact_ids it rests on. State nothing the facts don't support. NO speculation, "
    "future-guessing, or unobservable personality traits — omit those (they are "
    "dreams, handled elsewhere). Prefer concrete traits like interest:<topic>, "
    "preference:<x>, routine:<x>, intent:<x>. Respond with ONLY JSON: "
    '{"opinions": [{"trait": "interest:travel", "value": "...", "confidence": 0.85, '
    '"evidence_fact_ids": ["f1"]}]}'
)


def _facts_block(facts: list[Fact]) -> str:
    return "\n".join(f"- {f.id} [{f.source}/{f.kind}]: {f.summary}" for f in facts)


def build_group_prompt(facts: list[Fact]) -> str:
    return f"{GROUP_SYSTEM}\n\nFACTS:\n{_facts_block(facts)}"


def build_form_prompt(themes: list[Theme], facts: list[Fact]) -> str:
    by_id = {f.id: f for f in facts}
    lines = [FORM_SYSTEM, "", "THEMES:"]
    for t in themes:
        lines.append(f"# {t.label}")
        lines += [f"- {i}: {by_id[i].summary}" for i in t.fact_ids if i in by_id]
    return "\n".join(lines)


async def group_facts(facts: list[Fact], fn: LlmFn) -> list[Theme]:
    parsed = extract_json(await fn(build_group_prompt(facts)))
    themes: list[Theme] = []
    for raw in parsed.get("themes", []) if isinstance(parsed, dict) else []:
        if not isinstance(raw, dict):
            continue
        ids = [str(i) for i in raw.get("fact_ids", []) if isinstance(i, str | int)]
        if ids:
            themes.append(Theme(label=str(raw.get("label") or "theme"), fact_ids=ids))
    # Fallback: one theme over all facts, so a parse miss never loses the digest.
    return themes or [Theme(label="all", fact_ids=[f.id for f in facts])]


async def form_opinions(themes: list[Theme], facts: list[Fact], fn: LlmFn) -> list[ProposedOpinion]:
    parsed = extract_json(await fn(build_form_prompt(themes, facts)))
    out: list[ProposedOpinion] = []
    for raw in parsed.get("opinions", []) if isinstance(parsed, dict) else []:
        if not isinstance(raw, dict):
            continue
        trait = str(raw.get("trait") or "").strip()
        if not trait:
            continue
        value = raw.get("value")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        ids = [str(i) for i in raw.get("evidence_fact_ids", []) if isinstance(i, str | int)]
        out.append(ProposedOpinion(trait, value, conf, ids))
    return out


def calibrate(n_citations: int, n_sources: int) -> float:
    """High confidence must be EARNED by evidence — never blindly trust the LLM."""
    return min(
        0.95,
        round(0.5 + 0.15 * (max(1, n_citations) - 1) + 0.15 * (max(1, n_sources) - 1), 2),
    )


def validate_citations(opinions: list[ProposedOpinion], facts: list[Fact]) -> list[TraitSnapshot]:
    by_id = {f.id: f for f in facts}
    snaps: list[TraitSnapshot] = []
    for op in opinions:
        cited = [by_id[i] for i in op.evidence_fact_ids if i in by_id]
        if not cited:  # cite-or-omit: no real evidence -> dropped
            continue
        sources = sorted({f.source for f in cited})
        event_ids = list(dict.fromkeys(eid for f in cited for eid in f.event_ids))
        refs = list(dict.fromkeys(r for f in cited for r in f.refs))
        confidence = min(op.confidence, calibrate(len(cited), len(sources)))
        snaps.append(
            TraitSnapshot(
                trait=op.trait,
                value=op.value,
                confidence=confidence,
                evidence=len(cited),
                provenance=sources,
                derivation={
                    "method": "opinion-workflow",
                    "evidence_fact_ids": [f.id for f in cited],
                    "fact_summaries": [f.summary for f in cited],
                    "event_ids": event_ids,
                    "refs": refs,
                },
            )
        )
    # Dedup by trait — keep the best-supported snapshot so the survivor is deterministic.
    best: dict[str, TraitSnapshot] = {}
    for s in snaps:
        cur = best.get(s.trait)
        if cur is None or (s.confidence, s.evidence) > (cur.confidence, cur.evidence):
            best[s.trait] = s
    return list(best.values())


# ---------------------------------------------------------------------------
# Task 5: reviewer agent + OpinionWorkflow.run
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = (
    "You are Nidra's opinion reviewer — a skeptical second pass. For each opinion, "
    "decide whether the cited evidence ACTUALLY supports the claim. Drop opinions "
    "that overreach the evidence (keep=false); lower confidence when support is thin "
    "(confidence_adjustment in [-1.0, 0.0]). Keep only well-supported opinions. "
    'Respond with ONLY JSON: {"reviews": [{"trait": "...", "keep": true, '
    '"confidence_adjustment": 0.0, "reason": "..."}]}'
)


def build_review_prompt(snaps: list[TraitSnapshot]) -> str:
    lines = [REVIEW_SYSTEM, "", "OPINIONS (with their cited facts):"]
    for s in snaps:
        facts = "; ".join((s.derivation or {}).get("fact_summaries", []))
        lines.append(f"- {s.trait} = {s.value} (conf {s.confidence}) | evidence: {facts}")
    return "\n".join(lines)


async def review_opinions(snaps: list[TraitSnapshot], fn: LlmFn) -> list[TraitSnapshot]:
    if not snaps:
        return []
    parsed = extract_json(await fn(build_review_prompt(snaps)))
    reviews = parsed.get("reviews", []) if isinstance(parsed, dict) else []
    if snaps and not reviews:
        logger.warning("opinion_reviewer_empty", n_snaps=len(snaps))
    by_trait: dict[str, dict[str, Any]] = {
        str(r.get("trait")): r for r in reviews if isinstance(r, dict) and r.get("trait")
    }
    kept: list[TraitSnapshot] = []
    for s in snaps:
        r = by_trait.get(s.trait)
        if r is None:
            kept.append(s)  # unreviewed -> keep as-is (validator already grounded it)
            continue
        if r.get("keep") is False:
            continue
        try:
            adj = max(-1.0, min(0.0, float(r.get("confidence_adjustment", 0.0))))
        except (TypeError, ValueError):
            adj = 0.0
        derivation = dict(s.derivation or {})
        derivation["review"] = {"reason": str(r.get("reason") or ""), "confidence_adjustment": adj}
        kept.append(
            TraitSnapshot(
                trait=s.trait,
                value=s.value,
                confidence=round(max(0.0, s.confidence + adj), 2),
                evidence=s.evidence,
                provenance=s.provenance,
                derivation=derivation,
            )
        )
    return kept


class OpinionWorkflow:
    """group -> form -> validate -> review -> persist. LLM stages are injected."""

    def __init__(
        self, model: UserModelStore, *, group_fn: LlmFn, form_fn: LlmFn, review_fn: LlmFn
    ) -> None:
        self._model = model
        self._group_fn = group_fn
        self._form_fn = form_fn
        self._review_fn = review_fn

    async def run(self, facts: list[Fact]) -> list[TraitSnapshot]:
        if not facts:
            return []
        themes = await group_facts(facts, self._group_fn)
        proposed = await form_opinions(themes, facts, self._form_fn)
        validated = validate_citations(proposed, facts)
        reviewed = await review_opinions(validated, self._review_fn)
        await self._model.write(reviewed)
        return reviewed
