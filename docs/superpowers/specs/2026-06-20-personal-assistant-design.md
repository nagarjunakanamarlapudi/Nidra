# Pragya — Personal Assistant · Design Spec

**Status:** Approved (2026-06-20)
**Owner:** Pragyarjuna
**Scope of this doc:** Overall product vision + architecture, plus the **Phase 1** sub-project in implementable detail. Later phases each get their own spec → plan → build cycle.

---

## 1. Product definition

A **single-user personal assistant**, fully owned and controlled by its user. It is a reactive agent you converse with over **Telegram** and a **custom web app**, backed by a rich, durable memory of your world (notes, people, birthdays, tasks, finances, preferences). It proactively delivers **scheduled digests** (e.g. morning briefing, weekly finance summary, upcoming birthdays). It *suggests and drafts*; the human stays in the loop. It runs on a **home server** first and is built to lift to **AWS/Azure** later without a rewrite.

### Confirmed decisions (from scoping interview)

| Dimension | Decision |
|---|---|
| Users | Single user (the owner). No multi-tenancy. |
| Behavior | Reactive chat **+** scheduled digests. No autonomous, unattended actions in early phases. |
| Surfaces | Telegram bot (primary, mobile) **+** custom React/Next web app. Both call one backend API. |
| Memory | Hybrid: structured records (Postgres) **+** semantic index (pgvector) **+** a preferences/profile layer. |
| LLM | Pluggable provider layer, configurable & per-task routable: Anthropic API, OpenAI API, local Ollama. (Optional: Claude subscription via Agent SDK, non-critical path.) |
| Stack | Python backend (agent, memory, RAG, integrations, scheduler, bot) + React/Next web app. |
| Storage | One Postgres instance with the `pgvector` extension (structured + vector in one DB). |
| Hosting | Home server first (Docker), public endpoints via tunnel; portable to cloud. |

### Non-negotiables (engineering)

- **Production-grade, modular, extensible.** Clear bounded modules with well-defined interfaces; no hacks/patches.
- **Fully testable.** Unit + integration tests; high coverage of core logic; tests are first-class.
- **DevOps-minded.** Containerized, env-driven config, reproducible local dev, CI from day one, observability hooks.
- **Portable.** No home-server-specific assumptions in code; cloud migration is a redeploy.
- **Secure.** Secrets encrypted at rest; finance/personal data handled with care; least surprise (write-with-confirm).

---

## 2. Architecture (target)

```
   Telegram bot  ┐                              ┌─ LLM provider layer (anthropic │ openai │ ollama)
   Web app (Next)┤── HTTP API (FastAPI) ── Agent ┤─ Memory service (exact query + semantic search)
                 ┘                          core  └─ Tool registry: memory, calendar, email, web, finance
                                  Scheduler (cron) ── digest engine ── Telegram delivery
                                              │
                                  Postgres + pgvector  (one database)
```

- **Backend (Python):** agent core, LLM provider layer, memory service, tool registry, integration adapters, scheduler, Telegram bot, FastAPI API. Single deployable (plus DB), runnable via Docker Compose.
- **Frontend (React/Next):** custom chat UI + single-user login, talking to the backend API.
- **Infra:** Docker Compose (app + Postgres/pgvector); public endpoints exposed from home via Cloudflare Tunnel / Tailscale; config via environment variables; secrets encrypted.

### Module boundaries (backend)

| Module | Responsibility | Depends on |
|---|---|---|
| `config` | Typed settings from env (pydantic-settings). | — |
| `llm` | Provider-agnostic chat + tool-calling interface; Anthropic/OpenAI/Ollama implementations; per-task routing. | `config` |
| `memory` | DB models, repositories, embeddings, memory service (exact + semantic). | `config`, `llm` (embeddings) |
| `agent` | Agent loop: prompt assembly, tool-calling orchestration, conversation state. | `llm`, `memory`, `tools` |
| `tools` | Tool definitions + registry (memory tools first; integrations later). | `memory`, integrations |
| `api` | FastAPI app, routes, auth, dependency wiring. | `agent`, `memory` |
| `channels/telegram` | Telegram webhook + message adapter to the agent. | `agent`, `api` |
| `scheduler` | Cron + digest engine (Phase 2). | `agent`, `memory`, channels |

Each module is independently testable, communicates through explicit interfaces, and can be reasoned about in isolation.

---

## 3. Memory model

- **Structured (Postgres):** `people` (name, relationship, birthday, notes), `notes`, `tasks`, `events` (calendar cache), `preferences`; later `accounts`/`transactions`.
- **Semantic (pgvector):** embeddings over free-form note/doc/email text for fuzzy recall.
- **Agent memory tools:**
  - `exact_query` — precise structured lookups ("sum dining spend in May", "birthdays this month").
  - `semantic_search` — meaning-based recall ("that restaurant I liked").
  - `remember` — persist a fact/note (routes to structured and/or semantic store).
  - `update_profile` — maintain durable preferences/profile.

Embeddings are produced through the **same pluggable provider layer** (configurable model), so the embedding backend is swappable and can run locally via Ollama.

---

## 4. Phased roadmap

Each phase ships something usable and gets its **own spec → plan → build** cycle.

| Phase | Delivers | Notes |
|---|---|---|
| **1 — Walking skeleton** | Agent core + LLM provider layer + hybrid memory + Telegram + web-app shell + single-user login. Chat on both surfaces; it remembers people, birthdays, notes, preferences (exact + semantic recall). | Proves the whole architecture end-to-end. **This doc details Phase 1.** |
| **2 — Daily driver** | Scheduler + digests (morning briefing, birthdays-this-week) · Calendar (read/create) · Web search · tasks/reminders. | Highest value, lowest risk. |
| **3 — Email** | Gmail/IMAP read · triage · summarize · draft (no auto-send). Email feeds the digest. | Cleanly isolated adapter. |
| **4 — Finance module** (own mini-spec) | Read-only: statement/email/SMS parsing → accounts/transactions → weekly finance digest. RBI Account Aggregator (Setu/Finvu) later. Encrypted at rest. | Long pole + most sensitive data; sequenced last so it never gates the rest. |
| **5+ — Later plug-ins** | WhatsApp/Slack surfaces, doc import (Notion/Drive), voice, opt-in autonomous actions, cloud migration. | Genuine laters. |

---

## 5. Phase 1 — detailed scope (this build)

**Goal:** a thin, *complete*, production-grade spine you can talk to and that remembers your world. No external integrations yet.

### Deliverables

1. **Project foundation** — uv-managed Python package, ruff + mypy + pytest, Dockerized app, Postgres+pgvector via Compose, CI workflow, env-driven config, one-command local dev.
2. **LLM provider layer** — `ChatProvider` interface (chat with tool-calling) + `EmbeddingProvider` interface; Anthropic, OpenAI, and Ollama implementations; factory/registry selecting providers from config; per-task model routing. Network calls isolated behind the interface (mockable).
3. **Memory v1** — SQLAlchemy models (`Person`, `Note`, `Preference`, `Conversation`, `Message`) with Alembic migrations; pgvector column for note embeddings; repositories; `MemoryService` exposing exact + semantic operations.
4. **Agent core** — provider-agnostic agent loop with tool-calling; the four memory tools wired in; conversation persistence; deterministic, testable orchestration.
5. **HTTP API (FastAPI)** — `POST /chat` (and streaming variant), health/readiness endpoints; single-user auth (API token / single login); OpenAPI docs.
6. **Telegram bot** — webhook handler, chat-ID allowlist, adapter from Telegram messages to the agent and back.
7. **Web app shell (React/Next)** — minimal chat UI + single-user login, calling the API.

### Definition of done

- `docker compose up` brings up DB + backend; migrations apply automatically.
- You can chat via **both** Telegram and the web app.
- Telling it "my sister's birthday is March 3" persists a `Person` record; later "whose birthdays are coming up?" answers via `exact_query`, and "what did I say about the car?" answers via `semantic_search`.
- `make test` / `uv run pytest` passes; CI is green; lint + type-check clean.

### Phase 1 explicitly out of scope

Calendar, email, web search, finance, scheduler/digests, autonomous actions — all later phases.

---

## 6. Cross-cutting requirements

- **Testing:** unit tests for every module (providers mocked); integration tests against a real Postgres+pgvector (via Compose/testcontainers); the agent loop tested with a fake provider; API tested with FastAPI TestClient.
- **Config & secrets:** all config via env (`.env` for local, real secrets manager later); secrets never logged; encryption at rest for sensitive values.
- **Observability:** structured logging, request IDs, basic metrics/health endpoints from day one.
- **Security defaults:** **write-with-confirm** (agent reads freely, confirms before any state-changing/outbound action); single-user auth (strong login + Telegram allowlist), not a full multi-user auth system.
- **Portability:** Docker images, standard Postgres, env config — cloud move is a redeploy.

---

## 7. Assumptions & open questions

- **Assumed:** write-with-confirm default; single-user auth; pgvector (not a separate vector DB); embeddings via the pluggable provider; English-first.
- **Open (defer to later phases):** India Account Aggregator provider choice (Setu vs Finvu vs …); calendar provider specifics (Google API vs CalDAV); email provider (Gmail API vs IMAP); cloud target (AWS vs Azure) at migration time.
