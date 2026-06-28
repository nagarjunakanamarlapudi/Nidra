"""Scenario scorecard — the falsifiable measure of how well we model the user.

Computed over a trailing window. The honest-verification rules carry into the
math: **expired branches are excluded from the hit-rate** (a no-match on-platform
is not a miss), and ``expired_rate`` is surfaced *separately* as an observability
gap, not a failure. ``top_branch_accuracy`` (did our highest-prior branch win?) is
the headline RSI metric; the ΔPolicy/ΔState split buckets resolved batches by
whether policy lessons were injected, so improvement from in-context lessons is
not confused with improvement from fresher Opinions.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from pragya_assistant.memory.models import Scenario, ScenarioBatch
from pragya_assistant.user_model.scenarios import ScenarioStore


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _safe_div(num: float, den: float) -> float:
    return round(num / den, 3) if den else 0.0


def _top_branch_confirmed(batch: ScenarioBatch) -> bool:
    if not batch.branches:
        return False
    return min(batch.branches, key=lambda b: b.rank).status == "confirmed"


def _brier(branches: Sequence[Scenario]) -> float:
    """Mean squared error of the prior vs. the realized outcome, over resolved
    branches (outcome = 1 if confirmed, else 0). Lower is better-calibrated."""
    scored = [
        (b.prior, 1.0 if b.status == "confirmed" else 0.0)
        for b in branches
        if b.status in ("confirmed", "refuted")
    ]
    if not scored:
        return 0.0
    return round(sum((p - o) ** 2 for p, o in scored) / len(scored), 3)


def _bucket_stats(batches: Sequence[ScenarioBatch]) -> dict[str, Any]:
    branches = [br for b in batches for br in b.branches]
    confirmed = sum(1 for br in branches if br.status == "confirmed")
    refuted = sum(1 for br in branches if br.status == "refuted")
    return {
        "batches": len(batches),
        "top_branch_accuracy": _safe_div(
            sum(1 for b in batches if _top_branch_confirmed(b)), len(batches)
        ),
        "hit_rate": _safe_div(confirmed, confirmed + refuted),
    }


def compute_scorecard(
    batches: Sequence[ScenarioBatch], *, now: dt.datetime, window_days: int = 30
) -> dict[str, Any]:
    cutoff = now - dt.timedelta(days=window_days)
    in_window = [b for b in batches if b.created_at is not None and b.created_at >= cutoff]
    branches = [br for b in in_window for br in b.branches]

    batch_counts = {
        "total": len(in_window),
        "open": sum(1 for b in in_window if b.status == "open"),
        "resolved": sum(1 for b in in_window if b.status == "resolved"),
        "expired": sum(1 for b in in_window if b.status == "expired"),
    }
    branch_counts = {
        "total": len(branches),
        "confirmed": sum(1 for br in branches if br.status == "confirmed"),
        "refuted": sum(1 for br in branches if br.status == "refuted"),
        "expired": sum(1 for br in branches if br.status == "expired"),
        "open": sum(1 for br in branches if br.status == "open"),
    }

    resolved_batches = [b for b in in_window if b.status == "resolved"]
    # confirmed / (confirmed + refuted) — expired excluded (the confounding rule).
    resolved_branch_count = branch_counts["confirmed"] + branch_counts["refuted"]
    return {
        "window_days": window_days,
        "batches": batch_counts,
        "branches": branch_counts,
        "hit_rate": _safe_div(branch_counts["confirmed"], resolved_branch_count),
        "top_branch_accuracy": _safe_div(
            sum(1 for b in resolved_batches if _top_branch_confirmed(b)), len(resolved_batches)
        ),
        "brier": _brier(branches),
        # Separate signal: how often the user acted off-platform (we couldn't see it).
        "expired_rate": _safe_div(
            batch_counts["expired"], batch_counts["resolved"] + batch_counts["expired"]
        ),
        "rsi": _rsi_split(resolved_batches),
    }


def _rsi_split(resolved_batches: Sequence[ScenarioBatch]) -> dict[str, Any]:
    """Separate ΔPolicy (in-context lessons helped) from ΔState (fresher Opinions
    helped). Fresher Opinions lift both buckets; the marginal lift in the
    with-lessons bucket is the policy's own contribution."""
    with_lessons = _bucket_stats([b for b in resolved_batches if b.lessons_used > 0])
    without_lessons = _bucket_stats([b for b in resolved_batches if b.lessons_used == 0])
    return {
        "with_lessons": with_lessons,
        "without_lessons": without_lessons,
        "delta_policy_top_branch": round(
            with_lessons["top_branch_accuracy"] - without_lessons["top_branch_accuracy"], 3
        ),
    }


async def scenario_scorecard(
    store: ScenarioStore, *, window_days: int = 30, now: dt.datetime | None = None
) -> dict[str, Any]:
    at = now if now is not None else _now()
    return compute_scorecard(await store.all_batches(), now=at, window_days=window_days)
