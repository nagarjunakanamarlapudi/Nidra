"""The per-source collectors shape cited facts from every source except finance."""

from __future__ import annotations

from types import SimpleNamespace

from pragya_assistant.user_model.facts import (
    collect_browser_facts,
    collect_email_facts,
    collect_memory_facts,
)


def test_collect_browser_facts_shapes_searches_and_choices() -> None:
    rows = [
        SimpleNamespace(id=1, event_type="search", data={"query": "flights to tokyo"},
                        title=None, domain="google.com", metrics=None),
        SimpleNamespace(id=2, event_type="reading", data={}, title="Best ryokans in Kyoto",
                        domain="medium.com", metrics={"dwellMs": 840000, "readPct": 95}),
        SimpleNamespace(id=3, event_type="interaction",
                        data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
                        title=None, domain="sixt.com", metrics=None),
        SimpleNamespace(id=4, event_type="action", title=None, domain="shop.com",
                        metrics=None, data={"milestone": "reached_checkout", "funnel": "purchase"}),
    ]
    facts = collect_browser_facts(rows)
    kinds = {f.kind for f in facts}
    assert {"search", "reading", "choice"} <= kinds
    assert "action" in kinds
    search = next(f for f in facts if f.kind == "search")
    assert "flights to tokyo" in search.summary and search.event_ids == [1]
    assert search.source == "browser"


def test_collect_email_facts_cites_message_ids() -> None:
    msgs = [SimpleNamespace(from_="a@b.com", subject="Invoice #42", message_id="<m1@x>")]
    facts = collect_email_facts(msgs)
    assert facts[0].source == "email" and facts[0].refs == ["<m1@x>"]
    assert "Invoice #42" in facts[0].summary


def test_collect_memory_facts_prefs_and_tasks() -> None:
    facts = collect_memory_facts(
        {"diet": "vegetarian"}, [SimpleNamespace(id=3, title="Renew passport")]
    )
    kinds = {f.kind: f for f in facts}
    assert kinds["preference"].refs == ["pref:diet"]
    assert kinds["task"].refs == ["task:3"] and "passport" in kinds["task"].summary
