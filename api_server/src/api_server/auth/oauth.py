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

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

import httpx
import jwt as _pyjwt
from authlib.integrations.starlette_client import OAuth
from google.auth import exceptions as _google_exceptions
from google.auth.transport import requests as _google_ga_requests
from google.oauth2 import id_token as _google_id_token

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

# Phase 23-06 (D-15..D-17, D-23): process-wide google-auth Request transport.
# Reused by every call to ``verify_google_id_token`` so the underlying
# ``requests.Session`` keeps HTTP keep-alive open against googleapis.com,
# amortizing the TLS handshake across consecutive sign-ins. google-auth's
# ``Request`` is thread-safe; ``asyncio.to_thread`` wraps the blocking call
# at the helper boundary.
#
# Per RESEARCH §"Pattern 5" we deliberately SKIP a custom 6h JWKS cache —
# the google-auth library's own caching is sufficient for MVP, and a hand-
# rolled cache risks masking key-rotation incidents (the most likely
# failure mode for a JWKS-validated path).
_GOOGLE_REQUEST = _google_ga_requests.Request()


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
    """Upsert a user via the user_identities join table + canonical_email link.

    2026-05-17 — Bug #1 fix. Three-step resolution to collapse N OAuth
    identities of the same human into ONE ``users.id``:

      1. **Fast path — known identity.** SELECT ``user_id`` from
         ``user_identities WHERE (provider, sub) = ($1, $2)``. If found,
         touch ``last_login_at`` on both tables and return the existing
         ``user_id`` — the user is signing back in via the same provider.

      2. **Link path — canonical_email match.** Compute
         ``canonical_email(email)`` (Gmail dot-collapse, +tag strip,
         googlemail → gmail, privacy-relay → NULL). If non-NULL and
         matches an existing ``users.canonical_email``, INSERT a new
         ``user_identities`` row pointing at that ``user_id``. The
         human just signed in with a NEW provider but our system
         recognizes them via canonicalized email; their existing
         agents / credits / sessions follow them.

      3. **New user path.** No identity match, no canonical_email match
         (or canonical_email is NULL for Apple privacy-relay). INSERT a
         new ``users`` row + INSERT the ``user_identities`` row pointing
         at it. Returns the new ``users.id``.

    The legacy (provider, sub) columns on ``users`` are still written
    for backward compat — migration 017 will drop them after the
    destructive merge.

    Caller signature unchanged from the pre-016 version so the 6 OAuth
    route handlers don't need touching.
    """
    from .canonical import canonical_email as _canonical_email

    canonical = _canonical_email(email)

    # ---- Race defense: advisory lock on canonical_email --------------
    # Migration 016 deliberately does NOT add UNIQUE on canonical_email
    # yet (017's audit + merge is the gate). Without UNIQUE, two
    # simultaneous first-time sign-ins from different providers with the
    # same canonical_email can BOTH miss steps 1 + 2 and BOTH execute
    # step 3 -- reproducing the duplicate-rows bug 016 is fixing.
    # ``pg_advisory_xact_lock`` serializes these on the canonical_email
    # hash and releases at the end of the caller's transaction
    # (``async with conn.transaction():``). NULL canonical (Apple privacy-
    # relay / missing email) skips the lock -- those identities are
    # already (provider, sub)-only by design.
    if canonical is not None:
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended($1::text, 0))",
            canonical,
        )

    # ---- Step 1: fast path — identity already exists ----------------
    row = await conn.fetchrow(
        "SELECT user_id FROM user_identities "
        "WHERE provider = $1 AND sub = $2",
        provider, sub,
    )
    if row is not None:
        user_id = row["user_id"]
        await conn.execute(
            "UPDATE user_identities SET last_login_at = NOW(), email = $3 "
            "WHERE provider = $1 AND sub = $2",
            provider, sub, email,
        )
        await conn.execute(
            "UPDATE users "
            "SET last_login_at = NOW(), display_name = $2, avatar_url = $3 "
            "WHERE id = $1",
            user_id, display_name, avatar_url,
        )
        return user_id

    # ---- Step 2: link path — canonical_email matches existing user ---
    # ORDER BY created_at LIMIT 1 = OLDEST users.id wins as the merge
    # anchor when duplicate-rows state still exists (pre-017). Migration
    # 017's audit + merge will collapse the losers into this winner.
    if canonical is not None:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE canonical_email = $1 "
            "ORDER BY created_at LIMIT 1",
            canonical,
        )
        if existing is not None:
            user_id = existing["id"]
            # ON CONFLICT defensive: under the advisory lock above no
            # other transaction is racing for this canonical, but the
            # (provider, sub) UNIQUE could still trip if a same-provider
            # row was created in a parallel non-canonical path (e.g. a
            # prior request without canonical_email).
            await conn.execute(
                "INSERT INTO user_identities (user_id, provider, sub, email) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (provider, sub) DO UPDATE "
                "SET last_login_at = NOW(), email = EXCLUDED.email",
                user_id, provider, sub, email,
            )
            await conn.execute(
                "UPDATE users "
                "SET last_login_at = NOW(), display_name = $2, avatar_url = $3 "
                "WHERE id = $1",
                user_id, display_name, avatar_url,
            )
            return user_id

    # ---- Step 3: new user — first time this human has signed up ------
    # The legacy `provider` + `sub` columns on `users` are still written
    # to keep migration-005's partial-UNIQUE invariant intact. Migration
    # 017 will drop both columns AND this INSERT will be rewritten in the
    # same PR -- DO NOT ship 017 without updating this site too.
    # REMOVE-IN-017: provider, sub from INSERT column list.
    new_row = await conn.fetchrow(
        "INSERT INTO users "
        "(provider, sub, email, canonical_email, display_name, "
        " avatar_url, last_login_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, NOW()) "
        "RETURNING id",
        provider, sub, email, canonical, display_name, avatar_url,
    )
    if new_row is None:
        raise RuntimeError("upsert_user returned no row")
    user_id = new_row["id"]

    # Insert the identity with ON CONFLICT to handle the same-(provider,
    # sub) concurrent first-signin race (NULL canonical path -- Apple
    # privacy-relay or missing email -- where the advisory lock above
    # didn't trigger). If a concurrent transaction won the identity
    # INSERT first, ON CONFLICT returns its winning ``user_id``; we then
    # delete our just-orphaned `users` row so we don't leave a stray.
    identity_row = await conn.fetchrow(
        "INSERT INTO user_identities (user_id, provider, sub, email) "
        "VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (provider, sub) DO UPDATE "
        "SET last_login_at = NOW(), email = EXCLUDED.email "
        "RETURNING user_id",
        user_id, provider, sub, email,
    )
    if identity_row is None:
        raise RuntimeError("user_identities insert returned no row")
    winner_id = identity_row["user_id"]
    if winner_id != user_id:
        # Lost the race; another transaction created this (provider, sub)
        # first. Drop our orphaned users row and return the winner.
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        return winner_id
    return user_id


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


# ---------------------------------------------------------------------------
# Phase 23-06 mobile-OAuth credential verification helpers
# ---------------------------------------------------------------------------
#
# These helpers cover REQ API-05 (D-15..D-17, D-23, D-24, D-30): the mobile
# Flutter app obtains a credential from a NATIVE SDK (google_sign_in or
# flutter_appauth) and POSTs it to the API. The API verifies the credential
# server-side and only THEN trusts the claimed identity to upsert the user
# + mint a session.
#
# Both helpers raise ``ValueError`` on every failure mode; the routes layer
# maps that to a 401 ``UNAUTHORIZED`` envelope. We do NOT log the raw
# credential bytes — log_redact middleware redacts request bodies, and the
# helpers' error messages reference the failure category (signature /
# audience / expiry / status code) without echoing the token itself
# (T-23-V7-TOKEN-LOG-LEAK mitigation).


async def verify_google_id_token(
    id_token: str, mobile_client_ids: list[str]
) -> dict:
    """Verify a Google-issued ID token against the mobile client IDs.

    Calls ``google.oauth2.id_token.verify_oauth2_token`` inside
    ``asyncio.to_thread`` (the library is synchronous and contacts the
    Google JWKS endpoint via blocking ``requests``). The ``audience``
    argument accepts ``list[str]`` and matches ANY entry — Wave 0
    spike A1 verified this empirically (D-23: Android + iOS client IDs
    coexist in one process).

    Raises ``ValueError`` on every failure mode (signature mismatch,
    expiry, audience mismatch, missing claims, malformed token, library
    error). The route handler maps that to a 401 envelope.

    If ``mobile_client_ids`` is empty (env not configured), we refuse
    immediately rather than letting google-auth attempt verify against
    an empty list — the empty-list semantic is library-version-dependent
    and we'd rather emit a clear "not configured" error.
    """
    if not mobile_client_ids:
        raise ValueError("no mobile client IDs configured")

    def _verify_sync():
        return _google_id_token.verify_oauth2_token(
            id_token, _GOOGLE_REQUEST, audience=mobile_client_ids
        )

    try:
        return await asyncio.to_thread(_verify_sync)
    except _google_exceptions.GoogleAuthError as e:
        # google-auth raises GoogleAuthError subclasses for transport /
        # crypto failures. Re-raise as ValueError with a redacted
        # message — we never echo the raw token in the error string.
        raise ValueError(f"google id_token rejected: {e}") from e
    except ValueError as e:
        # google-auth raises ValueError directly for audience mismatch,
        # expiry, missing claims, malformed JWT structure. Pass through
        # so the route handler's existing ValueError handler catches it.
        # 2026-05-12 — before re-raising, log the unverified `aud` project
        # prefix at WARN so prod-side config drift (mobile app trusting a
        # different Google Cloud project than the backend) is visible in
        # docker logs even when Sentry's _before_send filter drops the
        # USER_ERROR-bucket 401 envelope. We decode the JWT WITHOUT
        # verification (signature already failed) and log ONLY the
        # numeric project prefix (e.g. "303159181051") — never the full
        # client ID, never the user-identifying sub/email.
        try:
            unverified = _pyjwt.decode(
                id_token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_exp": False,
                    "verify_iss": False,
                },
            )
            raw_aud = unverified.get("aud") or ""
            project = (
                raw_aud.split("-", 1)[0] if isinstance(raw_aud, str) else "?"
            )
            _log.warning(
                "google_id_token_verify_failed err=%s aud_project=%s "
                "configured_projects=%s",
                str(e)[:200],
                project,
                sorted({
                    cid.split("-", 1)[0]
                    for cid in mobile_client_ids
                    if isinstance(cid, str)
                }),
            )
        except Exception:
            # Defensive — never let logging crash the verify path.
            _log.warning("google_id_token_verify_failed (aud unparseable)")
        raise


async def exchange_github_code(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
    http_client: "httpx.AsyncClient",
    code_verifier: str | None = None,
) -> str:
    """Exchange a GitHub authorization code for an access_token.

    Mobile (Phase 25 Wave 5) — flutter_appauth's authorize() returns
    the authorization code (no exchange) so the client_secret never
    lives on the device. This server-side helper performs the exchange
    using the mobile-app's GitHub OAuth credentials (separate from the
    web OAuth App because GitHub allows only one callback URL per app).

    Critical: GitHub's ``/login/oauth/access_token`` defaults to a
    ``application/x-www-form-urlencoded`` response body. We send
    ``Accept: application/json`` so the response is JSON and we can
    parse it without form-decoding. Without this header, AppAuth-iOS
    fails with NSCocoaErrorDomain code=3840 ("JSON text did not start
    with array or object") — the very bug that drove this refactor.

    Raises ``ValueError`` on any failure mode (transport error,
    non-200, missing access_token, GitHub error envelope) without
    leaking the secret in the message.
    """
    if not client_id or not client_secret:
        raise ValueError("github mobile OAuth credentials not configured")
    try:
        form = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier
        res = await http_client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data=form,
            timeout=10.0,
        )
    except Exception as e:  # httpx HTTPError, TLS, DNS
        raise ValueError(f"github code exchange transport failure: {type(e).__name__}") from e
    if res.status_code != 200:
        # Wave 5 debugging: surface GitHub's response body so the failure
        # category (missing field, wrong endpoint, etc) is visible to the
        # mobile UI instead of just the status code.
        body_preview = (res.text or "")[:200]
        raise ValueError(
            f"github code exchange returned {res.status_code}: {body_preview}",
        )
    body = res.json()
    if isinstance(body, dict) and body.get("error"):
        # GitHub returns {error, error_description, error_uri} on auth failure.
        # Wave 5 debugging: include error_description so the mobile UI can
        # show the actual reason (e.g. "redirect_uri does not match...").
        err = body.get("error")
        desc = body.get("error_description") or ""
        raise ValueError(f"github code exchange rejected: {err}: {desc}".strip(": "))
    access_token = body.get("access_token") if isinstance(body, dict) else None
    if not access_token:
        raise ValueError("github code exchange returned no access_token")
    return str(access_token)


async def verify_github_access_token(
    access_token: str, http_client: "httpx.AsyncClient"
) -> dict:
    """Validate a GitHub access token; return a normalized profile dict.

    Mirrors the browser GitHub callback flow at routes/auth.py:246-278:

      1. ``GET /user`` with ``Authorization: Bearer <token>``
      2. If ``email`` is null (user set primary email private), follow up
         with ``GET /user/emails`` and pick the first ``primary=True,
         verified=True`` entry.
      3. Refuse account creation if no verified email is recoverable
         (D-22c-OAUTH-03 second half).

    The browser callback uses ``authlib.oauth.github.get(...)`` which is
    a different transport path (authlib's httpx_client) than the raw
    ``http_client`` we pass here. Because the path is different we keep
    the duplication rather than refactoring the browser callback —
    consolidating the two would force authlib's token-aware client into
    the mobile path or our raw httpx client into the browser path, both
    of which are larger surface changes than this MVP justifies. Logged
    as a deferred-ideas item.

    Raises ``ValueError`` on every failure (HTTP error, non-200, no
    profile id, no verified email).

    Returns ``{sub: str, email: str, display_name: str,
                avatar_url: str | None}``.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        r = await http_client.get(
            "https://api.github.com/user", headers=headers, timeout=10.0,
        )
    except httpx.HTTPError as e:
        raise ValueError(f"github /user fetch failed: {e}") from e

    if r.status_code != 200:
        raise ValueError(
            f"github access_token rejected (status {r.status_code})"
        )

    profile = r.json()
    if not profile.get("id"):
        raise ValueError("github profile missing id")

    email = profile.get("email")
    if not email:
        try:
            er = await http_client.get(
                "https://api.github.com/user/emails",
                headers=headers,
                timeout=10.0,
            )
            er.raise_for_status()
            emails = er.json()
            email = next(
                (
                    e["email"]
                    for e in emails
                    if e.get("primary")
                    and e.get("verified")
                    and e.get("email")
                ),
                None,
            )
        except httpx.HTTPError:
            email = None

    if not email:
        raise ValueError("no verified primary email")

    return {
        "sub": str(profile["id"]),
        "email": email,
        "display_name": (
            profile.get("name") or profile.get("login") or "user"
        ),
        "avatar_url": profile.get("avatar_url"),
    }


# ---------------------------------------------------------------------------
# 2026-05-12 — Sign in with Apple identity_token verifier.
# ---------------------------------------------------------------------------
#
# Apple's flow: the iOS native `sign_in_with_apple` package returns an
# `identity_token` (a signed JWT issued by `https://appleid.apple.com`).
# The token's `aud` claim is the app's bundle ID
# (`com.solvrlabs.agentplayground` — set by `oauth_apple_audience`).
# The `sub` claim is Apple's stable per-app user identifier.
# The `email` claim is either the user's real email or a relay address
# of the form `<random>@privaterelay.appleid.com` (forwarded to the user's
# real address by Apple).
#
# We verify the JWT signature against Apple's JWKS endpoint
# (https://appleid.apple.com/auth/keys). PyJWT's PyJWKClient handles JWKS
# fetch + key-id matching + RS256/ES256 verification. PyJWKClient caches
# keys in-process for `lifespan` seconds (default 300) — adequate for MVP;
# Apple rotates keys infrequently and the cache survives until the next
# server restart in the worst case.
#
# The verifier raises `ValueError` on every failure mode. The route handler
# maps that to a 401 envelope. We never log the raw `id_token` bytes.

_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_ISSUER = "https://appleid.apple.com"

# Process-wide JWKS client. PyJWKClient is thread-safe and caches keys
# in-process; we wrap each `get_signing_key_from_jwt` call in
# `asyncio.to_thread` because the underlying HTTP fetch is blocking
# (urllib via `requests`-compatible code path).
_APPLE_JWK_CLIENT = _pyjwt.PyJWKClient(_APPLE_JWKS_URL, cache_keys=True)


async def verify_apple_identity_token(
    id_token: str, audience: str
) -> dict:
    """Verify a Sign-in-with-Apple identity_token (JWT) and return its claims.

    Validates: signature against Apple's JWKS, issuer == appleid.apple.com,
    audience == `audience` (the iOS bundle ID), `exp` not expired,
    `iat`/`nbf` not in the future.

    Returns the verified claims dict on success. Raises ``ValueError`` on
    every failure mode — the route handler maps that to a 401 envelope.

    The PyJWKClient blocks while fetching keys (first call only — keys are
    cached for the remainder of the process). We wrap the entire verify
    path in `asyncio.to_thread` so the event loop is never stalled.
    """
    if not id_token:
        raise ValueError("empty apple identity_token")
    if not audience:
        raise ValueError("apple audience not configured")

    def _verify_sync() -> dict:
        try:
            signing_key = _APPLE_JWK_CLIENT.get_signing_key_from_jwt(id_token)
        except _pyjwt.PyJWKClientError as e:
            raise ValueError(
                f"apple jwks key lookup failed: {type(e).__name__}"
            ) from e
        except _pyjwt.DecodeError as e:
            # get_signing_key_from_jwt() internally calls
            # `jwt.get_unverified_header()` which raises DecodeError on a
            # non-JWT string (e.g. our 401-smoke probe).
            raise ValueError(
                f"apple identity_token malformed: {type(e).__name__}"
            ) from e
        except _pyjwt.InvalidTokenError as e:
            raise ValueError(
                f"apple identity_token rejected at jwks: {type(e).__name__}"
            ) from e
        try:
            return _pyjwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=audience,
                issuer=_APPLE_ISSUER,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
            )
        except _pyjwt.ExpiredSignatureError as e:
            raise ValueError("apple identity_token expired") from e
        except _pyjwt.InvalidAudienceError as e:
            raise ValueError("apple identity_token audience mismatch") from e
        except _pyjwt.InvalidIssuerError as e:
            raise ValueError("apple identity_token issuer mismatch") from e
        except _pyjwt.InvalidSignatureError as e:
            raise ValueError("apple identity_token signature invalid") from e
        except _pyjwt.MissingRequiredClaimError as e:
            raise ValueError(f"apple identity_token missing claim: {e.claim}") from e
        except _pyjwt.DecodeError as e:
            raise ValueError(
                f"apple identity_token decode failed: {type(e).__name__}"
            ) from e
        except _pyjwt.InvalidTokenError as e:
            raise ValueError(
                f"apple identity_token rejected: {type(e).__name__}"
            ) from e

    return await asyncio.to_thread(_verify_sync)
