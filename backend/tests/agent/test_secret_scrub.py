"""Tests for the deterministic output secret-scrubber (Sec-2).

Written before the implementation (TDD). These pin the redaction set, the
prose-safety guarantee, and idempotency that ``GuardedEngine`` will rely on so
secret-shaped text can never leave the system even if a prompt injection coaxes
the model into emitting it."""

from __future__ import annotations

from pragya_assistant.agent.secret_scrub import scrub_secrets


def test_redacts_keys_and_numbers() -> None:
    assert "AKIA" not in scrub_secrets("key AKIAIOSFODNN7EXAMPLE here")
    assert "sk-" not in scrub_secrets("token sk-abcdefghijklmnopqrstuvwx")
    assert "[REDACTED]" in scrub_secrets("password = hunter2supersecret")
    assert "4111111111111111" not in scrub_secrets("card 4111 1111 1111 1111")
    assert "BEGIN" not in scrub_secrets(
        "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"
    )


def test_leaves_prose_untouched() -> None:
    t = "You read 3 articles about Kyoto and prefer Apple Pay."
    assert scrub_secrets(t) == t


def test_prose_with_years_and_small_numbers_survives() -> None:
    # A 4-digit year, single-/double-digit counts, and a room number must all
    # survive: none is card-length (>=13 digits) nor a long bare run (>=9).
    t = "In 2024 we shipped 3 features across 12 sprints; see room 401."
    assert scrub_secrets(t) == t


def test_idempotent() -> None:
    sample = (
        "creds: password = hunter2supersecret, key AKIAIOSFODNN7EXAMPLE, "
        "token sk-abcdefghijklmnopqrstuvwx, card 4111 1111 1111 1111, "
        "acct 123456789012, and a PEM:\n"
        "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBg\n-----END PRIVATE KEY-----"
    )
    once = scrub_secrets(sample)
    assert scrub_secrets(once) == once
    for leaked in ("AKIA", "sk-", "hunter2supersecret", "BEGIN", "123456789012"):
        assert leaked not in once


def test_redacts_long_account_number() -> None:
    assert scrub_secrets("account 1234567890") == "account [REDACTED]"


def test_generic_assignment_keeps_key_redacts_value() -> None:
    assert scrub_secrets("api_key: abcd1234efgh5678") == "api_key: [REDACTED]"
    assert scrub_secrets("Bearer: tok_live_abcdefghij") == "Bearer: [REDACTED]"


def test_redacts_dash_grouped_card() -> None:
    assert "4111111111111111" not in scrub_secrets("4111-1111-1111-1111")
