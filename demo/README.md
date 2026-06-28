# Nidra — live demo runbook

Two real agents, same question, same Claude model. The only difference is the memory.

- **Baseline — Claude Code + RAW memory.** Reads `raw_memory.md` (476 signals, ~6k
  tokens) → generic tourist itinerary. The preferences are in there, scattered, but a
  retrieval agent won't stitch them into taste.
- **Nidra — our chat + CURATED memory (real backend).** Ambient browsing events →
  `/opinions/refresh` induces cited opinions → `/dreams/run` adds cross-signal foresight
  → `/chat` plans from that learned model. Personalized, proactive.

> Raw facts give the model too many degrees of freedom — it defaults to the tourist
> average. A self-improving agent that learns you, validates beliefs against your
> activity, and revises them hands the model a small, trustworthy picture of you.
> **Less context, more truth.**

---

## A. Nidra side — the real loop (this is the product)

Backend must be up (`make up`; `:8088` healthy). Then:

```bash
python3 demo/seed_and_run.py            # ingest -> opinions -> dreams -> show -> chat
# or drive steps individually:
python3 demo/seed_and_run.py --ingest   # push 18 browsing events to Postgres
python3 demo/seed_and_run.py --opinions # curate cited opinions (claude-code, ~80s)
python3 demo/seed_and_run.py --dreams   # cross-signal dreams (claude-code, ~45s)
python3 demo/seed_and_run.py --chat     # ask the itinerary question (~55s)
```

For recording: pre-run ingest/opinions/dreams (they persist in the DB), then run
`--chat` live so the camera catches the personalized answer.

**What it proves (verified live):**
- 18 plain browsing signals → **9 cited opinions**, including `preference:local-authentic-over-tourist`
  — *induced* from a 96% read on "neighborhood izakayas, skip the tourist spots" vs a
  **9% bounce** on "Top 10 Tourist Attractions." Nobody told it that. It learned it.
- **7 dreams** with provenance back to those opinions (e.g. "will pick teamLab Planets
  over Borderless — matches the local-authentic pattern"; "Hakone weekend slots fill
  4–8 weeks out — most time-critical booking").
- The chat answer names his actual coffee roasters, jazz neighborhoods, the running loop,
  and leads with the dreams as "3 things to book before you fly."

## B. Baseline side — Claude Code on raw memory

In a second window, Claude Code:
```
Read demo/raw_memory.md and answer as my assistant:
"Plan my Tokyo trip — suggest an itinerary (where to stay, eat, and what to do) based on my preferences."
```
It churns ~6k tokens and returns the tourist average (Senso-ji, Shibuya, Tokyo Tower),
likely a Hakone ryokan, generic food — because it can only retrieve the scattered
signals, not consolidate them into taste.

---

## The question (ask both, verbatim)
> *"Plan my Tokyo trip — suggest an itinerary (where to stay, eat, and what to do)
> based on my preferences."*

## The RSI line to say
"The preferences were never stated — they live in browsing as scattered signals. Nidra
**consolidated** them into cited opinions, **induced** taste the data only implies
(local-over-tourist, from a 9% bounce on a listicle), **dreamed** the next needs, and
handed the agent a small validated model. Claude Code with the raw dump can only
retrieve — so it gives you the tourist average. **Retrieval gives the average. Learning
gives the person.**"

## Q&A one-liners
- **"Isn't this RAG?"** RAG retrieves raw chunks — that's the Claude Code side, and it
  gave the generic answer. Nidra *induces* beliefs (the local-vs-tourist call came from
  read-time, not any stated fact), files speculative *dreams*, and the loop validates
  them against later activity. Retrieval can't do that.
- **"Is the curated memory hand-written?"** No — `/opinions/refresh` and `/dreams/run`
  generated it from the 18 ingested events on camera. `seed_and_run.py` just pushes the
  events and calls the real endpoints.
- **"Same model both sides?"** Yes — Claude on both. Only the memory differs.

## Files
- `seed_and_run.py` — drives the real backend: ingest → opinions → dreams → chat
- `raw_memory.md` — the flat dump for the Claude Code baseline
- `gen_memory.py` — regenerates `raw_memory.md` (and a reference `curated_memory.md`)
