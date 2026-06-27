"""Claude Code engine — drives Claude Code via the Claude Agent SDK.

Runs on the user's Claude subscription (the Claude Code login in ``~/.claude``)
or ``ANTHROPIC_API_KEY``. Our memory tools are exposed in-process as SDK MCP
tools, and ``allowed_tools`` restricts Claude Code to ONLY those (no bash / file
/ web built-ins). ``setting_sources=[]`` keeps behaviour driven by our own
system prompt, not the host's Claude config. The query function is injectable so
tests need no real Claude Code or auth.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

import structlog
from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query, tool

from pragya_assistant.agent.tools import Tool
from pragya_assistant.llm.types import Effort, Message

log = structlog.get_logger(__name__)

QueryFn = Callable[..., AsyncIterator[Any]]

_MCP_SERVER = "pragya"
_ROLE_LABELS = {"user": "User", "assistant": "Assistant"}


class ClaudeCodeEngine:
    def __init__(
        self,
        *,
        tools: list[Tool],
        system_prompt: str,
        model: str | None = None,
        max_turns: int = 8,
        native_tools: tuple[str, ...] = (),
        query_fn: QueryFn | None = None,
    ) -> None:
        self._tools = tools
        self._system_prompt = system_prompt
        self._model = model
        self._max_turns = max_turns
        self._native_tools = native_tools
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
        allowed += list(self._native_tools)
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt,
            mcp_servers={_MCP_SERVER: self._mcp_server},
            allowed_tools=allowed,
            permission_mode="bypassPermissions",
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
