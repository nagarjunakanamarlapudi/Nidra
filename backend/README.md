# Pragya backend

Python 3.12 · FastAPI · SQLAlchemy 2 (async) + Postgres/pgvector · uv.

## Local development

```bash
cd backend
make install        # uv sync (installs Python 3.12 + deps)
make check          # lint + format-check + type-check + tests
```

Common targets (`make help`):

| Target | Action |
|---|---|
| `make test` | run pytest |
| `make lint` / `make fmt` | ruff check / format |
| `make typecheck` | mypy on `src` |
| `make run` | uvicorn dev server on :8000 |

### Tests that need a database

Memory/integration tests run against a real Postgres+pgvector. Point them at one via `TEST_DATABASE_URL` (defaults to the Compose database):

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya
make test
```

The easiest way to get that database is the Compose stack in [`../infra`](../infra).

## Layout

```
src/pragya_assistant/
  config.py        # typed env settings
  llm/             # provider-agnostic chat + embedding layer (anthropic/openai/ollama)
  memory/          # db, models, repositories, MemoryService (exact + semantic)
  agent/           # tool-calling loop + memory tools
  api/             # FastAPI app, auth, routes
  channels/        # telegram (+ future surfaces)
  scheduler/       # digests (Phase 2)
```
