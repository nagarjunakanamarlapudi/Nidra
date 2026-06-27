# Pragya — Personal Assistant

A single-user, fully self-owned personal assistant. You chat with it over **Telegram** and a **custom web app**; it keeps a durable, hybrid memory of your world (people, birthdays, notes, tasks, finances, preferences) and proactively delivers scheduled digests. It runs on your own hardware and is built to lift to the cloud without a rewrite.

> Full design & scope: [`docs/superpowers/specs/2026-06-20-personal-assistant-design.md`](docs/superpowers/specs/2026-06-20-personal-assistant-design.md)
> Architecture deep-dive (block, sequence & ER diagrams): [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Architecture

```
   Telegram bot  ┐                              ┌─ LLM provider layer (anthropic │ openai │ ollama)
   Web app (Next)┤── HTTP API (FastAPI) ── Agent ┤─ Memory service (exact query + semantic search)
                 ┘                          core  └─ Tool registry: memory (+ integrations, later)
                                  Scheduler (cron) ── digest engine ── delivery   (Phase 2+)
                                              │
                                  Postgres + pgvector  (one database)
```

- **`backend/`** — Python: agent core, LLM provider layer, memory, tools, API, Telegram bot, scheduler.
- **`frontend/`** — React/Next web app.
- **`infra/`** — Docker Compose, deployment.
- **`docs/`** — specs and plans.

## Roadmap

| Phase | Delivers |
|---|---|
| **1 — Walking skeleton** | Agent + LLM provider layer + hybrid memory + Telegram + web shell + single-user login. |
| 2 — Daily driver | Scheduler + digests · Calendar · Web search · tasks/reminders. |
| 3 — Email | Gmail/IMAP read · triage · summarize · draft. |
| 4 — Finance | Read-only statement/AA parsing → accounts/transactions → finance digest. |
| 5+ | WhatsApp/Slack, doc import, voice, opt-in autonomy, cloud migration. |

## Quickstart

```bash
make setup     # create .env from the example + install backend & frontend deps
make doctor    # check prereqs (docker, uv, node) + that .env is filled in
# edit .env: set API_AUTH_TOKEN (web sign-in). For the default claude-code engine
#   set CLAUDE_CODE_OAUTH_TOKEN (run: claude setup-token); set OPENAI_API_KEY for notes.
make up        # build + start db, backend, web app (migrations run automatically)
```

> **Claude Code state is isolated:** Pragya keeps Claude Code's sessions/transcripts in `~/.pragya-assistant` (locally) / `/home/pragya/.pragya-assistant` (Docker) — separate from your personal `~/.claude` — via `CLAUDE_CONFIG_DIR`, wired in the Makefile + compose. Auth is the `CLAUDE_CODE_OAUTH_TOKEN` (config-dir-independent), so no extra login.

`make help` lists every task — `setup` · `doctor` · `up` · `down` · `logs` · `ps` · `test` · `lint` · `check` · `db-up` · `db-shell` · `migrate` · `backup` · `restore` · `smoke` · `engine-smoke` · `clean`. This builds and starts **db + backend + web app** (all with `restart: unless-stopped`, so they survive reboots); the backend entrypoint applies migrations (`alembic upgrade head`) automatically, then serves the API.

**Backups:** `make backup` writes `backups/pragya-<timestamp>.sql.gz`; `make restore FILE=backups/pragya-….sql.gz` restores it. **Production:** set `APP_ENV=production` (the app then refuses to boot with placeholder secrets) and use strong `API_AUTH_TOKEN`, `APP_SECRET_KEY`, and `POSTGRES_PASSWORD`.

- Web app: `http://localhost:${WEB_PORT:-3000}` (enter your `API_AUTH_TOKEN` to sign in)
- API: `http://localhost:${APP_PORT:-8000}` · OpenAPI docs: `…/docs`
- `APP_PORT` / `WEB_PORT` let you avoid host-port clashes. `NEXT_PUBLIC_API_BASE` must match the API's host URL (it's baked into the web bundle at build time).

For chat to work, set a real LLM provider key in `.env` (e.g. `ANTHROPIC_API_KEY` with `LLM_CHAT_PROVIDER=anthropic`), or run a local Ollama.

See [`backend/README.md`](backend/README.md) and [`frontend/README.md`](frontend/README.md) for running each part on its own.

## Engines (the brain)

The brain is pluggable via one `AGENT_ENGINE` setting, spanning three plug categories:

| Category | `AGENT_ENGINE` | Auth |
|---|---|---|
| Coding-agent subscriptions | `claude-code` (default), `codex` | `claude login` / `codex login` |
| Model API keys | `anthropic-api`, `openai-api` | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` |
| Local LLM | `ollama` | none (run Ollama) |

`claude-code` and `codex` run on your subscriptions and call Pragya's memory tools over MCP; the others run Pragya's own loop over a raw model. Embeddings are a separate setting (`LLM_EMBEDDING_PROVIDER`).

**Test any engine live** (auto-starts Postgres; the coding-agent engines use their CLI's login):

```bash
make engine-smoke ENGINE=claude-code MSG="remember my sister's birthday is 2026-07-04, then list upcoming birthdays"
make engine-smoke ENGINE=codex
make engine-smoke ENGINE=ollama          # needs a local Ollama
```

> **Subscription auth in Docker:** the macOS Keychain isn't reachable in a container, so for `make up` with `claude-code` you provide a long-lived token. On your host run `claude setup-token`, paste it into `.env` as `CLAUDE_CODE_OAUTH_TOKEN=…` (keep `ANTHROPIC_API_KEY` empty so it wins), then `make up`. Locally (`make engine-smoke`) it uses your Keychain login directly. Codex-in-Docker additionally needs the `codex` binary in the image (follow-up); Codex works locally today.

## Security & pre-commit

```bash
make hooks    # install pre-commit hooks after cloning (run once)
```

Every commit runs: **gitleaks** (secret detection), **detect-private-key**, large-file guard, YAML/TOML/JSON syntax, trailing-whitespace/EOF fixers, and **ruff** lint + format on `backend/`.

CI enforces on every PR and push to `main`:
- `lint` — ruff (including bandit `S` rules) + mypy strict
- `backend-tests` — pytest against a real Postgres (`pgvector/pgvector:pg16`)
- `frontend` — eslint + jest + next build
- `security` — gitleaks full-history scan (blocking), pip-audit, bandit SAST, npm audit

See [SECURITY.md](SECURITY.md) for the vulnerability-disclosure policy.

## Engineering principles

Modular and extensible · fully tested · DevOps-minded (containerized, env-driven, CI) · portable · secure (secrets encrypted, write-with-confirm).
