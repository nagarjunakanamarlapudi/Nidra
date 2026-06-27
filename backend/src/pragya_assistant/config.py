"""Application configuration, sourced from environment variables / .env."""

from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ChatProviderName = Literal["anthropic", "openai", "ollama"]
EmbeddingProviderName = Literal["openai", "ollama"]
# The single "brain" selector across all plug categories:
#   coding-agent subscriptions: claude-code, codex
#   model API keys:             anthropic-api, openai-api
#   local LLM:                  ollama
AgentEngineName = Literal["claude-code", "codex", "anthropic-api", "openai-api", "ollama"]

# Secrets that must never be used outside local dev (the shipped placeholders).
_PLACEHOLDER_SECRETS = {
    "",
    "dev-token",
    "changeme",
    "change-me",
    "change-me-to-a-long-random-string",
}
# Output dimensions of well-known embedding models, to catch model/dim mismatches.
_KNOWN_EMBEDDING_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
}


class Settings(BaseSettings):
    """Typed application settings.

    All values come from the environment (or a local ``.env``). Required fields
    have no default and raise ``ValidationError`` if absent.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- App ---
    app_env: str = "local"
    log_level: str = "INFO"
    app_secret_key: str
    api_auth_token: str
    # Public base URL of the web app — the OAuth callback redirects the browser
    # back here (to the marketplace) when done.
    app_base_url: str = "http://localhost:3000"
    # Public base URL of the BACKEND API, where the OAuth callback ROUTE lives
    # (.../connectors/oauth/callback). This is what gets registered as the Google
    # redirect URI. Defaults to APP_BASE_URL (correct for single-origin prod behind
    # one domain); for split dev (web :3000, api :8088) set it to the API's URL.
    oauth_redirect_base_url: str | None = None

    # --- Database ---
    database_url: str

    # --- Agent engine (the brain) — one selector spanning all plug categories ---
    agent_engine: AgentEngineName = "claude-code"
    # Model for the loop-based brains (anthropic-api / openai-api / ollama).
    llm_chat_model: str = "claude-opus-4-8"
    # Optional model override for coding-agent engines (None -> the CLI's own default).
    codex_model: str | None = None
    claude_code_model: str | None = None

    # --- Browser Activity connector + the dreamer ---
    # The on-device Ollama model the dreamer uses to connect signals into intent.
    dream_model: str = "gemma4:latest"

    # --- LLM: embeddings ---
    llm_embedding_provider: EmbeddingProviderName = "openai"
    llm_embedding_model: str = "text-embedding-3-small"
    llm_embedding_dim: int = 1536

    # --- Provider credentials / endpoints ---
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # --- Telegram ---
    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: Annotated[list[int], NoDecode] = []

    # --- Digest (proactive daily summary) ---
    digest_enabled: bool = True
    digest_hour: int = 8
    digest_minute: int = 0
    digest_timezone: str = "UTC"

    # --- Connectors: server-side OAuth client (enables one-click "Connect with
    # Google" — register one OAuth client, set these once, and the UI drops the
    # client-id/secret fields). When unset, the connector falls back to per-
    # connector credentials entered in the marketplace UI. ---
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None

    # --- Calendar (read-only .ics feed; feature off when unset) ---
    calendar_ics_url: str | None = None

    # --- Web search ---
    # Lets the claude-code engine use Claude's built-in WebSearch/WebFetch tools.
    web_search_enabled: bool = True

    # --- Email (read-only Gmail/IMAP + drafts; feature off until configured) ---
    email_address: str | None = None
    email_app_password: str | None = None
    email_imap_host: str = "imap.gmail.com"

    # --- Finance (Plaid; read-only, feature off until configured) ---
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"  # sandbox | production
    finance_sync_hour: int = 6
    finance_sync_minute: int = 30
    finance_weekly_enabled: bool = True
    finance_weekly_day: str = "mon"  # APScheduler day_of_week

    # --- CORS (web app origins allowed to call the API) ---
    cors_allow_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("telegram_allowed_chat_ids", mode="before")
    @classmethod
    def _parse_chat_ids(cls, value: object) -> object:
        """Accept a comma-separated string of chat IDs (or a list)."""
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        return value

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """Accept a comma-separated string of origins (or a list)."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> Self:
        """Refuse to run with placeholder/weak secrets outside local dev."""
        if self.app_env != "local":
            for name in ("api_auth_token", "app_secret_key"):
                value = getattr(self, name)
                if value in _PLACEHOLDER_SECRETS or len(value) < 16:
                    raise ValueError(
                        f"{name} must be a strong, non-placeholder value when APP_ENV != 'local'"
                    )
        return self

    @model_validator(mode="after")
    def _check_embedding_dim(self) -> Self:
        """Catch a known embedding model paired with the wrong vector dimension."""
        expected = _KNOWN_EMBEDDING_DIMS.get(self.llm_embedding_model)
        if expected is not None and expected != self.llm_embedding_dim:
            raise ValueError(
                f"LLM_EMBEDDING_DIM={self.llm_embedding_dim} but model "
                f"'{self.llm_embedding_model}' produces {expected}-dim vectors"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
