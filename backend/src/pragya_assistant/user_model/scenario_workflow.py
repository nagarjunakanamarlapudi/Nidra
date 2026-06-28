"""The scenario-forming workflow: investigate -> validate -> calibrate -> review ->
persist.

Mirrors :class:`OpinionWorkflow`: the engine runs the model<->tool loop (filling
the evidence ledger via the query tools), then this workflow validates the agent's
cited branches against that ledger (cite-or-omit), calibrates the priors (renormalize
+ an exploration cap so no single branch can dominate), runs an optional skeptical
review, scrubs secrets at the persistence boundary, and writes one batch. Branches
are predictions, never beliefs -- they are NEVER written to ``user_model_snapshots``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from typing import Any

import structlog

from pragya_assistant.agent.completion import CompletionFn, extract_json
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.memory.models import ScenarioBatch
from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.opinion_workflow import _scrub_json  # shared secret redactor
from pragya_assistant.user_model.scenarios import (
    NewScenario,
    NewScenarioBatch,
    ScenarioStore,
)

logger = structlog.get_logger(__name__)

# No single branch may exceed this prior — the batch can never collapse onto one
# trajectory, so exploration (and the chance to be surprised) is preserved.
MAX_PRIOR = 0.8


@dataclass(frozen=True)
class ProposedBranch:
    summary: str
    checkpoints: list[str]
    horizon_hours: float
    prior: float
    evidence_fact_ids: list[str]


@dataclass(frozen=True)
class _Branch:
    """A cited branch after citation validation, before prior calibration."""

    summary: str
    checkpoints: list[str]
    prior: float
    horizon_hours: float
    derivation: dict[str, Any]


@dataclass(frozen=True)
class ScenarioRun:
    batch_id: int  # 0 when no branch survived validation (nothing persisted)
    branches: list[NewScenario] = field(default_factory=list)


def validate_branch_citations(branches: list[ProposedBranch], facts: list[Fact]) -> list[_Branch]:
    """Cite-or-omit: drop any branch whose citations don't resolve to ledger facts,
    and build the same evidence-chain ``derivation`` shape as opinions."""
    by_id = {f.id: f for f in facts}
    out: list[_Branch] = []
    for op in branches:
        cited = [by_id[i] for i in op.evidence_fact_ids if i in by_id]
        if not cited:  # cite-or-omit
            continue
        event_ids = list(dict.fromkeys(eid for f in cited for eid in f.event_ids))
        refs = list(dict.fromkeys(r for f in cited for r in f.refs))
        out.append(
            _Branch(
                summary=op.summary,
                checkpoints=op.checkpoints,
                prior=op.prior,
                horizon_hours=op.horizon_hours,
                derivation={
                    "method": "scenario-workflow",
                    "evidence_fact_ids": [f.id for f in cited],
                    "fact_summaries": [f.summary for f in cited],
                    "event_ids": event_ids,
                    "refs": refs,
                },
            )
        )
    return out


def _cap_priors(priors: list[float], cap: float) -> list[float]:
    """Water-fill: clamp each prior to <= ``cap``, redistributing the excess to the
    uncapped branches (proportional to their current mass), so no branch dominates.
    With fewer than two branches there is nothing to redistribute to."""
    p = list(priors)
    n = len(p)
    if n < 2:
        return p
    for _ in range(n + 1):
        over = [i for i in range(n) if p[i] > cap + 1e-9]
        if not over:
            break
        excess = sum(p[i] - cap for i in over)
        for i in over:
            p[i] = cap
        under = [i for i in range(n) if p[i] < cap - 1e-9]
        if not under:
            break
        denom = sum(p[i] for i in under)
        for i in under:
            share = (p[i] / denom) if denom > 0 else (1.0 / len(under))
            p[i] += excess * share
    return p


def calibrate_priors(branches: list[_Branch], *, now: dt.datetime) -> list[NewScenario]:
    """Renormalize priors to sum to 1, apply the exploration cap, freeze the rank
    (1 = top prior), and turn each horizon into a concrete ``deadline_at``."""
    if not branches:
        return []
    raw = [max(0.0, b.prior) for b in branches]
    total = sum(raw)
    norm = [r / total for r in raw] if total > 0 else [1.0 / len(raw)] * len(raw)
    capped = _cap_priors(norm, MAX_PRIOR)
    # Rank by capped prior (desc); original index breaks ties so it is deterministic.
    order = sorted(range(len(capped)), key=lambda i: (-capped[i], i))
    rank_of = {idx: r + 1 for r, idx in enumerate(order)}
    return [
        NewScenario(
            summary=b.summary,
            checkpoints=b.checkpoints,
            prior=round(capped[i], 3),
            rank=rank_of[i],
            deadline_at=now + dt.timedelta(hours=b.horizon_hours),
            derivation=b.derivation,
        )
        for i, b in enumerate(branches)
    ]


REVIEW_SYSTEM = (
    "You are Nidra's scenario reviewer -- a skeptical second pass over predicted "
    "branches. Drop a branch (keep=false) if it is NOT genuinely falsifiable, NOT "
    "distinct from another branch, or NOT supported by the cited evidence. Keep the "
    'rest. Respond with ONLY JSON: {"reviews": [{"summary": "...", "keep": true}]}'
)


def build_branch_review_prompt(branches: list[_Branch]) -> str:
    lines = [REVIEW_SYSTEM, "", "BRANCHES (with checkpoints + cited facts):"]
    for b in branches:
        facts = "; ".join(b.derivation.get("fact_summaries", []))
        lines.append(f"- {b.summary} | checkpoints: {'; '.join(b.checkpoints)} | evidence: {facts}")
    return "\n".join(lines)


async def review_branches(branches: list[_Branch], fn: CompletionFn) -> list[_Branch]:
    if not branches:
        return []
    parsed = extract_json(await fn(build_branch_review_prompt(branches)))
    reviews = parsed.get("reviews", []) if isinstance(parsed, dict) else []
    dropped = {
        str(r.get("summary")) for r in reviews if isinstance(r, dict) and r.get("keep") is False
    }
    return [b for b in branches if b.summary not in dropped]


def _scrub_branch(branch: NewScenario) -> NewScenario:
    """Redact secret-shaped text before persistence. As with opinions, the evidence
    chain is assembled from raw ledger facts that bypass the engine's output guard,
    so re-scrub here (idempotent)."""
    return replace(
        branch,
        summary=_scrub_json(branch.summary),
        checkpoints=_scrub_json(branch.checkpoints),
        derivation=_scrub_json(branch.derivation) if branch.derivation is not None else None,
    )


class ScenarioWorkflow:
    """Drives the tool-using scenario agent -> validate -> calibrate -> review ->
    persist. ``review_fn`` (the skeptical pass) is injected so tests stay
    deterministic; ``track_record`` + ``lesson_texts`` are the in-context RSI signal
    rendered into the kickoff."""

    def __init__(
        self,
        scenarios: ScenarioStore,
        *,
        engine: AgentEngine,
        ledger: Any,
        now: dt.datetime,
        review_fn: CompletionFn | None = None,
        track_record: list[ScenarioBatch] | None = None,
        lesson_texts: list[str] | None = None,
        lessons_used: int = 0,
    ) -> None:
        self._scenarios = scenarios
        self._engine = engine
        self._ledger = ledger
        self._now = now
        self._review_fn = review_fn
        self._track_record = track_record or []
        self._lesson_texts = lesson_texts or []
        self._lessons_used = lessons_used

    async def run(self) -> ScenarioRun:
        # Imported inside run() to avoid the scenario_agent <-> scenario_workflow cycle.
        from pragya_assistant.user_model.scenario_agent import (
            build_scenario_kickoff,
            parse_proposed_branches,
            run_scenario_agent,
        )

        kickoff = build_scenario_kickoff(self._track_record, self._lesson_texts)
        reply = await run_scenario_agent(self._engine, kickoff)
        proposed = parse_proposed_branches(reply)
        validated = validate_branch_citations(proposed, self._ledger.facts)
        if self._review_fn is not None:
            validated = await review_branches(validated, self._review_fn)
        branches = [_scrub_branch(b) for b in calibrate_priors(validated, now=self._now)]
        if not branches:
            return ScenarioRun(batch_id=0, branches=[])
        snapshot = {"facts": [_scrub_json(f.summary) for f in self._ledger.facts]}
        batch_id = await self._scenarios.add_batch(
            NewScenarioBatch(
                branches=branches,
                due_at=max(b.deadline_at for b in branches),
                context_snapshot=snapshot,
                lessons_used=self._lessons_used,
                created_at=self._now,
            )
        )
        return ScenarioRun(batch_id=batch_id, branches=branches)
