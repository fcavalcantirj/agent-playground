"""AMD-07: prod boot without ``AP_OAUTH_STATE_SECRET`` must raise RuntimeError.

Regression trap for operators upgrading from a pre-22c deploy template.
The state secret was introduced in Phase 22c-03 (AMD-07); ``get_oauth()``
calls ``_resolve_or_fail(settings, "oauth_state_secret", ...)`` which
raises in prod when the env var is missing. This test proves the
RuntimeError actually fires rather than silently falling back to the dev
placeholder in prod — which would leave the session cookie signed with
a known-public value and make CSRF state unverifiable.

Dev path is also asserted so a future refactor that breaks the dev
placeholder doesn't silently stop the whole test harness from booting.

These tests are pure unit tests (no DB, no network, no FastAPI app) — they
run in the DEFAULT pytest invocation (no ``api_integration`` marker
required), which is why the file lives under ``tests/config/`` rather
than ``tests/auth/`` (auth tests all require integration infra).
"""
from __future__ import annotations

import os

import pytest


def _strip_oauth_env(monkeypatch):
    """Remove every AP_OAUTH_* env var from the running shell env."""
    for k in list(os.environ):
        if k.startswith("AP_OAUTH_"):
            monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _reset_oauth_cache():
    """Clear the module-level ``_oauth`` cache so each test re-registers."""
    from api_server.auth.oauth import reset_oauth_for_tests
    reset_oauth_for_tests()
    yield
    reset_oauth_for_tests()


def test_prod_fails_boot_without_state_secret(monkeypatch):
    """AP_ENV=prod + missing AP_OAUTH_STATE_SECRET → RuntimeError naming the env var.

    All 6 other OAuth vars are set so the state-secret check is the only
    one that can fail — proves the fail-loud wiring covers
    ``oauth_state_secret`` specifically (the AMD-07-introduced var is
    the one most likely to be missing in a half-migrated deploy).
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    monkeypatch.setenv("AP_ENV", "prod")
    _strip_oauth_env(monkeypatch)
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
    # Deliberately omit AP_OAUTH_STATE_SECRET.

    from api_server.auth.oauth import get_oauth
    from api_server.config import Settings

    with pytest.raises(RuntimeError, match=r"OAUTH_STATE_SECRET"):
        get_oauth(Settings())


def test_dev_boots_without_state_secret(monkeypatch):
    """AP_ENV=dev with NO OAuth creds at all → registry built, no raise.

    Covers the local-dev path: a fresh clone with no secrets exported
    must still produce a working (placeholder-wired) OAuth registry so
    unit tests and dev-server smoke checks boot.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    monkeypatch.setenv("AP_ENV", "dev")
    _strip_oauth_env(monkeypatch)

    from api_server.auth.oauth import get_oauth
    from api_server.config import Settings

    registry = get_oauth(Settings())
    # Both providers registered on the same registry instance.
    assert "google" in registry._registry
    assert "github" in registry._registry
