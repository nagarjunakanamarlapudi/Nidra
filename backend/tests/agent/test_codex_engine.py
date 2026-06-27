import json
from typing import Any

import pytest
import structlog

from pragya_assistant.agent.codex_engine import CodexEngine
from pragya_assistant.llm.types import Message


def _jsonl(*objs: dict[str, Any]) -> bytes:
    return ("\n".join(json.dumps(o) for o in objs)).encode()


async def test_runs_codex_and_returns_agent_message() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["cmd"] = cmd
        captured["stdin"] = stdin
        out = _jsonl(
            {"type": "thread.started", "thread_id": "t1"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Hello from Codex"},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 3}},
        )
        return out, b"", 0

    engine = CodexEngine(model="gpt-5.5", system_prompt="SYS", runner=runner)
    reply, produced = await engine.respond([], "hi")

    assert reply == "Hello from Codex"
    assert [(m.role, m.content) for m in produced] == [
        ("user", "hi"),
        ("assistant", "Hello from Codex"),
    ]
    assert captured["cmd"][:3] == ["codex", "exec", "--json"]
    assert "-m" in captured["cmd"] and "gpt-5.5" in captured["cmd"]
    assert b"SYS" in captured["stdin"] and b"hi" in captured["stdin"]


async def test_includes_history_in_prompt() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["stdin"] = stdin
        return (
            _jsonl({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            b"",
            0,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    await engine.respond(
        [Message(role="user", content="earlier"), Message(role="assistant", content="prev")], "now"
    )

    text = captured["stdin"].decode()
    assert "earlier" in text and "prev" in text and "now" in text


async def test_last_agent_message_wins() -> None:
    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        return (
            _jsonl(
                {"type": "item.completed", "item": {"type": "agent_message", "text": "first"}},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "final"}},
            ),
            b"",
            0,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    reply, _ = await engine.respond([], "x")
    assert reply == "final"


async def test_no_model_omits_flag() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["cmd"] = cmd
        return (
            _jsonl({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            b"",
            0,
        )

    engine = CodexEngine(model=None, system_prompt="SYS", runner=runner)
    await engine.respond([], "x")
    assert "-m" not in captured["cmd"]


async def test_raises_when_no_agent_message() -> None:
    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        return (
            _jsonl({"type": "item.completed", "item": {"type": "error", "text": "boom"}}),
            b"stderr",
            1,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    with pytest.raises(RuntimeError):
        await engine.respond([], "x")


async def test_mcp_and_bypass_flags() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["cmd"] = cmd
        return (
            _jsonl({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            b"",
            0,
        )

    engine = CodexEngine(
        model="m",
        system_prompt="SYS",
        runner=runner,
        mcp_command=["/py", "-m", "pragya_assistant.mcp_memory"],
        mcp_env={"DATABASE_URL": "postgresql://x"},
        bypass_sandbox=True,
    )
    await engine.respond([], "hi")
    cmd = captured["cmd"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "-s" not in cmd  # bypass replaces the sandbox flag
    joined = " ".join(cmd)
    assert "mcp_servers.pragya.command=" in joined
    assert "pragya_assistant.mcp_memory" in joined
    assert "mcp_servers.pragya.args=" in joined
    assert "mcp_servers.pragya.env=" in joined
    assert "DATABASE_URL" in joined


async def test_no_mcp_keeps_sandbox() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["cmd"] = cmd
        return (
            _jsonl({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            b"",
            0,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    await engine.respond([], "hi")
    assert "-s" in captured["cmd"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in captured["cmd"]
    assert "mcp_servers" not in " ".join(captured["cmd"])


async def test_logs_usage() -> None:
    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        return (
            _jsonl(
                {"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}},
                {"type": "turn.completed", "usage": {"input_tokens": 19442, "output_tokens": 17}},
            ),
            b"",
            0,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    with structlog.testing.capture_logs() as logs:
        await engine.respond([], "x")
    usage = [e for e in logs if e["event"] == "engine_usage"]
    assert usage and usage[0]["engine"] == "codex"
    assert usage[0]["usage"] == {"input_tokens": 19442, "output_tokens": 17}


async def test_effort_flag() -> None:
    captured: dict[str, Any] = {}

    async def runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
        captured["cmd"] = cmd
        return (
            _jsonl({"type": "item.completed", "item": {"type": "agent_message", "text": "ok"}}),
            b"",
            0,
        )

    engine = CodexEngine(model="m", system_prompt="SYS", runner=runner)
    await engine.respond([], "x", effort="low")
    joined = " ".join(captured["cmd"])
    assert "model_reasoning_effort=" in joined and "low" in joined
