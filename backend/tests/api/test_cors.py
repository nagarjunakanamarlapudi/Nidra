import httpx
from httpx import ASGITransport

from pragya_assistant.config import Settings
from tests.conftest import AppBuilder
from tests.fakes import ScriptedChatProvider


def _settings(**overrides: object) -> Settings:
    base = {
        "app_secret_key": "s",
        "api_auth_token": "t",
        "database_url": "postgresql+asyncpg://pragya:pragya@localhost/pragya",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def test_cors_origins_parse_from_csv() -> None:
    settings = _settings(cors_allow_origins="http://a.com, http://b.com")
    assert settings.cors_allow_origins == ["http://a.com", "http://b.com"]


def test_cors_origins_default_includes_localhost() -> None:
    assert "http://localhost:3000" in _settings().cors_allow_origins


async def test_cors_header_present_for_allowed_origin(build_test_app: AppBuilder) -> None:
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
