"""The dreamer — Nidra's LLM "Sleep" pass over ingested browser activity.

Where the store just records events, the dreamer asks an LLM to CONNECT signals
across them into higher-level intent + a persona + next-needs (e.g. flight search
+ car-rental search + hotel reading = "planning a trip"). Default engine:
on-device Gemma 4 via Ollama. The completion callable is injected so tests stay
deterministic — no network.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
    from pragya_assistant.memory.models import BrowserActivityEvent

# A completion callable: (user digest) -> raw model text (expected to be JSON).
DreamFn = Callable[[str], Awaitable[str]]

SYSTEM = (
    'You are Nidra\'s "dreamer". While the user sleeps you consolidate their recent online '
    "activity. Your job is to CONNECT THE DOTS ACROSS signals into higher-level understanding "
    "— NOT to repeat the activity back. Look hard for latent intent that spans MULTIPLE signals "
    "(e.g. a flight search + a car-rental search + reading about hotels = planning a trip; "
    "repeated reading on one topic + a related search = an active project). Infer interests, "
    "reading taste, active projects, and the user's likely next needs. Be specific and confident "
    "when several signals corroborate; hedge when the evidence is thin. Never invent activity that "
    "isn't in the digest. Respond with ONLY a JSON object of this exact shape: "
    '{"connectedInsights": [{"insight": "one clear sentence", "fromSignals": ["signal"], '
    '"confidence": 0.0, "reasoning": "why these connect"}], "persona": "2-3 sentence portrait of '
    'who this person is right now", "beliefs": [{"statement": "a durable belief", "confidence": '
    '0.0}], "nextNeeds": ["a proactive thing Nidra could do next"]}'
)


def build_digest(events: list[BrowserActivityEvent]) -> str:
    """The compact, already-redacted text the dreamer reads."""

    def of(event_type: str) -> list[BrowserActivityEvent]:
        return [e for e in events if e.event_type == event_type]

    lines: list[str] = []

    searches = [
        str((e.data or {}).get("query")) for e in of("search") if (e.data or {}).get("query")
    ]
    if searches:
        lines.append("SEARCHES:\n" + "\n".join(f"- {q}" for q in searches))

    reading: list[str] = []
    for e in of("reading"):
        d = e.data or {}
        tags = ", ".join(str(t) for t in (d.get("tags") or [])[:5])
        title = d.get("title") or e.title or e.domain or "(page)"
        author = f" by {d['author']}" if d.get("author") else ""
        suffix = f" ({tags})" if tags else ""
        reading.append(f'- "{title}"{author}{suffix} [{e.source}]')
    if reading:
        lines.append("READING:\n" + "\n".join(reading))

    emails = [
        f"- {(e.data or {}).get('action', 'mail')}: {(e.data or {}).get('subject', '(no subject)')}"
        for e in of("email")
    ]
    if emails:
        lines.append("EMAIL:\n" + "\n".join(emails))

    calendar = [
        f"- {(e.data or {}).get('action', 'view')}: {(e.data or {}).get('eventTitle', '(event)')}"
        for e in of("calendar")
    ]
    if calendar:
        lines.append("CALENDAR:\n" + "\n".join(calendar))

    domains: dict[str, int] = {}
    for e in events:
        if e.domain:
            domains[e.domain] = domains.get(e.domain, 0) + 1
    top = sorted(domains, key=lambda d: domains[d], reverse=True)[:8]
    if top:
        lines.append("TOP SITES: " + ", ".join(top))

    return "\n\n".join(lines) or "(no activity captured)"


def extract_json(text: str) -> dict[str, Any]:
    """Robustly pull a JSON object out of a model response."""
    if not text:
        return {}
    stripped = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class DreamResult:
    generated_from: int
    persona: str | None
    connected_insights: list[dict[str, Any]]
    beliefs: list[dict[str, Any]]
    next_needs: list[str]
    engine: str


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class DreamerService:
    """Reads recent activity, asks the LLM to connect the dots, returns a dream."""

    def __init__(
        self,
        store: BrowserActivityEventStore,
        complete: DreamFn,
        *,
        connector_key: str = "browser_activity",
        engine_label: str = "mock",
    ) -> None:
        self._store = store
        self._complete = complete
        self._key = connector_key
        self._engine_label = engine_label

    async def dream(self, *, limit: int = 200) -> DreamResult:
        events = await self._store.recent(self._key, limit=limit)
        parsed = extract_json(await self._complete(build_digest(events)))
        persona = parsed.get("persona")
        return DreamResult(
            generated_from=len(events),
            persona=persona if isinstance(persona, str) else None,
            connected_insights=_as_list(parsed.get("connectedInsights") or parsed.get("insights")),
            beliefs=_as_list(parsed.get("beliefs")),
            next_needs=[str(n) for n in _as_list(parsed.get("nextNeeds"))],
            engine=self._engine_label,
        )


def ollama_dream_fn(base_url: str, model: str, *, timeout: float = 120.0) -> DreamFn:
    """The default engine: on-device Gemma 4 via Ollama with forced JSON output."""

    async def _call(digest: str) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3},
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": digest},
                    ],
                },
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            message = data.get("message") or {}
            return str(message.get("content") or "")

    return _call
