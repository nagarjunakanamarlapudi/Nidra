import pytest
from pydantic import ValidationError


def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "secret")
    monkeypatch.setenv("API_AUTH_TOKEN", "token")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://pragya:pragya@localhost:5432/pragya")


def test_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111, 222")
    from pragya_assistant.config import Settings

    s = Settings(_env_file=None)

    assert s.api_auth_token == "token"
    assert s.database_url.startswith("postgresql+asyncpg://")
    assert s.telegram_allowed_chat_ids == [111, 222]
    # sane defaults
    assert s.agent_engine == "claude-code"
    assert s.llm_chat_model == "claude-opus-4-8"
    assert s.llm_embedding_provider == "openai"
    assert s.llm_embedding_dim == 1536


def test_empty_chat_ids_parses_to_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    from pragya_assistant.config import Settings

    s = Settings(_env_file=None)
    assert s.telegram_allowed_chat_ids == []


def test_missing_required_field_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("APP_SECRET_KEY", "API_AUTH_TOKEN", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    from pragya_assistant.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_invalid_engine_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    monkeypatch.setenv("AGENT_ENGINE", "not-an-engine")
    from pragya_assistant.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_agent_engine_accepts_all_categories(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    from pragya_assistant.config import Settings

    for engine in ("claude-code", "codex", "anthropic-api", "openai-api", "ollama"):
        monkeypatch.setenv("AGENT_ENGINE", engine)
        assert Settings(_env_file=None).agent_engine == engine


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _base_env(monkeypatch)
    from pragya_assistant.config import get_settings

    get_settings.cache_clear()
    assert get_settings() is get_settings()


def _full(**overrides: object) -> object:
    from pragya_assistant.config import Settings

    base: dict[str, object] = {
        "_env_file": None,
        "app_secret_key": "x" * 40,
        "api_auth_token": "y" * 40,
        "database_url": "postgresql+asyncpg://pragya:pragya@localhost/pragya",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_rejects_placeholder_secrets_in_non_local() -> None:
    with pytest.raises(ValidationError):
        _full(app_env="production", api_auth_token="dev-token")


def test_allows_placeholder_secrets_in_local() -> None:
    s = _full(app_env="local", api_auth_token="dev-token", app_secret_key="changeme")
    assert s.api_auth_token == "dev-token"  # type: ignore[attr-defined]


def test_allows_strong_secrets_in_non_local() -> None:
    s = _full(app_env="production")
    assert s.app_env == "production"  # type: ignore[attr-defined]


def test_rejects_known_embedding_model_dim_mismatch() -> None:
    with pytest.raises(ValidationError):
        _full(llm_embedding_model="nomic-embed-text", llm_embedding_dim=1536)


def test_allows_matching_embedding_model_dim() -> None:
    s = _full(llm_embedding_model="text-embedding-3-small", llm_embedding_dim=1536)
    assert s.llm_embedding_dim == 1536  # type: ignore[attr-defined]


def test_unknown_embedding_model_skips_dim_check() -> None:
    s = _full(llm_embedding_model="some-custom-model", llm_embedding_dim=999)
    assert s.llm_embedding_dim == 999  # type: ignore[attr-defined]


def test_plaid_defaults_off() -> None:
    from pragya_assistant.config import Settings

    s = Settings(
        app_secret_key="x" * 16,
        api_auth_token="x" * 16,
        database_url="postgresql+asyncpg://u:p@localhost/db",
    )
    assert s.plaid_client_id is None
    assert s.plaid_env == "sandbox"
    assert s.finance_sync_hour == 6


def test_finance_weekly_defaults() -> None:
    from pragya_assistant.config import Settings

    s = Settings(
        _env_file=None,
        app_secret_key="x" * 16,
        api_auth_token="x" * 16,
        database_url="postgresql+asyncpg://u:p@localhost/db",
    )
    assert s.finance_weekly_enabled is True
    assert s.finance_weekly_day == "mon"
