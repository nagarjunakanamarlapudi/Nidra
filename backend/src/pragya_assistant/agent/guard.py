"""``GuardedEngine`` — the engine-agnostic output scrubber (Sec-3 of the defense).

This is the linchpin of the prompt-injection output defense: it wraps *any*
``AgentEngine`` and runs everything that engine returns -- the reply text and the
``content`` of each message it asks to persist -- through :func:`scrub_secrets`.
Sitting at the engine boundary, it is brain-agnostic (loop or coding-agent) and
guarantees secret-shaped text can never leave the system even if an injection
coaxes the model into emitting it.

Scrubbing the persisted messages (not just the reply) is essential: a stored
turn would otherwise carry a secret into history and ride into the next prompt.

``GuardedEngine`` satisfies the ``AgentEngine`` protocol exactly, so it is a
drop-in wrapper. Use :func:`guard` as the single, reusable wrap point (the
factory wraps every built engine through it).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.secret_scrub import scrub_secrets
from pragya_assistant.llm.types import Effort, Message


class GuardedEngine:
    """An ``AgentEngine`` decorator that scrubs secrets from every output.

    Delegates the turn to ``inner`` unchanged, then redacts the reply text and
    the ``content`` of each message it returns. All other message fields (role,
    tool calls, tool-call id) pass through untouched.
    """

    def __init__(self, inner: AgentEngine, *, scrub: Callable[[str], str] = scrub_secrets) -> None:
        self._inner = inner
        self._scrub = scrub

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        text, messages = await self._inner.respond(history, user_text, effort=effort)
        scrubbed = [replace(m, content=self._scrub(m.content)) for m in messages]
        return self._scrub(text), scrubbed


def guard(engine: AgentEngine, *, scrub: Callable[[str], str] = scrub_secrets) -> AgentEngine:
    """Wrap ``engine`` so all of its output is scrubbed.

    The one reusable wrap point shared by the factory (and later confined
    builders), so engines are guarded exactly once at a single boundary.
    """
    return GuardedEngine(engine, scrub=scrub)
