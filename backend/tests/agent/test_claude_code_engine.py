from types import SimpleNamespace
from typing import Any

import pytest
import structlog

from pragya_assistant.agent.claude_code_engine import ClaudeCodeEngine
from pragya_assistant.agent.tools import Tool
from pragya_assistant.llm.types import Message


def _tool() -> Tool:
    async def handler(args: dict[str, Any]) -> str:
        return "ok"

    return Tool(
        name="remember_note", description="d", input_schema={"type": "object"}, handler=handler
    )


def _assistant(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


async def test_returns_text_and_passes_options() -> None:
    captured: dict[str, Any] = {}

    async def fake_query(*, prompt: str, options: Any) -> Any:
        captured["prompt"] = prompt
        captured["options"] = options
        yield _assistant("Hi from Claude Code")

    engine = ClaudeCodeEngine(
        tools=[_tool()], system_prompt="SYS", model="claude-opus-4-8", query_fn=fake_query
    )
    reply, produced = await engine.respond([], "hello")

    assert reply == "Hi from Claude Code"
    assert [(m.role, m.content) for m in produced] == [
        ("user", "hello"),
        ("assistant", "Hi from Claude Code"),
    ]
    opts = captured["options"]
    assert opts.system_prompt == "SYS"
    assert opts.allowed_tools == ["mcp__pragya__remember_note"]
    assert "pragya" in opts.mcp_servers
    assert captured["prompt"] == "hello"


async def test_includes_history_in_prompt() -> None:
    captured: dict[str, Any] = {}

    async def fake_query(*, prompt: str, options: Any) -> Any:
        captured["prompt"] = prompt
        yield _assistant("ok")

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    await engine.respond(
        [Message(role="user", content="earlier"), Message(role="assistant", content="prev")], "now"
    )
    assert (
        "earlier" in captured["prompt"]
        and "prev" in captured["prompt"]
        and "now" in captured["prompt"]
    )


async def test_concatenates_assistant_texts() -> None:
    async def fake_query(*, prompt: str, options: Any) -> Any:
        yield _assistant("part1")
        yield _assistant("part2")

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    reply, _ = await engine.respond([], "x")
    assert reply == "part1\npart2"


async def test_raises_when_no_text() -> None:
    async def fake_query(*, prompt: str, options: Any) -> Any:
        yield SimpleNamespace(content=[])

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    with pytest.raises(RuntimeError):
        await engine.respond([], "x")


async def test_logs_usage() -> None:
    async def fake_query(*, prompt: str, options: Any) -> Any:
        yield SimpleNamespace(content=[SimpleNamespace(text="hi")], usage={"input_tokens": 7})

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    with structlog.testing.capture_logs() as logs:
        await engine.respond([], "hi")
    usage = [e for e in logs if e["event"] == "engine_usage"]
    assert usage and usage[0]["engine"] == "claude-code"
    assert usage[0]["usage"] == {"input_tokens": 7}


async def test_passes_effort_to_options() -> None:
    captured: dict[str, Any] = {}

    async def fake_query(*, prompt: str, options: Any) -> Any:
        captured["options"] = options
        yield SimpleNamespace(content=[SimpleNamespace(text="ok")])

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    await engine.respond([], "hi", effort="high")
    assert captured["options"].effort == "high"


async def test_native_tools_added_to_allowed() -> None:
    captured: dict[str, Any] = {}

    async def fake_query(*, prompt: str, options: Any) -> Any:
        captured["options"] = options
        yield _assistant("ok")

    engine = ClaudeCodeEngine(
        tools=[_tool()],
        system_prompt="SYS",
        native_tools=("WebSearch", "WebFetch"),
        query_fn=fake_query,
    )
    await engine.respond([], "hi")
    allowed = captured["options"].allowed_tools
    assert "WebSearch" in allowed and "WebFetch" in allowed
    assert "mcp__pragya__remember_note" in allowed  # memory tools still present


async def test_no_native_tools_by_default() -> None:
    captured: dict[str, Any] = {}

    async def fake_query(*, prompt: str, options: Any) -> Any:
        captured["options"] = options
        yield _assistant("ok")

    engine = ClaudeCodeEngine(tools=[_tool()], system_prompt="SYS", query_fn=fake_query)
    await engine.respond([], "hi")
    assert "WebSearch" not in captured["options"].allowed_tools
