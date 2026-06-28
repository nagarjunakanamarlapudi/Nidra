# Nidra — Opinion-Forming as a Tool-Using Agent

- **Date:** 2026-06-27
- **Status:** Approved design (revised), pre-implementation
- **Revises:** the first cut of this spec, which formed opinions from a *static, pre-fetched
  fact digest* fed to one-shot LLM calls. This revision makes the opinion-maker a
  **tool-using ReAct agent** that *pulls* the data it needs, widens the calendar
  connector to carry past **and** future, and **decouples** the opinion subsystem from
  the dreamer (shared neutral utilities, separate routes, legacy duplicate retired).
- **Builds on:** the architecture in `2026-06-27-nidra-opinions-dreams-rsi-design.md`
  (Opinions = grounded facts; Dreams = speculation; one-way valve between them).

## 0. Why this revision

Three problems with the first cut:

1. **Calendar was inert.** The fact builder queried calendar *backward* (`now−30d → now`),
   but the connector only persists `[now−1d, now+30d]` — the windows barely overlap, so
   the strongest signal (an upcoming booked flight; a recurring weekly 1:1) never became a
   fact. Both **past routines** and **future commitments** describe the user and must be
   available.
2. **The opinion-maker was handed a fixed snapshot.** A pre-fetched digest can't decide
   "I should look back 90 days for routines, or ahead 60 for plans." The opinion-maker
   should **query data as it needs it** — especially calendar windows.
3. **Opinions were coupled to the dreamer.** `opinion_workflow.py` imported `extract_json`
   from `user_model/dreamer.py`; the opinions route imported `engine_dream_fn` (dreamer) and
   `ollama_dream_fn` (a *connector* module). There are two dreamer modules, two dream
   routes, `extract_json` duplicated, and `DreamFn` defined three times. Opinions and
   dreams are deliberately separate subsystems; they must not import each other.

## 1. Principles (the invariants do not change)

- **Opinions = facts, not guesses.** High-confidence, fact-based, **cited**, no imagination.
  Speculation stays in Dreams.
- **Cite-or-omit, enforced deterministically.** Every opinion cites the exact signals
  behind it; uncited opinions are dropped by code, not trusted to the prompt.
- **Confidence is earned.** The LLM proposes confidence; a deterministic step caps it by
  evidence strength; the reviewer can only lower it.
- **Auditable.** Every opinion persists a `derivation` evidence chain to its facts.
- **NEW — the opinion-maker investigates.** It is an agent with tools that pulls data
  (browser, calendar past+future, email, memory) as needed, rather than consuming a fixed
  digest.

## 2. Architecture — the opinion agent

```mermaid
flowchart TD
  subgraph Agent["Opinion-maker — ReAct loop (engine-agnostic)"]
    M["LLM turn: emit JSON →\nACTION(tool) or FINAL(opinions)"]
    M -->|ACTION| T["run query tool"]
    T --> L["Evidence Ledger\n(every returned Fact, f1..fn)"]
    L --> M
  end
  M -->|FINAL| V["validate_citations (deterministic)\ncite-or-omit · dedup · cap confidence"]
  V --> R["review_opinions (LLM)\nskeptical 2nd pass · lower-only"]
  R --> P["persist → user_model_snapshots (+ derivation chain)"]
  P --> C["chat about_me + dreamer read"]
  Q[("query tools:\ncalendar · browsing · email · memory")] -. available to .- M
```

### 2.1 Reuse the existing tool-using engines — we write NO loop

The repo already has tool-using agents; the opinion-maker reuses them rather than
hand-rolling a ReAct loop:

- **`LoopEngine`** (`agent/core.py`) takes a `ToolRegistry` and runs the model↔tool loop via
  the provider's native `tool_calls` — for the `anthropic-api` / `openai-api` / `ollama` brains.
- **`ClaudeCodeEngine`** (`agent/claude_code_engine.py`) takes `tools: list[Tool]`, exposes
  them through an in-process **MCP server** (`create_sdk_mcp_server`), and the Claude Code SDK
  runs its **own** agentic loop — this is the **`claude-code` default, and it needs no API key**.
- **`CodexEngine`** exposes tools via an MCP server too.
- **`build_engine()`** (`agent/factory.py`) already selects the right engine for
  `settings.agent_engine` **and** wires a tool list in.

The opinion-maker therefore gets a **dedicated engine instance** built for the configured
brain, wired with the **query tools** (§2.2) and an opinion-forming system prompt. We call
`engine.respond([], "<form opinions>")`; the engine drives its **own** loop, calling our
tools, and returns final text we parse into proposed opinions. **No loop code is written by
us** — we add only the tools, the evidence ledger, and the cite-validation (mostly already
built).

To avoid duplicating `build_engine`'s engine-selection `if/elif`, extract that switch into a
small shared helper (`_make_engine(settings, *, tools, system_prompt)`) reused by both
`build_engine` and a new `build_opinion_engine(settings, *, tools)`.

**Testability:** the existing `ScriptedChatProvider` can return a `ChatResult` with
`tool_calls` then a final `ChatResult`, so the opinion-maker is tested deterministically
through `LoopEngine` (scripted: tool-call turn → observation → final opinions), exactly like
the chat tests. `max_turns`/`max_steps` already bound the loop in each engine.

### 2.2 Query tools (the investigation surface)

Each tool is a standard **`Tool`** object (`agent/tools.py` — the same abstraction as the
existing `recent_browsing` / `about_me` chat tools), whose `handler` runs the corresponding
**`facts.py` collector**, appends the returned `Fact`s to the run's evidence ledger (§2.3),
and returns a text observation listing those facts **with their ledger ids** so the model can
cite them:

| Tool | Args | Returns |
|---|---|---|
| `query_calendar` | `days_back`, `days_ahead` | calendar facts — **past routines + future commitments** |
| `query_browsing` | `days`, `kinds?`, `query?` | search / reading / choice / action facts |
| `query_email` | `n` | recent sender+subject facts (refs = message ids) |
| `query_memory` | — | preferences + open tasks facts |

Tools degrade gracefully: a source that's unconfigured (no email creds) or empty returns no
facts rather than erroring.

### 2.3 Evidence ledger (how grounding survives "pull")

A per-run **ledger** accumulates every `Fact` every tool returns, numbered `f1..fn` as they
arrive. This ledger is the **citable universe**: the deterministic `validate_citations` step
resolves each opinion's `evidence_fact_ids` against it and **drops any opinion that cites
nothing real**. So moving from "push a digest" to "pull via tools" changes *how* evidence is
gathered, not the guarantee — the agent cannot cite what it never pulled.

### 2.4 Validate → review → persist (unchanged, already built)

- **`validate_citations`** (deterministic): drop uncited/unresolvable; dedup by trait
  (keep best-supported); cap `confidence = min(proposed, calibrate(n_citations, n_sources))`;
  build the `derivation` chain `{method, evidence_fact_ids, fact_summaries, event_ids, refs}`.
- **`review_opinions`** (LLM, separate call): skeptical second pass; drop overreach; only
  *lower* confidence (`confidence_adjustment ∈ [-1,0]`); record `derivation["review"]`.
- **Persist** to `user_model_snapshots` (latest-per-trait on read). No migration — the
  `derivation` column already exists (0018).

## 3. Calendar connector — sync a wide past+future window

`connectors/google_calendar/connector.py` currently syncs `[now−1d, now+sync_days_ahead]`
(default 30 ahead). Add a **backward** window:

- New connector config `sync_days_back` (default **90**); keep `sync_days_ahead` (default 30).
- Sync `[now − sync_days_back, now + sync_days_ahead]`.
- No schema change (the `calendar_events` table already stores `start`/`end`); just more rows.
- `test_connection`'s probe window is unchanged (it's a health check, not the data sync).

This makes both routines (recurring past events) and commitments (upcoming events) real,
queryable signals for `query_calendar`.

## 4. De-coupling & reorg (high-craftsmanship cleanup)

### 4.1 A neutral completion utility
New `src/pragya_assistant/agent/completion.py` — the single home for the generic LLM
plumbing both subsystems share:

```python
CompletionFn = Callable[[str], Awaitable[str]]          # was DreamFn (×3)
def engine_completion_fn(engine: AgentEngine) -> CompletionFn   # was engine_dream_fn
def ollama_completion_fn(base_url, model, *, timeout=120) -> CompletionFn  # moved out of the connector
def extract_json(text: str) -> dict[str, Any]           # ONE canonical copy
```

### 4.2 Repoint and retire
- `user_model/dreamer.py` and `user_model/opinion_workflow.py` (and the new opinion agent)
  import from `agent/completion.py`. **No subsystem imports another.**
- **Retire the legacy duplicate** `connectors/browser_activity/dreamer.py`: its
  `extract_json`, `ollama_dream_fn`, `DreamFn`, and the old browser-only `DreamerService` +
  `build_digest` are superseded by `user_model/dreamer.py` (multi-source) and
  `agent/completion.py`. The old dream endpoint in `api/routes/browser_activity.py` that uses
  it is superseded by `/dreams/run`; remove it (and migrate/move the `build_digest` tests, or
  delete them with the code). *If any of the legacy path is still relied on (e.g. an
  extension call), confirm before deleting — default is delete.*
- **Split routes:** new `api/routes/opinions.py` holds `/opinions/*`; `api/routes/dreams.py`
  holds `/dreams/*` only.

### 4.3 Target layout
```
agent/completion.py            ← CompletionFn, engine_completion_fn, ollama_completion_fn, extract_json
user_model/opinion_agent.py    ← query Tools + evidence ledger + engine wiring (NO loop of our own) (NEW)
user_model/opinion_workflow.py → keeps validate_citations / review_opinions / calibrate; run() drives the agent
user_model/dreamer.py          → dreams only; imports agent/completion
user_model/facts.py            → Fact + collectors (now also used as tool bodies)
api/routes/opinions.py         ← /opinions/refresh                          (NEW)
api/routes/dreams.py           → /dreams/* only
connectors/google_calendar/connector.py → + sync_days_back
(retired) connectors/browser_activity/dreamer.py + its route
```

## 5. What's reused / reworked / retired

- **Reused:** `facts.py` collectors (become the tool bodies); `validate_citations`,
  `review_opinions`, `calibrate`; `UserModelStore` + `derivation` column; the engine
  selection + 503 guard pattern.
- **Reworked:** `FactDigestBuilder` (static push) → query `Tool`s + evidence ledger;
  `group_facts`/`form_opinions` (static two-stage) → a dedicated tool-wired engine that runs
  its own loop (`opinion_agent.py` holds the tools/ledger/engine wiring, not a loop); the
  route → split into `routes/opinions.py` and driven through the agent.
- **Retired:** the legacy connector dreamer duplication; the static digest builder; the
  separate grouping stage (the agent organizes its own investigation).

## 6. Testing (TDD)

- **Query tools:** each returns faithful `Fact`s with correct ids/refs; graceful when a
  source is empty/unconfigured.
- **Engine tool loop:** drive the opinion-maker through `LoopEngine` + a `ScriptedChatProvider`
  scripted as `tool_calls(query_calendar)` → observation → final `ChatResult` with the
  opinions JSON. Assert the right tool ran, the ledger captured the facts, and cited opinions
  persisted with the chain. Cover: model emits final immediately (no tools); model calls two
  tools; model never finalizes (engine `max_steps`/`max_turns` bounds it); model emits garbage
  (no crash).
- **Evidence ledger / validator:** citation to a real ledger id survives; to a non-existent
  id is dropped; confidence capped (already covered, keep).
- **Reviewer:** drop / lower-only / unreviewed-kept (already covered, keep).
- **Calendar connector:** seeding the sync uses `[now − sync_days_back, now + sync_days_ahead]`.
- **Reorg:** `extract_json`/completion fns import from `agent/completion`; assert no import
  from `user_model.opinion_*` to `dreamer` (and vice-versa); the legacy connector dreamer is
  gone and nothing imports it.
- **Route:** `/opinions/refresh` (in `routes/opinions.py`) drives the agent with a scripted
  provider and persists a cited opinion; engine selection + 503 guard intact.

## 7. Decisions log

- The opinion-maker is a **tool-using agent**, not a static-digest consumer — it **pulls**
  what it needs.
- **We write no ReAct loop.** We reuse the repo's existing tool-using engines via a dedicated
  engine instance + `Tool` objects. `claude-code` (the default) already exposes our tools via
  its in-process MCP server and runs its own loop — **no API key required**; `LoopEngine`
  does the same via native tool-calls for the api/ollama brains.
- **Grounding is preserved** by a per-run **evidence ledger** + the existing deterministic
  cite-or-omit validator.
- **Calendar carries past + future** (connector `sync_days_back` default 90).
- **Opinions are decoupled from the dreamer:** shared `agent/completion.py`, split routes,
  legacy connector dreamer retired.
- The validator/reviewer/persist invariants from the first cut are **unchanged**.

## 8. Out of scope (Phase 2, unchanged)

- Finance fact collector / `query_finance` tool.
- Snapshot retention/decay.
