"""Provider-agnostic value types for the LLM layer.

These types are the contract every provider maps to and from, so the rest of
the system never imports a vendor SDK type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "tool_calls"]
# How hard the model should reason for a turn (maps to provider effort knobs).
Effort = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool advertised to the model (name, description, JSON-schema input)."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Message:
    """A single conversation turn.

    - ``role="tool"`` carries a tool result in ``content`` and references the
      originating call via ``tool_call_id``.
    - an assistant turn that calls tools carries them in ``tool_calls``.
    """

    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    """The normalized result of one provider ``chat`` call."""

    text: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: FinishReason
    usage: dict[str, int]
    reasoning: str = ""
