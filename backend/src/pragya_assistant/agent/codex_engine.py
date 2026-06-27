"""Codex engine — drives OpenAI Codex via ``codex exec --json`` (subprocess).

No Python SDK exists for Codex, so we shell out to the CLI and parse its JSONL
event stream. Auth is handled by the CLI itself (ChatGPT subscription via
``codex login``, or ``OPENAI_API_KEY``). The subprocess runner is injectable so
tests need no real ``codex`` binary.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from pragya_assistant.llm.types import Effort, Message

log = structlog.get_logger(__name__)

# (cmd, stdin_bytes) -> (stdout, stderr, returncode)
CodexRunner = Callable[[list[str], bytes], Awaitable[tuple[bytes, bytes, int]]]

_ROLE_LABELS = {"user": "User", "assistant": "Assistant"}
_MCP_SERVER = "pragya"


async def _default_runner(cmd: list[str], stdin: bytes) -> tuple[bytes, bytes, int]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(stdin)
    return stdout, stderr, proc.returncode if proc.returncode is not None else -1


class CodexEngine:
    """``AgentEngine`` backed by the Codex CLI.

    Phase-1 cut: the conversation is rendered into the prompt each turn
    (stateless); Codex-side session resume and exposing our memory tools over
    MCP are follow-ups.
    """

    def __init__(
        self,
        *,
        model: str | None,
        system_prompt: str,
        runner: CodexRunner | None = None,
        sandbox: str = "read-only",
        cwd: str = ".",
        mcp_command: list[str] | None = None,
        mcp_env: dict[str, str] | None = None,
        bypass_sandbox: bool = False,
    ) -> None:
        self._model = model
        self._system_prompt = system_prompt
        self._runner = runner or _default_runner
        self._sandbox = sandbox
        self._cwd = cwd
        self._mcp_command = mcp_command
        self._mcp_env = mcp_env
        self._bypass_sandbox = bypass_sandbox

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-C", self._cwd]
        if self._bypass_sandbox:
            # The container/host is the isolation boundary; needed so the memory
            # MCP server (spawned by codex) can reach Postgres, and for headless
            # MCP tool calls. Single-user only — Codex gets only our memory tools.
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            cmd += ["-s", self._sandbox]
        cmd += self._mcp_config_flags()
        if self._model:
            cmd += ["-m", self._model]
        if effort:
            cmd += ["-c", f"model_reasoning_effort={_toml(effort)}"]
        cmd.append("-")  # prompt via stdin

        stdout, stderr, code = await self._runner(
            cmd, self._render_prompt(history, user_text).encode()
        )
        reply, usage = _parse_events(stdout)
        if reply is None:
            detail = stderr.decode(errors="replace")[:500]
            raise RuntimeError(f"Codex produced no agent message (exit {code}): {detail}")

        log.info("engine_usage", engine="codex", usage=usage)
        return reply, [
            Message(role="user", content=user_text),
            Message(role="assistant", content=reply),
        ]

    def _render_prompt(self, history: list[Message], user_text: str) -> str:
        lines = [self._system_prompt, ""]
        lines += [f"{_ROLE_LABELS.get(m.role, m.role)}: {m.content}" for m in history]
        lines.append(f"User: {user_text}")
        return "\n".join(lines)

    def _mcp_config_flags(self) -> list[str]:
        """Define the pragya memory MCP server inline via codex `-c` overrides."""
        if not self._mcp_command:
            return []
        command, *args = self._mcp_command
        flags = ["-c", f"mcp_servers.{_MCP_SERVER}.command={_toml(command)}"]
        if args:
            joined = ",".join(_toml(a) for a in args)
            flags += ["-c", f"mcp_servers.{_MCP_SERVER}.args=[{joined}]"]
        if self._mcp_env:
            kvs = ", ".join(f"{key} = {_toml(val)}" for key, val in self._mcp_env.items())
            flags += ["-c", f"mcp_servers.{_MCP_SERVER}.env={{{kvs}}}"]
        return flags


def _toml(value: str) -> str:
    """Encode a string as a TOML basic string for a codex `-c` value."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parse_events(stdout: bytes) -> tuple[str | None, dict[str, Any] | None]:
    reply: str | None = None
    usage: dict[str, Any] | None = None
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue  # non-JSON log lines can appear on stdout
        kind = event.get("type")
        if kind == "item.completed":
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                reply = item.get("text", reply)
        elif kind == "turn.completed":
            turn_usage = event.get("usage")
            if isinstance(turn_usage, dict):
                usage = turn_usage
    return reply, usage
