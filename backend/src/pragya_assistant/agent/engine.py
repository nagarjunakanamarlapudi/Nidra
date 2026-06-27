"""The engine ("brain") interface — pluggable across loop / coding-agent backends.

One level above ``ChatProvider``: a `ChatProvider` is raw model I/O, an
``AgentEngine`` is a whole agent that takes a turn. The loop engine runs our own
tool-calling loop over a provider; the coding-agent engines (Claude Code, Codex)
delegate the turn to those agents.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pragya_assistant.llm.types import Effort, Message


@runtime_checkable
class AgentEngine(Protocol):
    """Given prior history and the new user text, produce a reply plus the
    messages to persist (the visible user/assistant turn). ``effort`` is an
    optional per-turn reasoning-depth hint, honoured by engines that support it."""

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]: ...
