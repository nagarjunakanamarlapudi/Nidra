# Opinion-Maker → Tool-Using Agent: Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Turn the opinion-maker into a tool-using agent that *pulls* data (browser, calendar past+future, email, memory) via query tools and emits cited opinions — reusing the repo's existing engines (no new loop) — plus widen the calendar connector and decouple opinions from the dreamer.

**Architecture:** Reuse `ClaudeCodeEngine` (tools→MCP, default) / `LoopEngine` (native tool-calls) — both already run the model↔tool loop. We add: query `Tool`s wrapping the existing `facts.py` collectors, a per-run evidence ledger, and a thin `build_opinion_engine`. Keep the deterministic `validate_citations` + `review_opinions` + persist. Neutral `agent/completion.py` ends the opinion↔dreamer coupling.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, pytest (`uv run pytest`), ruff, mypy. Engines via `agent/factory.py`.

## Global Constraints

- Run all backend commands from `/Users/nagarjuna/projects/Nidra/backend`.
- **Reuse, don't rewrite.** Specific reuse is named in each task; do not duplicate logic that exists.
- TDD: failing test → watch fail → minimal impl → watch pass → commit.
- `uv run ruff check src tests` and `uv run mypy src` stay clean.
- Opinions stay **fact-bound**: every opinion cites real ledger ids; uncited dropped. Confidence capped by evidence; reviewer only lowers.
- No new DB migration (the `derivation` column exists, 0018).
- The opinion-maker runs on the configured `agent_engine` (default `claude-code`, **no API key**); tested through `LoopEngine` + `ScriptedChatProvider`.

## File Structure

**New:**
- `src/pragya_assistant/agent/completion.py` — `CompletionFn`, `engine_completion_fn`, `ollama_completion_fn`, `extract_json` (the one canonical home).
- `src/pragya_assistant/user_model/opinion_agent.py` — `EvidenceLedger`, `build_query_tools`, `OPINION_SYSTEM`, `parse_proposed_opinions`, `run_opinion_agent`.
- `src/pragya_assistant/api/routes/opinions.py` — `/opinions/refresh`.
- Tests: `tests/agent/test_completion.py`, `tests/user_model/test_opinion_agent.py`, `tests/api/test_opinions.py`.

**Modified:**
- `user_model/dreamer.py` — import from `agent/completion`; drop its local `extract_json`/`engine_dream_fn`/`DreamFn`.
- `user_model/opinion_workflow.py` — drop `Theme`/`GROUP`/`FORM`/`group_facts`/`form_opinions`/`LlmFn`; import `extract_json` + `CompletionFn` from `agent/completion`; rework `OpinionWorkflow.run` to drive the agent.
- `agent/factory.py` — extract `_make_engine(...)`; add `build_opinion_engine(...)`.
- `connectors/google_calendar/connector.py` — add `sync_days_back`.
- `api/routes/dreams.py` — drop `/opinions/*` + the opinions imports; use `engine_completion_fn`/`ollama_completion_fn` from `agent/completion`.
- `api/routes/browser_activity.py` — remove the `/connectors/browser_activity/dream` endpoint (keep `/ingest`).
- `api/app.py` — `include_router(opinions.router)`.

**Deleted (verified safe):**
- `connectors/browser_activity/dreamer.py` + `tests/connectors/browser_activity/test_dreamer.py` — legacy browser-only dreamer; its `/dream` endpoint is **not** called by the extension (only `/ingest` is).

---

## Task A: `agent/completion.py` — neutral LLM utility (decouple)

**Files:**
- Create: `src/pragya_assistant/agent/completion.py`, `tests/agent/test_completion.py`
- Modify: `user_model/dreamer.py`, `user_model/opinion_workflow.py`, `api/routes/dreams.py`

**Interfaces — Produces:**
- `CompletionFn = Callable[[str], Awaitable[str]]`
- `def engine_completion_fn(engine: AgentEngine) -> CompletionFn`
- `def ollama_completion_fn(base_url: str, model: str, *, timeout: float = 120.0) -> CompletionFn`
- `def extract_json(text: str) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_completion.py
"""Neutral LLM-completion helpers shared by the opinion-maker and the dreamer
(neither subsystem imports the other)."""

from __future__ import annotations

from pragya_assistant.agent.completion import engine_completion_fn, extract_json


def test_extract_json_strips_fences_and_salvages() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise {"b": 2} trailing') == {"b": 2}
    assert extract_json("not json") == {}


class _FakeEngine:
    async def respond(self, history, user_text, *, effort=None):  # type: ignore[no-untyped-def]
        return f"echo:{user_text}", []


async def test_engine_completion_fn_calls_respond() -> None:
    fn = engine_completion_fn(_FakeEngine())  # type: ignore[arg-type]
    assert await fn("hi") == "echo:hi"
```

- [ ] **Step 2: Run, watch it fail**

Run: `uv run pytest tests/agent/test_completion.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** — move the canonical copies out of the dreamers.

```python
# src/pragya_assistant/agent/completion.py
"""Neutral LLM-completion plumbing shared across subsystems (opinions, dreams).

Lives in `agent/` so neither the opinion-maker nor the dreamer has to import the
other for a generic "call the model" / "parse its JSON" helper."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from pragya_assistant.agent.engine import AgentEngine

# A one-shot completion: prompt -> raw model text (often JSON).
CompletionFn = Callable[[str], Awaitable[str]]


def engine_completion_fn(engine: AgentEngine) -> CompletionFn:
    """Back a completion with the configured agent engine (one-shot, no history)."""

    async def _call(prompt: str) -> str:
        reply, _ = await engine.respond([], prompt)
        return reply

    return _call


def ollama_completion_fn(base_url: str, model: str, *, timeout: float = 120.0) -> CompletionFn:
    """Back a completion with a local Ollama model (no tools, JSON expected)."""

    async def _call(prompt: str) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return str(resp.json().get("response", ""))

    return _call


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text — strip ```fences, salvage the first {...}."""
    if not text:
        return {}
    s = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}
```

Before writing `ollama_completion_fn`, open `connectors/browser_activity/dreamer.py:205` and copy the real body of `ollama_dream_fn` verbatim (the snippet above is the expected shape — match the actual implementation if it differs).

- [ ] **Step 4: Repoint the importers** (remove the duplicates)

- `user_model/dreamer.py`: delete its local `DreamFn`, `engine_dream_fn`, `extract_json`; add `from pragya_assistant.agent.completion import CompletionFn, engine_completion_fn, extract_json`. Replace internal uses of `DreamFn`→`CompletionFn`, `engine_dream_fn`→`engine_completion_fn`. Keep `DreamerService`, `build_dream_prompt`, `SYSTEM`, `_to_new_dream`.
- `user_model/opinion_workflow.py`: change `from pragya_assistant.user_model.dreamer import extract_json` → `from pragya_assistant.agent.completion import extract_json`. (More edits to this file in Task E.)
- `api/routes/dreams.py`: replace `from ...user_model.dreamer import DreamerService, engine_dream_fn` with `from ...user_model.dreamer import DreamerService` + `from ...agent.completion import engine_completion_fn`; replace `from ...connectors.browser_activity.dreamer import ollama_dream_fn` with `from ...agent.completion import ollama_completion_fn`; update the call sites (`engine_dream_fn`→`engine_completion_fn`, `ollama_dream_fn`→`ollama_completion_fn`).
- Update `tests/user_model/test_dreamer.py` imports of `extract_json`/`engine_dream_fn` (if any) to the new locations.

- [ ] **Step 5: Verify reuse + no dangling refs**

Run:
```bash
grep -rn "engine_dream_fn\|from pragya_assistant.user_model.dreamer import.*extract_json" src tests   # expect: none
uv run pytest tests/agent/test_completion.py tests/user_model/test_dreamer.py tests/api/test_dreams.py -q
uv run ruff check src tests && uv run mypy src
```
Expected: grep empty; tests pass; clean.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(agent): neutral completion utility; decouple opinions/dreamer from shared LLM plumbing"
```

---

## Task B: retire the legacy connector dreamer + its `/dream` route

**Files:**
- Modify: `api/routes/browser_activity.py` (remove the `/dream` endpoint; keep `/ingest`)
- Delete: `connectors/browser_activity/dreamer.py`, `tests/connectors/browser_activity/test_dreamer.py`

**Interfaces — Consumes:** `ollama_completion_fn`/`extract_json` now live in `agent/completion` (Task A), so the connector dreamer has nothing unique left.

- [ ] **Step 1: Confirm the legacy dreamer is fully superseded**

Run:
```bash
grep -rn "connectors.browser_activity.dreamer\|browser_activity/dream\b" src tests ../nidra 2>/dev/null | grep -v "/ingest"
```
Expected: only `api/routes/browser_activity.py` (the `/dream` endpoint we're deleting) and the legacy test. The extension calls only `/connectors/browser_activity/ingest` (verified). If anything else appears, STOP and report.

- [ ] **Step 2: Remove the `/dream` endpoint from `routes/browser_activity.py`**

Delete the `@router.post("/connectors/browser_activity/dream", ...)` handler (`browser_activity.py:98-...`) and the `DreamOut` model it returns, plus the now-unused imports (`DreamerService`, `ollama_dream_fn`, any dream-only types). Keep the `/ingest` endpoint and everything it uses.

- [ ] **Step 3: Delete the legacy module + its tests**

```bash
git rm src/pragya_assistant/connectors/browser_activity/dreamer.py tests/connectors/browser_activity/test_dreamer.py
```

- [ ] **Step 4: Verify the app still boots + suite green**

Run:
```bash
grep -rn "connectors.browser_activity.dreamer" src tests   # expect: none
uv run pytest -q --ignore=tests/llm/test_anthropic.py
uv run ruff check src tests && uv run mypy src
```
Expected: grep empty; full suite passes; clean. (The `/ingest` ingest tests must still pass.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(browser_activity): retire legacy on-device dreamer + /dream route (superseded by /dreams/run)"
```

---

## Task C: calendar connector — wide past+future window

**Files:**
- Modify: `connectors/google_calendar/connector.py:48-64`
- Test: `tests/connectors/google_calendar/test_connector.py` (or the existing connector test file — find it and follow its pattern)

**Interfaces — Produces:** sync queries `[now − sync_days_back, now + sync_days_ahead]` (`sync_days_back` default 90).

- [ ] **Step 1: Write the failing test** — find the existing calendar connector sync test (`grep -rln "sync_days_ahead\|GoogleCalendarConnector" tests`) and add a case asserting the backward window. Use the same fake client the existing tests use; assert the `time_min` passed to `list_events` is `now − 90d` (default). Skeleton (adapt to the real fakes):

```python
async def test_sync_uses_backward_window() -> None:
    captured = {}

    class _Client:
        async def list_events(self, token, *, time_min, time_max, calendar_id):
            captured["time_min"], captured["time_max"] = time_min, time_max
            return []
    # ...construct the connector with _Client and a fixed now, run sync...
    assert captured["time_min"] == fixed_now - dt.timedelta(days=90)
    assert captured["time_max"] == fixed_now + dt.timedelta(days=30)
```

- [ ] **Step 2: Run, watch it fail** — `uv run pytest <that test> -q` → FAIL (still `now-1d`).

- [ ] **Step 3: Implement** — in `connector.py` `sync`:

```python
        days_ahead = int(ctx.config.get("sync_days_ahead") or 30)
        days_back = int(ctx.config.get("sync_days_back") or 90)
        now = self._now()
        ...
                time_min=now - dt.timedelta(days=days_back),
                time_max=now + dt.timedelta(days=days_ahead),
```

- [ ] **Step 4: Run, watch it pass**; `uv run ruff check` + `uv run mypy src` clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(calendar): sync a backward window (sync_days_back, default 90) so past routines are queryable"
```

---

## Task D: query tools + evidence ledger (`opinion_agent.py`, part 1)

**Files:**
- Create: `src/pragya_assistant/user_model/opinion_agent.py`, `tests/user_model/test_opinion_agent.py`

**Interfaces — Produces:**
- `class EvidenceLedger` — `.record(facts: list[Fact]) -> list[Fact]` (assigns `f{n}` ids, stores them), `.facts -> list[Fact]`.
- `def build_query_tools(ledger, *, browser=None, calendar=None, email=None, prefs=None, tasks=None, now, browser_key="browser_activity", calendar_key="google_calendar") -> list[Tool]`.

**Reuse:** the `collect_*` functions from `user_model/facts.py`; the `Tool` dataclass from `agent/tools.py`; the source stores from Task-1 era (`BrowserActivityEventStore`, `CalendarEventStore`, `EmailService`, `PreferenceReader`, `TaskStore`).

- [ ] **Step 1: Write the failing test**

```python
# tests/user_model/test_opinion_agent.py
"""Query tools feed an evidence ledger; the ledger is the citable universe."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, build_query_tools

KEY = "browser_activity"


def _tool(tools, name):  # type: ignore[no-untyped-def]
    return next(t for t in tools if t.name == name)


def test_ledger_assigns_ids_and_dedups() -> None:
    from pragya_assistant.user_model.facts import Fact

    led = EvidenceLedger()
    out = led.record([Fact("browser", "search", "a", event_ids=[1])])
    assert out[0].id == "f1" and led.facts[0].id == "f1"
    out2 = led.record([Fact("browser", "search", "b", event_ids=[2])])
    assert out2[0].id == "f2" and len(led.facts) == 2


async def test_query_browsing_tool_populates_ledger(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search", ts=dt.datetime(2026, 6, 20, 9),
                       data={"query": "flights to tokyo"})],
    )
    led = EvidenceLedger()
    tools = build_query_tools(led, browser=events, now=dt.datetime(2026, 6, 27, 12))
    out = await _tool(tools, "query_browsing").handler({"days": 30})
    assert "flights to tokyo" in out and "f1" in out      # observation cites the ledger id
    assert led.facts and led.facts[0].summary.startswith("searched")
```

- [ ] **Step 2: Run, watch it fail** — `uv run pytest tests/user_model/test_opinion_agent.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# src/pragya_assistant/user_model/opinion_agent.py  (part 1; Task E appends the runner)
"""The opinion-maker as a tool-using agent.

We do NOT write a loop: the configured engine (ClaudeCodeEngine via MCP, or
LoopEngine via native tool-calls) runs the model↔tool loop. We provide the query
TOOLS (wrapping the facts.py collectors), an EvidenceLedger that records every
fact a tool returns (the citable universe), and — in Task E — the prompt + a thin
runner + the final parse."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.user_model.facts import (
    Fact,
    PreferenceReader,
    collect_browser_facts,
    collect_calendar_facts,
    collect_email_facts,
    collect_memory_facts,
)


class EvidenceLedger:
    """Accumulates every Fact the tools return this run, numbered f1..fn — the
    universe an opinion may cite. Validation resolves citations against it."""

    def __init__(self) -> None:
        self._facts: list[Fact] = []

    def record(self, facts: list[Fact]) -> list[Fact]:
        for f in facts:
            f.id = f"f{len(self._facts) + 1}"
            self._facts.append(f)
        return facts

    @property
    def facts(self) -> list[Fact]:
        return self._facts


def _observe(facts: list[Fact]) -> str:
    if not facts:
        return "(no matching facts)"
    return "\n".join(f"- {f.id} [{f.source}/{f.kind}]: {f.summary}" for f in facts)


def build_query_tools(
    ledger: EvidenceLedger,
    *,
    browser: BrowserActivityEventStore | None = None,
    calendar: CalendarEventStore | None = None,
    email: Any | None = None,
    prefs: PreferenceReader | None = None,
    tasks: Any | None = None,
    now: dt.datetime,
    browser_key: str = "browser_activity",
    calendar_key: str = "google_calendar",
) -> list[Tool]:
    tools: list[Tool] = []

    if browser is not None:
        async def query_browsing(args: dict[str, Any]) -> str:
            days = max(1, int(args.get("days", 30)))
            rows = await browser.recent(
                browser_key,
                types=["search", "reading", "interaction", "action"],
                since=now - dt.timedelta(days=days),
                limit=300,
            )
            return _observe(ledger.record(collect_browser_facts(rows)))

        tools.append(Tool(
            name="query_browsing",
            description="The user's recent browsing: searches, reading, choices, actions. arg: days (int).",
            input_schema={"type": "object", "properties": {"days": {"type": "integer"}},
                          "required": [], "additionalProperties": False},
            handler=query_browsing,
        ))

    if calendar is not None:
        async def query_calendar(args: dict[str, Any]) -> str:
            back = max(0, int(args.get("days_back", 90)))
            ahead = max(0, int(args.get("days_ahead", 60)))
            events = await calendar.events_between(
                calendar_key, now - dt.timedelta(days=back), now + dt.timedelta(days=ahead)
            )
            return _observe(ledger.record(collect_calendar_facts(events)))

        tools.append(Tool(
            name="query_calendar",
            description="The user's calendar — past routines and upcoming commitments. args: days_back, days_ahead (int).",
            input_schema={"type": "object", "properties": {
                "days_back": {"type": "integer"}, "days_ahead": {"type": "integer"}},
                "required": [], "additionalProperties": False},
            handler=query_calendar,
        ))

    if email is not None:
        async def query_email(args: dict[str, Any]) -> str:
            n = max(1, int(args.get("n", 20)))
            return _observe(ledger.record(collect_email_facts(await email.list_recent(n))))

        tools.append(Tool(
            name="query_email",
            description="The user's recent email (sender + subject). arg: n (int).",
            input_schema={"type": "object", "properties": {"n": {"type": "integer"}},
                          "required": [], "additionalProperties": False},
            handler=query_email,
        ))

    if prefs is not None or tasks is not None:
        async def query_memory(_args: dict[str, Any]) -> str:
            p = await prefs.get_preferences() if prefs is not None else {}
            t = await tasks.list_tasks() if tasks is not None else []
            return _observe(ledger.record(collect_memory_facts(p, t)))

        tools.append(Tool(
            name="query_memory",
            description="What the user explicitly told the assistant: preferences and open tasks.",
            input_schema={"type": "object", "properties": {}, "required": [],
                          "additionalProperties": False},
            handler=query_memory,
        ))

    return tools
```

- [ ] **Step 4: Run, watch it pass**; `uv run ruff check src/pragya_assistant/user_model/opinion_agent.py tests/user_model/test_opinion_agent.py` + `uv run mypy src/pragya_assistant/user_model/opinion_agent.py` clean.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(user_model): query tools + evidence ledger for the opinion agent (reuse facts collectors)"
```

---

## Task E: `build_opinion_engine` + agent runner + rework `OpinionWorkflow`

**Files:**
- Modify: `agent/factory.py` (extract `_make_engine`; add `build_opinion_engine`)
- Modify: `user_model/opinion_agent.py` (add `OPINION_SYSTEM`, `parse_proposed_opinions`, `run_opinion_agent`)
- Modify: `user_model/opinion_workflow.py` (remove group/form; rework `run`)
- Modify: `tests/user_model/test_opinion_agent.py`, `tests/user_model/test_opinion_workflow.py`

**Interfaces:**
- Consumes: `EvidenceLedger`/`build_query_tools` (Task D); `validate_citations`/`review_opinions`/`calibrate`/`ProposedOpinion` (kept in `opinion_workflow.py`); `engine_completion_fn` (Task A); the engine classes.
- Produces: `build_opinion_engine(settings, *, tools: list[Tool]) -> AgentEngine`; `parse_proposed_opinions(text) -> list[ProposedOpinion]`; `async run_opinion_agent(engine) -> str`; reworked `OpinionWorkflow(model, *, engine, review_fn).run(ledger, tools_unused?) ...` (see below).

- [ ] **Step 1 — factory refactor test (failing).** In `tests/agent/` add `test_factory.py` (or extend an existing factory test):

```python
def test_build_opinion_engine_wires_tools_for_default_engine() -> None:
    from pragya_assistant.agent.tools import Tool
    from pragya_assistant.agent.factory import build_opinion_engine
    from pragya_assistant.config import Settings
    settings = Settings(_env_file=None, app_secret_key="s", api_auth_token="token",
                        database_url="postgresql+asyncpg://x/y")  # agent_engine defaults to claude-code
    tool = Tool(name="query_x", description="d", input_schema={"type": "object", "properties": {},
                "required": [], "additionalProperties": False}, handler=lambda a: "x")  # type: ignore[arg-type,return-value]
    engine = build_opinion_engine(settings, tools=[tool])
    assert engine.__class__.__name__ == "ClaudeCodeEngine"
```

- [ ] **Step 2: Run, watch it fail** (`build_opinion_engine` missing).

- [ ] **Step 3: Refactor `agent/factory.py`** — extract the engine-selection switch so it is reused, not duplicated:

```python
def _make_engine(settings: Settings, *, tools: list[Tool], system_prompt: str,
                 native_tools: tuple[str, ...] = ()) -> AgentEngine:
    engine = settings.agent_engine
    if engine in _LOOP_PROVIDERS:
        provider = build_chat_provider(settings, _LOOP_PROVIDERS[engine])
        return LoopEngine(provider=provider, registry=ToolRegistry(tools), system_prompt=system_prompt)
    if engine == "codex":
        return CodexEngine(model=settings.codex_model, system_prompt=system_prompt,
                           mcp_command=[sys.executable, "-m", "pragya_assistant.mcp_memory"],
                           mcp_env=_codex_mcp_env(settings), bypass_sandbox=True)
    if engine == "claude-code":
        return ClaudeCodeEngine(tools=tools, system_prompt=system_prompt,
                                model=settings.claude_code_model, native_tools=native_tools)
    raise ValueError(f"Unknown agent engine: {engine!r}")
```
Rewrite `build_engine(...)` to build its tool list as today and `return _make_engine(settings, tools=tools, system_prompt=build_system_prompt(), native_tools=native_tools)`. Then add:
```python
def build_opinion_engine(settings: Settings, *, tools: list[Tool]) -> AgentEngine:
    """Engine for the opinion-maker job: the configured brain, wired with the
    query tools + the opinion-forming prompt. Reuses the same engine switch."""
    from pragya_assistant.user_model.opinion_agent import OPINION_SYSTEM
    return _make_engine(settings, tools=tools, system_prompt=OPINION_SYSTEM)
```
(Codex note: like `build_engine`, Codex ignores the passed `tools` — it wires its own MCP memory tools. The opinion agent therefore targets claude-code/loop brains; Codex still runs but without the query tools. Acceptable — document in the docstring.)

- [ ] **Step 4: Run the factory test, watch it pass.**

- [ ] **Step 5 — agent runner + parse (failing test).** Extend `tests/user_model/test_opinion_agent.py`:

```python
from pragya_assistant.user_model.opinion_agent import parse_proposed_opinions


def test_parse_proposed_opinions_tolerates_garbage() -> None:
    text = ('{"opinions": [{"trait": "", "value": 1, "evidence_fact_ids": ["f1"]},'
            '{"trait": "intent:travel", "value": "Tokyo", "confidence": 0.9, "evidence_fact_ids": ["f1"]}]}')
    ops = parse_proposed_opinions(text)
    assert len(ops) == 1 and ops[0].trait == "intent:travel" and ops[0].evidence_fact_ids == ["f1"]
```

- [ ] **Step 6: Implement runner + parse in `opinion_agent.py`.** Move the opinion-parsing out of the old `form_opinions` (it is being deleted) into a reusable function:

```python
from pragya_assistant.agent.completion import extract_json
from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.user_model.opinion_workflow import ProposedOpinion

OPINION_SYSTEM = (
    "You are Nidra's opinion-maker. Investigate the user with the query tools "
    "(query_browsing, query_calendar, query_email, query_memory) — pull what you need, "
    "including calendar history AND upcoming events. Then state durable, HIGH-CONFIDENCE "
    "opinions the evidence DIRECTLY supports. Each opinion MUST cite the fact ids "
    "(e.g. f3) the tools returned. State nothing the facts don't support. NO speculation "
    "or future-guessing — that's the dreamer's job. Prefer interest:<topic>, preference:<x>, "
    "routine:<x>, intent:<x>. When done, output ONLY JSON: "
    '{"opinions": [{"trait": "interest:travel", "value": "...", "confidence": 0.0, '
    '"evidence_fact_ids": ["f1"]}]}'
)

_KICKOFF = "Form grounded opinions about the user. Investigate with the tools, then output the final JSON."


def parse_proposed_opinions(text: str) -> list[ProposedOpinion]:
    parsed = extract_json(text)
    out: list[ProposedOpinion] = []
    for raw in parsed.get("opinions", []) if isinstance(parsed, dict) else []:
        if not isinstance(raw, dict):
            continue
        trait = str(raw.get("trait") or "").strip()
        value = raw.get("value")
        if not trait or value is None or (isinstance(value, str) and not value.strip()):
            continue
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        except (TypeError, ValueError):
            conf = 0.0
        ids = [str(i) for i in raw.get("evidence_fact_ids", []) if isinstance(i, str | int)]
        out.append(ProposedOpinion(trait, value, conf, ids))
    return out


async def run_opinion_agent(engine: AgentEngine) -> str:
    """Drive the engine (its OWN tool loop populates the ledger via the tools) and
    return its final text."""
    reply, _ = await engine.respond([], _KICKOFF)
    return reply
```

- [ ] **Step 7: Run the parse test, watch it pass.**

- [ ] **Step 8 — rework `OpinionWorkflow` (failing test).** Replace the workflow tests' driving shape in `tests/user_model/test_opinion_workflow.py`. The end-to-end run is now driven by an engine; test it via `LoopEngine` + `ScriptedChatProvider` scripting a tool-call then the final opinions:

```python
from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import ToolRegistry
from pragya_assistant.llm.types import ChatResult, ToolCall  # confirm ToolCall import path
from pragya_assistant.user_model.opinion_agent import EvidenceLedger, build_query_tools
from pragya_assistant.user_model.opinion_workflow import OpinionWorkflow
# ...seed a browser search event via BrowserActivityEventStore...
# script: turn 1 -> tool_call query_browsing ; turn 2 -> final opinions citing f1
```
(Implementer: model the scripted `ChatResult(tool_calls=(ToolCall(...),), finish_reason="tool_calls")` on an existing tool-loop test if one exists — `grep -rn "tool_calls=" tests` — and reuse its exact construction.)

- [ ] **Step 9: Rework `opinion_workflow.py`.** Delete `LlmFn`, `Theme`, `GROUP_SYSTEM`, `FORM_SYSTEM`, `_facts_block`, `build_group_prompt`, `build_form_prompt`, `group_facts`, `form_opinions`. Keep `ProposedOpinion`, `calibrate`, `validate_citations`, `REVIEW_SYSTEM`, `build_review_prompt`, `review_opinions`. Replace `OpinionWorkflow` with:

```python
class OpinionWorkflow:
    """Drives the tool-using opinion agent → validate → review → persist."""

    def __init__(self, model: UserModelStore, *, engine: AgentEngine, review_fn: CompletionFn,
                 ledger: EvidenceLedger) -> None:
        self._model = model
        self._engine = engine
        self._review_fn = review_fn
        self._ledger = ledger

    async def run(self) -> list[TraitSnapshot]:
        from pragya_assistant.user_model.opinion_agent import parse_proposed_opinions, run_opinion_agent
        reply = await run_opinion_agent(self._engine)        # engine loop fills the ledger via tools
        proposed = parse_proposed_opinions(reply)
        validated = validate_citations(proposed, self._ledger.facts)
        reviewed = await review_opinions(validated, self._review_fn)
        await self._model.write(reviewed)
        return reviewed
```
Add imports: `from pragya_assistant.agent.completion import CompletionFn, extract_json`, `from pragya_assistant.agent.engine import AgentEngine`, `from pragya_assistant.user_model.opinion_agent import EvidenceLedger`. (Beware a circular import: `opinion_agent` imports `ProposedOpinion` from `opinion_workflow`, and `opinion_workflow` imports `EvidenceLedger`/parse from `opinion_agent`. Keep the `opinion_agent` imports for `parse_proposed_opinions`/`run_opinion_agent` **inside** `run()` as shown, and the `EvidenceLedger` type import under `TYPE_CHECKING` if needed.)

- [ ] **Step 10: Run** `uv run pytest tests/user_model/ tests/agent/ -q`, watch the reworked + kept tests pass; `uv run ruff check` + `uv run mypy src` clean. Remove now-dead tests for `group_facts`/`form_opinions`.

- [ ] **Step 11: Commit**

```bash
git add -A && git commit -m "feat(user_model): opinion-maker drives the engine's own tool loop (no hand-written loop); rework OpinionWorkflow"
```

---

## Task F: route split — `routes/opinions.py` driving the agent

**Files:**
- Create: `api/routes/opinions.py`, `tests/api/test_opinions.py`
- Modify: `api/routes/dreams.py` (remove `/opinions/*`), `api/app.py` (`include_router`)
- Move/rework the old opinions test out of `tests/api/test_dreams.py`

**Interfaces — Consumes:** `build_opinion_engine`, `build_query_tools`, `EvidenceLedger`, `OpinionWorkflow`, `engine_completion_fn`/`ollama_completion_fn`, the source stores/services.

- [ ] **Step 1: Write the failing route test** — `tests/api/test_opinions.py`. Reuse the `build_test_app`/`ScriptedChatProvider` pattern; script a `query_browsing` tool-call then final opinions; assert a cited opinion persists:

```python
# scripts: ChatResult(tool_calls=(ToolCall(name="query_browsing", ...),), finish_reason="tool_calls")
#          then _stop(final_opinions_json)
# seed a browser search; POST /opinions/refresh ; assert 200, traits==1, derivation.event_ids==[1]
```
(Construct the `ToolCall` exactly as the chat tool-loop tests do.)

- [ ] **Step 2: Run, watch it fail.**

- [ ] **Step 3: Implement `routes/opinions.py`**

```python
@router.post("/opinions/refresh")
async def refresh_opinions(settings: AppSettings, session_factory: SessionFactory, agent: Agent) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    ledger = EvidenceLedger()
    tools = build_query_tools(
        ledger,
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        now=now,
    )
    engine = build_opinion_engine(settings, tools=tools)
    review_fn = (ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
                 if settings.agent_engine == "ollama" else engine_completion_fn(agent))
    workflow = OpinionWorkflow(UserModelStore(session_factory), engine=engine,
                               review_fn=review_fn, ledger=ledger)
    try:
        formed = await workflow.run()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Opinion workflow unavailable: {exc}") from exc
    return {"ok": True, "traits": len(formed), "facts": len(ledger.facts)}
```
**The engine seam (resolved — do it this way, mirroring how `agent` is injected).**
The opinion engine is built **per request** (its tools bind to a fresh `EvidenceLedger`),
so it can't be a singleton like `components.agent`. Inject a *factory* instead:

- Add to `AppComponents` a field `opinion_engine_factory: Callable[[list[Tool]], AgentEngine]`.
- In `build_components` (production): `opinion_engine_factory=lambda tools: build_opinion_engine(settings, tools=tools)`.
- In `conftest.build_test_app` (tests): `opinion_engine_factory=lambda tools: LoopEngine(provider=provider, registry=ToolRegistry(tools), system_prompt="OPINION")` — so the **scripted provider drives the real tool loop with the per-request tools**.
- Add `deps.get_opinion_engine_factory(request) -> Callable[[list[Tool]], AgentEngine]` returning `components.opinion_engine_factory`.
- The route depends on it and does `engine = engine_factory(tools)` instead of calling `build_opinion_engine` directly.

This reuses the existing component-injection pattern exactly, keeps prod on the configured
brain, and makes the loop fully scriptable in tests (no real `ClaudeCodeEngine`/SDK call).
Route body:

```python
@router.post("/opinions/refresh")
async def refresh_opinions(settings: AppSettings, session_factory: SessionFactory,
                           agent: Agent, engine_factory: OpinionEngineFactory) -> dict[str, Any]:
    now = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    ledger = EvidenceLedger()
    tools = build_query_tools(
        ledger,
        browser=BrowserActivityEventStore(session_factory),
        calendar=CalendarEventStore(session_factory),
        email=build_email_service(settings),
        prefs=PreferenceReader(session_factory),
        tasks=TaskStore(session_factory),
        now=now,
    )
    engine = engine_factory(tools)
    review_fn = (ollama_completion_fn(settings.ollama_base_url, settings.dream_model)
                 if settings.agent_engine == "ollama" else engine_completion_fn(agent))
    workflow = OpinionWorkflow(UserModelStore(session_factory), engine=engine,
                               review_fn=review_fn, ledger=ledger)
    try:
        formed = await workflow.run()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"Opinion workflow unavailable: {exc}") from exc
    return {"ok": True, "traits": len(formed), "facts": len(ledger.facts)}
```
Define `router`, the `SessionFactory`/`AppSettings`/`Agent` deps mirroring `routes/dreams.py`,
and `OpinionEngineFactory = Annotated[Callable[[list[Tool]], AgentEngine], Depends(get_opinion_engine_factory)]`.

- [ ] **Step 4: Remove `/opinions/*` from `routes/dreams.py`**; delete the now-unused imports there. Add `include_router(opinions.router)` in `app.py`. Move the opinions test out of `test_dreams.py`.

- [ ] **Step 5: Run full suite + gates** — `uv run pytest -q --ignore=tests/llm/test_anthropic.py`, `uv run ruff check src tests`, `uv run mypy src`. Green/clean.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(api): /opinions/refresh in its own route, driven by the tool-using opinion agent"
```

---

## Task G: end-to-end verification (controller, real engine)

- [ ] **Step 1:** `docker compose -f infra/docker-compose.yml --env-file .env up -d --build backend`; wait for health.
- [ ] **Step 2:** `curl -s -X POST :8088/opinions/refresh -H "Authorization: Bearer $TOKEN"` → `{"ok":true,"traits":N,"facts":M}`.
- [ ] **Step 3:** Inspect `user_model_snapshots`: `derivation.method = "opinion-workflow"`, real `event_ids`, a `review` block; **no** decisiveness/deliberation; confidence ≤ 0.95.
- [ ] **Step 4:** Confirm the agent actually used tools (backend logs show tool calls / the `facts` count > 0). If `claude-code` MCP tool-calling misbehaves, capture the failure and report (do not paper over).
- [ ] **Step 5:** Update memory note (`nidra-opinions-dreams-rsi.md`) — opinions now a tool-using agent over a wide-window calendar, decoupled from the dreamer.

---

## Self-Review

**Spec coverage:** §2.1 reuse engines/no loop → Tasks D/E. §2.2 query tools → D. §2.3 ledger → D. §2.4 validate/review/persist → reused, E. §3 calendar window → C. §4 decoupling (completion.py, split routes, retire legacy) → A/B/F. §6 testing → each task's tests + G. ✓

**Reuse check (explicit):** collectors (D), validate/review/calibrate/ProposedOpinion (E), engine classes via `_make_engine` (E), `Tool`/`ToolRegistry`/`ScriptedChatProvider` (D/E/F), `build_email_service`/`PreferenceReader`/`TaskStore`/stores (D/F). No logic duplicated; the engine loop is the engines' own.

**Placeholder scan:** the two flagged integration risks (Task F test-seam; verbatim copy of `ollama_dream_fn` in A) are explicit "read X, then decide" instructions with a STOP-and-report fallback, not vague TODOs.

**Type consistency:** `ProposedOpinion`/`Fact`/`EvidenceLedger`/`CompletionFn` names consistent across A/D/E/F; `validate_citations(proposed, ledger.facts)` matches its kept signature; `OpinionWorkflow(model, *, engine, review_fn, ledger)` consistent between E (def) and F (use).

**Ordering/circular-import:** A→B→C→D→E→F→G. `opinion_agent`↔`opinion_workflow` cycle avoided by importing `parse_proposed_opinions`/`run_opinion_agent` inside `OpinionWorkflow.run` (Task E Step 9).
