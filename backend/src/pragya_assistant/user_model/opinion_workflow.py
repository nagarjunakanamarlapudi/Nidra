# src/pragya_assistant/user_model/opinion_workflow.py
"""The opinion-forming workflow: investigate -> validate -> review -> persist.

The opinion-maker is now a tool-using agent (see ``opinion_agent``): the engine
runs the model<->tool loop itself, the query tools fill an ``EvidenceLedger``, and
this workflow validates the agent's cited opinions against that ledger, runs the
skeptical reviewer pass, and persists. Opinions stay strictly fact-bound: high-
confidence, cited, no imagination (speculation is the dreamer's job). The
deterministic citation validator is the mechanical anti-hallucination gate; the
reviewer agent drops opinions overreaching their evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from pragya_assistant.agent.completion import CompletionFn, extract_json
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

if TYPE_CHECKING:  # avoid the opinion_agent <-> opinion_workflow import cycle at runtime
    from pragya_assistant.user_model.opinion_agent import EvidenceLedger

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ProposedOpinion:
    trait: str
    value: Any
    confidence: float
    evidence_fact_ids: list[str]


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


async def review_opinions(snaps: list[TraitSnapshot], fn: CompletionFn) -> list[TraitSnapshot]:
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
    """Drives the tool-using opinion agent -> validate -> review -> persist.

    The engine runs the model<->tool loop itself; the query tools fill ``ledger``
    (the citable universe). We then resolve the agent's cited opinions against the
    ledger, run the reviewer pass, and persist. ``review_fn`` is a one-shot
    completion (the skeptical second pass), injected so tests stay deterministic."""

    def __init__(
        self,
        model: UserModelStore,
        *,
        engine: AgentEngine,
        review_fn: CompletionFn,
        ledger: EvidenceLedger,
    ) -> None:
        self._model = model
        self._engine = engine
        self._review_fn = review_fn
        self._ledger = ledger

    async def run(self) -> list[TraitSnapshot]:
        # Imported inside run() to avoid the opinion_agent <-> opinion_workflow cycle.
        from pragya_assistant.user_model.opinion_agent import (
            parse_proposed_opinions,
            run_opinion_agent,
        )

        reply = await run_opinion_agent(self._engine)  # engine loop fills the ledger via tools
        proposed = parse_proposed_opinions(reply)
        validated = validate_citations(proposed, self._ledger.facts)
        reviewed = await review_opinions(validated, self._review_fn)
        await self._model.write(reviewed)
        return reviewed
