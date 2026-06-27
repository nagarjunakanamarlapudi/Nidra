# Nidra — a personal assistant that sleeps to learn you

**Hackathon concept for the AI Engineer World's Fair Hackathon 2026.**

**Status:** Brainstorm captured 2026-06-26. To review/refine on hackathon day (Sat 2026-06-27). Not yet specced into an implementation plan — open decisions at the bottom.

---

## THE demo we're shooting for (LOCKED 2026-06-27) — start every decision here

**Logline:** *Nidra spends one ordinary day watching how you work, read, and live — across your browser, inbox, and calendar — and overnight turns it into a single model of you that then shows up in everything it does.*

**Cohesion principle (why it's one story, not three features):** people don't live in silos. In a single morning you read a paper, book a flight, reply to your team, and move a meeting. Nidra watches *all* of it, **consolidates every surface into one model of you**, then applies a belief learned on one surface to a *different* one. That **cross-surface transfer** is the proof it's one mind, not a pile of recommenders. The whole demo follows **one person prepping a work trip to Tokyo** — which naturally lights up every surface.

**Canonical 3-min beat sheet:**
- **Hook (15s):** "You've told ChatGPT how you like things a hundred times. It still doesn't know you. Nidra learns you the way a friend does — by paying attention."
- **Act 1 — one ordinary day (35s):** Nidra observes; you instruct it on nothing. In ~a minute of normal activity it watches you: 📖 finish two distributed-systems papers, bounce off a "Top-10 microservices tips" listicle at 20%; 🌐 browse Tokyo flights → a ryokan → JR Pass; ✉️ fire a 2-line reply to your team (no greeting, no sign-off); 📅 drag a 9am review to 3pm. Panel: "observing — 1 day · 4 surfaces · 12 signals." You told it nothing. *(Staging: pre-seed the day; do ~20s live to prove it's real.)*
- **Act 2 — the Sleep, MONEY SHOT (55s):** hit `Sleep` → it consolidates the *whole day* into one model, each belief tagged with the surface it came from: 📅 "no meetings before 2pm" · ✉️ "voice: short, casual, no filler" · 📖 "trusts primary sources, skips listicles; deep in distributed systems" · 🌐 "Tokyo trip, ~spring, mid-range, compact/practical." Then the beat that wins it — a **cross-surface inference no single surface could make**: "reading consensus papers + you blocked Thursday afternoon + emailed about a 'design review' → you're prepping an architecture decision; I'll hold Thursday and put the Raft paper in front of you first." It **revises a prior belief** (strikethrough), prunes a one-off, **rewrites its own About-You file** (show the diff), self-evals → card: "5 beliefs · 1 revised · 1 cross-surface insight · predicted corrections ↓ 62%."
- **Act 3 — one ask, every belief (50s):** a single compound request it was never taught — "**Get me ready for Tokyo.**" Beliefs from four different surfaces converge into one action: books the pre-trip sync at **3pm** (from 📅) · drafts the team heads-up **short & casual** (from ✉️) — and that same voice appears in a **Telegram** ping (**cross-surface transfer**) · trip recap in **3 bullets** (format) · *"for the flight:"* the **one** paper worth your time **+ a challenger** to the view you keep reinforcing (from 📖) · hotel pick mid-range & walkable (from 🌐). Zero corrections. Then "actually, make it autumn" → the belief updates instantly (human stays in control; the correction feeds tonight's sleep). **Guards:** the flight-read is *evidence of opinion-formation, not a recommender*; never a reading feed/dashboard (trips "dashboard-as-main-feature").
- **Close (15s):** "One day of just paying attention. One model of you — and every night, it gets more yours. Nidra — the assistant that dreams."

**Rubric map:** Creativity (opinions from observation) · Technicality (induction → conflict revision → self-rewrite → self-eval gate) · Live Demo (Sleep button + belief diff + number + unprompted nail) · Future Potential (continual learning, zero intervention).

**Q&A armor:** not RAG (induces generalized beliefs + self-eval gate, applied to an unseen request) · privacy (on-device, redacted, opt-in, provenance, correctable) · built-this-weekend (Sleep engine + extension + self-eval gate; assistant shell is backdrop).

**Knobs (don't touch the spine):** scenario persona · Gemini $5k via Gemma-4 on-device or Antigravity · solo/team (real vs. staged transfer).

## Context

AI Engineer World's Fair Hackathon 2026, Shack15, SF. Hack window **Sat Jun 27 11:30am → Sun Jun 28 12:00pm** (submission). Solo allowed, teams ≤ 4, public repo, 1-min demo video + ~3-min live demo + 1–2 min Q&A.

**Required themes (pick one):** (1) Continual Learning, (2) Self-Improvement Stack, (3) Recursive Intelligence. → **We're in Theme 1 (Continual Learning)**, with a Self-Improvement-Stack flavored eval gate.

**Judging:** Technicality 40% · Creativity/Originality 25% · Live Demo 20% · Future Potential 15%. They explicitly want "completely unprecedented," not wrapper chatbots or basic prompts.

**Banned (instant DQ):** basic RAG, Streamlit, image analyzers, mental-health/medical/nutrition/personality/sports coaches, job screeners, **dashboard-as-main-feature**.

**New-work rule:** must clearly distinguish what was built during the event; the demo must spotlight the new engine. Existing Pragya code is minimal → rebuild into a **fresh public repo**; the self-improvement engine is the genuinely-new, scored part.

## Concept

**Nidra** (Sanskrit "sleep"; pairs with Pragya = "wisdom" → "wisdom through sleep"). English alt: **Lucid**.

> *The assistant that sleeps to learn you.* It learns from your corrections during the day; at night it "sleeps" — replays the day, induces generalized beliefs about you, revises old ones, rewrites its own behavior — and wakes up measurably smarter, with zero human intervention.

**Core differentiator (this is what keeps it out of the banned "basic RAG" bucket):** it does **not** memorize "move the 8am to 2pm." It **induces** "you don't do mornings" and applies that to a brand-new request it was never taught. Generalization, not retrieval.

## The unified RSI loop

1. **Daytime — capture.** Every turn logged as an episode `{context, action taken, user reaction/correction, connectors touched}`. Detect explicit ("no / actually / I prefer…") and implicit (user edits a draft/proposal) corrections.
2. **Night — the Sleep consolidation job (the RSI core).** Replay the day's episodes → cluster corrections → **induce generalized rules** (with confidence + evidence count) → resolve conflicts against existing beliefs (keep provenance) → prune one-offs / merge duplicates → **self-rewrite the user-model / "About You" behavior spec** (versioned, diffable).
3. **Self-eval gate (the Technicality flex).** Before promoting the new user-model, replay held-out episodes from the day old-vs-new and promote **only if** it would have needed fewer corrections. A true closed loop *with a guardrail*. Produces the demo's "predicted corrections ↓ 62%" number.
4. **Next day — measurably better.** Pre-empts, fewer corrections, transfers learning across connectors.

## The 3-minute demo (the story)

- **Hook (15s):** "What if your assistant could sleep — and dream about you?"
- **Act 1 — A day in your life (45s):** three corrections, each a *different dimension of you*: Calendar → it picks 8am, "No — never before 2pm"; Gmail → stiff draft, "Too formal, I write short and casual"; Summary → 5 paragraphs, "Just give me 3 bullets." Each flashes a quiet `📝 noted`.
- **Act 2 — The Sleep (45s, money shot):** hit `Sleep` → night mode → it induces the 3 generalized lessons live, **revises one prior belief** (strikethrough), prunes a one-off, and shows the **diff** of its self-written About-You file. Card: "Good morning. 3 new lessons, 1 belief revised. Predicted corrections ↓ 62%."
- **Act 3 — A smarter morning (45s):** a fresh compound task it was never taught — "Set up a call with the design team and give them a heads-up." Unprompted it books **3pm** (timing), drafts a **short casual** note (voice), recaps in **3 bullets** (format). Kicker: the casual voice learned in *email* shows up in a *Telegram* reply = **cross-domain transfer**.
- **Close (15s):** "It didn't just remember — it formed beliefs about you and revised them in its sleep. Nidra — the assistant that dreams."

## Why it wins (rubric map)

- **Technicality 40%** → consolidation engine: episodic→semantic induction, conflict resolution, self-rewriting behavior spec, + the self-eval gate. Not a weekend wrapper.
- **Creativity 25%** → "an AI that sleeps and dreams about you" is memorable and feels unprecedented.
- **Live Demo 20%** → a literal `Sleep` button, a visible diff, a hard number, an unprompted nail.
- **Future Potential 15%** → the path to assistants that adapt to individuals with zero intervention — Theme 1's thesis.

## Connectors = dimensions of you

Each connector is a different axis it learns and transfers across. Demo 3–4 that surface *distinct* dimensions (breadth of dimensions > breadth of integrations).

| Connector | Dimension it learns |
|---|---|
| Calendar | timing (when you meet) |
| Gmail / WhatsApp | voice & tone |
| Summaries / Web | information format |
| Tasks | what you prioritize |
| Finance | values (frugal vs. convenience) |

## Substrate

Build on Pragya's existing layers to move fast — Postgres + pgvector (episodes + semantic lessons), connector platform (Calendar / Gmail / Telegram / Web / Finance), pluggable agent engine. The demo spotlights **only** the new Sleep engine.

## Ambient browser-activity layer (added 2026-06-26)

A **browser extension** as a third, richest signal source: Nidra learns from how you actually live online, ambiently, zero effort — and **forms opinions from pure observation**, no instruction. This is likely the most original beat.

**Three signal layers, one Sleep engine:** (1) corrections (explicit, highest-confidence), (2) connector activity (calendar/email/etc.), (3) **ambient browser activity** (what you read/search/compare). All become episodes → nightly induction → one generalized model of you. They reinforce: observe → hypothesize → correct → consolidate.

**Feasibility — read the DOM, not the network.** Chrome MV3 extension, loaded unpacked (no store review for the demo):
- Easy / sufficient: `chrome.history` (backfill), `chrome.tabs` + `webNavigation` (live nav, dwell), **content script reads page DOM** (what they read — the gold), clicks/scroll/selections, **form inputs** (`input`/`change`, with secret redaction).
- Hard — **skip:** network *response* bodies (MV3 killed `webRequest` response reading; needs `chrome.debugger` + a warning banner). Not needed — the rendered DOM already has the content post-TLS.

**Privacy is the headline, not an afterthought** (also dodges the ethics-DQ rule): on-device / local-first processing (pairs with **Gemma 4 on-device** → Gemini/Gemma track), redaction allowlist (never capture password/payment fields; denylist banking/health/password-manager domains), opt-in with a visible "learning / pause" indicator, every inferred opinion carries provenance + is user-correctable (→ loops back to Layer 1).

**Demo variant:** browse normally for ~90s telling Nidra nothing → hit `Sleep` → it wakes with opinions ("planning a Japan trip in spring", "leans 14-inch over 16-inch", "reads primary sources, skips listicles") and acts on them unprompted.

**Scope:** extension (DOM + history + forms, redacted) ≈ 3–5 hrs; real work is feeding its episodes into the Sleep engine. Skip the network-response path.

**Mobile (ROADMAP — do NOT build this weekend):** browser plugin stays the only capture surface for the hackathon; native mobile capture is a time sink with no judging upside. Reality, for the pitch: a *profile* gives metadata only (MDM = app inventory; VPN/DNS = domains, not content unless you MITM — don't). Content-capture paths: **Android `AccessibilityService`** = system-wide on-screen text (sideload for demo; Play-forbidden), **iOS = reuse the plugin as a Safari Web Extension** + optional **screen-capture + on-device OCR** ("Computer Use for your phone"). NotificationListener (Android) and Share-sheet/Shortcuts are easy opt-in extras. Nidra is already *delivered* on mobile via the Telegram channel — delivery ≠ capture. Future-Potential line: "same on-device engine extends to your phone — Android accessibility, iOS screen understanding — all processed locally."

## Architecture + the dreamer (BUILT 2026-06-27)

Target shape (matches Pragya connectors): **capture → ingest to our server → the dreamer dreams on top.**
- **Capture** — MV3 WebExtension (Chrome + iOS Safari from one codebase) in `nidra/`. Reading/search/email(Gmail)/calendar(GCal)/forms/selections + history backfill; privacy-first (secrets skipped, PII redacted, denylist, pause, on-device). Validated: 20 unit + 2 e2e green; iOS compiles for the simulator.
- **Ingest** — **now a real Pragya connector (BUILT 2026-06-28).** `BrowserActivity` connector (`backend/.../connectors/browser_activity/`): declarative `ConnectorSpec` (auth `none`, capability `INGEST`), registered in the registry; the extension PUSHes events to `POST /connectors/browser_activity/ingest`, behind the app's **global bearer token** (one token — the extension already holds it to trigger dreams, so a separate per-connector secret bought nothing and was removed). Events persist to Postgres (`browser_activity_events`, migration `0013`), deduped by `(connector_key, client_id)`. The Node `nidra/collector/` remains as a zero-backend local fallback.
- **Dreamer** — ported to the backend: `backend/.../connectors/browser_activity/dreamer.py` (`DreamerService` + `build_digest` + `ollama_dream_fn`). Heuristic counting → the **LLM connects signals across activity** into intent + persona + next-needs. Default engine **on-device Gemma 4 via Ollama** (no API key); the completion callable is injected so tests are deterministic. Exposed at `POST /connectors/browser_activity/dream` (behind the app bearer token); the popup's **Dreams** tab calls it. (Node `dreamer.mjs` mirror still exists.) **Validated:** mypy strict + ruff clean; 10 new tests + the full ~380-test backend suite green. **Next:** embed activity to pgvector for semantic recall; persist dreams as memory notes so the agent/digest use them; schedule a nightly dream job.

**Proven (live Gemma 4, reproducible):** from raw signals *flights to tokyo · avis car rental · ryokan article · JR pass · Raft paper*, the dreamer returned 🔗 "planning a multi-destination Japan trip (Tokyo/Kyoto)" (90–100%) **and** 🔗 "two distinct interest areas: travel logistics AND advanced computer science" (80%) — the cross-signal leap the heuristic cannot make — plus proactive next-needs. This is **Act 2's "connect the dots" moment, running fully on-device.**

**Why it matters:** determinism tokenizes; the LLM brings world knowledge (Avis = car rental) and synthesis (flights + car + hotel = a trip). This is the heart of the demo, not a deferred extra.

## Open decisions (resume here on hackathon day)

1. **Gemini $5k booster?** Run the Sleep job as a **Gemini Antigravity managed agent** (stateful across nights via environment ID; skills declared in `AGENTS.md` / `SKILL.md`) → qualifies for the $5,000 Gemini prize. Or keep the brain on Claude/Codex / the on-device Gemma dreamer already built. (Gemma 4 on-device already advances the privacy angle + Gemma/Modular/DigitalOcean sponsor prizes.)
2. **Solo or team of 2–4?** Drives how much of the self-eval gate + cross-domain transfer is genuinely built vs. convincingly staged for the demo.
3. **Name:** Nidra vs. Lucid vs. other.

## Next step

On approval: write the full implementation spec → `writing-plans` → build. Reference: [[pragya-project-overview]].
