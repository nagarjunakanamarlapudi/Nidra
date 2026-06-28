"""Tests for ``GuardedEngine`` — the engine-agnostic output scrubber (Sec-3).

Written before the implementation (TDD). These pin that the wrapper redacts
secrets from BOTH the reply text and each persisted message's ``content``, that
it works with ANY inner engine implementing the ``AgentEngine`` protocol (it
wraps by protocol, not inheritance), and that ordinary prose passes through
untouched. Scrubbing message content matters because a stored turn would
otherwise carry a secret into history and into the next prompt.
"""

from __future__ import annotations

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.guard import GuardedEngine, guard
from pragya_assistant.llm.types import Effort, Message

# Fake secrets the scrubber must redact (same shapes the Sec-2 tests pin).
_OPENAI_KEY = "sk-test-keytestkeytestkey1234567"
_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


class _FakeEngine:
    """A minimal inner engine: records its call and returns scripted output."""

    def __init__(self, text: str, messages: list[Message]) -> None:
        self._text = text
        self._messages = messages
        self.seen: dict[str, object] = {}

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        self.seen = {"history": history, "user_text": user_text, "effort": effort}
        return self._text, self._messages


async def test_scrubs_both_reply_text_and_message_content() -> None:
    inner = _FakeEngine(
        f"here is your key {_OPENAI_KEY} ok",
        [
            Message(role="user", content="show me the aws creds"),
            Message(role="assistant", content=f"the key is {_AWS_KEY} there"),
        ],
    )

    text, messages = await GuardedEngine(inner).respond([], "hi")

    assert "sk-proj-T3" not in text
    assert "[REDACTED]" in text
    assert "AKIAIOSF" not in messages[1].content
    assert "[REDACTED]" in messages[1].content
    # Roles (and message count/order) are preserved — only content is scrubbed.
    assert [m.role for m in messages] == ["user", "assistant"]


async def test_engine_agnostic_any_protocol_impl_is_guarded() -> None:
    # A structurally different inner with no shared base still gets scrubbed,
    # proving the wrapper guards by protocol, not by inheritance.
    class _OtherEngine:
        async def respond(
            self,
            history: list[Message],
            user_text: str,
            *,
            effort: Effort | None = None,
        ) -> tuple[str, list[Message]]:
            return _AWS_KEY, [Message(role="assistant", content=_OPENAI_KEY)]

    inner: AgentEngine = _OtherEngine()
    wrapped = guard(inner)

    assert isinstance(wrapped, AgentEngine)
    text, messages = await wrapped.respond([], "x")
    assert "AKIAIOSF" not in text
    assert "sk-proj-T3" not in messages[0].content


async def test_normal_text_passes_through_unchanged() -> None:
    inner = _FakeEngine(
        "You read 3 articles about Kyoto today.",
        [Message(role="assistant", content="Sounds good, see you in room 401.")],
    )

    text, messages = await GuardedEngine(inner).respond([], "hi")

    assert text == "You read 3 articles about Kyoto today."
    assert messages[0].content == "Sounds good, see you in room 401."


async def test_forwards_history_user_text_and_effort_to_inner() -> None:
    inner = _FakeEngine("ok", [])
    history = [Message(role="user", content="prior")]

    await GuardedEngine(inner).respond(history, "now", effort="high")

    assert inner.seen == {"history": history, "user_text": "now", "effort": "high"}
