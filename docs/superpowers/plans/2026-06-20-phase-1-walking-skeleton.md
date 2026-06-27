# Phase 1 — Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A thin, complete, production-grade spine: a provider-agnostic agent with hybrid (structured + semantic) memory, reachable via a FastAPI HTTP API, a Telegram bot, and a minimal Next.js web app — single-user, Dockerized, tested, CI-green.

**Architecture:** Python backend, async end-to-end. An `llm` provider layer abstracts Anthropic/OpenAI/Ollama behind `ChatProvider`/`EmbeddingProvider` interfaces. A `memory` service stores structured records (Postgres) and embeddings (pgvector) and exposes exact + semantic recall. An `agent` core runs a provider-agnostic tool-calling loop wired to memory tools. `api` (FastAPI) and `channels/telegram` are thin adapters over the agent. A Next.js app is a thin client. One Postgres+pgvector database. Everything in Docker Compose.

**Tech Stack:** Python 3.12 (uv), FastAPI, SQLAlchemy 2 (async) + asyncpg + Alembic + pgvector, `anthropic` & `openai` SDKs, httpx (Ollama + Telegram), pydantic-settings, structlog; pytest + pytest-asyncio + respx; ruff + mypy; Next.js (TypeScript) + React; Docker Compose; GitHub Actions.

## Global Constraints

- Python **3.12**; managed by **uv**; package import root `pragya_assistant` under `backend/src/`.
- **Async everywhere** (DB, HTTP, providers, FastAPI handlers).
- **No network in unit tests** — providers mocked (respx / fakes). DB integration tests run against a real Postgres+pgvector service.
- **TDD**: every behavior gets a failing test first. **Frequent commits** (one per task minimum).
- **Lint/type clean**: `ruff check`, `ruff format --check`, `mypy` must pass.
- **Config only via env** (pydantic-settings). Secrets never logged.
- **LLM defaults:** chat `anthropic` / `claude-opus-4-8` (adaptive thinking, **no** `temperature`/`top_p`/`budget_tokens` — removed on Opus 4.8); embeddings `openai` / `text-embedding-3-small` (dim 1536).
- **Security default:** write-with-confirm (Phase 1 memory writes are explicit tool calls; no autonomous outbound actions exist yet).

---

### Task 0: Backend foundation & tooling

**Files:**
- Create: `backend/pyproject.toml`, `backend/uv.lock` (generated), `backend/.python-version`
- Create: `backend/src/pragya_assistant/__init__.py`, `backend/src/pragya_assistant/py.typed`
- Create: `backend/ruff.toml`, `backend/mypy.ini`, `backend/pytest.ini`
- Create: `backend/Makefile`
- Create: `backend/tests/__init__.py`, `backend/tests/test_smoke.py`
- Create: `backend/README.md`

**Interfaces:**
- Produces: a working `uv run pytest` / `uv run ruff` / `uv run mypy` toolchain; package importable as `pragya_assistant`.

- [ ] **Step 1:** `pyproject.toml` with `[project]` (name `pragya-assistant`, requires-python `>=3.12`), runtime deps (`fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `sqlalchemy[asyncio]>=2`, `asyncpg`, `alembic`, `pgvector`, `anthropic`, `openai`, `httpx`, `structlog`, `cryptography`), `[dependency-groups] dev` (`pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`, `mypy`). `[tool.hatch]`/`build-system` with hatchling; package path `src`.
- [ ] **Step 2:** `ruff.toml` (line length 100, select E,F,I,UP,B,SIM,ASYNC), `mypy.ini` (strict, `python_version=3.12`), `pytest.ini` (`asyncio_mode=auto`, `testpaths=tests`, coverage opts). `Makefile` targets: `install`, `test`, `lint`, `typecheck`, `fmt`, `run`.
- [ ] **Step 3:** Write `tests/test_smoke.py`:
  ```python
  def test_package_imports():
      import pragya_assistant
      assert pragya_assistant.__version__
  ```
- [ ] **Step 4:** Run `uv run pytest tests/test_smoke.py -v` → FAIL (no `__version__`).
- [ ] **Step 5:** Add `__version__ = "0.1.0"` to `pragya_assistant/__init__.py`. Run → PASS. `uv run ruff check . && uv run mypy src`.
- [ ] **Step 6:** Commit `feat(backend): project foundation, tooling, smoke test`.

---

### Task 1: Config module

**Files:**
- Create: `backend/src/pragya_assistant/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings `BaseSettings`) with fields: `app_env: str`, `log_level: str`, `app_secret_key: str`, `api_auth_token: str`, `database_url: str`, `llm_chat_provider: Literal["anthropic","openai","ollama"]`, `llm_chat_model: str`, `llm_embedding_provider: Literal["openai","ollama"]`, `llm_embedding_model: str`, `llm_embedding_dim: int`, `anthropic_api_key: str|None`, `openai_api_key: str|None`, `ollama_base_url: str`, `telegram_bot_token: str|None`, `telegram_allowed_chat_ids: list[int]`. `get_settings() -> Settings` (lru_cached). Env prefix none; `telegram_allowed_chat_ids` parsed from comma string.

- [ ] **Step 1:** Test: setting env vars yields a populated `Settings`; `telegram_allowed_chat_ids="1,2"` parses to `[1,2]`; missing required (`api_auth_token`) raises `ValidationError`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `Settings` with `SettingsConfigDict(env_file=".env", extra="ignore")` and a field validator splitting chat IDs.
- [ ] **Step 4:** Run → PASS; lint+type.
- [ ] **Step 5:** Commit `feat(config): typed env-driven settings`.

---

### Task 2: LLM layer — types & interfaces

**Files:**
- Create: `backend/src/pragya_assistant/llm/__init__.py`, `backend/src/pragya_assistant/llm/types.py`, `backend/src/pragya_assistant/llm/base.py`
- Test: `backend/tests/llm/test_types.py`

**Interfaces (Produces):**
```python
# types.py
Role = Literal["system", "user", "assistant", "tool"]
@dataclass(frozen=True) class ToolSpec: name: str; description: str; input_schema: dict
@dataclass(frozen=True) class ToolCall: id: str; name: str; arguments: dict
@dataclass(frozen=True) class Message: role: Role; content: str = ""; tool_calls: tuple[ToolCall,...] = (); tool_call_id: str|None = None
@dataclass(frozen=True) class ChatResult: text: str; tool_calls: tuple[ToolCall,...]; finish_reason: Literal["stop","tool_calls"]; usage: dict
# base.py  (typing.Protocol)
class ChatProvider(Protocol):
    async def chat(self, *, messages: list[Message], tools: list[ToolSpec] | None = None, model: str | None = None) -> ChatResult: ...
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]: ...
```

- [ ] **Step 1:** Test constructing each dataclass; `Message` defaults; frozen immutability raises on mutation.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement `types.py` + `base.py` Protocols. **Step 4:** Run → PASS; type-check. **Step 5:** Commit `feat(llm): provider-agnostic types and interfaces`.

---

### Task 3: LLM providers — Anthropic, OpenAI, Ollama + factory

**Files:**
- Create: `backend/src/pragya_assistant/llm/anthropic_provider.py`, `openai_provider.py`, `ollama_provider.py`, `factory.py`
- Test: `backend/tests/llm/test_anthropic.py`, `test_openai.py`, `test_ollama.py`, `test_factory.py`

**Interfaces:**
- Consumes: `Message`, `ToolSpec`, `ChatResult`, `ToolCall`, `ChatProvider`, `EmbeddingProvider` (Task 2); `Settings` (Task 1).
- Produces: `AnthropicChatProvider(api_key, default_model)`; `OpenAIChatProvider(...)`; `OllamaChatProvider(base_url, default_model)`; `OpenAIEmbeddingProvider`, `OllamaEmbeddingProvider`; `build_chat_provider(settings) -> ChatProvider`, `build_embedding_provider(settings) -> EmbeddingProvider`.

Notes for implementer:
- **Anthropic:** use `anthropic.AsyncAnthropic`. `messages.create(model, max_tokens=4096, system=..., messages=..., tools=..., thinking={"type":"adaptive"})`. Map our `Message`/`ToolSpec` → Anthropic shapes; map response `content` blocks: `text` → text, `tool_use` → `ToolCall(id, name, input)`; `stop_reason=="tool_use"` → finish `tool_calls`. **Do not** send `temperature`/`top_p`/`budget_tokens` (400 on Opus 4.8). Tool schema: `{"name","description","input_schema"}`.
- **OpenAI:** `openai.AsyncOpenAI`; `chat.completions.create` with `tools=[{"type":"function","function":{name,description,parameters}}]`; map `tool_calls` → `ToolCall`.
- **Ollama:** httpx POST `{base}/api/chat` with `{model, messages, tools, stream:false}`; map `message.tool_calls`. Embeddings: POST `{base}/api/embed`.
- **Mock all network** with `respx` (or SDK `base_url` pointed at respx). Tests assert request body shape AND response→`ChatResult` mapping, including a tool-call response.

- [ ] **Step 1:** `test_anthropic.py`: mock a text response and a `tool_use` response; assert `ChatResult.text`, `tool_calls`, `finish_reason`; assert no `temperature` key in request. → FAIL → implement → PASS.
- [ ] **Step 2:** Repeat for OpenAI (chat + tool_calls) and Ollama (chat + embed).
- [ ] **Step 3:** `test_factory.py`: factory returns correct concrete type per `Settings`; unknown provider raises `ValueError`.
- [ ] **Step 4:** lint+type; Commit `feat(llm): anthropic/openai/ollama providers + factory`.

---

### Task 4: Database, models & migrations

**Files:**
- Create: `backend/src/pragya_assistant/memory/__init__.py`, `db.py` (engine/session/Base), `models.py`
- Create: `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_initial.py`
- Test: `backend/tests/memory/conftest.py` (db fixture), `backend/tests/memory/test_models.py`

**Interfaces (Produces):**
- `Base`, `engine`, `async_session_factory`, `get_session()` context manager (in `db.py`, built from `settings.database_url`).
- ORM models: `Person(id, name, relationship, birthday: date|None, notes, created_at)`, `Note(id, text, embedding: Vector(dim)|None, created_at)`, `Preference(id, key unique, value)`, `Conversation(id, channel, external_id, created_at)`, `Message(id, conversation_id fk, role, content, created_at)`.
- Migration `0001` creates `CREATE EXTENSION IF NOT EXISTS vector` + all tables + an ivfflat/hnsw index on `Note.embedding`.

- [ ] **Step 1:** `conftest.py`: session-scoped fixture connecting to `TEST_DATABASE_URL` (defaults to compose DB), creates a fresh schema (`Base.metadata.create_all` + ensure vector ext), yields a session, rolls back per test.
- [ ] **Step 2:** `test_models.py`: insert a `Person` with birthday, read back; insert `Note` with a 1536-float embedding, read back vector length. → FAIL (no models).
- [ ] **Step 3:** Implement `db.py` + `models.py` (pgvector `Vector` column). Generate Alembic baseline matching models; hand-author `0001` incl. extension + index.
- [ ] **Step 4:** Run tests against running Postgres → PASS. lint+type.
- [ ] **Step 5:** Commit `feat(memory): db, ORM models, initial migration (pgvector)`.

---

### Task 5: Repositories & MemoryService

**Files:**
- Create: `backend/src/pragya_assistant/memory/repositories.py`, `backend/src/pragya_assistant/memory/service.py`
- Test: `backend/tests/memory/test_service.py`

**Interfaces:**
- Consumes: models + session (Task 4); `EmbeddingProvider` (Task 2/3).
- Produces: `MemoryService(session_factory, embedder: EmbeddingProvider, embedding_model)` with:
  - `async remember_note(text) -> Note` (embeds + stores)
  - `async remember_person(name, relationship=None, birthday=None, notes=None) -> Person`
  - `async set_preference(key, value) -> Preference`
  - `async upcoming_birthdays(within_days: int) -> list[Person]`
  - `async find_people(query) -> list[Person]`
  - `async semantic_search(query, k=5) -> list[tuple[Note, float]]` (embeds query, pgvector cosine distance ordering)
  - `async get_preferences() -> dict[str,str]`

- [ ] **Step 1:** Tests (integration DB + a `FakeEmbeddingProvider` returning deterministic vectors): `remember_note` stores embedding; `semantic_search` ranks the closest note first; `remember_person` + `upcoming_birthdays` returns people with birthday within window (handles year wrap); `set_preference` upserts.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement repositories + service. **Step 4:** Run → PASS; lint+type. **Step 5:** Commit `feat(memory): repositories and MemoryService (exact + semantic)`.

---

### Task 6: Agent core & memory tools

**Files:**
- Create: `backend/src/pragya_assistant/agent/__init__.py`, `tools.py` (Tool abstraction + registry), `memory_tools.py`, `core.py`, `prompts.py`
- Test: `backend/tests/agent/test_tools.py`, `backend/tests/agent/test_core.py`

**Interfaces:**
- Consumes: `ChatProvider`, `Message`, `ToolSpec`, `ToolCall`, `ChatResult` (Task 2); `MemoryService` (Task 5).
- Produces:
  - `class Tool: name; description; input_schema: dict; handler: Callable[[dict], Awaitable[str]]`; `def spec() -> ToolSpec`.
  - `class ToolRegistry: register(tool); specs() -> list[ToolSpec]; async run(tool_call: ToolCall) -> Message` (returns role="tool" message).
  - `build_memory_tools(memory: MemoryService) -> list[Tool]` → `remember`, `exact_query` (params: kind ∈ {birthdays, people, preferences}, ...), `semantic_search`, `update_profile`.
  - `class Agent(provider: ChatProvider, registry: ToolRegistry, system_prompt, max_steps=6)` with `async respond(history: list[Message], user_text: str) -> tuple[str, list[Message]]` running the tool loop until `finish_reason=="stop"` or `max_steps`.

- [ ] **Step 1:** `test_tools.py`: registry runs a fake tool, returns a `tool` Message with the result and matching `tool_call_id`.
- [ ] **Step 2:** `test_core.py` with a `ScriptedChatProvider` (queue of `ChatResult`s): first result requests `remember`, second returns final text. Assert: tool executed (memory side effect via a fake/spy `MemoryService`), final text returned, conversation messages include user/assistant/tool turns, loop stops; and a `max_steps` guard test.
- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement `tools.py`, `memory_tools.py`, `prompts.py` (system prompt: identity, write-with-confirm posture, tool-use guidance), `core.py`. **Step 5:** Run → PASS; lint+type. **Step 6:** Commit `feat(agent): tool-calling loop + memory tools`.

---

### Task 7: FastAPI application

**Files:**
- Create: `backend/src/pragya_assistant/api/__init__.py`, `app.py` (factory + lifespan), `deps.py` (DI), `auth.py`, `routes/chat.py`, `routes/health.py`, `schemas.py`
- Create: `backend/src/pragya_assistant/main.py` (uvicorn entry), `backend/src/pragya_assistant/logging.py` (structlog setup)
- Test: `backend/tests/api/test_health.py`, `backend/tests/api/test_chat.py`

**Interfaces:**
- Consumes: `Settings`, providers factory, `MemoryService`, `Agent`.
- Produces: `create_app(settings, *, agent_factory=None) -> FastAPI`. Routes: `GET /health` (liveness), `GET /ready` (DB ping), `POST /chat {message, conversation_id?}` → `{reply, conversation_id}` (persists conversation+messages). Bearer-token dependency (`Authorization: Bearer <API_AUTH_TOKEN>`); 401 without it.

- [ ] **Step 1:** `test_health.py`: `/health` → 200 `{status:"ok"}` (no auth).
- [ ] **Step 2:** `test_chat.py`: `/chat` without token → 401; with token + an injected fake Agent → 200 with reply; conversation persisted (spy). Use FastAPI dependency overrides to inject the fake agent.
- [ ] **Step 3:** Run → FAIL. **Step 4:** Implement app factory, lifespan (init engine), `deps.py` wiring real providers/memory/agent, auth dependency, routes, structlog with request-id middleware. **Step 5:** Run → PASS; lint+type. **Step 6:** Commit `feat(api): FastAPI app, auth, chat + health routes`.

---

### Task 8: Telegram channel

**Files:**
- Create: `backend/src/pragya_assistant/channels/__init__.py`, `telegram/__init__.py`, `telegram/client.py` (httpx sendMessage), `telegram/webhook.py` (FastAPI router + update parsing + allowlist)
- Modify: `backend/src/pragya_assistant/api/app.py` (mount telegram router)
- Test: `backend/tests/channels/test_telegram.py`

**Interfaces:**
- Consumes: `Agent`, `Settings`, `Conversation`/`Message` persistence via memory/session.
- Produces: `TelegramClient(token).send_message(chat_id, text)` (httpx, mockable); `router` exposing `POST /telegram/webhook` that: validates `chat.id ∈ allowed_chat_ids` (ignore otherwise, 200), maps update→agent input (conversation keyed by chat_id), calls agent, sends reply via `TelegramClient`.

- [ ] **Step 1:** `test_telegram.py`: webhook with disallowed chat id → 200 and **no** agent call / no send (respx asserts no request); allowed chat id → agent invoked, `sendMessage` called with reply (respx mock). Inject fake agent + mock httpx.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement client + webhook + mount. **Step 4:** Run → PASS; lint+type. **Step 5:** Commit `feat(telegram): webhook channel with chat-id allowlist`.

---

### Task 9: Dockerization & Compose

**Files:**
- Create: `backend/Dockerfile`, `backend/.dockerignore`, `backend/entrypoint.sh`
- Create: `infra/docker-compose.yml`
- Modify: root `README.md` quickstart if needed

**Interfaces:**
- Produces: `docker compose -f infra/docker-compose.yml up --build` brings up `db` (`pgvector/pgvector:pg16`, healthcheck) + `backend` (multi-stage uv build; entrypoint runs `alembic upgrade head` then `uvicorn`). Env from root `.env`.

- [ ] **Step 1:** Backend `Dockerfile` (multi-stage: uv install → slim runtime, non-root user). `entrypoint.sh`: wait-for-db, `alembic upgrade head`, exec uvicorn.
- [ ] **Step 2:** `docker-compose.yml`: `db` with volume `pgdata`, healthcheck `pg_isready`; `backend` `depends_on: db: condition: service_healthy`, ports `8000:8000`, `env_file: ../.env`.
- [ ] **Step 3 (verify):** `cp .env.example .env`, set a dummy `ANTHROPIC_API_KEY`/tokens, `docker compose up --build -d`, poll `GET /health` → 200, `GET /ready` → 200 (DB reachable), check `alembic` applied (`/ready` proves connection; also `docker compose exec db psql -c "\dt"`). Tear down.
- [ ] **Step 4:** Commit `feat(infra): Dockerfile, entrypoint, compose (pgvector)`.

---

### Task 10: Frontend web app shell (Next.js)

**Files:**
- Create: `frontend/` Next.js app (TypeScript, App Router): `package.json`, `app/layout.tsx`, `app/page.tsx` (login gate), `app/chat/page.tsx` (chat UI), `lib/api.ts` (typed client), `app/api/.../` not needed (calls backend directly), `.env.local.example`, `Dockerfile`
- Test: `frontend/__tests__/api.test.ts` (vitest) for the client

**Interfaces:**
- Consumes: backend `POST /chat` with `Authorization: Bearer`.
- Produces: a minimal, clean chat UI: token entry (stored in memory/localStorage), message list, input box, calls `/chat`, renders replies; loading + error states.

- [ ] **Step 1:** Scaffold `npx create-next-app` (TS, app router, no telemetry). Add `lib/api.ts` `sendChat(message, conversationId?, token)` typed.
- [ ] **Step 2:** vitest test for `sendChat` (mock fetch) → asserts URL, auth header, body, parses reply. FAIL → implement → PASS.
- [ ] **Step 3:** Build `page.tsx` (token gate) + `chat/page.tsx` (chat UI) — clean, minimal styling; `NEXT_PUBLIC_API_BASE` env. `npm run build` succeeds; `npm run lint` clean.
- [ ] **Step 4:** Frontend `Dockerfile`; add `frontend` service to compose (optional for Phase 1 run, but include).
- [ ] **Step 5:** Commit `feat(frontend): Next.js single-user chat shell`.

---

### Task 11: CI

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: CI that lints+types+tests backend (with a Postgres+pgvector **service**), and lints+builds frontend.

- [ ] **Step 1:** `ci.yml`: trigger on push/PR. Job `backend`: `services: postgres: image: pgvector/pgvector:pg16` (env, healthcheck), steps: setup uv, `uv sync`, `ruff check`, `ruff format --check`, `mypy src`, `pytest` (with `TEST_DATABASE_URL` pointing at the service). Job `frontend`: setup node 24, `npm ci`, `npm run lint`, `npm run build`.
- [ ] **Step 2 (verify):** `act` not required; validate YAML and ensure local `make test` mirrors CI steps. Commit `ci: lint, type-check, test (backend + frontend)`.

---

## Self-Review

- **Spec coverage:** Foundation (T0) · LLM pluggable layer + per-task model arg (T2/T3) · hybrid memory Postgres+pgvector exact+semantic (T4/T5) · agent + 4 memory tools (T6) · API + single-user auth (T7) · Telegram allowlist (T8) · Docker Compose one-command (T9) · web app shell single-user login (T10) · CI/devops (T11). DoD (chat both surfaces; birthday persist + recall; tests/CI green) covered by T5/T6/T7/T8/T10 + T11. ✔
- **Placeholders:** none — interfaces and tests specified per task.
- **Type consistency:** `Message`/`ToolCall`/`ToolSpec`/`ChatResult` defined in T2 and reused verbatim in T3/T6; `MemoryService` methods defined in T5 and consumed by name in T6; `Agent.respond` defined T6, consumed T7/T8. ✔

## Execution

Hybrid: core spine built inline test-first to keep architecture coherent (no patching); isolated leaf work (the three providers, the frontend) parallelizable via subagents. Verify real functionality with Docker (Postgres up, API reachable, end-to-end chat) before declaring done.
