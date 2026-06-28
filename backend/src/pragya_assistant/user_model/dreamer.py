"""The dreamer — generates speculative Dreams on top of grounded Opinions.

In-context recursive self-improvement: the resolved-dream track record (what
paid off / flopped) is fed into the prompt, so each cycle is conditioned on real
outcomes. The dreamer writes ONLY to the dreams store — never user_model_snapshots
(the one-way valve). The completion callable is injected so tests stay
deterministic.
"""

from __future__ import annotations

from typing import Any

from pragya_assistant.agent.completion import CompletionFn, extract_json
from pragya_assistant.agent.untrusted import wrap_untrusted
from pragya_assistant.memory.models import Dream
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.store import UserModelStore

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


def build_dream_prompt(opinions: list[Any], record: list[Dream]) -> str:
    # SYSTEM is our trusted instruction and stays at the top level. The opinions
    # and track record are DERIVED from ingested data (a poisoned email subject
    # could ride into an opinion value, a crafted page title into a past dream
    # hypothesis), so the whole data body is fenced with wrap_untrusted: the model
    # reasons over it as DATA, never obeying instructions smuggled inside it.
    body = ["OPINIONS (grounded beliefs about the user):"]
    op_lines = [f"- {s.trait} = {s.value} (conf {s.confidence})" for s in opinions]
    body += op_lines or ["- (none yet)"]
    if record:
        body += ["", "TRACK RECORD (past dreams + how they turned out — learn from these):"]
        for d in record:
            signal = (d.outcome or {}).get("signal", "")
            body.append(f"- [{d.status}/{signal}] {d.hypothesis}")
    fenced = wrap_untrusted("user model", "\n".join(body))
    return f"{SYSTEM}\n\n{fenced}"


def _to_new_dream(raw: Any) -> NewDream | None:
    if not isinstance(raw, dict):
        return None
    # Tolerate the connectedInsights/insight shape gemma sometimes returns.
    hypothesis = str(raw.get("hypothesis") or raw.get("insight") or "").strip()
    if not hypothesis:
        return None
    kind_raw = raw.get("kind")
    kind = kind_raw if isinstance(kind_raw, str) and kind_raw in _KINDS else "foresight"
    try:
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    prov_raw = raw.get("provenance") or raw.get("fromSignals")
    prov = [str(p) for p in prov_raw if p] if isinstance(prov_raw, list) else []
    return NewDream(hypothesis=hypothesis, kind=kind, confidence=confidence, provenance=prov)


class DreamerService:
    def __init__(
        self,
        opinions: UserModelStore,
        dreams: DreamStore,
        complete: CompletionFn,
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
        parsed = extract_json(raw)
        items = (
            parsed.get("dreams")
            or parsed.get("connectedInsights")
            or parsed.get("insights")
            or []
        )
        proposed = [nd for r in items if (nd := _to_new_dream(r))]
        await self._dreams.add(proposed)
        return await self._dreams.active()
