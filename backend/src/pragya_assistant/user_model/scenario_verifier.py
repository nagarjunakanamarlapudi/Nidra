"""The live scenario verifier — reality is the judge.

The online generalization of :mod:`backtest`: instead of replaying history, it
resolves *open* batches against real activity as it arrives. For each batch it
reads activity in ``(batch.created_at, now]`` (point-in-time, no look-ahead) and
corroborates each branch's CORE checkpoint against it.

The honest rules (the load-bearing confounding guard):
  * **confirmed** — the core checkpoint matched real on-platform activity.
  * **refuted** — it did not match AND a competing sibling in the same batch did
    (we mis-ranked observable reality). This is the ONLY path to refuted.
  * **expired** — the horizon elapsed and NO branch in the batch matched. A miss
    on-platform is not evidence we were wrong: the user may have acted on factors
    we cannot observe. So expiry is a weak signal, never a negative.

A confirmed branch emits a real ``scenario_outcome`` activity signal (the one-way
valve, mirroring :class:`DreamFeedbackService`) so it can later ground an Opinion
through the normal grounded path — a scenario is never written as an Opinion. That
emitted signal is excluded from future ground truth (reality-only), so it can
never self-corroborate a later batch. Resolution is idempotent: branches resolve
under ``WHERE status='open'`` and the outcome event upserts on a deterministic id.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.memory.models import Scenario, ScenarioBatch
from pragya_assistant.user_model.backtest import keyword_corroborates
from pragya_assistant.user_model.scenarios import OPEN, ScenarioStore

Corroborates = Callable[[str, str], bool]

# Reality-only ground truth: the activity families a prediction can be checked
# against. Deliberately EXCLUDES ``scenario_outcome`` / ``dream_outcome`` so the
# verifier never corroborates a branch against the system's OWN emitted signals.
ACTIVITY_TYPES: list[str] = ["search", "reading", "interaction", "action"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def text_of(event: Any) -> str:
    """The observable text of an activity event, for corroboration. Mirrors the
    fields :func:`collect_browser_facts` reads (search query, reading title,
    choice value, action milestone/funnel) plus calendar summary/location."""
    data = getattr(event, "data", None) or {}
    parts: list[str] = []
    for key in ("query", "value", "milestone", "funnel", "group"):
        val = data.get(key)
        if val:
            parts.append(str(val))
    for attr in ("title", "summary", "location"):
        val = getattr(event, attr, None)
        if val:
            parts.append(str(val))
    return " ".join(parts)


@dataclass(frozen=True)
class VerifyResult:
    confirmed: int = 0
    refuted: int = 0
    expired: int = 0
    # Batch ids resolved as Case A (a branch confirmed) — the reconciler's input.
    resolved_batches: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class _BatchOutcome:
    confirmed: int = 0
    refuted: int = 0
    expired: int = 0
    case_a: bool = False  # reality spoke on-platform (a branch confirmed)


class ScenarioVerifier:
    def __init__(
        self,
        scenarios: ScenarioStore,
        events: BrowserActivityEventStore,
        *,
        calendar: CalendarEventStore | None = None,
        corroborates: Corroborates = keyword_corroborates,
        connector_key: str = "browser_activity",
        calendar_key: str = "google_calendar",
    ) -> None:
        self._scenarios = scenarios
        self._events = events
        self._calendar = calendar
        self._corroborates = corroborates
        self._key = connector_key
        self._cal_key = calendar_key

    async def verify(self, *, now: dt.datetime | None = None) -> VerifyResult:
        at = now if now is not None else _now()
        confirmed = refuted = expired = 0
        resolved: list[int] = []
        for batch in await self._scenarios.all_open_batches():
            outcome = await self._resolve_batch(batch, now=at)
            confirmed += outcome.confirmed
            refuted += outcome.refuted
            expired += outcome.expired
            if outcome.case_a:
                resolved.append(batch.id)
        return VerifyResult(
            confirmed=confirmed, refuted=refuted, expired=expired, resolved_batches=resolved
        )

    async def _ground_truth(self, since: dt.datetime, before: dt.datetime) -> list[Any]:
        rows: list[Any] = list(
            await self._events.recent(
                self._key, types=ACTIVITY_TYPES, since=since, before=before, limit=1000
            )
        )
        if self._calendar is not None:
            rows.extend(await self._calendar.events_between(self._cal_key, since, before))
        return rows

    async def _resolve_batch(self, batch: ScenarioBatch, *, now: dt.datetime) -> _BatchOutcome:
        if batch.status not in OPEN:  # already terminal — idempotent skip
            return _BatchOutcome()

        pairs = [(e, text_of(e)) for e in await self._ground_truth(batch.created_at, now)]
        matched_ids: dict[int, list[int]] = {}
        matched_txt: dict[int, str] = {}
        for branch in batch.branches:
            core = branch.checkpoints[0] if branch.checkpoints else branch.summary
            hits = [(e, t) for (e, t) in pairs if self._corroborates(core, t)]
            if hits:
                matched_ids[branch.id] = [
                    int(e.id) for (e, _t) in hits if getattr(e, "id", None) is not None
                ]
                matched_txt[branch.id] = hits[0][1]

        if matched_ids:  # CASE A — reality spoke on-platform
            confirmed = refuted = 0
            for branch in batch.branches:
                if branch.id in matched_ids:
                    done = await self._scenarios.resolve_branch(
                        branch.id,
                        status="confirmed",
                        signal="corroborated",
                        matched_event_ids=matched_ids[branch.id],
                        matched_text=matched_txt[branch.id],
                        score=1.0,
                        at=now,
                    )
                    if done:
                        confirmed += 1
                        await self._emit_outcome(batch.id, branch, matched_ids[branch.id], now)
                else:
                    # The ONLY path to refuted: a sibling won, so this branch
                    # mis-ranked OBSERVABLE reality — a usable negative.
                    done = await self._scenarios.resolve_branch(
                        branch.id, status="refuted", signal="mis_ranked_competitor", at=now
                    )
                    if done:
                        refuted += 1
            await self._scenarios.resolve_batch(batch.id, status="resolved", at=now)
            return _BatchOutcome(confirmed=confirmed, refuted=refuted, case_a=True)

        if now >= batch.due_at:  # CASE B — horizon elapsed, no branch matched
            expired = 0
            for branch in batch.branches:
                done = await self._scenarios.resolve_branch(
                    branch.id, status="expired", signal="no_match", at=now
                )
                if done:
                    expired += 1
            # No outcome signal emitted, and the reconciler ignores expired batches:
            # absence of on-platform evidence is not evidence we were wrong.
            await self._scenarios.resolve_batch(batch.id, status="expired", at=now)
            return _BatchOutcome(expired=expired)

        return _BatchOutcome()  # not yet due, no match yet — leave open

    async def _emit_outcome(
        self, batch_id: int, branch: Scenario, matched_event_ids: list[int], now: dt.datetime
    ) -> None:
        await self._events.add_events(
            self._key,
            [
                IngestedEvent(
                    client_id=f"scenario-{branch.id}-confirmed",  # deterministic → idempotent
                    event_type="scenario_outcome",
                    ts=now,
                    source="scenario",
                    data={
                        "batch_id": batch_id,
                        "branch_id": branch.id,
                        "signal": "corroborated",
                        "status": "confirmed",
                        "summary": branch.summary,
                        "matched_event_ids": matched_event_ids,
                    },
                )
            ],
        )
