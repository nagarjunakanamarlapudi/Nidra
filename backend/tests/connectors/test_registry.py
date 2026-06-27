"""The connector registry: the catalog of available connectors."""

from __future__ import annotations

from pragya_assistant.connectors.base import (
    ConnectorContext,
    ConnectorDeps,
    Health,
    RegisteredConnector,
)
from pragya_assistant.connectors.registry import ConnectorRegistry, build_default_registry
from pragya_assistant.connectors.spec import AuthStrategy, Capability, ConnectorSpec


class _Dummy:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)


def _rc(key: str, name: str) -> RegisteredConnector:
    spec = ConnectorSpec(
        key=key,
        name=name,
        category="Misc",
        pitch="x",
        icon="🔌",
        auth=AuthStrategy(kind="none"),
        capabilities=frozenset({Capability.TOOLS}),
    )
    return RegisteredConnector(spec=spec, build=lambda deps: _Dummy())


def test_register_and_get() -> None:
    reg = ConnectorRegistry()
    rc = _rc("a", "Alpha")
    reg.register(rc)
    assert reg.get("a") is rc
    assert "a" in reg


def test_get_unknown_returns_none() -> None:
    reg = ConnectorRegistry()
    assert reg.get("nope") is None
    assert "nope" not in reg


def test_all_specs_sorted_by_name() -> None:
    reg = ConnectorRegistry()
    reg.register(_rc("b", "Bravo"))
    reg.register(_rc("a", "Alpha"))
    assert [s.name for s in reg.all_specs()] == ["Alpha", "Bravo"]


def test_register_overwrites_same_key() -> None:
    reg = ConnectorRegistry()
    reg.register(_rc("a", "Alpha"))
    reg.register(_rc("a", "Alpha v2"))
    specs = reg.all_specs()
    assert len(specs) == 1
    assert specs[0].name == "Alpha v2"


def test_build_default_registry_returns_registry() -> None:
    deps = ConnectorDeps(session_factory=None, settings=None)  # type: ignore[arg-type]
    assert isinstance(build_default_registry(deps), ConnectorRegistry)
