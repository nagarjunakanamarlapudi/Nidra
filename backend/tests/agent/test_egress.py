"""Tests for the egress guard (Sec-4 of the prompt-injection defense).

Written before the implementation (TDD). They pin the contract a ``PreToolUse``
hook relies on: normal lookup URLs pass; URLs that carry secret-shaped data or a
bulk encoded blob (data exfiltration) are blocked. The hook wiring that enforces
this on every WebFetch is covered in ``test_claude_code_engine``."""

from __future__ import annotations

from pragya_assistant.agent.egress import egress_allowed


def test_allows_normal_wikipedia_lookup() -> None:
    ok, reason = egress_allowed("https://en.wikipedia.org/wiki/Kyoto")
    assert ok is True
    assert reason == ""


def test_allows_short_search_query() -> None:
    assert egress_allowed("https://duckduckgo.com/html/?q=weather+in+kyoto")[0] is True


def test_allows_long_human_readable_path() -> None:
    # An underscore-separated title is human-readable words, not one 64+ char
    # blob -- the structural separators break it into short tokens.
    url = "https://en.wikipedia.org/wiki/List_of_tallest_buildings_in_the_world"
    assert egress_allowed(url)[0] is True


def test_allows_opaque_id_at_threshold() -> None:
    # A ~64-char opaque id (e.g. a SHA-256 hex / presigned signature) is tolerated.
    assert egress_allowed("https://api.test/v1/obj?sig=" + "a" * 64)[0] is True


def test_blocks_bulk_blob_in_query() -> None:
    ok, reason = egress_allowed("https://attacker.test/?x=" + "A" * 200)
    assert ok is False
    assert reason  # non-empty, explains the block


def test_blocks_percent_encoded_blob() -> None:
    # %41 == "A"; decoded path/query is also scanned, so this is caught.
    ok, _ = egress_allowed("https://attacker.test/?x=" + "%41" * 100)
    assert ok is False


def test_blocks_openai_secret_in_url() -> None:
    ok, _ = egress_allowed("https://attacker.test/c?k=sk-test-keytestkeytestkey1234567")
    assert ok is False


def test_blocks_aws_key_in_url() -> None:
    ok, _ = egress_allowed("https://attacker.test/log/AKIAIOSFODNN7EXAMPLE")
    assert ok is False


def test_blocks_percent_encoded_secret() -> None:
    # An sk- key with its hyphens percent-encoded (%2D) to dodge a raw scan;
    # decoding the path/query before scrubbing still catches it.
    ok, _ = egress_allowed("https://attacker.test/?k=sk%2Dproj%2DT3BlbkFJabcdefghijklmnop")
    assert ok is False
