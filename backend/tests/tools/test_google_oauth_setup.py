"""Pure helpers behind `make google-oauth` (the interactive driver isn't unit-tested)."""

from __future__ import annotations

from pragya_assistant.tools.google_oauth_setup import (
    GOOGLE_APIS,
    api_overview_url,
    env_value,
    project_number_from_client_id,
    redirect_base,
    redirect_uri,
    upsert_env,
)


def test_redirect_base_reads_app_port() -> None:
    assert redirect_base("APP_PORT=8088\nX=1\n") == "http://localhost:8088"


def test_redirect_base_defaults_to_8000() -> None:
    assert redirect_base("X=1\n") == "http://localhost:8000"


def test_redirect_uri_appends_callback_path() -> None:
    assert (
        redirect_uri("http://localhost:8088") == "http://localhost:8088/connectors/oauth/callback"
    )
    assert (
        redirect_uri("https://pragya.example/")
        == "https://pragya.example/connectors/oauth/callback"
    )


def test_env_value_reads_uncommented_only() -> None:
    assert env_value("A=1\nB=two\n", "B") == "two"
    assert env_value("#B=hidden\n", "B") is None
    assert env_value("A=1\n", "Z") is None


def test_upsert_replaces_existing_empty_key() -> None:
    out = upsert_env(
        "APP_ENV=local\nGOOGLE_OAUTH_CLIENT_ID=\nFOO=bar\n", "GOOGLE_OAUTH_CLIENT_ID", "abc"
    )
    assert "GOOGLE_OAUTH_CLIENT_ID=abc" in out
    assert "APP_ENV=local" in out
    assert "FOO=bar" in out
    assert out.count("GOOGLE_OAUTH_CLIENT_ID=") == 1


def test_upsert_appends_when_missing() -> None:
    out = upsert_env("APP_ENV=local\n", "OAUTH_REDIRECT_BASE_URL", "http://localhost:8088")
    assert out.endswith("OAUTH_REDIRECT_BASE_URL=http://localhost:8088\n")
    assert "APP_ENV=local" in out


def test_upsert_leaves_commented_key_and_adds_real_one() -> None:
    out = upsert_env("#GOOGLE_OAUTH_CLIENT_ID=old\n", "GOOGLE_OAUTH_CLIENT_ID", "new")
    assert "#GOOGLE_OAUTH_CLIENT_ID=old" in out
    assert "GOOGLE_OAUTH_CLIENT_ID=new" in out


def test_project_number_from_client_id() -> None:
    # A Google client id is "<project-number>-<rand>.apps.googleusercontent.com".
    cid = "646777782566-ak6v75ppkrlgge1mhusprhk3g6pnulcu.apps.googleusercontent.com"
    assert project_number_from_client_id(cid) == "646777782566"


def test_project_number_from_client_id_rejects_malformed() -> None:
    assert project_number_from_client_id("not-a-real-client-id") is None
    assert project_number_from_client_id("") is None


def test_api_overview_url_is_project_scoped() -> None:
    # The exact deep link Google itself returns in its "API not enabled" error,
    # so the user enables it in the SAME project the client belongs to.
    assert api_overview_url("gmail.googleapis.com", "646777782566") == (
        "https://console.developers.google.com/apis/api/gmail.googleapis.com"
        "/overview?project=646777782566"
    )
    # Both Google APIs Pragya needs are covered.
    assert set(GOOGLE_APIS) == {"calendar-json.googleapis.com", "gmail.googleapis.com"}
