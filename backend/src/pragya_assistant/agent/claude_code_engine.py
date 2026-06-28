"""Claude Code engine — drives Claude Code via the Claude Agent SDK.

Runs on the user's Claude subscription (the Claude Code login in ``~/.claude``)
or ``ANTHROPIC_API_KEY``. Our memory tools are exposed in-process as SDK MCP
tools.

Tool access is confined by four layers, because ``allowed_tools`` alone only
*auto-approves* tools — it does NOT restrict which tools exist:

* ``tools=list(builtin_tools)`` — the ONLY built-ins made available (default
  none; chat passes ``WebSearch``/``WebFetch``). Built-in ``Read`` / ``Bash`` /
  ``Write`` are therefore never available, so prompt injection cannot read
  ``.env`` / ``~/.zshrc`` or run shell commands.
* ``disallowed_tools`` lists the dangerous filesystem/shell built-ins explicitly
  as defence in depth.
* ``permission_mode="dontAsk"`` denies anything not pre-approved (never
  ``bypassPermissions``, which would skip every check).
* ``can_use_tool`` is a deny-by-default backstop: it allows only our MCP tools
  and the enabled ``builtin_tools`` and denies everything else.

``setting_sources=[]`` keeps behaviour driven by our own system prompt, not the
host's Claude config. The query function is injectable so tests need no real
Claude Code or auth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
    create_sdk_mcp_server,
    query,
    tool,
)

from pragya_assistant.agent.tools import Tool
from pragya_assistant.llm.types import Effort, Message

log = structlog.get_logger(__name__)

QueryFn = Callable[..., AsyncIterator[Any]]

_MCP_SERVER = "pragya"
_ROLE_LABELS = {"user": "User", "assistant": "Assistant"}

# Built-in tools that must never be reachable by an injected prompt. Denied
# explicitly (defence in depth) on top of ``tools=`` not making them available.
_DANGEROUS_BUILTINS = (
    "Read",
    "Bash",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
)


class ClaudeCodeEngine:
    def __init__(
        self,
        *,
        tools: list[Tool],
        system_prompt: str,
        model: str | None = None,
        max_turns: int = 8,
        builtin_tools: tuple[str, ...] = (),
        query_fn: QueryFn | None = None,
    ) -> None:
        self._tools = tools
        self._system_prompt = system_prompt
        self._model = model
        self._max_turns = max_turns
        self._builtin_tools = builtin_tools
        self._query = query_fn or query
        self._mcp_server = create_sdk_mcp_server(
            name=_MCP_SERVER, tools=[_to_sdk_tool(t) for t in tools]
        )

    async def respond(
        self, history: list[Message], user_text: str, *, effort: Effort | None = None
    ) -> tuple[str, list[Message]]:
        texts: list[str] = []
        usage: Any = None
        async for message in self._query(
            prompt=self._render_prompt(history, user_text), options=self._options(effort)
        ):
            content = getattr(message, "content", None)
            if isinstance(content, list):
                for block in content:
                    text = getattr(block, "text", None)
                    if isinstance(text, str) and text:
                        texts.append(text)
            message_usage = getattr(message, "usage", None)
            if message_usage is not None:
                usage = message_usage

        reply = "\n".join(texts).strip()
        if not reply:
            raise RuntimeError("Claude Code produced no text response")
        log.info("engine_usage", engine="claude-code", usage=usage)
        return reply, [
            Message(role="user", content=user_text),
            Message(role="assistant", content=reply),
        ]

    def _options(self, effort: Effort | None = None) -> ClaudeAgentOptions:
        allowed = [f"mcp__{_MCP_SERVER}__{t.name}" for t in self._tools]
        allowed += list(self._builtin_tools)
        allowed_set = set(allowed)

        async def _can_use_tool(
            name: str, _input: dict[str, Any], _ctx: ToolPermissionContext
        ) -> PermissionResultAllow | PermissionResultDeny:
            # Deny-by-default backstop: only our MCP tools and the enabled
            # built-ins are ever allowed.
            if name in allowed_set:
                return PermissionResultAllow()
            return PermissionResultDeny(
                message=f"tool {name!r} is not permitted", interrupt=True
            )

        return ClaudeAgentOptions(
            system_prompt=self._system_prompt,
            mcp_servers={_MCP_SERVER: self._mcp_server},
            tools=list(self._builtin_tools),  # availability: ONLY these built-ins (default none)
            allowed_tools=allowed,
            disallowed_tools=list(_DANGEROUS_BUILTINS),
            permission_mode="dontAsk",  # deny anything not pre-approved (no blanket bypass)
            can_use_tool=_can_use_tool,  # deny-by-default backstop
            setting_sources=[],
            max_turns=self._max_turns,
            model=self._model,
            effort=effort,
        )

    def _render_prompt(self, history: list[Message], user_text: str) -> str:
        if not history:
            return user_text
        lines = [f"{_ROLE_LABELS.get(m.role, m.role)}: {m.content}" for m in history]
        lines.append(f"User: {user_text}")
        return "\n".join(lines)


def _to_sdk_tool(t: Tool) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        result = await t.handler(args)
        return {"content": [{"type": "text", "text": result}]}

    return tool(t.name, t.description, t.input_schema)(handler)
