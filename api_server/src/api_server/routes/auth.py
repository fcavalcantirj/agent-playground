"""OAuth2 authorize + callback + logout routes (Phase 22c).

Surface::

    GET  /v1/auth/google            -> 302 to Google authorize endpoint
    GET  /v1/auth/google/callback   -> exchange code, upsert user, mint session, 302 /dashboard
    GET  /v1/auth/github            -> 302 to GitHub authorize endpoint
    GET  /v1/auth/github/callback   -> exchange code, fetch /user (+/user/emails fallback), mint session
    POST /v1/auth/logout            -> delete sessions row, clear cookie, 204

Two cookies participate in the OAuth round-trip:

* ``ap_oauth_state`` — Starlette's built-in ``SessionMiddleware`` stores
  the authlib-generated CSRF state nonce here. Signed via
  ``AP_OAUTH_STATE_SECRET`` (AMD-07). TTL 10 minutes.
* ``ap_session`` — our opaque session cookie. UUID pointing at a
  ``sessions`` row in Postgres. TTL 30 days (D-22c-OAUTH-04).

Error-redirect contract (D-22c-FE-03):

* ``access_denied``   — user denied consent on the provider screen
                         (arrives as ``?error=access_denied`` query param)
* ``state_mismatch``  — authlib raised ``OAuthError(error="mismatching_state")``
                         (CSRF defense tripped). EXACT match — NOT substring.
* ``oauth_failed``    — any other OAuthError / token-endpoint 5xx /
                         userinfo failure / non-primary GitHub email /
                         missing sub. Catch-all fallback.

EXACT match rationale: authlib's error value for the state-nonce check is
the literal string ``"mismatching_state"``. Substring matching on the
message (which humans read) risks misclassifying hypothetical future
errors whose descriptions contain "state" but are not CSRF violations.
We key on the canonical error code only.

GitHub email-fallback contract (D-22c-OAUTH-03):

If the ``/user`` response's ``email`` is null (the user set their primary
email to private on GitHub), make one follow-up call to ``/user/emails``
and pick the first ``primary=true, verified=true`` entry. If still null,
fail to ``/login?error=oauth_failed`` — we refuse to create accounts
without a verified email on file.
"""
from __future__ import annotations

import logging
from uuid import UUID

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from ..auth.deps import require_user
from ..auth.oauth import get_oauth, mint_session, upsert_user
from ..models.errors import ErrorCode, make_error_envelope

router = APIRouter()
_log = logging.getLogger("api_server.auth")

_SESSION_COOKIE = "ap_session"
_SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days — matches SESSION_TTL in auth/oauth.py
# Paths only — prefixed with settings.frontend_base_url at call site so the
# 302 lands on the frontend (port 3000) and not the API origin (port 8000).
# Plan gap surfaced by Phase 22c manual smoke (D-22c-FE-03 + 22c-09).
_DASHBOARD_PATH = "/dashboard"
_LOGIN_PATH = "/login"


def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Stripe-shape error envelope — mirrors ``routes/agent_events.py::_err``."""
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )


def _set_session_cookie(resp: Response, session_id: str, settings) -> None:
    """Set the ``ap_session`` cookie per D-22c-OAUTH-04.

    HttpOnly + SameSite=Lax + Path=/ always; ``Secure`` only when
    ``AP_ENV=prod`` so dev on ``http://localhost:*`` still accepts the
    cookie (mirrors the env-gated pattern in ``crypto/age_cipher.py``).
    """
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value=session_id,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )


def _clear_session_cookie(resp: Response, settings) -> None:
    """Clear the ``ap_session`` cookie on logout (Set-Cookie with Max-Age=0)."""
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )


def _login_redirect_with_error(settings, code: str) -> RedirectResponse:
    """302 to ``<frontend_base_url>/login?error=<code>`` — frontend reads
    ``?error=`` on mount and surfaces a toast (D-22c-FE-03)."""
    return RedirectResponse(
        f"{settings.frontend_base_url}{_LOGIN_PATH}?error={code}",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# Google (OIDC)
# ---------------------------------------------------------------------------


@router.get("/auth/google")
async def google_login(request: Request):
    """Kick off the Google OAuth2 flow.

    authlib's ``authorize_redirect`` generates the state nonce, stores it
    in ``request.session`` (Starlette's built-in SessionMiddleware backed
    by the ``ap_oauth_state`` cookie), and returns a 302 to
    ``accounts.google.com/o/oauth2/v2/auth`` with our ``client_id`` +
    ``redirect_uri`` + ``state`` + scope ``openid email profile``
    (D-22c-OAUTH-02 — no ``access_type=offline``; refresh tokens dropped
    per AMD-02).
    """
    settings = request.app.state.settings
    oauth = get_oauth(settings)
    return await oauth.google.authorize_redirect(
        request, settings.oauth_google_redirect_uri
    )


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    """Callback handler — exchange code, upsert user, mint session, set cookie."""
    settings = request.app.state.settings
    oauth = get_oauth(settings)

    # Google redirects back with ?error=access_denied when the user cancels
    # consent on the Google screen. Handle before touching authlib so a
    # denial doesn't run through the token-endpoint path.
    err_param = request.query_params.get("error")
    if err_param == "access_denied":
        return _login_redirect_with_error(settings, "access_denied")

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        # EXACT match on authlib's canonical CSRF-state error value.
        # Substring matching is fragile — other errors (e.g. a future
        # authlib version that adds a different "state"-containing message)
        # could be misclassified. We key on the canonical error code only.
        if e.error == "mismatching_state":
            return _login_redirect_with_error(settings, "state_mismatch")
        _log.warning("google oauth_failed: %s", e.error)
        return _login_redirect_with_error(settings, "oauth_failed")

    # Google OIDC flow — authlib parses the id_token and returns userinfo
    # inside the token dict. Fall back to explicit ``userinfo()`` if the
    # token dict doesn't include one (shouldn't happen with standard
    # ``openid`` scope, but be defensive).
    userinfo = token.get("userinfo")
    if userinfo is None:
        try:
            userinfo = await oauth.google.userinfo(token=token)
        except Exception:
            _log.exception("google userinfo fetch failed")
            return _login_redirect_with_error(settings, "oauth_failed")

    if not userinfo or not userinfo.get("sub"):
        return _login_redirect_with_error(settings, "oauth_failed")

    display_name = userinfo.get("name") or userinfo.get("email") or "user"
    pool = request.app.state.db
    async with pool.acquire() as conn:
        user_id = await upsert_user(
            conn,
            provider="google",
            sub=str(userinfo["sub"]),
            email=userinfo.get("email"),
            display_name=display_name,
            avatar_url=userinfo.get("picture"),
        )
        session_id = await mint_session(conn, user_id=user_id, request=request)

    resp = RedirectResponse(
        f"{settings.frontend_base_url}{_DASHBOARD_PATH}", status_code=302
    )
    _set_session_cookie(resp, session_id, settings)
    return resp


# ---------------------------------------------------------------------------
# GitHub (non-OIDC)
# ---------------------------------------------------------------------------


@router.get("/auth/github")
async def github_login(request: Request):
    """Kick off the GitHub OAuth2 flow.

    Scope ``read:user user:email`` (D-22c-OAUTH-03). GitHub is NOT OIDC,
    so the callback will need to call ``/user`` (and possibly
    ``/user/emails``) explicitly — authlib doesn't parse an id_token here.
    """
    settings = request.app.state.settings
    oauth = get_oauth(settings)
    return await oauth.github.authorize_redirect(
        request, settings.oauth_github_redirect_uri
    )


@router.get("/auth/github/callback")
async def github_callback(request: Request):
    """Callback handler — exchange code, fetch user profile, mint session."""
    settings = request.app.state.settings
    oauth = get_oauth(settings)

    err_param = request.query_params.get("error")
    if err_param == "access_denied":
        return _login_redirect_with_error(settings, "access_denied")

    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError as e:
        # EXACT match — see google_callback for rationale.
        if e.error == "mismatching_state":
            return _login_redirect_with_error(settings, "state_mismatch")
        _log.warning("github oauth_failed: %s", e.error)
        return _login_redirect_with_error(settings, "oauth_failed")

    try:
        user_resp = await oauth.github.get("user", token=token)
        profile = user_resp.json()
    except Exception:
        _log.exception("github /user fetch failed")
        return _login_redirect_with_error(settings, "oauth_failed")

    sub = profile.get("id")
    if sub is None:
        return _login_redirect_with_error(settings, "oauth_failed")

    # GitHub returns a null ``email`` when the user set their primary email
    # to private. Fall back to ``/user/emails`` and pick the first
    # primary+verified entry. If still null, refuse to create the account.
    email = profile.get("email")
    if not email:
        try:
            emails_resp = await oauth.github.get("user/emails", token=token)
            emails = emails_resp.json()
            email = next(
                (
                    e["email"]
                    for e in emails
                    if e.get("primary") and e.get("verified") and e.get("email")
                ),
                None,
            )
        except Exception:
            _log.exception("github /user/emails fetch failed")
            email = None

    if not email:
        return _login_redirect_with_error(settings, "oauth_failed")

    display_name = profile.get("name") or profile.get("login") or "user"
    pool = request.app.state.db
    async with pool.acquire() as conn:
        user_id = await upsert_user(
            conn,
            provider="github",
            sub=str(sub),
            email=email,
            display_name=display_name,
            avatar_url=profile.get("avatar_url"),
        )
        session_id = await mint_session(conn, user_id=user_id, request=request)

    resp = RedirectResponse(
        f"{settings.frontend_base_url}{_DASHBOARD_PATH}", status_code=302
    )
    _set_session_cookie(resp, session_id, settings)
    return resp


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/auth/logout")
async def logout(request: Request):
    """Delete the ``sessions`` row + clear the ``ap_session`` cookie.

    Protected by ``require_user`` — no cookie = 401. Valid cookie but a
    session that's already been revoked/expired also hits the 401 path
    (the middleware won't populate ``request.state.user_id`` in that
    case, so ``require_user`` returns the 401 envelope).

    Flow:

    1. ``require_user`` gate (401 on no / invalid session).
    2. Read the raw ``ap_session`` cookie to get the session UUID; only
       used for the DELETE — we don't re-authenticate against it.
    3. ``DELETE FROM sessions WHERE id = $1`` — single PK delete. If the
       row is already gone (double-logout race), the DELETE is a no-op
       and we still return 204. Idempotent.
    4. Build a 204 response + clear the cookie.

    Returns ``204 No Content`` with ``Set-Cookie: ap_session=; Max-Age=0``.
    """
    settings = request.app.state.settings
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    # We have an authenticated user_id; delete the sessions row that matched.
    session_uuid = _read_session_cookie_uuid(request)

    pool = request.app.state.db
    async with pool.acquire() as conn:
        if session_uuid is not None:
            await conn.execute("DELETE FROM sessions WHERE id = $1", session_uuid)

    # 204 No Content — no body. Response(status_code=204) is the correct
    # primitive; JSONResponse(content=None, 204) would still emit a
    # Content-Length header for the JSON "null", which violates the 204
    # contract (no body at all).
    resp = Response(status_code=204)
    _clear_session_cookie(resp, settings)
    return resp


def _read_session_cookie_uuid(request: Request) -> UUID | None:
    """Read the ``ap_session`` cookie, coerce to UUID, return None on failure."""
    raw = request.cookies.get(_SESSION_COOKIE)
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


__all__ = [
    "router",
    "google_login",
    "google_callback",
    "github_login",
    "github_callback",
    "logout",
]
