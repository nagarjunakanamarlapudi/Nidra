from typing import Any

import structlog

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import Tool, ToolRegistry
from pragya_assistant.llm.types import ChatResult, Message, ToolCall
from tests.fakes import ScriptedChatProvider


def _spy_registry(recorder: list[dict[str, Any]]) -> ToolRegistry:
    async def handler(args: dict[str, Any]) -> str:
        recorder.append(args)
        return "stored"

    return ToolRegistry(
        [
            Tool(
                name="remember_note",
                description="d",
                input_schema={"type": "object"},
                handler=handler,
            )
        ]
    )


async def test_runs_tool_then_returns_final_text() -> None:
    recorder: list[dict[str, Any]] = []
    provider = ScriptedChatProvider(
        [
            ChatResult(
                text="",
                tool_calls=(ToolCall(id="c1", name="remember_note", arguments={"text": "x"}),),
                finish_reason="tool_calls",
                usage={},
            ),
            ChatResult(text="Saved it.", tool_calls=(), finish_reason="stop", usage={}),
        ]
    )
    agent = LoopEngine(provider=provider, registry=_spy_registry(recorder), system_prompt="SYS")

    reply, new_messages = await agent.respond(history=[], user_text="remember x")

    assert reply == "Saved it."
    assert recorder == [{"text": "x"}]  # tool was actually executed
    assert [m.role for m in new_messages] == ["user", "assistant", "tool", "assistant"]
    # the tool result message references the call id
    assert new_messages[2].tool_call_id == "c1"
    # system prompt goes to the provider but is not part of the stored turn
    first_sent = provider.calls[0]["messages"]
    assert first_sent[0].role == "system" and first_sent[0].content == "SYS"


async def test_passes_tool_specs_to_provider() -> None:
    provider = ScriptedChatProvider(
        [ChatResult(text="hi", tool_calls=(), finish_reason="stop", usage={})]
    )
    agent = LoopEngine(provider=provider, registry=_spy_registry([]), system_prompt="SYS")

    await agent.respond(history=[], user_text="hello")

    assert [s.name for s in provider.calls[0]["tools"]] == ["remember_note"]


async def test_includes_history() -> None:
    provider = ScriptedChatProvider(
        [ChatResult(text="ok", tool_calls=(), finish_reason="stop", usage={})]
    )
    agent = LoopEngine(provider=provider, registry=ToolRegistry([]), system_prompt="SYS")
    history = [
        Message(role="user", content="earlier"),
        Message(role="assistant", content="reply"),
    ]

    await agent.respond(history=history, user_text="now")

    sent = provider.calls[0]["messages"]
    assert [m.role for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[-1].content == "now"


async def test_stops_at_max_steps() -> None:
    always_tool = ChatResult(
        text="thinking",
        tool_calls=(ToolCall(id="c", name="remember_note", arguments={"text": "x"}),),
        finish_reason="tool_calls",
        usage={},
    )
    provider = ScriptedChatProvider([always_tool, always_tool, always_tool])
    agent = LoopEngine(
        provider=provider, registry=_spy_registry([]), system_prompt="SYS", max_steps=2
    )

    reply, _ = await agent.respond(history=[], user_text="go")

    assert len(provider.calls) == 2  # did not loop forever
    assert reply == "thinking"


async def test_passes_effort_to_provider() -> None:
    provider = ScriptedChatProvider(
        [ChatResult(text="hi", tool_calls=(), finish_reason="stop", usage={})]
    )
    engine = LoopEngine(provider=provider, registry=_spy_registry([]), system_prompt="SYS")
    await engine.respond(history=[], user_text="hi", effort="high")
    assert provider.calls[0]["effort"] == "high"


async def test_logs_engine_reasoning() -> None:
    provider = ScriptedChatProvider(
        [
            ChatResult(
                text="answer",
                tool_calls=(),
                finish_reason="stop",
                usage={},
                reasoning="because the sky is blue",
            )
        ]
    )
    engine = LoopEngine(provider=provider, registry=_spy_registry([]), system_prompt="SYS")
    with structlog.testing.capture_logs() as logs:
        await engine.respond(history=[], user_text="why?")

    reasoning = [e for e in logs if e["event"] == "engine_reasoning"]
    assert reasoning and "sky is blue" in reasoning[0]["reasoning"]


async def test_logs_engine_usage() -> None:
    provider = ScriptedChatProvider(
        [
            ChatResult(
                text="hi",
                tool_calls=(),
                finish_reason="stop",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
        ]
    )
    engine = LoopEngine(provider=provider, registry=_spy_registry([]), system_prompt="SYS")
    with structlog.testing.capture_logs() as logs:
        await engine.respond(history=[], user_text="hello")

    usage = [e for e in logs if e["event"] == "engine_usage"]
    assert usage and usage[0]["engine"] == "loop"
    assert usage[0]["usage"] == {"input_tokens": 10, "output_tokens": 5}
