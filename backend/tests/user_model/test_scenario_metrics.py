"""The scorecard: hit-rate excludes expired (a no-match isn't a miss); expired_rate
is reported separately; top_branch_accuracy is the headline; the ΔPolicy/ΔState
split separates lesson-driven gains from fresher-Opinion gains."""

from __future__ import annotations

import datetime as dt

from pragya_assistant.memory.models import Scenario, ScenarioBatch
from pragya_assistant.user_model.scenario_metrics import compute_scorecard

NOW = dt.datetime(2026, 6, 28, 12, 0)


def _branch(rank: int, prior: float, status: str) -> Scenario:
    return Scenario(
        summary=f"b{rank}",
        checkpoints=["c"],
        prior=prior,
        rank=rank,
        status=status,
        deadline_at=NOW,
    )


def _batch(
    status: str,
    branches: list[Scenario],
    *,
    lessons_used: int = 0,
    created_at: dt.datetime = NOW,
) -> ScenarioBatch:
    batch = ScenarioBatch(
        status=status, due_at=NOW, lessons_used=lessons_used, created_at=created_at
    )
    batch.branches = branches
    return batch


def test_hit_rate_excludes_expired_and_reports_expired_separately() -> None:
    # Batch A (resolved): rank-1 confirmed, rank-2 refuted → top-branch hit.
    a = _batch("resolved", [_branch(1, 0.7, "confirmed"), _branch(2, 0.3, "refuted")])
    # Batch B (expired): both branches expired (no on-platform evidence).
    b = _batch("expired", [_branch(1, 0.5, "expired"), _branch(2, 0.5, "expired")])
    card = compute_scorecard([a, b], now=NOW, window_days=30)

    assert card["branches"] == {"total": 4, "confirmed": 1, "refuted": 1, "expired": 2, "open": 0}
    assert card["hit_rate"] == 0.5  # 1 confirmed / (1 confirmed + 1 refuted); expired excluded
    assert card["top_branch_accuracy"] == 1.0  # the one resolved batch's rank-1 won
    assert card["expired_rate"] == 0.5  # 1 expired batch / (1 resolved + 1 expired)
    assert card["batches"]["expired"] == 1
    assert card["batches"]["resolved"] == 1


def test_brier_rewards_calibrated_priors() -> None:
    # Confident-and-right (prior .9 confirmed) vs confident-and-wrong (prior .9 refuted).
    right = _batch("resolved", [_branch(1, 0.9, "confirmed")])
    wrong = _batch("resolved", [_branch(1, 0.9, "refuted")])
    # brier = mean[(.9-1)^2, (.9-0)^2] = mean[.01, .81] = .41
    assert compute_scorecard([right, wrong], now=NOW)["brier"] == 0.41


def test_rsi_split_isolates_policy_from_state() -> None:
    with_lessons = _batch(
        "resolved", [_branch(1, 0.6, "confirmed"), _branch(2, 0.4, "refuted")], lessons_used=2
    )
    without = _batch(
        "resolved", [_branch(1, 0.6, "refuted"), _branch(2, 0.4, "confirmed")], lessons_used=0
    )
    rsi = compute_scorecard([with_lessons, without], now=NOW)["rsi"]
    assert rsi["with_lessons"]["top_branch_accuracy"] == 1.0  # rank-1 won
    assert rsi["without_lessons"]["top_branch_accuracy"] == 0.0  # rank-1 lost
    assert rsi["delta_policy_top_branch"] == 1.0


def test_window_excludes_old_batches() -> None:
    old = _batch("resolved", [_branch(1, 1.0, "confirmed")], created_at=dt.datetime(2026, 1, 1))
    card = compute_scorecard([old], now=NOW, window_days=30)
    assert card["batches"]["total"] == 0  # outside the 30-day window
