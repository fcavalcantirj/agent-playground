"""OAuth client registry + user/session helpers (Phase 22c).

This module owns three things:
  1. ``get_oauth(settings)`` — a cached authlib ``OAuth()`` registry with
     ``google`` (OIDC via discovery URL) and ``github`` (non-OIDC, hand-
     specified endpoints) providers registered. Per AMD-01 both providers
     ship in 22c.

  2. ``upsert_user(conn, provider, sub, email, display_name, avatar_url)
     -> UUID`` — upserts into ``users`` keyed on
     ``UNIQUE (provider, sub) WHERE sub IS NOT NULL`` (the partial index
     added by alembic 005). Returns the user's UUID (new or existing).
     Writes provider's ``name`` into ``display_name`` per D-22c-MIG-01
     (no separate ``name`` column).

  3. ``mint_session(conn, user_id, request) -> str`` — inserts a sessions
     row, returns the opaque session_id string (the row's ``id`` UUID).
     ``sessions.id`` uses ``gen_random_uuid()`` as the PK default
     (122 bits of randomness) so the cookie carries that value directly
     — no separate ``token_urlsafe`` column needed. Cookie expiry = 30
     days from now; matches the cookie ``Max-Age=2592000`` set in
     ``routes/auth.py`` per D-22c-OAUTH-04.

Fail-loud discipline mirrors ``crypto/age_cipher.py::_master_key``:
prod boot raises ``RuntimeError`` if any of the 7 OAuth env vars is
missing; dev uses deterministic placeholders so tests boot without
credentials.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from authlib.integrations.starlette_client import OAuth

if TYPE_CHECKING:
    import asyncpg
    from fastapi import Request

    from ..config import Settings

_log = logging.getLogger("api_server.auth.oauth")

# Module-level cache. ``get_oauth`` is idempotent; we register providers once
# per interpreter.
_oauth: OAuth | None = None

# Dev fallbacks — used ONLY when AP_ENV != prod and a given secret is missing.
# These are deliberately non-secret placeholders so tests can exercise the
# registration path without provisioning real credentials.
_DEV_PLACEHOLDER = "dev-placeholder-not-for-prod"
_DEV_REDIRECT_GOOGLE = "http://localhost:8000/v1/auth/google/callback"
_DEV_REDIRECT_GITHUB = "http://localhost:8000/v1/auth/github/callback"
_DEV_STATE_SECRET = "dev-oauth-state-key-not-for-prod-0000000000000000"


def _resolve_or_fail(
    settings: "Settings", field: str, dev_fallback: str
) -> str:
    """Read ``settings.<field>``; fail in prod if missing, else use dev fallback."""
    value = getattr(settings, field)
    if value:
        return value
    if settings.env == "prod":
        raise RuntimeError(
            f"{field.upper()} (env AP_{field.upper()}) required when AP_ENV=prod"
        )
    _log.warning(
        "OAuth config %s missing in dev; using placeholder", field
    )
    return dev_fallback


def get_oauth(settings: "Settings") -> OAuth:
    """Return the process-wide authlib OAuth registry.

    Registers the ``google`` (OIDC) and ``github`` (non-OIDC) providers on
    first call; subsequent calls return the cached registry.

    In prod (``AP_ENV=prod``), raises ``RuntimeError`` if any of the 7
    OAuth env vars is missing (fail-loud; mirrors
    ``crypto/age_cipher.py::_master_key``). In dev, falls back to
    deterministic placeholder strings so the local test harness boots
    without real credentials.
    """
    global _oauth
    if _oauth is not None:
        return _oauth

    google_client_id = _resolve_or_fail(
        settings, "oauth_google_client_id", _DEV_PLACEHOLDER
    )
    google_client_secret = _resolve_or_fail(
        settings, "oauth_google_client_secret", _DEV_PLACEHOLDER
    )
    github_client_id = _resolve_or_fail(
        settings, "oauth_github_client_id", _DEV_PLACEHOLDER
    )
    github_client_secret = _resolve_or_fail(
        settings, "oauth_github_client_secret", _DEV_PLACEHOLDER
    )
    # Redirect URIs + state secret are read through ``_resolve_or_fail`` so
    # the prod fail-loud check covers them even though they're not passed
    # into ``oauth.register`` directly. ``routes/auth.py`` reads them from
    # ``settings`` at call time; the state secret is consumed by Starlette's
    # built-in ``SessionMiddleware`` during app construction.
    _resolve_or_fail(
        settings, "oauth_google_redirect_uri", _DEV_REDIRECT_GOOGLE
    )
    _resolve_or_fail(
        settings, "oauth_github_redirect_uri", _DEV_REDIRECT_GITHUB
    )
    _resolve_or_fail(
        settings, "oauth_state_secret", _DEV_STATE_SECRET
    )

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid email profile"},
    )
    # GitHub is NOT OIDC — authlib needs the endpoints spelled out and the
    # userinfo flow is handled manually in routes/auth.py
    # (``/user`` + ``/user/emails`` when primary is private) per D-22c-OAUTH-03.
    oauth.register(
        name="github",
        client_id=github_client_id,
        client_secret=github_client_secret,
        access_token_url="https://github.com/login/oauth/access_token",
        authorize_url="https://github.com/login/oauth/authorize",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )
    _oauth = oauth
    return oauth


def reset_oauth_for_tests() -> None:
    """Test-only hook — clears the module-level registry so a subsequent
    ``get_oauth(settings_with_new_creds)`` re-registers providers. NEVER
    call this in production code paths.
    """
    global _oauth
    _oauth = None


# ---------------------------------------------------------------------------
# upsert_user
# ---------------------------------------------------------------------------


async def upsert_user(
    conn: "asyncpg.Connection",
    *,
    provider: str,
    sub: str,
    email: str | None,
    display_name: str,
    avatar_url: str | None,
) -> UUID:
    """Upsert a users row keyed on ``UNIQUE (provider, sub) WHERE sub IS NOT NULL``.

    Returns the user's UUID (new or existing). Updates ``email``,
    ``display_name``, ``avatar_url``, ``last_login_at`` on conflict so a
    user whose Google/GitHub profile name changed sees the update on next
    login.

    CROSS-PLAN INVARIANT: the partial unique index
    ``uq_users_provider_sub`` is created by alembic migration 005
    (22c-02). This query's ON CONFLICT target matches that index's
    column list + WHERE clause verbatim — changing either side requires
    updating the other.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO users (provider, sub, email, display_name, avatar_url, last_login_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (provider, sub) WHERE sub IS NOT NULL
        DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            avatar_url = EXCLUDED.avatar_url,
            last_login_at = NOW()
        RETURNING id
        """,
        provider, sub, email, display_name, avatar_url,
    )
    if row is None:  # shouldn't happen with RETURNING; defensive
        raise RuntimeError("upsert_user returned no row")
    return row["id"]


# ---------------------------------------------------------------------------
# mint_session
# ---------------------------------------------------------------------------

SESSION_TTL = timedelta(days=30)


async def mint_session(
    conn: "asyncpg.Connection",
    *,
    user_id: UUID,
    request: "Request",
) -> str:
    """Insert a sessions row; return the opaque session_id string.

    The cookie carries ``sessions.id`` directly: the row's UUID PK uses
    ``gen_random_uuid()`` as the server default (122 bits of
    randomness), so no separate ``token_urlsafe`` column is needed.
    Cookie lookup → sessions row is a single PK SELECT.

    ``request.client.host`` gives us the direct peer; the
    ``AP_TRUSTED_PROXY``/X-Forwarded-For resolution lives in
    ``middleware/rate_limit.py`` and is intentionally NOT replicated here
    — we record the direct peer for future admin-UI display only.
    """
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """
        INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at, user_agent, ip_address)
        VALUES ($1, $2, $3, $2, $4, $5)
        RETURNING id
        """,
        user_id, now, now + SESSION_TTL, user_agent, ip,
    )
    if row is None:
        raise RuntimeError("mint_session returned no row")
    return str(row["id"])
