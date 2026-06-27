"""Safety: Gmail is strictly read-only and stores nothing locally."""

from __future__ import annotations

from pathlib import Path

from pragya_assistant.connectors.base import ConnectorDeps
from pragya_assistant.connectors.gmail.spec import GMAIL_READONLY_SCOPE, GMAIL_SPEC
from pragya_assistant.connectors.registry import build_default_registry
from pragya_assistant.connectors.spec import Capability

_PKG = Path(__file__).resolve().parents[3] / "src" / "pragya_assistant" / "connectors" / "gmail"


def test_only_gmail_readonly_scope() -> None:
    assert GMAIL_SPEC.auth.oauth is not None
    assert GMAIL_SPEC.auth.oauth.scopes == (GMAIL_READONLY_SCOPE,)
    assert GMAIL_READONLY_SCOPE.endswith("gmail.readonly")


def test_tools_only_no_ingest() -> None:
    # No local storage: tools-only, never declares ingest.
    assert GMAIL_SPEC.capabilities == frozenset({Capability.TOOLS})
    assert Capability.INGEST not in GMAIL_SPEC.capabilities


def test_no_send_modify_or_mutating_calls() -> None:
    sources = "\n".join(p.read_text() for p in _PKG.glob("*.py"))
    for forbidden in ("gmail.send", "gmail.modify", "gmail.compose", "/send", "/drafts", "/trash"):
        assert forbidden not in sources
    for verb in (".post(", ".put(", ".delete(", ".patch("):
        assert verb not in sources


def test_registered_in_default_registry() -> None:
    reg = build_default_registry(ConnectorDeps(session_factory=None, settings=None))  # type: ignore[arg-type]
    assert "gmail" in reg
    rc = reg.get("gmail")
    assert rc is not None
    assert rc.spec.name == "Gmail"
