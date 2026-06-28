"""Neutral LLM-completion plumbing shared across subsystems (opinions, dreams).

Lives in `agent/` so neither the opinion-maker nor the dreamer has to import the
other for a generic "call the model" / "parse its JSON" helper."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from pragya_assistant.agent.engine import AgentEngine

# A one-shot completion: prompt -> raw model text (often JSON).
CompletionFn = Callable[[str], Awaitable[str]]


def engine_completion_fn(engine: AgentEngine) -> CompletionFn:
    """Back a completion with the configured agent engine (one-shot, no history)."""

    async def _call(prompt: str) -> str:
        reply, _ = await engine.respond([], prompt)
        return reply

    return _call


def ollama_completion_fn(base_url: str, model: str, *, timeout: float = 120.0) -> CompletionFn:
    """Back a completion with a local Ollama model (no tools, JSON expected).

    Uses /api/generate — the prompt is self-contained (callers embed system
    instructions in the prompt string; the connector-specific SYSTEM in the legacy
    browser-activity dreamer is prepended by DreamerService before calling this)."""

    async def _call(prompt: str) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return str(resp.json().get("response", ""))

    return _call


def extract_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from model text — strip ```fences, salvage the first {...}."""
    if not text:
        return {}
    s = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(s)
    except json.JSONDecodeError:
        start, end = s.find("{"), s.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(s[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}
