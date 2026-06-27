"""Live smoke test: talk to the configured AGENT_ENGINE once, for real.

Usage (needs Postgres up — `make db-up` — and, for coding-agent engines, the
relevant CLI logged in):

    AGENT_ENGINE=claude-code DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya \
        uv run python scripts/engine_smoke.py "your message"

Or via make: `make engine-smoke ENGINE=claude-code MSG="hi"`.
"""

from __future__ import annotations

import asyncio
import sys

from pragya_assistant.agent.factory import build_engine
from pragya_assistant.config import get_settings
from pragya_assistant.llm.factory import build_embedding_provider
from pragya_assistant.memory.db import (
    create_all,
    create_engine,
    create_session_factory,
    ensure_vector_extension,
)
from pragya_assistant.memory.service import MemoryService

_DEFAULT_MESSAGE = "Say hello in one short sentence and tell me which assistant engine you are."


async def main() -> int:
    message = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_MESSAGE
    settings = get_settings()

    db = create_engine(settings.database_url)
    await ensure_vector_extension(db)
    await create_all(db)
    memory = MemoryService(
        session_factory=create_session_factory(db),
        embedder=build_embedding_provider(settings),
        embedding_model=settings.llm_embedding_model,
        embedding_dim=settings.llm_embedding_dim,
    )
    engine = build_engine(settings, memory)

    print(f"[engine={settings.agent_engine}]  you > {message}", flush=True)
    try:
        reply, _ = await engine.respond([], message)
        print(f"[engine={settings.agent_engine}] pragya < {reply}", flush=True)
        return 0
    except Exception as exc:  # surface the real failure for a smoke test
        print(f"FAILED: {type(exc).__name__}: {exc}", flush=True)
        return 1
    finally:
        await db.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
