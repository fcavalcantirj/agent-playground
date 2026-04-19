"""Phase 22c-03 — unit tests for OAuth config + authlib registry.

Covers:
  * All 7 AP_OAUTH_* env vars land as Pydantic ``Settings`` fields.
  * ``get_oauth(settings)`` in dev (AP_ENV=dev) succeeds without creds
    and registers both ``google`` and ``github`` providers.
  * ``get_oauth(settings)`` in prod (AP_ENV=prod) fails loud (RuntimeError)
    when any of the 7 OAuth env vars is missing — mirrors the
    ``crypto/age_cipher.py::_master_key`` discipline.
  * Real env values override the dev placeholders.

No DB + no network + no FastAPI app construction — pure unit tests.
Runs in the default pytest invocation (no ``api_integration`` marker).
"""
from __future__ import annotations

import pytest

# Purely a guard — if these modules fail to import, every assertion below
# would be misleading.
from api_server.auth.oauth import (
    _DEV_PLACEHOLDER,
    _DEV_REDIRECT_GITHUB,
    _DEV_REDIRECT_GOOGLE,
    _DEV_STATE_SECRET,
    get_oauth,
    mint_session,
    reset_oauth_for_tests,
    upsert_user,
)
from api_server.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip any ambient AP_OAUTH_* and AP_ENV from the user's shell env.

    The developer running these tests locally may have real creds in
    ``~/.zshrc`` or in a sourced ``deploy/.env.prod``; nuke them so every
    test starts from a deterministic baseline.
    """
    # Always provide DATABASE_URL — config.py's required field.
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    for k in (
        "AP_OAUTH_GOOGLE_CLIENT_ID",
        "AP_OAUTH_GOOGLE_CLIENT_SECRET",
        "AP_OAUTH_GOOGLE_REDIRECT_URI",
        "AP_OAUTH_GITHUB_CLIENT_ID",
        "AP_OAUTH_GITHUB_CLIENT_SECRET",
        "AP_OAUTH_GITHUB_REDIRECT_URI",
        "AP_OAUTH_STATE_SECRET",
        "AP_ENV",
    ):
        monkeypatch.delenv(k, raising=False)
    # Reset the module-level OAuth cache so each test registers fresh.
    reset_oauth_for_tests()
    yield
    reset_oauth_for_tests()


# ---------------------------------------------------------------------------
# config.py — 7 new fields
# ---------------------------------------------------------------------------


def test_settings_has_all_seven_oauth_fields():
    """Every AP_OAUTH_* alias lands on a Pydantic field as ``str | None``."""
    s = Settings()
    for field in (
        "oauth_google_client_id",
        "oauth_google_client_secret",
        "oauth_google_redirect_uri",
        "oauth_github_client_id",
        "oauth_github_client_secret",
        "oauth_github_redirect_uri",
        "oauth_state_secret",
    ):
        assert hasattr(s, field), f"Settings missing field: {field}"
        assert getattr(s, field) is None, (
            f"{field} should default to None when env is unset"
        )


def test_settings_reads_from_ap_oauth_env_aliases(monkeypatch):
    """``AP_OAUTH_*`` env vars populate the corresponding Pydantic fields."""
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_ID", "real-google-id")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_SECRET", "real-google-sec")
    monkeypatch.setenv(
        "AP_OAUTH_GOOGLE_REDIRECT_URI",
        "https://example.com/v1/auth/google/callback",
    )
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_ID", "real-github-id")
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_SECRET", "real-github-sec")
    monkeypatch.setenv(
        "AP_OAUTH_GITHUB_REDIRECT_URI",
        "https://example.com/v1/auth/github/callback",
    )
    monkeypatch.setenv(
        "AP_OAUTH_STATE_SECRET",
        "0" * 64,  # shape mimics `openssl rand -hex 32`
    )
    s = Settings()
    assert s.oauth_google_client_id == "real-google-id"
    assert s.oauth_google_client_secret == "real-google-sec"
    assert (
        s.oauth_google_redirect_uri
        == "https://example.com/v1/auth/google/callback"
    )
    assert s.oauth_github_client_id == "real-github-id"
    assert s.oauth_github_client_secret == "real-github-sec"
    assert (
        s.oauth_github_redirect_uri
        == "https://example.com/v1/auth/github/callback"
    )
    assert s.oauth_state_secret == "0" * 64


# ---------------------------------------------------------------------------
# auth/oauth.py — get_oauth dev path
# ---------------------------------------------------------------------------


def test_get_oauth_dev_registers_both_providers(monkeypatch):
    """Dev boot without any creds still yields a fully-registered OAuth()."""
    monkeypatch.setenv("AP_ENV", "dev")
    s = Settings()
    oauth = get_oauth(s)
    assert "google" in oauth._registry
    assert "github" in oauth._registry
    # Verify the registered Google provider uses OIDC discovery (server_metadata_url)
    google_cfg = oauth._registry["google"]
    assert google_cfg[-1].get("server_metadata_url") == (
        "https://accounts.google.com/.well-known/openid-configuration"
    )
    # Verify the registered GitHub provider uses the non-OIDC hand-specified
    # endpoints (no server_metadata_url).
    github_cfg = oauth._registry["github"]
    assert (
        github_cfg[-1].get("access_token_url")
        == "https://github.com/login/oauth/access_token"
    )
    assert (
        github_cfg[-1].get("authorize_url")
        == "https://github.com/login/oauth/authorize"
    )
    assert (
        github_cfg[-1].get("api_base_url")
        == "https://api.github.com/"
    )


def test_get_oauth_dev_uses_placeholders_when_creds_missing(monkeypatch):
    """With AP_ENV=dev and no creds, the registered client_id == placeholder."""
    monkeypatch.setenv("AP_ENV", "dev")
    s = Settings()
    oauth = get_oauth(s)
    google_cfg = oauth._registry["google"]
    assert google_cfg[-1].get("client_id") == _DEV_PLACEHOLDER
    assert google_cfg[-1].get("client_secret") == _DEV_PLACEHOLDER
    github_cfg = oauth._registry["github"]
    assert github_cfg[-1].get("client_id") == _DEV_PLACEHOLDER
    assert github_cfg[-1].get("client_secret") == _DEV_PLACEHOLDER


def test_get_oauth_uses_real_creds_in_dev_when_set(monkeypatch):
    """When dev env has real creds, the registered client_id is the real value."""
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_ID", "real-gid")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_SECRET", "real-gsec")
    monkeypatch.setenv(
        "AP_OAUTH_GOOGLE_REDIRECT_URI",
        "http://localhost:8000/v1/auth/google/callback",
    )
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_ID", "real-hid")
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_SECRET", "real-hsec")
    monkeypatch.setenv(
        "AP_OAUTH_GITHUB_REDIRECT_URI",
        "http://localhost:8000/v1/auth/github/callback",
    )
    monkeypatch.setenv("AP_OAUTH_STATE_SECRET", "1" * 64)
    s = Settings()
    oauth = get_oauth(s)
    assert oauth._registry["google"][-1].get("client_id") == "real-gid"
    assert oauth._registry["github"][-1].get("client_id") == "real-hid"


def test_get_oauth_is_idempotent(monkeypatch):
    """Calling get_oauth twice returns the same OAuth() instance (module cache)."""
    monkeypatch.setenv("AP_ENV", "dev")
    s = Settings()
    first = get_oauth(s)
    second = get_oauth(s)
    assert first is second


def test_reset_oauth_for_tests_clears_cache(monkeypatch):
    """``reset_oauth_for_tests`` allows a subsequent get_oauth to re-register."""
    monkeypatch.setenv("AP_ENV", "dev")
    s = Settings()
    first = get_oauth(s)
    reset_oauth_for_tests()
    second = get_oauth(s)
    assert first is not second


# ---------------------------------------------------------------------------
# auth/oauth.py — get_oauth prod fail-loud
# ---------------------------------------------------------------------------


def test_get_oauth_prod_raises_when_google_client_id_missing(monkeypatch):
    """Missing Google client_id in prod → RuntimeError naming the env var."""
    monkeypatch.setenv("AP_ENV", "prod")
    s = Settings()
    with pytest.raises(RuntimeError) as exc:
        get_oauth(s)
    msg = str(exc.value)
    assert "AP_OAUTH_GOOGLE_CLIENT_ID" in msg
    assert "AP_ENV=prod" in msg


def test_get_oauth_prod_raises_when_state_secret_missing(monkeypatch):
    """Missing AP_OAUTH_STATE_SECRET in prod → RuntimeError.

    Covers the middle-of-sequence case: the other 6 creds are set but
    the state secret (the AMD-07-introduced var) is not. This is the
    regression-trap most likely to bite operators upgrading from a
    pre-22c deploy template.
    """
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_ID", "gid")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_SECRET", "gsec")
    monkeypatch.setenv(
        "AP_OAUTH_GOOGLE_REDIRECT_URI",
        "https://example.com/v1/auth/google/callback",
    )
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_ID", "hid")
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_SECRET", "hsec")
    monkeypatch.setenv(
        "AP_OAUTH_GITHUB_REDIRECT_URI",
        "https://example.com/v1/auth/github/callback",
    )
    # AP_OAUTH_STATE_SECRET deliberately NOT set.
    s = Settings()
    with pytest.raises(RuntimeError) as exc:
        get_oauth(s)
    assert "AP_OAUTH_STATE_SECRET" in str(exc.value)


def test_get_oauth_prod_succeeds_when_all_creds_present(monkeypatch):
    """Prod boot with all 7 creds set must NOT raise."""
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_ID", "gid")
    monkeypatch.setenv("AP_OAUTH_GOOGLE_CLIENT_SECRET", "gsec")
    monkeypatch.setenv(
        "AP_OAUTH_GOOGLE_REDIRECT_URI",
        "https://example.com/v1/auth/google/callback",
    )
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_ID", "hid")
    monkeypatch.setenv("AP_OAUTH_GITHUB_CLIENT_SECRET", "hsec")
    monkeypatch.setenv(
        "AP_OAUTH_GITHUB_REDIRECT_URI",
        "https://example.com/v1/auth/github/callback",
    )
    monkeypatch.setenv("AP_OAUTH_STATE_SECRET", "0" * 64)
    s = Settings()
    oauth = get_oauth(s)
    assert oauth._registry["google"][-1].get("client_id") == "gid"
    assert oauth._registry["github"][-1].get("client_id") == "hid"


# ---------------------------------------------------------------------------
# Module surface contract
# ---------------------------------------------------------------------------


def test_module_exports_all_required_helpers():
    """Plan acceptance criteria: get_oauth, upsert_user, mint_session, reset_oauth_for_tests."""
    import inspect

    assert inspect.isfunction(get_oauth)
    assert inspect.iscoroutinefunction(upsert_user)
    assert inspect.iscoroutinefunction(mint_session)
    assert inspect.isfunction(reset_oauth_for_tests)

    # Signatures
    upsert_params = list(inspect.signature(upsert_user).parameters)
    assert upsert_params == [
        "conn",
        "provider",
        "sub",
        "email",
        "display_name",
        "avatar_url",
    ]
    mint_params = list(inspect.signature(mint_session).parameters)
    assert mint_params == ["conn", "user_id", "request"]


def test_dev_placeholder_constants_are_non_secret():
    """Sanity check the dev placeholders are obviously non-production."""
    assert "not-for-prod" in _DEV_PLACEHOLDER
    assert "localhost" in _DEV_REDIRECT_GOOGLE
    assert "localhost" in _DEV_REDIRECT_GITHUB
    assert "not-for-prod" in _DEV_STATE_SECRET
