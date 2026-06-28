"""Neutral LLM-completion plumbing shared across subsystems (opinions, dreams).

Lives in `agent/` so neither the opinion-maker nor the dreamer has to import the
other for a generic "call the model" / "parse its JSON" helper."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from pragya_assistant.agent.engine import AgentEngine
from pragya_assistant.agent.hardening import HARDENING_PREAMBLE
from pragya_assistant.agent.secret_scrub import scrub_secrets

# A one-shot completion: prompt -> raw model text (often JSON).
CompletionFn = Callable[[str], Awaitable[str]]


def engine_completion_fn(engine: AgentEngine) -> CompletionFn:
    """Back a completion with the configured agent engine (one-shot, no history)."""

    async def _call(prompt: str) -> str:
        reply, _ = await engine.respond([], prompt)
        return reply

    return _call


def ollama_completion_fn(base_url: str, model: str, *, timeout: float = 120.0) -> CompletionFn:
    """Back a completion with a local Ollama model — forced JSON, low temperature.

    Faithful to the original on-device call: ``/api/chat`` with ``format="json"``
    and ``temperature=0.3`` (so output is parseable + stable). Neutral on the system
    prompt — the caller embeds its own instructions in ``prompt`` (no subsystem-
    specific SYSTEM is baked in here).

    Unlike the engine paths, this raw HTTP call does not flow through ``harden`` or
    ``guard``, so it does both itself — keeping the spec's "hardening is on every
    path" and "output scrubbing is always-on" true even when ``AGENT_ENGINE=ollama``
    (the dreamer's ``/dreams/run`` and the opinion ``review_fn``):

    * the :data:`HARDENING_PREAMBLE` is prepended to the prompt, so the on-device
      model is primed to treat ingested content as data and refuse to leak secrets;
    * the response is run through :func:`scrub_secrets`, so a secret the model is
      coaxed into emitting is redacted before it leaves the system.

    Scrubbing is safe with forced JSON: ``[REDACTED]`` only ever replaces a secret-
    shaped substring *inside* a JSON string value, so the result stays parseable."""

    async def _call(prompt: str) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3},
                    "messages": [
                        {"role": "user", "content": f"{HARDENING_PREAMBLE}\n\n{prompt}"}
                    ],
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return scrub_secrets(str((data.get("message") or {}).get("content") or ""))

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
