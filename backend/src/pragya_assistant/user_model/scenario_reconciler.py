"""The reconciler — recursive self-improvement from mis-ranked predictions.

Runs after the verifier, ONLY over Case-A batches (a branch confirmed) where the
branch we ranked first did NOT win. Pure-``expired`` batches are never reconciled:
by the confounding rule, no on-platform evidence is not evidence we were wrong.

For a mis-ranked batch it (1) asks a confined LLM to *hypothesize* the missing
context (hedged, never asserted as a belief), persists it as the batch diagnosis;
(2) routes the two locked corrections, both respecting the one-way valve —
  (a) ΔState: trigger the grounded opinion-former to re-derive from the new real
      signals (the actual action is already ingested); debounced to once per run.
  (b) a LOW-WEIGHT, DECAYING policy lesson for the next generation prompt.
It NEVER writes an Opinion, a durable memory note, or decays an existing opinion.

``lessons_for_prompt`` is the guardrail that makes a lesson safe: exponential decay
by age, a hard cap on how many are injected, an ε floor so stale ones drop off, and
hedged framing — so one miss can never bias the agent, and exploration is preserved.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pragya_assistant.agent.completion import CompletionFn, extract_json
from pragya_assistant.agent.untrusted import wrap_untrusted
from pragya_assistant.memory.models import Scenario, ScenarioBatch, ScenarioLesson
from pragya_assistant.user_model.scenarios import LessonStore, ScenarioStore

RefreshOpinionsFn = Callable[[], Awaitable[Any]]

# Lesson guardrails: half-life ~2 weeks, at most 3 injected, drop below ε weight.
TAU_DAYS = 14.0
MAX_LESSONS = 3
EPSILON = 0.15

DIAGNOSE_SYSTEM = (
    "You are Nidra's scenario reconciler. A set of competing branches was predicted "
    "from the user's state; reality confirmed a branch we did NOT rank first. Propose "
    "the MOST LIKELY missing context that would have made the winning branch rank "
    "first. HEDGE -- this is a HYPOTHESIS, not a fact: the user may have acted on "
    "factors we cannot observe. Do NOT assert a new durable belief about the user, and "
    "do NOT propose changing any stored opinion. Output ONLY JSON: "
    '{"what_we_missed": "...", "hypothesized_missing_context": "...", "confidence": 0.0}'
)


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def build_diagnosis_prompt(batch: ScenarioBatch, winner: Scenario) -> str:
    lines = ["PREDICTED BRANCHES (prior, rank, outcome):"]
    for b in batch.branches:
        lines.append(f"- {b.summary} (p={b.prior}, rank{b.rank}) -> {b.status}")
    lines.append("")
    lines.append(
        f"WINNING BRANCH (reality confirmed, but we ranked it #{winner.rank}): {winner.summary}"
    )
    matched = (winner.outcome or {}).get("matched_text")
    if matched:
        lines.append(f"MATCHED ACTIVITY: {matched}")
    fenced = wrap_untrusted("scenario outcome", "\n".join(lines))
    return f"{DIAGNOSE_SYSTEM}\n\n{fenced}"


def _decayed_weight(lesson: ScenarioLesson, now: dt.datetime) -> float:
    age_days = max(0.0, (now - lesson.created_at).total_seconds() / 86400.0)
    return float(lesson.base_weight) * math.exp(-age_days / TAU_DAYS)


def lessons_for_prompt(
    lessons: list[ScenarioLesson],
    *,
    now: dt.datetime,
    max_lessons: int = MAX_LESSONS,
    epsilon: float = EPSILON,
) -> list[str]:
    """Decay by age, drop those below ``epsilon``, keep the top-K by weight, and
    render each as a HEDGED hypothesis line. The cap + decay + framing are what keep
    one miss from biasing the agent; lessons are context only, never priors."""
    weighted = [(_decayed_weight(lesson, now), lesson) for lesson in lessons]
    live = [(w, lesson) for (w, lesson) in weighted if w >= epsilon]
    live.sort(key=lambda item: item[0], reverse=True)
    return [
        f"possible missing context: {lesson.hypothesized_missing_context} "
        "(we mis-ranked once before; treat as an exploration hint, not a rule)"
        for _w, lesson in live[:max_lessons]
        if lesson.hypothesized_missing_context.strip()
    ]


@dataclass(frozen=True)
class ReconcileResult:
    diagnosed: int = 0
    lessons: int = 0
    opinions_refreshed: bool = False


class ScenarioReconciler:
    def __init__(
        self,
        scenarios: ScenarioStore,
        lessons: LessonStore,
        *,
        diagnose_fn: CompletionFn,
        refresh_opinions_fn: RefreshOpinionsFn | None = None,
    ) -> None:
        self._scenarios = scenarios
        self._lessons = lessons
        self._diagnose_fn = diagnose_fn
        self._refresh_opinions_fn = refresh_opinions_fn

    async def reconcile(self, batch_ids: list[int]) -> ReconcileResult:
        diagnosed = 0
        created = 0
        for batch_id in batch_ids:
            batch = await self._scenarios.get_batch(batch_id)
            if batch is None or batch.status != "resolved":
                continue
            confirmed = [b for b in batch.branches if b.status == "confirmed"]
            top = min(batch.branches, key=lambda b: b.rank) if batch.branches else None
            if not confirmed or top is None or top.status == "confirmed":
                continue  # we ranked the winner first (or nothing confirmed) — no lesson
            winner = min(confirmed, key=lambda b: b.rank)

            diagnosis = await self._diagnose(batch, winner)
            await self._scenarios.set_diagnosis(batch_id, diagnosis)
            diagnosed += 1
            await self._lessons.add(
                batch_id=batch_id,
                predicted_branches=[
                    {"summary": b.summary, "prior": b.prior, "rank": b.rank} for b in batch.branches
                ],
                what_happened={
                    "winner_summary": winner.summary,
                    "matched_text": (winner.outcome or {}).get("matched_text"),
                },
                hypothesized_missing_context=diagnosis.get("hypothesized_missing_context", ""),
                confidence=_clamp01(diagnosis.get("confidence")),
            )
            created += 1

        refreshed = False
        # ΔState: re-derive Opinions ONCE from the new real signals (debounced) — the
        # always-safe path; the scenario never writes an Opinion itself.
        if created and self._refresh_opinions_fn is not None:
            await self._refresh_opinions_fn()
            refreshed = True
        return ReconcileResult(diagnosed=diagnosed, lessons=created, opinions_refreshed=refreshed)

    async def _diagnose(self, batch: ScenarioBatch, winner: Scenario) -> dict[str, Any]:
        parsed = extract_json(await self._diagnose_fn(build_diagnosis_prompt(batch, winner)))
        if not isinstance(parsed, dict):
            return {"what_we_missed": "", "hypothesized_missing_context": "", "confidence": 0.0}
        return {
            "what_we_missed": str(parsed.get("what_we_missed") or ""),
            "hypothesized_missing_context": str(parsed.get("hypothesized_missing_context") or ""),
            "confidence": _clamp01(parsed.get("confidence")),
        }
