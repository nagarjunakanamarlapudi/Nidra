# Nidra — Opinions, Dreams & Recursive Self-Improvement (Architecture)

- **Date:** 2026-06-27
- **Status:** Design / principles (pre-implementation)
- **Scope:** The backend two-layer user-model architecture (Opinions + Dreams),
  the one-way provenance valve between them, and the RSI loop that lets the
  Dream layer self-improve without collapsing.

This sits above the activity-capture work (see
`2026-06-27-nidra-activity-capture-design.md`). Capture produces *signals*;
this doc defines what forms beliefs from them and what reasons on top.

## 1. First principles

Two research traditions converge on the **same structural split**:

- **RL / world-models** (Ha & Schmidhuber 2018; Dreamer V1–V3, Hafner 2019–2023):
  a model of the world is fit **only on real experience**; behavior is improved
  on **imagined rollouts** *inside* that model. Imagination updates the **policy**,
  never the world model.
- **LLM agents** (Generative Agents, Park 2023; sleep-time compute, Lin 2025):
  raw observations are consolidated into higher-level **beliefs**; an **offline**
  pass anticipates future needs.

So: a **persistent model fit only on real data**, and a **generative process on
top that consumes it** — never produces ground truth. That is Opinions vs Dreams.

## 2. The two layers

### Opinions — the consolidated user model
- **Definition:** beliefs that are a **function of real signals** (raw extraction
  OR grounded synthesis/consolidation of them), each with confidence + provenance.
- **Source:** real signals only — browsing, email, calendar, Plaid financials, …
- **Cadence:** online, per-signal (cheap, continuous).
- **Store:** `user_model_snapshots` (append-only, latest-per-trait).
- **Answers:** "what is true about the user *now*."

### Dreams — offline generative reasoning on top
- **Definition:** speculative foresight / latent-intent hypotheses that **go beyond
  the data**. A Dream is **not an Opinion.**
- **Source:** the current Opinion set + recent raw signals across all connectors.
- **Cadence:** offline — nightly / idle, or when accumulated signal-importance
  crosses a threshold.
- **Store:** `dreams` (its own table; confidence + TTL + status). Dreams **never**
  write `user_model_snapshots`.
- **Answers:** "what's the latent story / what will they need."

### The hard invariant (the one-way valve)

```
real signals ─────────────▶ OPINIONS  (grounded, provenance)
                                 │
                                 ▼
                              DREAMS   (speculative — own store, TTL, NOT opinions)
                                 │
                                 ▼
                              ACTION   (proactive suggestion / act)
                                 │
                       user responds = a NEW REAL SIGNAL
                                 │
                                 ▼
                              OPINIONS  ◀── only now does it ground a belief
```

**A Dream becomes an Opinion only by being acted on and confirmed by a real
signal.** An unacted dream **expires** (TTL). The dreamer is forbidden from
writing Opinions directly — that is the foot-shooting / dreaming-on-dreams path
that causes model collapse (Shumailov et al., *Nature* 2024) and ungrounded
rollout error (Ha & Schmidhuber 2018).

**Consolidation vs speculation** (route differently):

| Offline output | Grounded in real data? | Destination |
|---|---|---|
| Consolidation — "read 12 Rust articles → interested in Rust" | yes (synthesis of real signals, with provenance) | **Opinion** (this is opinion-forming, not dreaming) |
| Speculation — "will research a larger car in ~3 months" | no (a leap past the data) | **Dream** only; grounds an Opinion only after acted-on + confirmed |

## 3. Recursive self-improvement of the Dream layer

**What self-improves:** the **dream policy** — the mapping
`(Opinions + signals) → useful proactive hypotheses/actions`. Not the beliefs.
(Mirror: Dreamer's imagination improves the policy; real experience updates the
world model.)

**The verifier is reality, not the model.** Every RSI method that works is anchored
to a grounded verifier — AlphaZero/MuZero (game outcome), STaR (keep only rationales
that reach the verified answer), Self-Instruct (filtered). The dangerous one is
Self-Rewarding (model judges itself → reward hacking). The action-gated valve in §2
*is* the RSI label source.

**Two grounded verifier forms (both real signals):**
1. **Direct** — the user acted on / dismissed the surfaced dream.
2. **Corroboration** — independent later activity *matches the dream's prediction*
   even if the suggestion was never touched (dreamt "planning a Japan trip"; user
   later books a Tokyo hotel). This is the **stronger, harder-to-game** signal.

`ignored` is **weak** signal, not a negative (didn't see it ≠ didn't want it).
Treating ignore as a strong negative trains the dreamer to be timid.

**The temporal loop** (t0 activity → t1 dream → t2 activity → t3 dream): dreams at
t3 should be better-targeted than t1. The t2 activity improves t3 through **two
distinct levers — keep them separate or the RSI metric lies:**

| t2 signal | Lever | Changes |
|---|---|---|
| acted on / corroborated / dismissed the t1 dreams | **ΔPolicy (RSI)** | *how* the dreamer dreams — the reward |
| new, independent activity | **ΔState (world model)** | *what* it dreams from — fresher Opinions |

ΔState is the safe, always-on path (better input → sharper dreams, unchanged
dreamer). ΔPolicy is the one needing the collapse/hacking guardrails. Don't credit
the policy for gains that were really just fresher data.

**"More relevant over time" is tracking a MOVING TARGET, not a monotonic climb.**
The user is non-stationary — intent at t3 ≠ t0. So the honest goal is "well-targeted
to the user's state *at t3*, with the hit-rate trend climbing across many cycles";
a single t1-vs-t3 comparison is confounded by changed context.

**Loop:**
1. Dream proposes hypotheses → some surfaced as actions.
2. Real outcomes label them: confirmed (direct or corroborated) / refuted / ignored(weak).
3. Labeled `{dream, outcome}` pairs improve the dream policy.

**Ladder (start safe):**
- **Phase 1 — in-context RSI (no training):** keep a track record of resolved
  dreams; feed recent confirmed/refuted exemplars into the next dream prompt
  ("patterns that paid off / flopped"). No weight updates → no collapse risk →
  fully auditable. Buildable immediately.
- **Phase 2 — STaR/DPO on reality-labeled pairs only:** once enough acted-and-
  confirmed dreams exist, fine-tune the dream policy on verified-good vs refuted
  examples. Train **only** on real-outcome-labeled data; hold out a real-outcome
  eval to detect collapse/hacking.

**Guardrails (non-negotiable):**
- Reality is the verifier; **never** use the dreamer's self-score as a *training*
  signal (cheap pre-filter only).
- Train only on real-outcome-labeled dreams (prevents model collapse).
- Bound the dream horizon; inject uncertainty so dreams can't exploit model gaps.
- **Preserve exploration** — protect the tails; keep proposing novel hypotheses so
  RSI doesn't collapse into a rut (one travel win shouldn't make every dream travel).
- **Non-stationarity (the user is a moving target):** recency-weight / decay
  Opinions so stale beliefs stop dragging dreams; **retract** dreams whose premise
  expired (trip cancelled at t2 → don't re-dream it at t3) — course-correction
  includes *killing* dreams, not only adding better ones.
- **Measure it:** RSI is real only if **dream hit-rate** (confirmed ÷ surfaced) and
  **calibration** trend up over time. Unmeasured = unfalsifiable.

### 3a. Cold start — backtesting on history (offline replay)

With enough past data, bootstrap the dreamer **without waiting for live feedback**:
dream *as of* a past time T (using only signals ≤ T), then verify against what the
user actually did in (T, T+Δ]. This is offline replay (Dreamer's buffer) + a
forecaster backtest, and it seeds the Phase-1 track record / Phase-2 training set
from day one. Three rules or it lies:

- **No look-ahead leakage.** Reconstruct Opinions *as they were at T* by replaying
  events ≤ T — never feed today's Opinions (the future is baked in), and exclude
  future dreams from the track record. Feasible here: `browser_activity_events.ts`
  + append-only `user_model_snapshots.computed_at` give point-in-time replay.
- **Backtest can use only the corroboration verifier, and measures PREDICTIVENESS,
  not LIFT.** There's no intervention in history (you can't surface a suggestion to
  the past user), so: absence of on-platform evidence ≠ refutation (false
  negatives), and a dreamer that backtests well may behave differently once it
  actually nudges (off-policy gap). The **live** loop is still required for
  intervention effect.
- **Recency-weight** — a dreamer tuned on 6-month-old patterns can be stale; use
  backtest to bootstrap + filter bad variants, then keep adapting live.

**Payoff:** a fixed historical benchmark to score and compare dreamer versions
**offline, before any live exposure** — this is also the answer to "is the dreamer
improving?" (the measurability guardrail above).

## 4. Data model

### `user_model_snapshots` (Opinions) — unchanged, written by the opinion-former only
`{ trait, value, confidence, evidence, provenance, computed_at }`. The grounded
opinion-former is the **only** writer; the dreamer never writes here.

### `dreams` (new) — written by the dreamer only

```python
class Dream(Base):
    __tablename__ = "dreams"
    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis: Mapped[str] = mapped_column(Text)              # the speculative claim / suggestion
    kind: Mapped[str] = mapped_column(String(32))              # foresight | suggestion | need
    confidence: Mapped[float] = mapped_column(default=0.0)
    provenance: Mapped[list | None] = mapped_column(JSONB)     # opinions + signals it drew on
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    #   proposed → surfaced → acted → (confirmed | refuted) ; or → expired
    outcome: Mapped[dict | None] = mapped_column(JSONB)        # the real feedback that resolved it
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[dt.datetime | None]                     # TTL — unacted dreams die
    resolved_at: Mapped[dt.datetime | None]
```

- Acting on a dream **emits a real activity event** ("suggested X → accepted/dismissed").
  That event ingests like any other signal and is what may ground a new Opinion.
- Resolved dreams (`confirmed`/`refuted`) are the RSI track record (Phase 1
  exemplars; Phase 2 training data).

## 5. Where it runs

- **Opinion-former** (backend, online): per-signal extraction + grounded
  cross-source consolidation → `user_model_snapshots`. Generalizes today's
  browser-only `derive.py` into a multi-source service.
- **Dreamer** (backend, offline LLM): reads Opinions + signals → `dreams`;
  self-improves in-context from the resolved-dream track record.
- **Extension:** signal collector only — no opinion-forming, no dreaming.

## 6. Open decisions

1. **RSI aggressiveness:** Phase 1 (in-context) now, Phase 2 (fine-tune) later —
   *recommended*; vs investing in fine-tuning earlier. (Lean: Phase 1 first.)
2. **Opinion-former mechanism:** cheap deterministic/rules vs a small LLM
   extraction pass per signal (both are "grounded"; the distinction is cost/quality).
3. **Dream cadence:** fixed nightly vs importance-threshold trigger (or both).
4. **Action surface:** where dreams are surfaced to the user (digest, assistant
   turn, proactive nudge) — determines how outcomes are captured.

## 7. Decisions log

- Opinions are **real-signal-only**; Dreams live in a **separate store** with TTL
  and never write Opinions.
- A Dream → Opinion transition happens **only** via acted-on → confirmed real
  feedback.
- RSI improves the **dream policy** (not beliefs), verified by **real outcomes**,
  **in-context first**; never train on unlabeled self-output, never self-reward
  for training.
- t2 feedback splits into **ΔPolicy (RSI)** vs **ΔState (fresher world model)** —
  measured separately so RSI isn't credited for data freshness.
- Verifier has two grounded forms — **direct action** and **corroborating
  activity**; `ignored` is weak signal, not a negative.
- Improvement tracks a **non-stationary** user: decay Opinions, retract
  expired-premise dreams, preserve exploration.
- **Backtesting on history** is the cold start + offline benchmark — point-in-time
  (no leakage), corroboration-only, measures predictiveness not lift; live loop
  still required for intervention effect.
