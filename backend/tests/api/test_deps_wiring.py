"""Regression test: build_components must wire finance tools to the agent.

Finance tools now reach the agent through the **Plaid connector** (enabled at
startup via seed_from_env), not via a direct build_engine argument. The wiring
that must hold: build_components threads the FinanceService into ConnectorDeps so
the registered plaid connector's build_tools() exposes the finance tools. (The
original bug this guards: finance configured but its tools never reaching the
agent.)

This test exercises the real build_components() call path offline (no network /
DB at construction — providers and SQLAlchemy engines are lazy; we inspect the
registered connector rather than calling startup(), which would hit the DB).
"""

from __future__ import annotations

from pragya_assistant.api.deps import build_components
from pragya_assistant.config import Settings
from pragya_assistant.connectors.base import ConnectorContext
from pragya_assistant.memory.models import EMBEDDING_DIM


def _finance_settings() -> Settings:
    """Minimal Settings that produce a LoopEngine with finance tools — offline.

    Embedding provider: ollama (no API key required at construction).
    Embedding model: "test-model" (unknown, skips known-model dim check in
    Settings._check_embedding_dim), dim=1536 == EMBEDDING_DIM.
    Agent engine: anthropic-api (LoopEngine path; AnthropicChatProvider only
    contacts the network when .chat() is awaited).
    """
    return Settings(
        _env_file=None,
        app_secret_key="x" * 32,
        api_auth_token="y" * 32,
        database_url="postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test",
        # Loop-based engine so build_engine constructs a LoopEngine (toolable)
        agent_engine="anthropic-api",
        anthropic_api_key="sk-ant-dummy-key-for-offline-test",
        # Ollama embedding: no API key, constructs offline
        llm_embedding_provider="ollama",
        llm_embedding_model="test-model",  # unknown model → skips dim mismatch check
        llm_embedding_dim=EMBEDDING_DIM,  # must equal 1536 for build_components
        # Plaid: dummy values so build_finance_service returns a FinanceService
        plaid_client_id="dummy-client-id",
        plaid_secret="dummy-secret",
        plaid_env="sandbox",
    )


def test_build_components_wires_finance_into_plaid_connector() -> None:
    """Regression: finance tools must reach the agent via the Plaid connector.

    build_components must thread the FinanceService into ConnectorDeps so the
    registered plaid connector exposes the finance tools (which the manager then
    folds into the engine when the connector is enabled at startup).
    """
    settings = _finance_settings()
    components = build_components(settings)

    # --- 1. finance service itself must be present ---
    assert components.finance is not None, (
        "build_components returned finance=None even though plaid_client_id and "
        "plaid_secret were set"
    )

    # --- 2. the manager + plaid connector must be wired with that finance ---
    assert components.connectors is not None
    deps = components.connectors._deps  # type: ignore[attr-defined]
    assert deps.finance is components.finance, "finance not threaded into ConnectorDeps"

    rc = components.connectors._registry.get("plaid")  # type: ignore[attr-defined]
    assert rc is not None, "plaid connector not registered"
    conn = rc.build(deps)

    # --- 3. the built connector must expose the finance tools ---
    tool_names = {t.name for t in conn.build_tools(ConnectorContext(key="plaid", config={}))}
    finance_tools = {
        "account_balances",
        "net_worth",
        "spending_summary",
        "search_transactions",
        "holdings",
        "upcoming_bills",
    }
    missing = finance_tools - tool_names
    assert not missing, (
        f"Finance tools missing from the Plaid connector: {sorted(missing)}. "
        f"Connector tools: {sorted(tool_names)}."
    )
