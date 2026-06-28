"""Tests for the system-prompt hardening preamble (Sec-5, soft defense layer).

Written before the implementation (TDD). The preamble is hygiene: it states the
untrusted-data and no-exfiltration rules in the system prompt so the model is
primed to resist injected instructions. The hard guarantees live elsewhere
(confinement, output scrub, egress guard); these tests only pin that the key
clauses are present and that ``harden`` prepends idempotently."""

from __future__ import annotations

from pragya_assistant.agent.hardening import HARDENING_PREAMBLE, harden


def test_preamble_states_the_key_clauses() -> None:
    text = HARDENING_PREAMBLE.lower()
    assert "untrusted" in text  # external content is data...
    assert "instruction" in text  # ...never instructions
    assert "never reveal" in text  # no exfiltration of...
    assert "secret" in text  # ...secrets / credentials


def test_harden_prepends_preamble_keeping_the_rest() -> None:
    out = harden("BASE PROMPT")
    assert out.startswith(HARDENING_PREAMBLE)
    assert "BASE PROMPT" in out  # original content is preserved


def test_harden_is_idempotent() -> None:
    once = harden("BASE PROMPT")
    twice = harden(once)
    assert twice == once  # already-hardened prompt is never double-prepended
