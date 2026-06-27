# Cron Sidecar Replaces In-Process APScheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Pragya's in-process APScheduler with a tiny Alpine-based cron sidecar container that POSTs to the backend's HTTP endpoints on schedule, eliminating the scheduling concern from the API process.

**Architecture:** The cron sidecar is a separate Docker service (`infra/cron/`) that reads schedule settings from the same `.env` file the backend uses, writes `/etc/crontabs/root` at startup, and runs `curl` to hit `POST /digests/run`, `POST /finance/sync`, and the new `POST /digests/run-weekly`. The backend is stripped of its APScheduler lifespan code. A new `POST /digests/run-weekly` endpoint is added to the backend (TDD) so the weekly finance digest job has an HTTP surface.

**Tech Stack:** Python/FastAPI (backend), POSIX sh + busybox crond (sidecar), Alpine 3.20, Docker Compose, pytest + httpx for tests, ruff + mypy for quality gates.

## Global Constraints

- TDD for all backend code: write the failing test first, confirm it fails, then implement.
- Do NOT touch `telegram_poller` service or its code.
- Do NOT remove the `apscheduler` dependency from `pyproject.toml` or touch the lockfile.
- Do NOT push to remote; commit locally only.
- `uv run ruff check . && uv run ruff format --check . && uv run mypy src` must pass clean after every task.
- Backend test runner: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest -q`.
- Internal backend port inside Compose is `8000` (the container always binds 8000; `APP_PORT` is the HOST port).
- `env_file` for the backend and cron is `../.env` (relative to `infra/`).

---

### Task 1: Add `POST /digests/run-weekly` endpoint (TDD)

**Files:**
- Modify: `backend/src/pragya_assistant/api/routes/digests.py`
- Modify: `backend/tests/api/test_digests_api.py`

**Interfaces:**
- Consumes: `build_weekly_finance_prompt` from `pragya_assistant.agent.prompts` (already exists, signature: `(today: str) -> str`); `digests.run(prompt_fn)` from `DigestService` (already exists).
- Produces: `POST /digests/run-weekly` → `DigestOut` (same schema as `/digests/run`).

- [ ] **Step 1: Write the failing tests**

  Append to `backend/tests/api/test_digests_api.py`:

  ```python
  async def test_run_weekly_requires_token(build_test_app: AppBuilder) -> None:
      app = build_test_app(ScriptedChatProvider([]))
      async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
          resp = await c.post("/digests/run-weekly")
      assert resp.status_code == 401


  async def test_run_weekly_stores_digest(build_test_app: AppBuilder) -> None:
      app = build_test_app(
          ScriptedChatProvider([_stop("Weekly finance: all green.")])
      )
      async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
          run = await c.post("/digests/run-weekly", headers=AUTH)

      assert run.status_code == 200
      body = run.json()
      assert "Weekly finance" in body["content"]
      assert body["delivered"] == "stored"
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test \
    uv run pytest tests/api/test_digests_api.py -v -k "weekly" 2>&1 | tail -20
  ```

  Expected: two tests **FAILED** with `404 != 401` / `404 != 200` (route doesn't exist yet).

- [ ] **Step 3: Add the endpoint**

  Edit `backend/src/pragya_assistant/api/routes/digests.py` to add the import and new route. The full file should be:

  ```python
  """Digest endpoints — list recent digests and trigger one on demand."""

  from __future__ import annotations

  from typing import Annotated

  from fastapi import APIRouter, Depends

  from pragya_assistant.agent.prompts import build_weekly_finance_prompt
  from pragya_assistant.api.auth import require_token
  from pragya_assistant.api.deps import get_digests
  from pragya_assistant.api.schemas import DigestOut
  from pragya_assistant.digests.service import DigestService
  from pragya_assistant.memory.models import Digest

  router = APIRouter(tags=["digests"], dependencies=[Depends(require_token)])


  def _out(d: Digest) -> DigestOut:
      return DigestOut(id=d.id, content=d.content, delivered=d.delivered, created_at=d.created_at)


  @router.get("/digests", response_model=list[DigestOut])
  async def list_digests(
      digests: Annotated[DigestService, Depends(get_digests)],
  ) -> list[DigestOut]:
      return [_out(d) for d in await digests.recent()]


  @router.post("/digests/run", response_model=DigestOut)
  async def run_digest(
      digests: Annotated[DigestService, Depends(get_digests)],
  ) -> DigestOut:
      return _out(await digests.run())


  @router.post("/digests/run-weekly", response_model=DigestOut)
  async def run_weekly_digest(
      digests: Annotated[DigestService, Depends(get_digests)],
  ) -> DigestOut:
      return _out(await digests.run(build_weekly_finance_prompt))
  ```

- [ ] **Step 4: Run tests to verify they pass**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test \
    uv run pytest tests/api/test_digests_api.py -v 2>&1 | tail -20
  ```

  Expected: all 4 digest API tests **PASSED**.

- [ ] **Step 5: Lint + typecheck**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  uv run ruff check . && uv run ruff format --check . && uv run mypy src
  ```

  Expected: no errors.

- [ ] **Step 6: Commit**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  git add backend/src/pragya_assistant/api/routes/digests.py \
          backend/tests/api/test_digests_api.py
  git commit -m "feat(api): add POST /digests/run-weekly endpoint (TDD)"
  ```

---

### Task 2: Remove in-process scheduler from backend

**Files:**
- Modify: `backend/src/pragya_assistant/api/app.py`
- Modify: `backend/src/pragya_assistant/scheduling/__init__.py` (verify/fix)
- Delete: `backend/src/pragya_assistant/scheduling/scheduler.py`
- Delete: `backend/tests/scheduling/test_scheduler.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `app.py` with a simplified `lifespan` that only disposes the engine; no scheduler import.

- [ ] **Step 1: Check `scheduling/__init__.py` for re-exports**

  ```bash
  cat /Users/nagarjuna/projects/naga_personal_assistant/backend/src/pragya_assistant/scheduling/__init__.py
  ```

  The file currently only contains `"""Background scheduling (in-process APScheduler)."""` — no re-exports. If it re-exports `build_scheduler`, remove that line.

- [ ] **Step 2: Delete the scheduler module and its tests**

  ```bash
  rm /Users/nagarjuna/projects/naga_personal_assistant/backend/src/pragya_assistant/scheduling/scheduler.py
  rm /Users/nagarjuna/projects/naga_personal_assistant/backend/tests/scheduling/test_scheduler.py
  ```

- [ ] **Step 3: Strip the scheduler from `app.py`**

  Replace the full content of `backend/src/pragya_assistant/api/app.py` with:

  ```python
  """FastAPI application factory."""

  from __future__ import annotations

  import uuid
  from collections.abc import AsyncIterator
  from contextlib import asynccontextmanager

  import structlog
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  from starlette.middleware.base import RequestResponseEndpoint
  from starlette.requests import Request
  from starlette.responses import Response

  from pragya_assistant.api.deps import AppComponents, build_components
  from pragya_assistant.api.routes import chat, conversations, digests, finance, health
  from pragya_assistant.channels.telegram import webhook as telegram_webhook
  from pragya_assistant.config import Settings
  from pragya_assistant.logging_config import configure_logging


  def create_app(settings: Settings, *, components: AppComponents | None = None) -> FastAPI:
      """Build the app. Pass ``components`` to inject wiring (tests); otherwise
      the composition root builds it from settings."""
      configure_logging(settings.log_level)
      resolved = components or build_components(settings)

      @asynccontextmanager
      async def lifespan(_: FastAPI) -> AsyncIterator[None]:
          try:
              yield
          finally:
              await resolved.engine.dispose()

      app = FastAPI(title="Pragya", version="0.1.0", lifespan=lifespan)
      app.state.components = resolved

      app.add_middleware(
          CORSMiddleware,
          allow_origins=resolved.settings.cors_allow_origins,
          allow_credentials=True,
          allow_methods=["*"],
          allow_headers=["*"],
      )

      @app.middleware("http")
      async def bind_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
          structlog.contextvars.clear_contextvars()
          structlog.contextvars.bind_contextvars(request_id=str(uuid.uuid4()))
          return await call_next(request)

      app.include_router(health.router)
      app.include_router(chat.router)
      app.include_router(conversations.router)
      app.include_router(digests.router)
      app.include_router(finance.router)
      app.include_router(telegram_webhook.router)
      return app
  ```

- [ ] **Step 4: Update `scheduling/__init__.py` docstring** (remove the "in-process APScheduler" mention since the module is now empty/vestigial):

  ```python
  """Scheduling package (now delegated to the cron sidecar)."""
  ```

- [ ] **Step 5: Run full test suite**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test \
    uv run pytest -q 2>&1 | tail -20
  ```

  Expected: all tests pass (the scheduler tests we deleted are gone; everything else is green).

- [ ] **Step 6: Lint + typecheck**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  uv run ruff check . && uv run ruff format --check . && uv run mypy src
  ```

  Expected: no errors (the dangling `build_scheduler` import is gone from `app.py`).

- [ ] **Step 7: Commit**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  git add backend/src/pragya_assistant/api/app.py \
          backend/src/pragya_assistant/scheduling/__init__.py
  git rm backend/src/pragya_assistant/scheduling/scheduler.py \
         backend/tests/scheduling/test_scheduler.py
  git commit -m "refactor(backend): remove in-process APScheduler (replaced by cron sidecar)"
  ```

---

### Task 3: Build the cron sidecar image

**Files:**
- Create: `infra/cron/Dockerfile`
- Create: `infra/cron/entrypoint.sh`

**Interfaces:**
- Produces: Docker image `pragya-cron` that, when given env vars, writes `/etc/crontabs/root` and execs `crond -f -l 8 -L /dev/stdout`.
- Env vars consumed: `API_BASE`, `API_AUTH_TOKEN`, `DIGEST_HOUR`, `DIGEST_MINUTE`, `FINANCE_SYNC_HOUR`, `FINANCE_SYNC_MINUTE`, `FINANCE_WEEKLY_ENABLED`, `FINANCE_WEEKLY_DAY`, `TZ`.

- [ ] **Step 1: Create the directory**

  ```bash
  mkdir -p /Users/nagarjuna/projects/naga_personal_assistant/infra/cron
  ```

- [ ] **Step 2: Write the Dockerfile**

  Create `infra/cron/Dockerfile`:

  ```dockerfile
  FROM alpine:3.20
  RUN apk add --no-cache curl tzdata
  COPY entrypoint.sh /entrypoint.sh
  RUN chmod +x /entrypoint.sh
  ENTRYPOINT ["/entrypoint.sh"]
  ```

- [ ] **Step 3: Write the entrypoint script**

  Create `infra/cron/entrypoint.sh` (POSIX sh — no bashisms):

  ```sh
  #!/bin/sh
  set -e

  # Map day name → busybox crond DOW number (sun=0, mon=1, … sat=6)
  day_to_dow() {
      case "$1" in
          sun) echo 0 ;;
          mon) echo 1 ;;
          tue) echo 2 ;;
          wed) echo 3 ;;
          thu) echo 4 ;;
          fri) echo 5 ;;
          sat) echo 6 ;;
          *)   echo "ERROR: unknown FINANCE_WEEKLY_DAY='$1' (use sun..sat)" >&2; exit 1 ;;
      esac
  }

  AUTH_HEADER="Authorization: Bearer ${API_AUTH_TOKEN}"
  CURL_CMD="curl -fsS -m 280"

  # Build the crontab
  CRONTAB="${DIGEST_MINUTE} ${DIGEST_HOUR} * * * ${CURL_CMD} -X POST \"${API_BASE}/digests/run\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1
  ${FINANCE_SYNC_MINUTE} ${FINANCE_SYNC_HOUR} * * * ${CURL_CMD} -X POST \"${API_BASE}/finance/sync\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1"

  if [ "${FINANCE_WEEKLY_ENABLED}" = "true" ]; then
      DOW="$(day_to_dow "${FINANCE_WEEKLY_DAY}")"
      CRONTAB="${CRONTAB}
  ${DIGEST_MINUTE} ${DIGEST_HOUR} * * ${DOW} ${CURL_CMD} -X POST \"${API_BASE}/digests/run-weekly\" -H \"${AUTH_HEADER}\" >/proc/1/fd/1 2>&1"
  fi

  printf '%s\n' "${CRONTAB}" > /etc/crontabs/root

  echo "=== rendered crontab ==="
  cat /etc/crontabs/root
  echo "========================"

  exec crond -f -l 8 -L /dev/stdout
  ```

- [ ] **Step 4: Build the image and verify size**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  docker build -t pragya-cron infra/cron
  docker image inspect pragya-cron --format '{{.Size}}' | awk '{printf "%.1f MB\n", $1/1024/1024}'
  ```

  Expected: image is roughly 10–15 MB.

- [ ] **Step 5: Dry-run the entrypoint to verify rendered crontab**

  ```bash
  docker run --rm \
    -e API_BASE=http://backend:8000 \
    -e API_AUTH_TOKEN=xxx \
    -e DIGEST_HOUR=8 \
    -e DIGEST_MINUTE=0 \
    -e FINANCE_SYNC_HOUR=6 \
    -e FINANCE_SYNC_MINUTE=30 \
    -e FINANCE_WEEKLY_ENABLED=true \
    -e FINANCE_WEEKLY_DAY=mon \
    --entrypoint sh \
    pragya-cron \
    -c '. /entrypoint.sh' 2>&1 | head -20
  ```

  Expected output (between the `===` markers):
  ```
  0 8 * * * curl -fsS -m 280 -X POST "http://backend:8000/digests/run" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  30 6 * * * curl -fsS -m 280 -X POST "http://backend:8000/finance/sync" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  0 8 * * 1 curl -fsS -m 280 -X POST "http://backend:8000/digests/run-weekly" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  ```

  Note: `FINANCE_WEEKLY_ENABLED=false` should omit the third line. Verify:

  ```bash
  docker run --rm \
    -e API_BASE=http://backend:8000 \
    -e API_AUTH_TOKEN=xxx \
    -e DIGEST_HOUR=8 \
    -e DIGEST_MINUTE=0 \
    -e FINANCE_SYNC_HOUR=6 \
    -e FINANCE_SYNC_MINUTE=30 \
    -e FINANCE_WEEKLY_ENABLED=false \
    -e FINANCE_WEEKLY_DAY=mon \
    --entrypoint sh \
    pragya-cron \
    -c '. /entrypoint.sh' 2>&1 | head -10
  ```

  Expected: only 2 crontab lines (no `run-weekly`).

- [ ] **Step 6: Commit**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  git add infra/cron/Dockerfile infra/cron/entrypoint.sh
  git commit -m "feat(infra): add cron sidecar image (Alpine + busybox crond)"
  ```

---

### Task 4: Add `cron` service to docker-compose.yml

**Files:**
- Modify: `infra/docker-compose.yml`

**Interfaces:**
- Consumes: `infra/cron/` image built in Task 3; backend internal port 8000; `../.env` env file.
- Produces: `cron` Compose service that starts after the backend is healthy.

- [ ] **Step 1: Add the `cron` service**

  In `infra/docker-compose.yml`, insert the `cron` service block after the `telegram_poller` service and before `frontend`. The full services section (replace existing content after `  telegram_poller:` block ends and before `  frontend:`):

  ```yaml
    cron:
      build:
        context: ./cron
      restart: unless-stopped
      env_file:
        - ../.env
      environment:
        API_BASE: "http://backend:8000"
        TZ: "${DIGEST_TIMEZONE:-UTC}"
        DIGEST_HOUR: "${DIGEST_HOUR:-8}"
        DIGEST_MINUTE: "${DIGEST_MINUTE:-0}"
        FINANCE_SYNC_HOUR: "${FINANCE_SYNC_HOUR:-6}"
        FINANCE_SYNC_MINUTE: "${FINANCE_SYNC_MINUTE:-30}"
        FINANCE_WEEKLY_ENABLED: "${FINANCE_WEEKLY_ENABLED:-true}"
        FINANCE_WEEKLY_DAY: "${FINANCE_WEEKLY_DAY:-mon}"
      depends_on:
        backend:
          condition: service_healthy
  ```

  Place this block between the closing of `telegram_poller:` and `  frontend:`.

- [ ] **Step 2: Validate the compose file parses**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  docker compose -f infra/docker-compose.yml config --quiet
  ```

  Expected: no error output (exit 0).

- [ ] **Step 3: Commit**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  git add infra/docker-compose.yml
  git commit -m "feat(infra): add cron service to docker-compose (hits backend API endpoints)"
  ```

---

### Task 5: Make target + .env.example note

**Files:**
- Modify: `Makefile`
- Modify: `.env.example`

**Interfaces:**
- Produces: `make cron-logs` target; `.env.example` updated comment.

- [ ] **Step 1: Add `cron-logs` to the Makefile**

  In the `Makefile`, find the `logs-poller` target and add `cron-logs` after it. Also add `cron-logs` to the `.PHONY` list.

  Current `.PHONY` line (line 22–28):
  ```makefile
  .PHONY: help setup doctor require-env install backend-install web-install \
          up down restart reset build logs logs-poller ps \
          db-up db-shell migrate revision \
          test backend-test web-test \
          lint backend-lint web-lint typecheck fmt fmt-check \
          check backend-check web-check docs-check smoke engine-smoke backup restore clean \
          finance-sync
  ```

  Add `cron-logs` to the second line, after `logs-poller`:
  ```makefile
  .PHONY: help setup doctor require-env install backend-install web-install \
          up down restart reset build logs logs-poller cron-logs ps \
          db-up db-shell migrate revision \
          test backend-test web-test \
          lint backend-lint web-lint typecheck fmt fmt-check \
          check backend-check web-check docs-check smoke engine-smoke backup restore clean \
          finance-sync
  ```

  Then after the `logs-poller` target (currently at line 91-92):
  ```makefile
  logs-poller:  ## Follow the Telegram poller logs only
  	$(COMPOSE) logs -f telegram_poller
  ```

  Add:
  ```makefile

  cron-logs:  ## Follow the cron sidecar logs only
  	$(COMPOSE) logs -f cron
  ```

- [ ] **Step 2: Add note to `.env.example`**

  Find the Finance section in `.env.example` (lines 94-100) and update the `FINANCE_SYNC_HOUR/MINUTE` area — add a comment before/after `PLAID_CLIENT_ID`. The current section:

  ```
  # ---- Finance (Plaid; read-only, feature off until set) ----
  # Personal-use Trial keys from dashboard.plaid.com. Treat the secret like a password.
  PLAID_CLIENT_ID=
  PLAID_SECRET=
  PLAID_ENV=sandbox
  FINANCE_WEEKLY_ENABLED=true
  FINANCE_WEEKLY_DAY=mon
  ```

  Replace with:

  ```
  # ---- Finance (Plaid; read-only, feature off until set) ----
  # Personal-use Trial keys from dashboard.plaid.com. Treat the secret like a password.
  PLAID_CLIENT_ID=
  PLAID_SECRET=
  PLAID_ENV=sandbox
  # Scheduling: digest and finance jobs are run by the `cron` sidecar container,
  # which reads the DIGEST_HOUR/MINUTE, FINANCE_SYNC_HOUR/MINUTE, FINANCE_WEEKLY_*
  # vars below and calls POST /digests/run, POST /finance/sync, POST /digests/run-weekly.
  # The backend itself does NOT run any in-process scheduler.
  FINANCE_WEEKLY_ENABLED=true
  FINANCE_WEEKLY_DAY=mon
  ```

  Also add `FINANCE_SYNC_HOUR` and `FINANCE_SYNC_MINUTE` defaults to `.env.example` since they are used by the cron sidecar but currently missing from the example. Add them in the Digest section (after `DIGEST_MINUTE=0`):

  In the `# ---- Digest` section, after `DIGEST_MINUTE=0`, add:
  ```
  # Finance sync schedule (sidecar also reads these)
  FINANCE_SYNC_HOUR=6
  FINANCE_SYNC_MINUTE=30
  ```

- [ ] **Step 3: Verify Makefile help still renders cleanly**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  make help | grep -E "cron|logs"
  ```

  Expected: `cron-logs` and `logs-poller` both appear.

- [ ] **Step 4: Commit**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  git add Makefile .env.example
  git commit -m "chore: add cron-logs make target and document scheduling sidecar in .env.example"
  ```

---

### Task 6: Final verification + squash commit

**Files:** None (verification only, then a single commit squash if desired).

- [ ] **Step 1: Full backend test suite**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test \
    uv run pytest -q 2>&1 | tail -20
  ```

  Expected: all tests pass. (Sandbox Plaid tests skip — that's normal.)

- [ ] **Step 2: Full lint + typecheck**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant/backend
  uv run ruff check . && uv run ruff format --check . && uv run mypy src
  ```

  Expected: zero errors.

- [ ] **Step 3: Rebuild cron image + crontab dry-run**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  docker build -t pragya-cron infra/cron --quiet

  docker run --rm \
    -e API_BASE=http://backend:8000 \
    -e API_AUTH_TOKEN=xxx \
    -e DIGEST_HOUR=8 \
    -e DIGEST_MINUTE=0 \
    -e FINANCE_SYNC_HOUR=6 \
    -e FINANCE_SYNC_MINUTE=30 \
    -e FINANCE_WEEKLY_ENABLED=true \
    -e FINANCE_WEEKLY_DAY=mon \
    --entrypoint sh \
    pragya-cron \
    -c '. /entrypoint.sh' 2>&1
  ```

  Expected rendered crontab (3 lines):
  ```
  0 8 * * * curl -fsS -m 280 -X POST "http://backend:8000/digests/run" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  30 6 * * * curl -fsS -m 280 -X POST "http://backend:8000/finance/sync" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  0 8 * * 1 curl -fsS -m 280 -X POST "http://backend:8000/digests/run-weekly" -H "Authorization: Bearer xxx" >/proc/1/fd/1 2>&1
  ```

- [ ] **Step 4: Compose config validates**

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  docker compose -f infra/docker-compose.yml config --quiet && echo "compose OK"
  ```

- [ ] **Step 5: Write report**

  ```bash
  mkdir -p /Users/nagarjuna/projects/naga_personal_assistant/.superpowers/sdd
  ```

  Write findings to `/Users/nagarjuna/projects/naga_personal_assistant/.superpowers/sdd/cron-sidecar-report.md` with:
  - Status (done/blocked)
  - Commit SHA + subject line
  - Backend test result summary
  - Rendered crontab (3 lines)
  - Cron image size in MB
  - Concerns / notes

- [ ] **Step 6: Final squash commit (optional — only if user wants clean history)**

  The individual commits from Tasks 1–5 are already clean. If a single commit is preferred:

  ```bash
  cd /Users/nagarjuna/projects/naga_personal_assistant
  # Count how many commits were added (should be 5):
  git log --oneline -6
  # If squashing: git rebase -i HEAD~5
  # Otherwise skip — the per-task commits are fine.
  ```

  The spec asks for: `feat(infra): cron sidecar replaces in-process APScheduler (curls digest/sync endpoints)` — use this as the squash message if requested, otherwise leave the per-task commits.

---

## Self-Review Checklist

**Spec coverage:**
- [x] Part 1 — `POST /digests/run-weekly` with TDD (Task 1)
- [x] Part 2 — Remove in-process scheduler from `app.py`, delete `scheduler.py` + `test_scheduler.py`, fix `__init__.py` (Task 2)
- [x] Part 3 — `infra/cron/Dockerfile` + `entrypoint.sh` with all required env vars and DOW mapping (Task 3)
- [x] Part 4 — `cron` Compose service with `env_file`, `environment`, `depends_on: backend: healthy` (Task 4)
- [x] Part 5 — `make cron-logs` target + `.env.example` note (Task 5)
- [x] Verify section — full pytest, ruff, mypy, docker build + dry-run, compose config (Task 6)

**Type consistency:**
- `digests.run(build_weekly_finance_prompt)` — `build_weekly_finance_prompt` is `Callable[[str], str]`, which matches `DigestService.run`'s optional prompt-fn parameter. Already verified in the existing scheduler code.
- `DigestOut` schema used in new endpoint matches the existing `_out()` helper exactly.

**Placeholders scan:** None found — all code blocks are complete and runnable.

**Edge case noted:** The `entrypoint.sh` uses `printf '%s\n'` rather than `echo` for the crontab write to avoid busybox echo flag differences. The `set -e` means an unknown `FINANCE_WEEKLY_DAY` will exit 1 cleanly before writing a bad crontab.
