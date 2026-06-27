"""The dreamer — generates speculative Dreams on top of grounded Opinions.

In-context recursive self-improvement: the resolved-dream track record (what
paid off / flopped) is fed into the prompt, so each cycle is conditioned on real
outcomes. The dreamer writes ONLY to the dreams store — never user_model_snapshots
(the one-way valve). The completion callable is injected so tests stay
deterministic.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pragya_assistant.memory.models import Dream
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.store import UserModelStore

# A completion callable: (prompt) -> raw model text (expected JSON).
DreamFn = Callable[[str], Awaitable[str]]

_KINDS = {"foresight", "suggestion", "need"}

SYSTEM = (
    "You are Nidra's dreamer. On top of GROUNDED OPINIONS about the user, produce "
    "SPECULATIVE foresight — latent intent and likely near-future needs that go "
    "BEYOND the current facts. Do NOT restate opinions. Connect signals across "
    "sources. Each dream is a hypothesis that will be tested against what the user "
    "actually does, so be specific and falsifiable; hedge confidence when evidence "
    "is thin. LEARN from the TRACK RECORD: do more like the confirmed dreams, avoid "
    "the refuted ones, and don't repeat a dream whose premise is already resolved. "
    'Respond with ONLY JSON: {"dreams": [{"hypothesis": "one clear sentence", '
    '"kind": "foresight|suggestion|need", "confidence": 0.0, "provenance": ["source"]}]}'
)


def extract_json(text: str) -> dict[str, Any]:
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


def build_dream_prompt(opinions: list[Any], record: list[Dream]) -> str:
    lines = [SYSTEM, "", "OPINIONS (grounded beliefs about the user):"]
    op_lines = [f"- {s.trait} = {s.value} (conf {s.confidence})" for s in opinions]
    lines += op_lines or ["- (none yet)"]
    if record:
        lines += ["", "TRACK RECORD (past dreams + how they turned out — learn from these):"]
        for d in record:
            signal = (d.outcome or {}).get("signal", "")
            lines.append(f"- [{d.status}/{signal}] {d.hypothesis}")
    return "\n".join(lines)


def _to_new_dream(raw: dict[str, Any]) -> NewDream | None:
    hypothesis = str(raw.get("hypothesis") or "").strip()
    if not hypothesis:
        return None
    kind_raw = raw.get("kind")
    kind = kind_raw if isinstance(kind_raw, str) and kind_raw in _KINDS else "foresight"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    prov_raw = raw.get("provenance")
    prov = [str(p) for p in prov_raw if p] if isinstance(prov_raw, list) else []
    return NewDream(hypothesis=hypothesis, kind=kind, confidence=confidence, provenance=prov)


class DreamerService:
    def __init__(
        self,
        opinions: UserModelStore,
        dreams: DreamStore,
        complete: DreamFn,
        *,
        engine_label: str = "mock",
    ) -> None:
        self._opinions = opinions
        self._dreams = dreams
        self._complete = complete
        self._engine_label = engine_label

    async def dream(self, *, track_limit: int = 20) -> list[Dream]:
        model = await self._opinions.current_model()
        record = await self._dreams.track_record(limit=track_limit)
        raw = await self._complete(build_dream_prompt(model, record))
        proposed = [nd for r in extract_json(raw).get("dreams", []) if (nd := _to_new_dream(r))]
        await self._dreams.add(proposed)
        return await self._dreams.active()
