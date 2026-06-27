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
Self-Rewarding (model judges itself → reward hacking). Nidra's verifier is the
**real outcome of acting on a dream** (accepted / engaged / dismissed / corrected).
The action-gated valve in §2 *is* the RSI label source.

**Loop:**
1. Dream proposes hypotheses → some are surfaced as actions.
2. Real outcomes label them: confirmed / refuted / ignored.
3. Labeled `{dream, action, outcome}` pairs improve the dream policy.

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
  RSI doesn't collapse into a rut.
- **Measure it:** RSI is real only if **dream hit-rate** (acted-&-confirmed ÷
  surfaced) and **calibration** trend up over time. Unmeasured = unfalsifiable.

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
