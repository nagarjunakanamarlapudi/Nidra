"""Safety: Google Calendar is strictly read-only.

Mirrors the email connector's no-send guarantee — assert the connector requests
only the read-only scope and never issues a mutating request.
"""

from __future__ import annotations

from pathlib import Path

from pragya_assistant.connectors.base import ConnectorDeps
from pragya_assistant.connectors.google_calendar.spec import (
    CALENDAR_READONLY_SCOPE,
    GOOGLE_CALENDAR_SPEC,
)
from pragya_assistant.connectors.registry import build_default_registry

_PKG = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "pragya_assistant"
    / "connectors"
    / "google_calendar"
)


def test_only_readonly_scope() -> None:
    assert GOOGLE_CALENDAR_SPEC.auth.oauth is not None
    assert GOOGLE_CALENDAR_SPEC.auth.oauth.scopes == (CALENDAR_READONLY_SCOPE,)
    assert CALENDAR_READONLY_SCOPE.endswith("calendar.readonly")


def test_no_broad_scope_or_mutating_endpoint() -> None:
    sources = "\n".join(p.read_text() for p in _PKG.glob("*.py"))
    # No broad read-write Calendar scope (only the .readonly variant is allowed).
    assert 'auth/calendar"' not in sources
    assert "auth/calendar.events" not in sources
    # The client only ever GETs — no mutating verbs anywhere in the package.
    for verb in (".post(", ".put(", ".delete(", ".patch("):
        assert verb not in sources


def test_default_registry_registers_google_calendar() -> None:
    reg = build_default_registry(ConnectorDeps(session_factory=None, settings=None))  # type: ignore[arg-type]
    assert "google_calendar" in reg
    rc = reg.get("google_calendar")
    assert rc is not None
    assert rc.spec.name == "Google Calendar"
