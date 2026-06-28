# Opinion-Forming Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the deterministic trait heuristics with a fact-grounded, LLM opinion-forming workflow: deterministic fact digest → grouping agent → opinion-forming agent → citation-grounding validator → reviewer agent → persist.

**Architecture:** A deterministic `FactDigestBuilder` gathers cited `Fact`s from every source except finance (browser, calendar, email, memory). Three injected LLM stages (group, form, review) bracket a deterministic citation validator. Opinions persist to `user_model_snapshots` with the existing `derivation` evidence chain. Invoked manually via `POST /opinions/refresh` and hourly via cron, with the same engine selection as the dreamer.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg, pytest (`uv run pytest`), ruff, mypy. LLM via the injected `engine_dream_fn(agent)` (claude-code default) / `ollama_dream_fn` (when `AGENT_ENGINE=ollama`).

## Global Constraints

- Run all backend commands from `/Users/nagarjuna/projects/Nidra/backend`.
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- `uv run ruff check src tests` and `uv run mypy src` must stay clean.
- Opinions are **fact-bound**: every opinion cites `evidence_fact_ids`; uncited opinions are dropped. No imagination (speculation is the dreamer's job).
- LLM stages take an injected `LlmFn = Callable[[str], Awaitable[str]]` so tests are deterministic. Reuse `extract_json` from `pragya_assistant.user_model.dreamer`.
- `Fact.id` handles are per-run (`f1`, `f2`, …) assigned by the builder.
- Confidence is capped by evidence: `calibrate(n_citations, n_sources) = min(0.95, round(0.5 + 0.15*(max(1,n_citations)-1) + 0.15*(max(1,n_sources)-1), 2))`.
- No new DB migration — `user_model_snapshots.derivation` already exists (migration 0018).

---

## File Structure

**New:**
- `src/pragya_assistant/user_model/facts.py` — `Fact` + pure per-source collectors + `FactDigestBuilder` + `PreferenceReader`.
- `src/pragya_assistant/user_model/opinion_workflow.py` — `LlmFn`, `Theme`, `ProposedOpinion`, stage prompts, `OpinionWorkflow`, `calibrate`.
- `tests/user_model/test_facts.py`
- `tests/user_model/test_opinion_workflow.py`

**Modified:**
- `src/pragya_assistant/api/routes/dreams.py` — `/opinions/refresh` runs `OpinionWorkflow`.
- `src/pragya_assistant/agent/activity_tools.py` — `_format_trait` counts `refs` too.
- `src/pragya_assistant/config.py` — `opinions_enabled`, `opinions_minute`.
- `infra/cron/entrypoint.sh`, `infra/docker-compose.yml`, `infra/.env.example`.
- `tests/api/test_dreams.py` — update the `/opinions/refresh` test.

**Deleted (the retired deterministic opinion layer):**
- `src/pragya_assistant/connectors/browser_activity/derive.py` + `tests/connectors/browser_activity/test_derive.py`
- `src/pragya_assistant/user_model/extractors.py` + `tests/user_model/test_extractors.py`
- `src/pragya_assistant/user_model/opinions.py` + `tests/user_model/test_opinions.py`

---

## Task 1: `Fact` + browser & calendar fact collectors + builder

**Files:**
- Create: `src/pragya_assistant/user_model/facts.py`
- Test: `tests/user_model/test_facts.py`

**Interfaces:**
- Produces: `Fact(id, source, kind, summary, event_ids: list[int], refs: list[str])`; pure `collect_browser_facts(rows) -> list[Fact]`, `collect_calendar_facts(events) -> list[Fact]`; `FactDigestBuilder(*, browser=None, calendar=None, email=None, prefs=None, tasks=None, browser_key="browser_activity", calendar_key="google_calendar", now: dt.datetime).build() -> list[Fact]` (assigns `f{n}` ids).

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_facts.py
"""The fact digest builder gathers cited facts from every source except finance."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.facts import FactDigestBuilder, collect_browser_facts

KEY = "browser_activity"


def test_collect_browser_facts_shapes_searches_and_choices() -> None:
    rows = [
        SimpleNamespace(id=1, event_type="search", data={"query": "flights to tokyo"},
                        title=None, domain="google.com", metrics=None),
        SimpleNamespace(id=2, event_type="reading", data={}, title="Best ryokans in Kyoto",
                        domain="medium.com", metrics={"dwellMs": 840000, "readPct": 95}),
        SimpleNamespace(id=3, event_type="interaction",
                        data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
                        title=None, domain="sixt.com", metrics=None),
    ]
    facts = collect_browser_facts(rows)
    kinds = {f.kind for f in facts}
    assert {"search", "reading", "choice"} <= kinds
    search = next(f for f in facts if f.kind == "search")
    assert "flights to tokyo" in search.summary and search.event_ids == [1]
    assert search.source == "browser"


async def test_builder_assigns_ids_and_merges_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search", ts=dt.datetime(2026, 6, 20, 9),
                       data={"query": "tokyo"})],
    )
    builder = FactDigestBuilder(
        browser=events, calendar=None, email=None, prefs=None, tasks=None,
        now=dt.datetime(2026, 6, 27, 12),
    )
    facts = await builder.build()
    assert facts and facts[0].id == "f1"
    assert all(f.id.startswith("f") for f in facts)
    assert any("tokyo" in f.summary for f in facts)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/user_model/test_facts.py -q`
Expected: FAIL with `ModuleNotFoundError: ... user_model.facts`.

- [ ] **Step 3: Write the implementation**

```python
# src/pragya_assistant/user_model/facts.py
"""Stage 0 of the opinion workflow: gather cited FACTS from every source except
finance (browser, calendar, email, explicit memory). Pure per-source collectors
(testable without IO) + a builder that fetches, runs them, and numbers the facts.
No conclusions — just grounded facts, each tagged with its source ids."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.memory.repositories import PreferenceRepository


@dataclass
class Fact:
    """One grounded fact, tagged with its source ids (ints for browser/calendar
    rows, strings for gmail message ids / memory rows)."""

    source: str
    kind: str
    summary: str
    event_ids: list[int] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    id: str = ""  # assigned by the builder, e.g. "f1"


def _dwell_min(metrics: dict[str, Any] | None) -> int | None:
    ms = (metrics or {}).get("dwellMs")
    return round(ms / 60000) if isinstance(ms, int | float) and ms > 0 else None


def collect_browser_facts(rows: Sequence[Any]) -> list[Fact]:
    facts: list[Fact] = []
    for r in rows:
        d = r.data or {}
        if r.event_type == "search" and d.get("query"):
            facts.append(Fact("browser", "search", f"searched '{d['query']}'", event_ids=[r.id]))
        elif r.event_type == "reading" and (r.title or d.get("title")):
            title = r.title or d.get("title")
            mins = _dwell_min(r.metrics)
            pct = (r.metrics or {}).get("readPct")
            extra = f" ({mins}m, {pct}%)" if mins and pct else (f" ({mins}m)" if mins else "")
            facts.append(Fact("browser", "reading", f"read '{title}'{extra}", event_ids=[r.id]))
        elif r.event_type == "interaction" and d.get("action") == "choose" and d.get("value"):
            grp = d.get("group") or "option"
            facts.append(
                Fact("browser", "choice", f"chose {d['value']} for {grp}", event_ids=[r.id])
            )
        elif r.event_type == "action" and d.get("milestone"):
            funnel = d.get("funnel") or "flow"
            facts.append(
                Fact("browser", "action", f"{d['milestone']} in {funnel}", event_ids=[r.id])
            )
    return facts


def collect_calendar_facts(events: Sequence[Any], *, cap: int = 40) -> list[Fact]:
    facts: list[Fact] = []
    for e in events[:cap]:
        when = e.start.strftime("%a") if getattr(e, "start", None) else "?"
        facts.append(
            Fact("calendar", "event", f"calendar: '{e.summary}' ({when})", event_ids=[e.id])
        )
    return facts


def collect_email_facts(messages: Sequence[Any], *, cap: int = 20) -> list[Fact]:
    facts: list[Fact] = []
    for m in messages[:cap]:
        facts.append(
            Fact("email", "email", f"email from {m.from_} — {m.subject}", refs=[m.message_id])
        )
    return facts


def collect_memory_facts(
    preferences: dict[str, str], tasks: Sequence[Any]
) -> list[Fact]:
    facts: list[Fact] = []
    for k, v in preferences.items():
        facts.append(Fact("memory", "preference", f"preference {k}: {v}", refs=[f"pref:{k}"]))
    for t in tasks:
        facts.append(Fact("memory", "task", f"open task: {t.title}", refs=[f"task:{t.id}"]))
    return facts


class _PrefsSource(Protocol):
    async def get_preferences(self) -> dict[str, str]: ...


class _TasksSource(Protocol):
    async def list_tasks(self, include_done: bool = False) -> list[Any]: ...


class _EmailSource(Protocol):
    async def list_recent(self, n: int = 10) -> list[Any]: ...


class PreferenceReader:
    """Light read-only preferences accessor (no embedder needed, unlike
    MemoryService) so the builder can be wired from a session factory alone."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get_preferences(self) -> dict[str, str]:
        async with self._sf() as s:
            return await PreferenceRepository(s).all_as_dict()


class FactDigestBuilder:
    """Gathers facts from whatever sources are available (skips any that are
    None / empty) and numbers them f1..fn for citation."""

    def __init__(
        self,
        *,
        browser: BrowserActivityEventStore | None = None,
        calendar: CalendarEventStore | None = None,
        email: _EmailSource | None = None,
        prefs: _PrefsSource | None = None,
        tasks: _TasksSource | None = None,
        now: dt.datetime,
        window_days: int = 30,
        browser_key: str = "browser_activity",
        calendar_key: str = "google_calendar",
    ) -> None:
        self._browser = browser
        self._calendar = calendar
        self._email = email
        self._prefs = prefs
        self._tasks = tasks
        self._now = now
        self._window = window_days
        self._browser_key = browser_key
        self._calendar_key = calendar_key

    async def build(self) -> list[Fact]:
        collected: list[Fact] = []
        if self._browser is not None:
            rows = await self._browser.recent(
                self._browser_key,
                types=["search", "reading", "interaction", "action"],
                since=self._now - dt.timedelta(days=self._window),
                limit=300,
            )
            collected += collect_browser_facts(rows)
        if self._calendar is not None:
            events = await self._calendar.events_between(
                self._calendar_key, self._now - dt.timedelta(days=self._window), self._now
            )
            collected += collect_calendar_facts(events)
        if self._email is not None:
            collected += collect_email_facts(await self._email.list_recent(20))
        if self._prefs is not None and self._tasks is not None:
            collected += collect_memory_facts(
                await self._prefs.get_preferences(), await self._tasks.list_tasks()
            )
        for i, f in enumerate(collected, start=1):
            f.id = f"f{i}"
        return collected
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/user_model/test_facts.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check src/pragya_assistant/user_model/facts.py tests/user_model/test_facts.py
uv run mypy src/pragya_assistant/user_model/facts.py
git add src/pragya_assistant/user_model/facts.py tests/user_model/test_facts.py
git commit -m "feat(user_model): Fact + browser/calendar fact collectors + digest builder"
```

---

## Task 2: email & memory fact collectors (builder integration)

**Files:**
- Modify: `tests/user_model/test_facts.py` (add cases)

**Interfaces:**
- Consumes: `collect_email_facts`, `collect_memory_facts`, `PreferenceReader` from Task 1.
- Produces: verified email/memory facts + graceful-skip behavior.

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_facts.py  (append)
from pragya_assistant.user_model.facts import collect_email_facts, collect_memory_facts


def test_collect_email_facts_cites_message_ids() -> None:
    msgs = [SimpleNamespace(from_="a@b.com", subject="Invoice #42", message_id="<m1@x>")]
    facts = collect_email_facts(msgs)
    assert facts[0].source == "email" and facts[0].refs == ["<m1@x>"]
    assert "Invoice #42" in facts[0].summary


def test_collect_memory_facts_prefs_and_tasks() -> None:
    facts = collect_memory_facts(
        {"diet": "vegetarian"}, [SimpleNamespace(id=3, title="Renew passport")]
    )
    kinds = {f.kind: f for f in facts}
    assert kinds["preference"].refs == ["pref:diet"]
    assert kinds["task"].refs == ["task:3"] and "passport" in kinds["task"].summary


async def test_builder_skips_unavailable_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # No sources at all → empty digest, no error.
    builder = FactDigestBuilder(now=dt.datetime(2026, 6, 27, 12))
    assert await builder.build() == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/user_model/test_facts.py -q`
Expected: FAIL on the email/memory imports or the empty-builder case (if collectors absent). If Task 1 already defined them, the email/memory tests pass and only confirm behavior — in that case this task is purely additional coverage; proceed.

- [ ] **Step 3: Implementation**

No new code if Task 1's collectors are complete. If `test_builder_skips_unavailable_sources` fails because `build()` requires sources, confirm all constructor args default to `None` (they do in Task 1).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/user_model/test_facts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/user_model/test_facts.py
git commit -m "test(user_model): email/memory fact collectors + graceful source skip"
```

---

## Task 3: `OpinionWorkflow` — grouping + forming stages

**Files:**
- Create: `src/pragya_assistant/user_model/opinion_workflow.py`
- Test: `tests/user_model/test_opinion_workflow.py`

**Interfaces:**
- Consumes: `Fact` (Task 1); `extract_json` from `pragya_assistant.user_model.dreamer`; `UserModelStore`, `TraitSnapshot` from `pragya_assistant.user_model.store`.
- Produces: `LlmFn = Callable[[str], Awaitable[str]]`; `Theme(label: str, fact_ids: list[str])`; `ProposedOpinion(trait: str, value: Any, confidence: float, evidence_fact_ids: list[str])`; `OpinionWorkflow(model, *, group_fn, form_fn, review_fn)`; module fns `group_facts(facts, fn) -> list[Theme]`, `form_opinions(themes, facts, fn) -> list[ProposedOpinion]`; prompt builders `build_group_prompt(facts)`, `build_form_prompt(themes, facts)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_opinion_workflow.py
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: FAIL with `ModuleNotFoundError: ... opinion_workflow`.

- [ ] **Step 3: Implementation**

```python
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

from pragya_assistant.user_model.dreamer import extract_json
from pragya_assistant.user_model.facts import Fact
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

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
    '{"opinions": [{"trait": "interest:travel", "value": "...", "confidence": 0.0, '
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
        lines += [f"- {by_id[i].id}: {by_id[i].summary}" for i in t.fact_ids if i in by_id]
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
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        ids = [str(i) for i in raw.get("evidence_fact_ids", []) if isinstance(i, str | int)]
        out.append(ProposedOpinion(trait, raw.get("value"), conf, ids))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
uv run mypy src/pragya_assistant/user_model/opinion_workflow.py
git add src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
git commit -m "feat(user_model): opinion workflow grouping + forming LLM stages"
```

---

## Task 4: citation-grounding validator + confidence cap

**Files:**
- Modify: `src/pragya_assistant/user_model/opinion_workflow.py`
- Modify: `tests/user_model/test_opinion_workflow.py`

**Interfaces:**
- Consumes: `ProposedOpinion`, `Fact`.
- Produces: `calibrate(n_citations: int, n_sources: int) -> float`; `validate_citations(opinions, facts) -> list[TraitSnapshot]` — drops uncited/unresolvable opinions, caps confidence, builds the `derivation` chain (`{method, evidence_fact_ids, fact_summaries, event_ids, refs}`), sets `evidence` = citation count, `provenance` = sorted distinct sources.

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_opinion_workflow.py  (append)
from pragya_assistant.user_model.opinion_workflow import calibrate, validate_citations


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


def test_calibrate_curve() -> None:
    assert calibrate(1, 1) == 0.5
    assert calibrate(5, 3) == min(0.95, round(0.5 + 0.15 * 4 + 0.15 * 2, 2))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: FAIL with `ImportError: cannot import name 'validate_citations'`.

- [ ] **Step 3: Implementation (append to `opinion_workflow.py`)**

```python
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
        event_ids = [eid for f in cited for eid in f.event_ids]
        refs = [r for f in cited for r in f.refs]
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
    return snaps
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
uv run mypy src/pragya_assistant/user_model/opinion_workflow.py
git add src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
git commit -m "feat(user_model): citation-grounding validator + evidence-capped confidence"
```

---

## Task 5: reviewer agent + `OpinionWorkflow.run` (full pipeline, persist)

**Files:**
- Modify: `src/pragya_assistant/user_model/opinion_workflow.py`
- Modify: `tests/user_model/test_opinion_workflow.py`

**Interfaces:**
- Consumes: `group_facts`, `form_opinions`, `validate_citations`, `UserModelStore`.
- Produces: `review_opinions(snaps, fn) -> list[TraitSnapshot]` (drops `keep:false`, applies `confidence_adjustment`, records `derivation["review"]`); `OpinionWorkflow(model, *, group_fn, form_fn, review_fn).run(facts) -> list[TraitSnapshot]` (group → form → validate → review → `model.write`).

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_opinion_workflow.py  (append)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow, review_opinions
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore


def _snap(trait: str) -> TraitSnapshot:
    return TraitSnapshot(trait=trait, value="v", confidence=0.8, evidence=1,
                         provenance=["browser"], derivation={"method": "opinion-workflow"})


async def test_review_drops_and_downgrades() -> None:
    snaps = [_snap("intent:travel"), _snap("trait:overreach")]

    async def fake(_prompt: str) -> str:
        return (
            '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": -0.1, '
            '"reason": "well supported"}, {"trait": "trait:overreach", "keep": false, '
            '"reason": "evidence does not support this"}]}'
        )

    kept = await review_opinions(snaps, fake)
    assert [s.trait for s in kept] == ["intent:travel"]
    assert kept[0].confidence == 0.7  # 0.8 - 0.1
    assert kept[0].derivation["review"]["reason"] == "well supported"


async def test_workflow_run_persists_reviewed_opinions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    facts = [Fact("browser", "search", "searched 'tokyo'", event_ids=[1], id="f1")]
    model = UserModelStore(session_factory)

    async def group_fn(_p: str) -> str:
        return '{"themes": [{"label": "travel", "fact_ids": ["f1"]}]}'

    async def form_fn(_p: str) -> str:
        return ('{"opinions": [{"trait": "intent:travel", "value": "Tokyo trip", '
                '"confidence": 0.9, "evidence_fact_ids": ["f1"]}]}')

    async def review_fn(_p: str) -> str:
        return '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": 0}]}'

    wf = OpinionWorkflow(model, group_fn=group_fn, form_fn=form_fn, review_fn=review_fn)
    out = await wf.run(facts)
    assert [s.trait for s in out] == ["intent:travel"]
    current = {s.trait: s for s in await model.current_model()}
    assert current["intent:travel"].derivation["event_ids"] == [1]


async def test_workflow_run_empty_facts_is_noop(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    wf = OpinionWorkflow(
        UserModelStore(session_factory),
        group_fn=_unused, form_fn=_unused, review_fn=_unused,
    )
    assert await wf.run([]) == []


async def _unused(_p: str) -> str:  # pragma: no cover - must never be called
    raise AssertionError("LLM should not be called for empty facts")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: FAIL with `ImportError: cannot import name 'OpinionWorkflow'`.

- [ ] **Step 3: Implementation (append to `opinion_workflow.py`)**

```python
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
        derivation["review"] = {"reason": str(r.get("reason") or "")}
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
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/user_model/test_opinion_workflow.py -q`
Expected: PASS (all workflow tests).

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
uv run mypy src/pragya_assistant/user_model/opinion_workflow.py
git add src/pragya_assistant/user_model/opinion_workflow.py tests/user_model/test_opinion_workflow.py
git commit -m "feat(user_model): reviewer agent + OpinionWorkflow.run (full pipeline)"
```

---

## Task 6: wire `/opinions/refresh` to the workflow + retire the deterministic layer

**Files:**
- Modify: `src/pragya_assistant/api/routes/dreams.py:76-83` (the `refresh_opinions` handler + imports)
- Modify: `src/pragya_assistant/agent/activity_tools.py:27-37` (`_format_trait` counts refs)
- Modify: `tests/api/test_dreams.py` (the `/opinions/refresh` test)
- Delete: `src/pragya_assistant/connectors/browser_activity/derive.py`, `tests/connectors/browser_activity/test_derive.py`
- Delete: `src/pragya_assistant/user_model/extractors.py`, `tests/user_model/test_extractors.py`
- Delete: `src/pragya_assistant/user_model/opinions.py`, `tests/user_model/test_opinions.py`

**Interfaces:**
- Consumes: `FactDigestBuilder`, `PreferenceReader` (Task 1); `OpinionWorkflow` (Task 5); `engine_dream_fn`/`ollama_dream_fn`, `build_email_service`, `TaskStore`, `CalendarEventStore`.

- [ ] **Step 1: Update the `/opinions/refresh` route test (failing)**

The test app (`build_test_app`) injects a **`ScriptedChatProvider`** (a fake LLM over `LoopEngine`), so `engine_dream_fn(agent)` returns scripted text — no real LLM call. The workflow makes exactly **3** engine calls in order (group, form, review); script one `ChatResult` per stage. Replace the existing `test_opinions_refresh_forms_grounded_opinions` in `tests/api/test_dreams.py` with:

```python
import datetime as dt

from pragya_assistant.llm.types import ChatResult


def _stop(text: str) -> ChatResult:
    return ChatResult(text=text, tool_calls=(), finish_reason="stop", usage={})


async def test_opinions_refresh_runs_workflow(
    engine: AsyncEngine, build_test_app: AppBuilder
) -> None:
    """Refresh forms a fact-grounded, cited opinion (the 3 LLM stages are scripted)."""
    sf = create_session_factory(engine)
    await BrowserActivityEventStore(sf).add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search",
                       ts=dt.datetime(2026, 6, 28, 9), data={"query": "flights to tokyo"})],
    )
    group = '{"themes": [{"label": "travel", "fact_ids": ["f1"]}]}'
    form = ('{"opinions": [{"trait": "intent:travel", "value": "planning a Tokyo trip", '
            '"confidence": 0.9, "evidence_fact_ids": ["f1"]}]}')
    review = '{"reviews": [{"trait": "intent:travel", "keep": true, "confidence_adjustment": 0}]}'
    app = build_test_app(ScriptedChatProvider([_stop(group), _stop(form), _stop(review)]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/opinions/refresh", headers=AUTH)
    assert resp.status_code == 200 and resp.json()["traits"] == 1

    current = {s.trait: s for s in await UserModelStore(sf).current_model()}
    assert "intent:travel" in current
    assert current["intent:travel"].derivation["event_ids"] == [1]
```

Ensure these imports exist at the top of `tests/api/test_dreams.py` (most already do): `httpx`, `from httpx import ASGITransport`, `from sqlalchemy.ext.asyncio import AsyncEngine`, `from pragya_assistant.llm.types import ChatResult`, `from tests.fakes import ScriptedChatProvider`, `from pragya_assistant.memory.db import create_session_factory`. **Remove** any `OpinionFormer`/`BrowserExtractor` import. The `engine` fixture starts each test with a fresh DB, so the seeded search row is `id=1`.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/api/test_dreams.py -q`
Expected: FAIL (old test references removed symbols, or asserts old deterministic behavior).

- [ ] **Step 3: Rewrite the route handler + imports**

In `src/pragya_assistant/api/routes/dreams.py`, remove these imports:
```python
from pragya_assistant.user_model.extractors import BrowserExtractor
from pragya_assistant.user_model.opinions import OpinionFormer
```
Add:
```python
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.email_inbox.service import build_email_service
from pragya_assistant.tasks.store import TaskStore
from pragya_assistant.user_model.facts import FactDigestBuilder, PreferenceReader
from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow
```
Replace the `refresh_opinions` handler with:
```python
@router.post("/opinions/refresh")
async def refresh_opinions(
    settings: AppSettings, session_factory: SessionFactory, agent: Agent
) -> dict[str, Any]:
    """Form fact-grounded opinions via the workflow (digest -> group -> form ->
    validate -> review -> persist). Browser+calendar+email+memory; finance is
    Phase 2. Same engine selection as the dreamer. Manual + hourly via cron."""
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    facts = await FactDigestBuilder(
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        now=now,
    ).build()
    if settings.agent_engine == "ollama":
        fn = ollama_dream_fn(settings.ollama_base_url, settings.dream_model)
    else:
        fn = engine_dream_fn(agent)
    model = UserModelStore(session_factory)
    workflow = OpinionWorkflow(model, group_fn=fn, form_fn=fn, review_fn=fn)
    try:
        formed = await workflow.run(facts)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Opinion workflow unavailable: {exc}",
        ) from exc
    return {"ok": True, "traits": len(formed), "facts": len(facts)}
```
Add `import datetime as dt` at the top of the file if not present.

- [ ] **Step 4: Update `_format_trait` to count refs**

In `src/pragya_assistant/agent/activity_tools.py`, change the signal count line so email/memory refs also count:
```python
    n = 0
    if isinstance(d, dict):
        n = len(d.get("event_ids", [])) + len(d.get("refs", []))
```

- [ ] **Step 5: Delete the retired deterministic layer**

```bash
git rm src/pragya_assistant/connectors/browser_activity/derive.py \
       tests/connectors/browser_activity/test_derive.py \
       src/pragya_assistant/user_model/extractors.py \
       tests/user_model/test_extractors.py \
       src/pragya_assistant/user_model/opinions.py \
       tests/user_model/test_opinions.py
```

- [ ] **Step 6: Run the full suite + lint + mypy**

Run:
```bash
uv run pytest -q --ignore=tests/llm/test_anthropic.py
uv run ruff check src tests
uv run mypy src
```
Expected: PASS / clean. If any other module imports a deleted symbol, the error names the file — remove that import (none expected per the blast-radius grep: only `routes/dreams.py` and the deleted tests referenced them).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(api): /opinions/refresh runs the fact-grounded workflow; retire deterministic heuristics"
```

---

## Task 7: hourly cron + config

**Files:**
- Modify: `src/pragya_assistant/config.py:88-91` (add opinions settings near the digest block)
- Modify: `infra/cron/entrypoint.sh:21-31` (crontab)
- Modify: `infra/docker-compose.yml:64-69` (cron env)
- Modify: `infra/.env.example`

**Interfaces:**
- Consumes: `/opinions/refresh` (Task 6).
- Produces: `Settings.opinions_enabled: bool`, `Settings.opinions_minute: int`; an hourly cron line.

- [ ] **Step 1: Add settings (no test — config is declarative; verified by import)**

In `config.py`, after the digest block (around line 91), add:
```python
    # --- Opinions (hourly fact-grounded opinion workflow) ---
    opinions_enabled: bool = True
    opinions_minute: int = 7  # minute past every hour (off :00 to avoid the fleet)
```

- [ ] **Step 2: Add the hourly cron line**

In `infra/cron/entrypoint.sh`, inside the `CRONTAB` heredoc (after the dream line, ~line 25), append a line (mind the quoting/escaping used by the existing lines):
```sh
${OPINIONS_MINUTE} * * * * ${CURL_CMD} -X POST \"${API_BASE}/opinions/refresh\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1
```
Add `OPINIONS_MINUTE="${OPINIONS_MINUTE:-7}"` near the other env defaults at the top of the script (where `DREAM_MINUTE` etc. are read).

- [ ] **Step 3: Wire compose + .env.example**

In `infra/docker-compose.yml`, in the cron service `environment:` block (near line 68), add:
```yaml
      OPINIONS_MINUTE: "${OPINIONS_MINUTE:-7}"
```
In `infra/.env.example`, add:
```
# Opinions: hourly fact-grounded opinion workflow (minute past each hour)
OPINIONS_MINUTE=7
```

- [ ] **Step 4: Verify config imports + render**

Run:
```bash
uv run python -c "from pragya_assistant.config import Settings; print(Settings().opinions_minute)"
docker compose -f infra/docker-compose.yml --env-file .env config >/dev/null && echo "compose ok"
```
Expected: prints `7`; `compose ok`.

- [ ] **Step 5: Commit**

```bash
git add src/pragya_assistant/config.py infra/cron/entrypoint.sh infra/docker-compose.yml infra/.env.example
git commit -m "feat(infra): hourly opinion-workflow cron + OPINIONS_MINUTE setting"
```

---

## Task 8: end-to-end verification (manual, real engine)

**Files:** none (verification only)

- [ ] **Step 1: Rebuild + run the workflow live**

```bash
cd /Users/nagarjuna/projects/Nidra
docker compose -f infra/docker-compose.yml --env-file .env up -d --build backend
TOKEN=$(grep -E '^API_AUTH_TOKEN=' .env | cut -d= -f2)
curl -s -X POST http://localhost:8088/opinions/refresh -H "Authorization: Bearer $TOKEN"
```
Expected: `{"ok":true,"traits":N,"facts":M}` with M > 0.

- [ ] **Step 2: Inspect the evidence chain**

```bash
docker exec pragya-db-1 psql -U pragya -d pragya -x -c \
 "SELECT trait, value, confidence, provenance, jsonb_pretty(derivation) FROM user_model_snapshots ORDER BY computed_at DESC LIMIT 5;"
```
Expected: opinions whose `derivation.method = "opinion-workflow"`, each with `evidence_fact_ids`, `fact_summaries`, and a `review` block; confidence ≤ 0.95 and capped by evidence; **no** `decisiveness`/`deliberation`.

- [ ] **Step 3: Confirm via the chat tool**

```bash
curl -s -X POST http://localhost:8088/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"message":"what do you know about me?"}'
```
Expected: `about_me` reflects the new opinions with "derived by:" lines.

- [ ] **Step 4: Update memory + commit any doc note**

Update `~/.claude/projects/-Users-nagarjuna-projects-Nidra/memory/nidra-opinions-dreams-rsi.md` to note opinions are now the fact-grounded LLM workflow (group→form→validate→review), heuristics retired. No code commit needed if only memory changed.

---

## Self-Review

**Spec coverage:**
- §3 pipeline (digest → group → form → validate → review → persist): Tasks 1–5. ✓
- §3 sources browser/calendar/email/memory: Tasks 1–2 (finance excluded → Phase 2). ✓
- §3 cite-or-omit + confidence cap: Task 4. ✓
- §3 reviewer agent (v1): Task 5. ✓
- §4 manual `/opinions/refresh` + hourly cron + engine selection: Tasks 6–7. ✓
- §5 retire decisiveness/deliberation + deterministic former: Task 6 (deletes derive.py/extractors.py/opinions.py). ✓
- §5 `derivation` column unchanged / no migration: honored (Task 4 writes into it). ✓
- §6 confidence curve: Task 4 `calibrate`. ✓
- §8 testing (digest, per-source collectors, workflow with fakes, validator edges, reviewer): Tasks 1–5. ✓
- Phase 2 (finance, retention): intentionally absent. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. Task 6 Step 1 adapts to the existing `test_dreams.py` fixtures (named explicitly: match `AUTH`/`client`).

**Type consistency:** `LlmFn` reused across stages; `Theme`/`ProposedOpinion`/`Fact` field names match between definition (Tasks 1, 3) and use (Tasks 4, 5); `validate_citations`/`review_opinions`/`OpinionWorkflow.run` signatures consistent across Tasks 4–6; `derivation` keys (`method`, `evidence_fact_ids`, `fact_summaries`, `event_ids`, `refs`, `review`) consistent between Task 4 (writes) and Task 8 (reads), and `activity_tools` counts `event_ids`+`refs` (Task 6).
