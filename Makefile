# Pragya — project task runner. Run `make` (or `make help`) to list everything.
#
# Loads .env so docker/db/smoke targets use your configured ports & creds.
# (Not `export`ed — that would leak app config into `make test` and break
# tests that assert default settings. Recipes use make-level $(VAR) expansion.)
-include .env

COMPOSE     := docker compose -f infra/docker-compose.yml --env-file .env
APP_PORT    ?= 8000
WEB_PORT    ?= 3000
POSTGRES_USER ?= pragya
POSTGRES_DB ?= pragya
TEST_DATABASE_URL ?= postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test
LOCAL_DATABASE_URL ?= postgresql+asyncpg://pragya:pragya@localhost:5432/pragya
# Isolate Pragya's Claude Code sessions/transcripts from your personal ~/.claude.
# Override to use your system login: make engine-smoke CLAUDE_CONFIG_DIR=$(HOME)/.claude
CLAUDE_CONFIG_DIR ?= $(HOME)/.pragya-assistant
ENGINE ?= claude-code
MSG ?= Say hello in one short sentence and tell me which assistant engine you are.

.DEFAULT_GOAL := help
.PHONY: help setup doctor require-env install backend-install web-install \
        up down restart reset build logs logs-poller cron-logs ps \
        db-up db-shell migrate revision \
        test backend-test web-test \
        lint backend-lint web-lint typecheck fmt fmt-check \
        check backend-check web-check docs-check smoke engine-smoke backup restore clean \
        finance-sync google-oauth hooks security \
        extension-build install-extension run-extension extension-package

help:  ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---- setup ----
setup: ## First-time setup: create .env, install all deps, print next steps
	@test -f .env || { cp .env.example .env && echo "✓ created .env from .env.example"; }
	@$(MAKE) install
	@echo ""
	@echo "Next steps:"
	@echo "  1. Edit .env — set API_AUTH_TOKEN (web sign-in). For the default claude-code"
	@echo "     engine set CLAUDE_CODE_OAUTH_TOKEN (run: claude setup-token); for semantic"
	@echo "     notes set OPENAI_API_KEY + LLM_EMBEDDING_PROVIDER=openai."
	@echo "  2. make doctor    # verify your environment"
	@echo "  3. make up        # build + start db, backend, web app"
	@echo "  4. open http://localhost:$(WEB_PORT) and sign in with your API_AUTH_TOKEN"

google-oauth: require-env ## Guided platform Google OAuth setup → writes creds to .env
	cd backend && uv run python -m pragya_assistant.tools.google_oauth_setup --env-file ../.env

doctor: ## Check prerequisites + .env for a working setup
	@echo "Prerequisites:"
	@command -v docker >/dev/null 2>&1 && echo "  ✓ docker" || echo "  ✗ docker — install Docker Desktop"
	@docker info >/dev/null 2>&1 && echo "  ✓ docker daemon running" || echo "  ✗ docker not running — start Docker"
	@command -v uv >/dev/null 2>&1 && echo "  ✓ uv" || echo "  ✗ uv — https://docs.astral.sh/uv/"
	@command -v node >/dev/null 2>&1 && echo "  ✓ node $$(node -v 2>/dev/null)" || echo "  ✗ node — install Node 20+"
	@echo "Config (.env):"
	@test -f .env && echo "  ✓ .env present" || echo "  ✗ .env missing — run 'make setup'"
	@grep -Eq '^API_AUTH_TOKEN=.+' .env 2>/dev/null && echo "  ✓ API_AUTH_TOKEN set" || echo "  ✗ API_AUTH_TOKEN empty (web sign-in won't work)"
	@grep -Eq '^CLAUDE_CODE_OAUTH_TOKEN=.+' .env 2>/dev/null && echo "  ✓ CLAUDE_CODE_OAUTH_TOKEN set" || echo "  • CLAUDE_CODE_OAUTH_TOKEN empty (needed for claude-code; run: claude setup-token)"
	@grep -Eq '^OPENAI_API_KEY=.+' .env 2>/dev/null && echo "  ✓ OPENAI_API_KEY set" || echo "  • OPENAI_API_KEY empty (needed for semantic notes / openai engines)"
	@echo "Claude Code state dir (local): $(CLAUDE_CONFIG_DIR)"

require-env:
	@test -f .env || { echo "No .env found. Run 'make setup' first."; exit 1; }

install: backend-install web-install  ## Install backend + frontend dependencies

backend-install:  ## Install backend deps (uv sync)
	$(MAKE) -C backend install

web-install:  ## Install frontend deps (npm ci)
	$(MAKE) -C frontend install

# ---- docker stack ----
up: require-env  ## Build + start the full stack (db, backend, web); wait for healthy
	$(COMPOSE) up --build -d --wait --remove-orphans
	@echo "web → http://localhost:$(WEB_PORT)   api docs → http://localhost:$(APP_PORT)/docs"

down:  ## Stop and remove containers (keeps the data volume)
	$(COMPOSE) down

restart: down up  ## Restart the full stack

reset:  ## Stop containers AND delete the database volume (destroys data)
	$(COMPOSE) down -v

build: require-env  ## Build images without starting
	$(COMPOSE) build

logs:  ## Follow logs from all services
	$(COMPOSE) logs -f

logs-telegram:  ## Follow Telegram worker logs (now in-process in the backend)
	$(COMPOSE) logs -f backend

cron-logs:  ## Follow the cron sidecar logs only
	$(COMPOSE) logs -f cron

ps:  ## Show service status
	$(COMPOSE) ps

# ---- database ----
db-up: require-env  ## Start only Postgres (for local dev/tests); wait for healthy
	$(COMPOSE) up -d --wait db

db-shell:  ## Open a psql shell on the db service
	$(COMPOSE) exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

migrate:  ## Apply DB migrations in the running backend container
	$(COMPOSE) exec backend alembic upgrade head

revision:  ## Autogenerate a backend migration: make revision m="message"
	$(MAKE) -C backend revision m="$(m)"

# ---- tests ----
test: backend-test web-test  ## Run all tests (backend needs Postgres: run `make db-up`)

backend-test:  ## Backend tests (needs Postgres at TEST_DATABASE_URL)
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest

web-test:  ## Frontend tests
	$(MAKE) -C frontend test

# ---- quality ----
lint: backend-lint web-lint  ## Lint backend + frontend

backend-lint:  ## Lint backend (ruff)
	$(MAKE) -C backend lint

web-lint:  ## Lint frontend (eslint)
	$(MAKE) -C frontend lint

typecheck:  ## Type-check backend (mypy)
	$(MAKE) -C backend typecheck

fmt:  ## Format backend (ruff)
	$(MAKE) -C backend fmt

fmt-check:  ## Check backend formatting
	$(MAKE) -C backend fmt-check

check: backend-check web-check  ## Run ALL gates (lint + type + tests) for both

backend-check:  ## Backend gates (needs Postgres)
	cd backend && TEST_DATABASE_URL=$(TEST_DATABASE_URL) $(MAKE) check

web-check:  ## Frontend gates (lint + test + build)
	$(MAKE) -C frontend check

docs-check:  ## Validate all Mermaid diagrams in docs/ (chromium-free)
	@cd tools/mermaid-check && { [ -d node_modules ] || npm install --silent --no-audit --no-fund; } \
		&& node check.mjs ../../docs

# ---- misc ----
smoke:  ## Curl /health and /ready against a running stack
	@curl -fsS http://localhost:$(APP_PORT)/health && echo "  ← /health" || { echo "API not reachable — run 'make up'"; exit 1; }
	@curl -fsS http://localhost:$(APP_PORT)/ready && echo "  ← /ready"

finance-sync:  ## Trigger a Plaid sync now
	@curl -fsS -X POST http://localhost:$(APP_PORT)/finance/sync -H "Authorization: Bearer $(API_AUTH_TOKEN)" && echo

engine-smoke: db-up  ## Live-test an engine: make engine-smoke ENGINE=claude-code MSG="hi"
	@DATABASE_URL="$(LOCAL_DATABASE_URL)" AGENT_ENGINE="$(ENGINE)" \
		CLAUDE_CONFIG_DIR="$(CLAUDE_CONFIG_DIR)" CLAUDE_CODE_OAUTH_TOKEN="$(CLAUDE_CODE_OAUTH_TOKEN)" \
		uv run --project backend python backend/scripts/engine_smoke.py "$(MSG)"

backup: db-up  ## Back up the database → backups/pragya-<timestamp>.sql.gz
	@mkdir -p backups
	@$(COMPOSE) exec -T db pg_dump -U $(POSTGRES_USER) -d $(POSTGRES_DB) --clean --if-exists \
		| gzip > backups/pragya-$$(date +%Y%m%d-%H%M%S).sql.gz
	@ls -1t backups/*.sql.gz | head -1 | sed 's/^/backed up → /'

restore: db-up  ## Restore the database: make restore FILE=backups/pragya-....sql.gz
	@test -n "$(FILE)" || { echo "usage: make restore FILE=backups/pragya-....sql.gz"; exit 1; }
	@gunzip -c "$(FILE)" | $(COMPOSE) exec -T db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) \
		-v ON_ERROR_STOP=1 >/dev/null
	@echo "restored from $(FILE)"

clean:  ## Remove caches and build artifacts
	rm -rf backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache backend/.coverage frontend/.next
	@echo "cleaned caches"

# ---- browser extension (Nidra) ----
EXT_DIR := $(abspath nidra/extension)

extension-build:  ## Build the Nidra extension (installs deps, bakes root .env → extension/dist/)
	cd nidra && { [ -d node_modules ] || npm install; } && npm run build

install-extension: extension-build  ## Build Nidra, then open Chrome's extensions page to load it unpacked
	@echo "Nidra extension built. Load it unpacked from:"
	@echo "  $(EXT_DIR)"
	@open -R "$(EXT_DIR)" 2>/dev/null || true
	@open -a "Google Chrome" "chrome://extensions/" 2>/dev/null || true
	@echo "→ chrome://extensions: turn on Developer mode → 'Load unpacked' → pick the folder above."
	@echo "  Already loaded? Just click the ⟳ reload icon on the Nidra card to pick up this rebuild."

run-extension: extension-build  ## Launch a throwaway Chrome with Nidra preloaded (separate dev profile, zero clicks)
	@open -na "Google Chrome" --args \
		--user-data-dir="/tmp/nidra-chrome-dev" \
		--load-extension="$(EXT_DIR)" \
		--no-first-run --no-default-browser-check \
		&& echo "Launched Chrome (dev profile at /tmp/nidra-chrome-dev) with Nidra loaded." \
		|| echo "Couldn't auto-launch; use 'make install-extension' and load it manually."

extension-package:  ## Build the store artifact: NIDRA_BACKEND_URL=https://… make extension-package
	cd nidra && { [ -d node_modules ] || npm install; } && NIDRA_ENV=prod npm run build
	@echo "→ Chrome: upload the zip above at https://chrome.google.com/webstore/devconsole"
	@echo "  Safari/iOS: cd nidra && npm run ios, then archive + submit in Xcode."

# ---- security ----
hooks:  ## Install pre-commit hooks (run once after clone)
	pre-commit install
	pre-commit install --hook-type pre-push

security:  ## Run all local security checks (gitleaks, pip-audit, npm-audit, bandit)
	gitleaks detect --no-banner --config .gitleaks.toml --source .
	cd backend && uvx pip-audit
	cd frontend && npm audit --audit-level=high || true
	pip install --quiet bandit && bandit -r backend/src -ll
