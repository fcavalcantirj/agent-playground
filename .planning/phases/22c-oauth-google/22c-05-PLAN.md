---
phase: 22c-oauth-google
plan: 05
type: execute
wave: 3
depends_on: [22c-04]
files_modified:
  - api_server/src/api_server/auth/deps.py
  - api_server/src/api_server/routes/auth.py
  - api_server/src/api_server/routes/users.py
  - api_server/src/api_server/models/users.py
  - api_server/src/api_server/main.py
  - api_server/tests/auth/test_google_authorize.py
  - api_server/tests/auth/test_google_callback.py
  - api_server/tests/auth/test_github_authorize.py
  - api_server/tests/auth/test_github_callback.py
  - api_server/tests/auth/test_logout.py
  - api_server/tests/routes/test_users_me.py
  - api_server/tests/config/test_oauth_state_secret_fail_loud.py
  - api_server/tests/conftest.py
autonomous: false
requirements: [R1, R2, R4, R5, AMD-01, AMD-02, AMD-07, D-22c-AUTH-01, D-22c-AUTH-03, D-22c-OAUTH-01, D-22c-OAUTH-02, D-22c-OAUTH-03, D-22c-OAUTH-04, D-22c-OAUTH-05, D-22c-FE-03, D-22c-FE-04]
must_haves:
  truths:
    - "GET /v1/auth/google returns 302 to https://accounts.google.com/ with client_id + state + redirect_uri"
    - "GET /v1/auth/github returns 302 to https://github.com/login/oauth/authorize with client_id + state + redirect_uri"
    - "GET /v1/auth/google/callback with valid code + matching state upserts user + inserts session + Set-Cookie ap_session + 302 to /dashboard"
    - "GET /v1/auth/google/callback with authlib OAuthError (error == 'mismatching_state') returns 302 to /login?error=state_mismatch (EXACT match, not substring)"
    - "GET /v1/auth/google/callback with non-state OAuthError (e.g., token-endpoint 500) returns 302 to /login?error=oauth_failed"
    - "GET /v1/auth/github/callback fetches /user + falls back to /user/emails when primary email is null"
    - "GET /v1/users/me with valid cookie returns 200 + {id, email, display_name, avatar_url, provider, created_at}"
    - "GET /v1/users/me without cookie returns 401 + Stripe-shape envelope {error: {code: 'unauthorized', ...}}"
    - "POST /v1/auth/logout with valid cookie DELETEs sessions row + Set-Cookie ap_session=; Max-Age=0 + returns 204"
    - "middleware stack order in main.py: CorrelationId -> AccessLog -> StarletteSession -> OurSession -> RateLimit -> Idempotency"
    - "In prod (AP_ENV=prod), missing AP_OAUTH_STATE_SECRET causes app boot RuntimeError"
  artifacts:
    - path: "api_server/src/api_server/auth/deps.py"
      provides: "require_user(request) -> JSONResponse | UUID"
    - path: "api_server/src/api_server/routes/auth.py"
      provides: "5 endpoints: /v1/auth/{google,github} + /v1/auth/{google,github}/callback + POST /v1/auth/logout"
    - path: "api_server/src/api_server/routes/users.py"
      provides: "GET /v1/users/me"
    - path: "api_server/src/api_server/models/users.py"
      provides: "SessionUserResponse Pydantic model"
    - path: "api_server/src/api_server/main.py"
      provides: "Updated middleware stack + auth + users router includes"
  key_links:
    - from: "routes/auth.py google/github callback"
      to: "auth/oauth.py upsert_user + mint_session"
      via: "import + async call"
      pattern: "from .*auth.oauth import"
    - from: "auth/deps.py require_user"
      to: "models/errors.py make_error_envelope"
      via: "401 Stripe-envelope"
      pattern: "make_error_envelope.*UNAUTHORIZED"
    - from: "main.py add_middleware(SessionMiddleware)"
      to: "middleware/session.py"
      via: "add_middleware call in declaration-outermost-last order"
      pattern: "add_middleware.SessionMiddleware"
---

<objective>
Ship the full OAuth HTTP surface: 5 auth routes (`/v1/auth/{google,github}` + their callbacks + `POST /v1/auth/logout`), the `/v1/users/me` route, the `require_user(request) -> JSONResponse | UUID` inline helper per D-22c-AUTH-03 (NOT a FastAPI `Depends` — the codebase uses inline `_err()` pattern), a small `SessionUserResponse` Pydantic model, and the `main.py` patch that (a) wires Starlette's built-in SessionMiddleware + our `SessionMiddleware` into the stack per D-22c-AUTH-01 and (b) includes the new auth + users routers.

All 6 route handlers + the middleware wiring land in a single plan because the routes test the middleware (`/v1/users/me` + `/v1/auth/logout` rely on `request.state.user_id`), the middleware's throttle cache lives on `app.state.session_last_seen` initialized by main.py's app factory, and the StarletteSessionMiddleware signing key is read via `get_oauth(settings)`'s fail-loud resolver.

Integration tests (Task 4) land in the SAME plan (not split) because every test exercises the whole cold path from route -> middleware -> PG + respx-stubbed OAuth provider. Splitting the tests across plans would recompile the same fixtures twice. However, a `checkpoint:human-verify` task is inserted between Task 3 and Task 4 so execute-phase Pattern B segments the plan — Task 4 runs in a **fresh subagent context window** (the segment after a human-verify checkpoint is a new subagent per execute-plan.md parse_segments). Tasks 1+2+3 are pure source-file authorship + wiring (~30% context), Task 4 is a 7-file test suite (~25-35% context). Keeping them in one plan preserves co-location of fixtures with their consumers; the body-level checkpoint preserves context quality.

Purpose: Close the backend auth loop — a browser can now click "Sign in with Google", round-trip through Google, and come back with a valid `ap_session` cookie. The frontend rewrite in plans 22c-07 + 22c-08 is a separate concern.
Output: Backend auth wired end-to-end with ≥13 integration tests green (3 authorize + 5 callback + 1 logout + 2 /users/me + 2 config fail-loud).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22c-oauth-google/22c-SPEC.md
@.planning/phases/22c-oauth-google/22c-CONTEXT.md
@.planning/phases/22c-oauth-google/22c-RESEARCH.md
@.planning/phases/22c-oauth-google/22c-PATTERNS.md
@api_server/src/api_server/routes/agent_events.py
@api_server/src/api_server/routes/runs.py
@api_server/src/api_server/routes/agents.py
@api_server/src/api_server/main.py
@api_server/src/api_server/models/errors.py
@api_server/src/api_server/models/agents.py
@api_server/src/api_server/auth/oauth.py
@api_server/src/api_server/middleware/session.py

<interfaces>
<!-- From auth/oauth.py (plan 22c-03 shipped these) -->
```python
def get_oauth(settings) -> OAuth  # registers google + github; fails loud in prod
async def upsert_user(conn, *, provider, sub, email, display_name, avatar_url) -> UUID
async def mint_session(conn, *, user_id, request) -> str  # returns sessions.id as str
```

<!-- From models/errors.py (already present) -->
```python
class ErrorCode(str, Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    BAD_REQUEST = "BAD_REQUEST"
    ...
def make_error_envelope(code, message, *, param=None, category=None) -> dict
```

<!-- From routes/agent_events.py::_err (the canonical inline helper shape, L87-106) -->
```python
def _err(status, code, message, *, param=None, category=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```

<!-- From frontend/lib/api.ts SessionUser (response target shape) -->
```typescript
interface SessionUser {
  id: string;
  email?: string;
  display_name: string;
  avatar_url?: string;
  provider?: string;
}
```

<!-- Middleware stack current shape (main.py L208-211) — to be modified -->
```python
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

<!-- authlib OAuthError.error canonical string values (from authlib source) -->
```
"mismatching_state"  → state nonce mismatch (CSRF defense tripped)
"invalid_grant"      → expired/reused authorization code
"invalid_client"     → client_id/secret wrong
"access_denied"      → user denied consent (USUALLY arrives as ?error= query param, NOT an OAuthError)
<any other>          → route to /login?error=oauth_failed
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: auth/deps.py + models/users.py + routes/users.py (the /users/me surface)</name>
  <files>api_server/src/api_server/auth/deps.py, api_server/src/api_server/models/users.py, api_server/src/api_server/routes/users.py</files>
  <read_first>
    - api_server/src/api_server/routes/agent_events.py lines 87-106 (the canonical `_err` helper)
    - api_server/src/api_server/models/errors.py (ErrorCode + make_error_envelope)
    - api_server/src/api_server/models/agents.py (Pydantic response-model shape to mirror)
    - api_server/src/api_server/routes/agents.py (simple GET route shape — this is what routes/users.py mirrors)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-AUTH-03 (require_user return shape)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §auth/deps.py (lines 292-343) + §routes/users.py (lines 443-483)
  </read_first>
  <action>
**File 1: `api_server/src/api_server/auth/deps.py`**

```python
"""Request-level auth helpers — Phase 22c.

Exports ``require_user`` which returns either a ``JSONResponse`` (401 when
no session) or a ``UUID`` (the authenticated user). Matches the codebase
convention of inline ``_err()``-style early-return (see
``routes/agent_events.py::_err``) rather than FastAPI ``Depends`` + ``HTTPException``
which would double-wrap the Stripe-shape envelope (RESEARCH §Anti-Patterns).

Usage in a route:
    from ..auth.deps import require_user
    @router.get("/users/me")
    async def get_me(request: Request):
        result = require_user(request)
        if isinstance(result, JSONResponse):
            return result
        user_id: UUID = result
        ...
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope


def require_user(request: Request) -> JSONResponse | UUID:
    """Resolve request.state.user_id or return a 401 JSONResponse."""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "Authentication required",
                param="ap_session",
            ),
        )
    if isinstance(user_id, UUID):
        return user_id
    # SessionMiddleware should always set UUID or None; defensive coerce.
    try:
        return UUID(str(user_id))
    except (ValueError, AttributeError):
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "Authentication required",
                param="ap_session",
            ),
        )
```

**File 2: `api_server/src/api_server/models/users.py`**

Mirror the shape of `models/agents.py`. One Pydantic response model:

```python
"""Pydantic response models for user-scoped routes (Phase 22c)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionUserResponse(BaseModel):
    """Shape returned by GET /v1/users/me. Matches frontend/lib/api.ts::SessionUser."""

    id: UUID
    email: str | None = None
    display_name: str
    avatar_url: str | None = None
    provider: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
```

**File 3: `api_server/src/api_server/routes/users.py`**

```python
"""User-scoped routes (Phase 22c)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth.deps import require_user
from ..models.errors import ErrorCode, make_error_envelope
from ..models.users import SessionUserResponse

router = APIRouter()


@router.get("/users/me", response_model=SessionUserResponse)
async def get_me(request: Request):
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id = result

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, display_name, avatar_url, provider, created_at "
            "FROM users WHERE id = $1",
            user_id,
        )
    if row is None:
        # Session pointed at a deleted user — rare, treat as 401.
        return JSONResponse(
            status_code=401,
            content=make_error_envelope(
                ErrorCode.UNAUTHORIZED,
                "User not found",
                param="ap_session",
            ),
        )
    return SessionUserResponse(**dict(row))
```
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.auth.deps import require_user; from api_server.models.users import SessionUserResponse; from api_server.routes.users import router; assert router.routes, 'no routes registered'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/src/api_server/auth/deps.py` exports `require_user(request) -> JSONResponse | UUID`
    - `api_server/src/api_server/models/users.py` exports `SessionUserResponse` with fields `id, email, display_name, avatar_url, provider, created_at`
    - `api_server/src/api_server/routes/users.py` registers a `GET /users/me` route under its APIRouter (no prefix; main.py adds `/v1`)
    - All three files import cleanly (no circular imports)
  </acceptance_criteria>
  <done>users-scope surface ships: require_user helper, SessionUserResponse model, /users/me route.</done>
</task>

<task type="auto">
  <name>Task 2: routes/auth.py — 5 OAuth endpoints (EXACT OAuthError match)</name>
  <files>api_server/src/api_server/routes/auth.py</files>
  <read_first>
    - api_server/src/api_server/routes/runs.py lines 60-92 (router + _err + route decl pattern)
    - api_server/src/api_server/auth/oauth.py (get_oauth + upsert_user + mint_session)
    - api_server/src/api_server/auth/deps.py (require_user)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pattern 2 (Google OIDC callback) + §Pattern 3 (GitHub non-OIDC)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-OAUTH-01 to 05 + §D-22c-FE-03 (error-redirect codes)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §routes/auth.py (lines 380-441)
  </read_first>
  <action>
Create `api_server/src/api_server/routes/auth.py`. Hand-merge RESEARCH Patterns 2 + 3 with the codebase's `_err()` + APIRouter style.

Key invariants:
- 5 endpoints: `GET /auth/google`, `GET /auth/google/callback`, `GET /auth/github`, `GET /auth/github/callback`, `POST /auth/logout`
- All paths relative to the router; main.py mounts with `prefix="/v1"`
- Cookie setter helper: `_set_session_cookie(resp, session_id, settings)` — SameSite=Lax, HttpOnly, Path=/, Max-Age=2592000, Secure only if `settings.env == "prod"` (D-22c-OAUTH-04)
- Cookie clearer on logout: `Set-Cookie: ap_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax` (+ Secure in prod)
- OAuthError handling: **use EXACT match on `e.error == "mismatching_state"`** — NOT a substring check. authlib's error value is the literal string `"mismatching_state"`. Substring matching risks misclassifying other errors like `"mismatching_request"` (hypothetical) or a state-unrelated error whose message happens to contain "state". Catch-all `OAuthError` AFTER the exact match routes to `oauth_failed`.
  - `access_denied` when the callback's query_params contain `error=access_denied` (Google denies consent — arrives as query param, not OAuthError)
  - authlib OAuthError with `e.error == "mismatching_state"` -> `state_mismatch`
  - Any other OAuthError -> `oauth_failed`
- GitHub flow: after `authorize_access_token`, call `await oauth.github.get("user", token=token)`. If the response's `email` is null, call `/user/emails`, pick the first `primary && verified` entry. If still null, redirect to `/login?error=oauth_failed`.

Body (copy verbatim, fill in any import you find missing):

```python
"""OAuth2 authorize + callback + logout routes (Phase 22c).

Surface:
  GET  /v1/auth/google            -> 302 to Google authorize endpoint
  GET  /v1/auth/google/callback   -> exchange code, upsert user, mint session, 302 /dashboard
  GET  /v1/auth/github            -> 302 to GitHub authorize endpoint
  GET  /v1/auth/github/callback   -> exchange code, fetch /user (+/user/emails fallback), mint session
  POST /v1/auth/logout            -> delete sessions row, clear cookie, 204

The state nonce lives in Starlette's SessionMiddleware (cookie ``ap_oauth_state``;
signed via ``AP_OAUTH_STATE_SECRET``). Our ``ap_session`` cookie is a separate
mechanism — opaque UUID pointing at a ``sessions`` row.
"""
from __future__ import annotations

import logging
from uuid import UUID

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth.deps import require_user
from ..auth.oauth import get_oauth, mint_session, upsert_user
from ..models.errors import ErrorCode, make_error_envelope

router = APIRouter()
_log = logging.getLogger("api_server.auth")

_SESSION_COOKIE = "ap_session"
_SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
_DASHBOARD_REDIRECT = "/dashboard"
_LOGIN_REDIRECT = "/login"


def _err(status, code, message, *, param=None, category=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )


def _set_session_cookie(resp: RedirectResponse | JSONResponse, session_id: str, settings) -> None:
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value=session_id,
        max_age=_SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )


def _clear_session_cookie(resp, settings) -> None:
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )


def _login_redirect_with_error(code: str) -> RedirectResponse:
    return RedirectResponse(f"{_LOGIN_REDIRECT}?error={code}", status_code=302)


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------

@router.get("/auth/google")
async def google_login(request: Request):
    settings = request.app.state.settings
    oauth = get_oauth(settings)
    return await oauth.google.authorize_redirect(
        request, settings.oauth_google_redirect_uri
    )


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    settings = request.app.state.settings
    oauth = get_oauth(settings)

    # Google redirects back with ?error=access_denied when the user cancels consent.
    err_param = request.query_params.get("error")
    if err_param == "access_denied":
        return _login_redirect_with_error("access_denied")

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        # EXACT match on authlib's canonical CSRF-state error value.
        # Substring matching is fragile (other errors may contain "state"
        # in their message without being CSRF violations).
        if e.error == "mismatching_state":
            return _login_redirect_with_error("state_mismatch")
        _log.warning("google oauth_failed: %s", e.error)
        return _login_redirect_with_error("oauth_failed")

    userinfo = token.get("userinfo")
    if userinfo is None:
        try:
            userinfo = await oauth.google.userinfo(token=token)
        except Exception:
            _log.exception("google userinfo fetch failed")
            return _login_redirect_with_error("oauth_failed")

    if not userinfo or not userinfo.get("sub"):
        return _login_redirect_with_error("oauth_failed")

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

    resp = RedirectResponse(_DASHBOARD_REDIRECT, status_code=302)
    _set_session_cookie(resp, session_id, settings)
    return resp


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------

@router.get("/auth/github")
async def github_login(request: Request):
    settings = request.app.state.settings
    oauth = get_oauth(settings)
    return await oauth.github.authorize_redirect(
        request, settings.oauth_github_redirect_uri
    )


@router.get("/auth/github/callback")
async def github_callback(request: Request):
    settings = request.app.state.settings
    oauth = get_oauth(settings)

    err_param = request.query_params.get("error")
    if err_param == "access_denied":
        return _login_redirect_with_error("access_denied")

    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError as e:
        # EXACT match — see google_callback for rationale.
        if e.error == "mismatching_state":
            return _login_redirect_with_error("state_mismatch")
        _log.warning("github oauth_failed: %s", e.error)
        return _login_redirect_with_error("oauth_failed")

    try:
        user_resp = await oauth.github.get("user", token=token)
        profile = user_resp.json()
    except Exception:
        _log.exception("github /user fetch failed")
        return _login_redirect_with_error("oauth_failed")

    sub = profile.get("id")
    if sub is None:
        return _login_redirect_with_error("oauth_failed")

    email = profile.get("email")
    if not email:
        try:
            emails_resp = await oauth.github.get("user/emails", token=token)
            emails = emails_resp.json()
            email = next(
                (e["email"] for e in emails
                 if e.get("primary") and e.get("verified") and e.get("email")),
                None,
            )
        except Exception:
            _log.exception("github /user/emails fetch failed")
            email = None

    if not email:
        return _login_redirect_with_error("oauth_failed")

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

    resp = RedirectResponse(_DASHBOARD_REDIRECT, status_code=302)
    _set_session_cookie(resp, session_id, settings)
    return resp


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/auth/logout")
async def logout(request: Request):
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

    resp = JSONResponse(content=None, status_code=204)
    _clear_session_cookie(resp, settings)
    return resp


def _read_session_cookie_uuid(request: Request) -> UUID | None:
    raw = request.cookies.get(_SESSION_COOKIE)
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None
```

Note: `request.app.state.settings` must be set in main.py's app factory if it isn't already. Check main.py's existing code for where `settings` is constructed and add `app.state.settings = settings` if absent (this IS a safe addition for task 3).
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.routes.auth import router; paths = {r.path for r in router.routes}; expected = {'/auth/google', '/auth/google/callback', '/auth/github', '/auth/github/callback', '/auth/logout'}; assert expected.issubset(paths), f'missing: {expected - paths}'; print('OK')" && grep -q 'e.error == "mismatching_state"' api_server/src/api_server/routes/auth.py</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/src/api_server/routes/auth.py` exists
    - Router exposes all 5 routes at the expected paths
    - `import api_server.routes.auth` succeeds
    - `grep -c 'e.error == "mismatching_state"' api_server/src/api_server/routes/auth.py` returns 2 (one in google_callback, one in github_callback)
    - `grep -c 'oauth_failed' api_server/src/api_server/routes/auth.py` returns ≥4 (fallback paths in both callbacks)
    - All error paths use `_login_redirect_with_error(code)` -> 302 redirect to `/login?error=<code>`
    - Logout route returns 204 with cleared cookie
  </acceptance_criteria>
  <done>5 OAuth endpoints + 1 logout ship with EXACT authlib error matching. Ready for main.py to include the router + StarletteSessionMiddleware + our SessionMiddleware.</done>
</task>

<task type="auto">
  <name>Task 3: main.py — wire middleware stack + routers + app.state.settings</name>
  <files>api_server/src/api_server/main.py</files>
  <read_first>
    - api_server/src/api_server/main.py (whole file — existing middleware order lines 208-211 + router includes L213+)
    - api_server/src/api_server/auth/oauth.py (for `get_oauth` + understanding prod fail-loud behavior)
    - api_server/src/api_server/middleware/session.py (plan 22c-04's SessionMiddleware class)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-AUTH-01 (middleware order)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §"Wire Starlette SessionMiddleware" (lines 748-769)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §main.py (lines 504-555)
  </read_first>
  <action>
Modify `api_server/src/api_server/main.py` in a minimally-invasive way. Preserve every existing line except the middleware block + router include block.

**Change 1: imports at the top of the file.** Add (after existing middleware imports):

```python
from starlette.middleware.sessions import SessionMiddleware as StarletteSessionMiddleware
from .middleware.session import SessionMiddleware as ApSessionMiddleware
from .auth.oauth import get_oauth
from .routes import auth as auth_route
from .routes import users as users_route
```

**Change 2: expose settings on app.state.**  Inside the app factory (wherever `settings = Settings()` is currently constructed — grep for `Settings()` in main.py), immediately AFTER that line add:

```python
app.state.settings = settings
```

If a `create_app()` function factors settings into a different variable name, use that name. Do NOT duplicate the Settings() construction. If `app.state.settings` already exists (check with grep first), skip this change.

**Change 3: Call `get_oauth(settings)` eagerly in the app factory so prod fail-loud fires at boot.** Add, after `app.state.settings = settings` and BEFORE any `add_middleware` call:

```python
# Phase 22c — eagerly construct the OAuth registry so prod boots fail loud
# when AP_OAUTH_* env vars are missing. Dev uses placeholders.
get_oauth(settings)
```

**Change 4: Middleware stack.** REPLACE the existing `add_middleware` block (currently lines 208-211):
```python
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

WITH this new block (note: Starlette's `add_middleware` is OUTERMOST-LAST, meaning the LAST-added middleware runs FIRST on incoming requests):

```python
# Middleware stack declaration order = OUTERMOST LAST.
# Effective request-in order: CorrelationId -> AccessLog -> StarletteSession
#   -> OurSession -> RateLimit -> Idempotency -> route.
# (Plan 22c-04 ships OurSession; plan 22c-03 ships AP_OAUTH_STATE_SECRET config.)
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ApSessionMiddleware)  # ap_session cookie -> request.state.user_id
app.add_middleware(
    StarletteSessionMiddleware,          # authlib CSRF state store (ap_oauth_state cookie)
    secret_key=(
        settings.oauth_state_secret
        or "dev-oauth-state-key-not-for-prod-0000000000000000"
    ),
    session_cookie="ap_oauth_state",
    max_age=600,
    same_site="lax",
    https_only=(settings.env == "prod"),
    path="/",
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

**Change 5: Router includes.** In the existing `app.include_router(...)` block (L213+), APPEND:

```python
app.include_router(auth_route.router, prefix="/v1", tags=["auth"])
app.include_router(users_route.router, prefix="/v1", tags=["users"])
```

DO NOT reorder or remove any existing router include. DO NOT duplicate prefix registrations.

**Change 6: `app.state.session_last_seen` init.** Somewhere near the top of the app factory (before `add_middleware(ApSessionMiddleware)`), add:

```python
app.state.session_last_seen = {}
```

If the lifespan function has an init hook, that's an acceptable alternative location — either works.
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.main import app; mw_names = [m.cls.__name__ for m in app.user_middleware]; print('middleware:', mw_names); assert 'ApSessionMiddleware' in mw_names; assert 'StarletteSessionMiddleware' in mw_names or 'SessionMiddleware' in mw_names; paths = {r.path for r in app.routes}; assert '/v1/auth/google' in paths and '/v1/users/me' in paths, f'missing routes; have: {paths}'; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `main.py` imports `SessionMiddleware as ApSessionMiddleware` from `middleware/session.py` AND `SessionMiddleware as StarletteSessionMiddleware` from `starlette.middleware.sessions`
    - `main.py` imports `get_oauth` + `auth_route` + `users_route`
    - `app.state.settings` is set to the `Settings()` instance
    - `get_oauth(settings)` is called eagerly inside the app factory (pre-middleware)
    - New middleware block has BOTH StarletteSessionMiddleware and ApSessionMiddleware at the CORRECT positions
    - `app.include_router(auth_route.router, prefix="/v1", tags=["auth"])` registered
    - `app.include_router(users_route.router, prefix="/v1", tags=["users"])` registered
    - All existing middleware + router includes preserved
    - `from api_server.main import app; print([r.path for r in app.routes])` includes `/v1/auth/google`, `/v1/auth/github`, `/v1/auth/logout`, `/v1/users/me`
  </acceptance_criteria>
  <done>main.py wires the full stack. App boots in dev. Prod without envs fails loud on `get_oauth(settings)`. The next element is a `checkpoint:human-verify` — execute-phase Pattern B will resume Task 4 in a fresh subagent context.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>Tasks 1-3 complete: auth/deps.py, models/users.py, routes/users.py, routes/auth.py, and main.py wiring. The backend auth surface compiles and the app factory imports. Task 4 (the 7-file integration test suite) is intentionally gated behind this checkpoint so execute-phase Pattern B spawns a fresh subagent context for it — Tasks 1-3 already consume ~30% context; running Task 4's 13 tests + respx fixtures in the same context risks saturation.</what-built>
  <how-to-verify>
    Before typing "approved":
    1. Confirm Tasks 1-3 are committed on the current branch: `git log --oneline -3` should show the most recent 1-3 commits for this plan (or a single squashed commit if the executor committed at end of segment).
    2. Confirm the imports compile: `cd api_server && uv run python -c "from api_server.routes import auth, users; from api_server.auth.deps import require_user; from api_server.main import app; print('OK')"` exits 0.
    3. Confirm `api_server/tests/` has the expected parent directories (`tests/auth/`, or `tests/routes/` / `tests/config/` may still be empty — Task 4 creates them).
    4. **Run `/clear` before typing "approved"** so the follow-on subagent starts with a clean context window when it takes on Task 4.
  </how-to-verify>
  <acceptance_criteria>
    - Tasks 1-3 committed on the current branch
    - `cd api_server && uv run python -c "from api_server.routes import auth"` exits 0
    - `/clear` has been run (the next subagent starts in fresh context)
  </acceptance_criteria>
  <resume-signal>Type "approved" to continue to Task 4 in a fresh context, or describe any import/compile issue.</resume-signal>
</task>

<task type="auto">
  <name>Task 4: Integration tests — auth routes + /users/me + logout + fail-loud (FRESH CONTEXT)</name>
  <files>api_server/tests/auth/test_google_authorize.py, api_server/tests/auth/test_google_callback.py, api_server/tests/auth/test_github_authorize.py, api_server/tests/auth/test_github_callback.py, api_server/tests/auth/test_logout.py, api_server/tests/routes/__init__.py, api_server/tests/routes/test_users_me.py, api_server/tests/config/__init__.py, api_server/tests/config/test_oauth_state_secret_fail_loud.py, api_server/tests/conftest.py</files>
  <read_first>
    - api_server/tests/test_rate_limit.py (full fixture harness for integration tests)
    - api_server/tests/test_idempotency.py (ASGI + cookie manipulation patterns)
    - api_server/tests/test_log_redact.py (caplog usage)
    - api_server/tests/conftest.py (existing async_client fixture + truncate list at L120-124)
    - api_server/tests/spikes/test_respx_authlib.py (plan 22c-01 shipped this; respx pattern works)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Code Examples (lines 771-799 — respx stub shape)
    - .planning/phases/22c-oauth-google/22c-VALIDATION.md (authoritative test-to-req map; reuse the pytest commands listed there as test names)
  </read_first>
  <action>
Create the 7 test files listed below. Each test uses `@pytest.mark.api_integration` + `@pytest.mark.asyncio` and runs against the real FastAPI app + real PG + respx-stubbed OAuth providers.

---

### Shared fixtures (APPEND to `api_server/tests/conftest.py`)

DO NOT alter existing fixtures; APPEND the following at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Phase 22c — OAuth test fixtures
# ---------------------------------------------------------------------------

import httpx as _httpx_for_22c  # aliased to avoid collision with existing imports
import respx as _respx_for_22c
from datetime import datetime, timedelta, timezone
from uuid import uuid4


async def _insert_test_user(conn, *, provider: str, sub: str, email: str, display_name: str):
    user_id = uuid4()
    await conn.execute(
        "INSERT INTO users (id, provider, sub, email, display_name) "
        "VALUES ($1, $2, $3, $4, $5)",
        user_id, provider, sub, email, display_name,
    )
    return user_id


async def _mint_test_session(conn, user_id):
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=30)
    session_id = await conn.fetchval(
        "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
        "VALUES ($1, $2, $3, $2) RETURNING id",
        user_id, now, exp,
    )
    return session_id


@pytest_asyncio.fixture
async def authenticated_cookie(db_pool):
    """Seed a user + session; yield {"Cookie": "ap_session=<uuid>"}.

    Consumed by logout, /users/me, and cross-user-isolation tests.
    """
    async with db_pool.acquire() as conn:
        user_id = await _insert_test_user(
            conn,
            provider="google",
            sub=f"test-sub-{uuid4().hex[:8]}",
            email="alice@example.com",
            display_name="Alice",
        )
        session_id = await _mint_test_session(conn, user_id)
    yield {"Cookie": f"ap_session={session_id}", "_user_id": str(user_id), "_session_id": str(session_id)}


@pytest_asyncio.fixture
async def second_authenticated_cookie(db_pool):
    """Second distinct user for cross-user isolation tests (plan 22c-09)."""
    async with db_pool.acquire() as conn:
        user_id = await _insert_test_user(
            conn,
            provider="google",
            sub=f"test-sub-{uuid4().hex[:8]}",
            email="bob@example.com",
            display_name="Bob",
        )
        session_id = await _mint_test_session(conn, user_id)
    yield {"Cookie": f"ap_session={session_id}", "_user_id": str(user_id), "_session_id": str(session_id)}


@pytest.fixture
def respx_oauth_providers():
    """Context manager that stubs Google + GitHub OAuth endpoints.

    Usage:
        with respx_oauth_providers() as stubs:
            stubs["google_token"].mock(return_value=httpx.Response(200, json={...}))
            ...
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with _respx_for_22c.mock(assert_all_called=False) as m:
            stubs = {
                "google_token": m.post("https://oauth2.googleapis.com/token"),
                "google_userinfo": m.get("https://openidconnect.googleapis.com/v1/userinfo"),
                "google_jwks": m.get("https://www.googleapis.com/oauth2/v3/certs"),
                "google_discovery": m.get("https://accounts.google.com/.well-known/openid-configuration"),
                "github_token": m.post("https://github.com/login/oauth/access_token"),
                "github_user": m.get("https://api.github.com/user"),
                "github_user_emails": m.get("https://api.github.com/user/emails"),
            }
            yield stubs
    return _ctx
```

Also create empty package markers (if they do not already exist from plan 22c-01):
```bash
: > api_server/tests/routes/__init__.py
: > api_server/tests/config/__init__.py
```

---

### File 1: `api_server/tests/auth/test_google_authorize.py` — R1

```python
"""R1: GET /v1/auth/google returns 302 to Google authorize URL with state cookie."""
import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_302_with_state(async_client):
    r = await async_client.get("/v1/auth/google", follow_redirects=False)
    assert r.status_code == 302, r.text
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/"), loc
    assert "client_id=" in loc
    assert "state=" in loc
    assert "redirect_uri=" in loc
    # Starlette SessionMiddleware sets the ap_oauth_state cookie on first session write
    set_cookie = r.headers.get("set-cookie", "")
    assert "ap_oauth_state=" in set_cookie, set_cookie
```

---

### File 2: `api_server/tests/auth/test_google_callback.py` — R2 + D-22c-FE-03

Test function signatures + first 3 assertion lines shown. Full body to be written by executor mirroring this skeleton:

```python
"""R2 + D-22c-FE-03: Google callback — state mismatch, access_denied, happy path, fallback oauth_failed."""
from __future__ import annotations

import httpx
import pytest
import respx
from authlib.integrations.starlette_client import OAuthError


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_state_mismatch_redirects_to_login_error(async_client, monkeypatch):
    # Patch oauth.google.authorize_access_token to raise OAuthError("mismatching_state")
    from api_server.routes import auth as auth_route
    async def raise_state_err(_request):
        raise OAuthError(error="mismatching_state", description="State mismatch")
    # ... monkeypatch the oauth registry's google.authorize_access_token ...
    r = await async_client.get("/v1/auth/google/callback?state=bad&code=x", follow_redirects=False)
    assert r.status_code == 302
    assert "/login?error=state_mismatch" in r.headers["location"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_access_denied_redirects(async_client):
    r = await async_client.get("/v1/auth/google/callback?error=access_denied", follow_redirects=False)
    assert r.status_code == 302
    assert "/login?error=access_denied" in r.headers["location"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_non_state_error(async_client, monkeypatch):
    """WARNING-3 fix: non-state OAuthError must route to oauth_failed, NOT state_mismatch."""
    from authlib.integrations.starlette_client import OAuthError
    async def raise_other_err(_request):
        raise OAuthError(error="invalid_grant", description="Code expired")
    # ... monkeypatch ...
    r = await async_client.get("/v1/auth/google/callback?state=x&code=y", follow_redirects=False)
    assert r.status_code == 302
    assert "/login?error=oauth_failed" in r.headers["location"]
    assert "state_mismatch" not in r.headers["location"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_full_flow_respx(async_client, respx_oauth_providers, db_pool):
    """Happy path: respx stubs Google /token + /userinfo; assert user + session inserted + ap_session cookie."""
    with respx_oauth_providers() as stubs:
        stubs["google_token"].mock(return_value=httpx.Response(200, json={
            "access_token": "ya29.fake",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid email profile",
        }))
        stubs["google_userinfo"].mock(return_value=httpx.Response(200, json={
            "sub": "google-test-sub-123",
            "email": "test@example.com",
            "name": "Test User",
            "picture": "https://example.com/avatar.png",
        }))
        # ... drive /v1/auth/google first to seed the state cookie, then callback ...
        # ... assert response 302 /dashboard + Set-Cookie ap_session ...
        # ... assert users row with sub='google-test-sub-123' exists ...
        # ... assert sessions row for the new user exists ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_no_email(async_client, respx_oauth_providers):
    """userinfo returns no email -> upsert still succeeds; display_name falls back to 'user' or sub."""
    # Same shape as test_full_flow_respx but stubs userinfo with email=None
```

---

### File 3: `api_server/tests/auth/test_github_authorize.py` — R1

Same shape as `test_google_authorize.py`:

```python
import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_302_github_authorize(async_client):
    r = await async_client.get("/v1/auth/github", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://github.com/login/oauth/authorize"), loc
    assert "client_id=" in loc
    assert "state=" in loc
```

---

### File 4: `api_server/tests/auth/test_github_callback.py` — R2 + email fallback

```python
"""R2: GitHub callback — state mismatch, happy path w/ public email, /user/emails fallback, no-email path."""
from __future__ import annotations

import httpx
import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_state_mismatch(async_client, monkeypatch):
    """Same shape as google test_state_mismatch_redirects_to_login_error."""
    # ... see google_callback test_state_mismatch for template ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_non_state_error(async_client, monkeypatch):
    """WARNING-3 fix: non-state OAuthError must route to oauth_failed."""
    # ... mirror google test_oauth_failed_on_non_state_error ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_full_flow_with_public_email(async_client, respx_oauth_providers, db_pool):
    with respx_oauth_providers() as stubs:
        stubs["github_token"].mock(return_value=httpx.Response(200, json={
            "access_token": "gho_fake", "token_type": "bearer", "scope": "user:email",
        }))
        stubs["github_user"].mock(return_value=httpx.Response(200, json={
            "id": 42, "login": "octocat", "name": "The Octocat",
            "email": "octo@github.com", "avatar_url": "https://avatars.githubusercontent.com/u/42",
        }))
        # ... drive callback; assert 302 /dashboard + users.email='octo@github.com' ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_full_flow_emails_fallback(async_client, respx_oauth_providers, db_pool):
    with respx_oauth_providers() as stubs:
        stubs["github_token"].mock(return_value=httpx.Response(200, json={"access_token": "x", "token_type": "bearer"}))
        stubs["github_user"].mock(return_value=httpx.Response(200, json={
            "id": 42, "login": "octocat", "name": "The Octocat", "email": None,
        }))
        stubs["github_user_emails"].mock(return_value=httpx.Response(200, json=[
            {"email": "private@users.noreply.github.com", "primary": True, "verified": True},
            {"email": "other@github.com", "primary": False, "verified": True},
        ]))
        # ... drive callback; assert users.email='private@users.noreply.github.com' ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_oauth_failed_on_no_verified_email(async_client, respx_oauth_providers):
    """email null + /user/emails returns no primary+verified -> 302 /login?error=oauth_failed."""
    # ... similar fixture setup; assert Location has 'oauth_failed' ...
```

---

### File 5: `api_server/tests/auth/test_logout.py` — R5

```python
"""R5: POST /v1/auth/logout invalidates session + clears cookie."""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_204_and_invalidates(async_client, authenticated_cookie):
    # Confirm session is live via /users/me
    r1 = await async_client.get("/v1/users/me", headers={"Cookie": authenticated_cookie["Cookie"]})
    assert r1.status_code == 200

    # Logout
    r2 = await async_client.post("/v1/auth/logout", headers={"Cookie": authenticated_cookie["Cookie"]})
    assert r2.status_code == 204
    set_cookie = r2.headers.get("set-cookie", "")
    assert "ap_session=" in set_cookie
    assert "max-age=0" in set_cookie.lower() or "Max-Age=0" in set_cookie

    # Same cookie -> now 401
    r3 = await async_client.get("/v1/users/me", headers={"Cookie": authenticated_cookie["Cookie"]})
    assert r3.status_code == 401


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_401_no_cookie(async_client):
    r = await async_client.post("/v1/auth/logout")
    assert r.status_code == 401
```

---

### File 6: `api_server/tests/routes/test_users_me.py` — R4

```python
"""R4: GET /v1/users/me."""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_200_with_session(async_client, authenticated_cookie):
    r = await async_client.get("/v1/users/me", headers={"Cookie": authenticated_cookie["Cookie"]})
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == authenticated_cookie["_user_id"]
    assert "display_name" in body
    assert "email" in body
    assert "provider" in body
    assert "created_at" in body


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_401_no_session(async_client):
    r = await async_client.get("/v1/users/me")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] in ("UNAUTHORIZED", "unauthorized")


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_401_expired_session(async_client, db_pool):
    """Session with expires_at in the past -> 401 (SessionMiddleware rejects)."""
    # ... seed a session row with expires_at = now - 1 day; request /users/me with its cookie; assert 401 ...


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_401_revoked_session(async_client, db_pool):
    """Session with revoked_at set -> 401."""
    # ... seed + revoke; assert 401 ...
```

---

### File 7: `api_server/tests/config/test_oauth_state_secret_fail_loud.py` — AMD-07

```python
"""AMD-07: prod without AP_OAUTH_STATE_SECRET must RuntimeError on boot."""
from __future__ import annotations

import os
import pytest


def test_prod_fails_boot_without_state_secret(monkeypatch):
    monkeypatch.setenv("AP_ENV", "prod")
    for k in list(os.environ):
        if k.startswith("AP_OAUTH_"):
            monkeypatch.delenv(k)
    from api_server.config import Settings
    from api_server.auth.oauth import get_oauth
    with pytest.raises(RuntimeError, match=r"OAUTH_STATE_SECRET"):
        get_oauth(Settings())


def test_dev_boots_without_state_secret(monkeypatch):
    monkeypatch.setenv("AP_ENV", "dev")
    for k in list(os.environ):
        if k.startswith("AP_OAUTH_"):
            monkeypatch.delenv(k)
    from api_server.config import Settings
    from api_server.auth.oauth import get_oauth
    registry = get_oauth(Settings())
    # google + github both registered even without env (dev placeholders)
    assert hasattr(registry, "google")
    assert hasattr(registry, "github")
```

---

### Commit

```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/src/api_server/auth/deps.py api_server/src/api_server/models/users.py api_server/src/api_server/routes/auth.py api_server/src/api_server/routes/users.py api_server/src/api_server/main.py api_server/tests/auth/ api_server/tests/routes/ api_server/tests/config/ api_server/tests/conftest.py
git commit -m "feat(22c-05): OAuth routes + /v1/users/me + logout + middleware wiring"
```
  </action>
  <verify>
<automated>cd api_server && pytest tests/auth/ tests/routes/test_users_me.py tests/config/test_oauth_state_secret_fail_loud.py -x -v -m api_integration</automated>
  </verify>
  <acceptance_criteria>
    - ALL 7 test files exist and contain the cases listed above
    - `pytest tests/auth/ tests/routes/test_users_me.py tests/config/test_oauth_state_secret_fail_loud.py -m api_integration` passes (≥13 test functions green, including the NEW `test_oauth_failed_on_non_state_error` for both Google and GitHub)
    - `test_full_flow_respx` (Google) actually round-trips through the full authorize -> callback path with respx stubs, confirms users row inserted + sessions row inserted + ap_session cookie set
    - `test_full_flow_emails_fallback` (GitHub) confirms /user/emails fallback works
    - Two NEW `test_oauth_failed_on_non_state_error` tests (one per provider) confirm non-`mismatching_state` OAuthError routes to `oauth_failed` (WARNING-3/5 fix verification)
    - `test_prod_fails_boot_without_state_secret` passes (RuntimeError contains `OAUTH_STATE_SECRET`)
    - `authenticated_cookie` + `second_authenticated_cookie` + `respx_oauth_providers` fixtures live in conftest.py (reusable by plan 22c-09)
    - Commit on main: `feat(22c-05): OAuth routes + /v1/users/me + logout + middleware wiring`
  </acceptance_criteria>
  <done>Backend auth fully integrated and covered. Frontend plans (22c-07 + 22c-08) can now wire buttons to these routes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser -> /v1/auth/google (authorize) | Client can hit this freely; middleware rate-limits on IP. authlib generates state nonce. |
| Google -> /v1/auth/google/callback | Callback query string comes from Google after user consent. State cookie verifies it's our round-trip. |
| Callback -> upsert_user / mint_session | Inserts happen inside a PG connection acquired per request. CASCADE FKs mean a later user DELETE wipes sessions. |
| require_user inline helper | Any protected route reads request.state.user_id; require_user early-returns 401 on None with Stripe envelope. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-13 | Spoofing | Forged callback with made-up state | mitigate | authlib validates state via Starlette session cookie signed by AP_OAUTH_STATE_SECRET (prod fail-loud). Mismatch -> OAuthError with error=="mismatching_state" -> /login?error=state_mismatch (EXACT match, not substring) |
| T-22c-14 | Tampering | Replay of expired authorize code | mitigate | Google + GitHub enforce one-time-use on authorization codes at the provider. Second exchange returns `invalid_grant`; authlib raises OAuthError; callback redirects to /login?error=oauth_failed (verified by test_oauth_failed_on_non_state_error) |
| T-22c-15 | Information disclosure | id_token or access_token in logs | mitigate | log_redact allowlist already blocks all non-whitelisted headers + request bodies; authlib tokens never touch a log line. Verified in test_log_redact_cookies.py (plan 22c-04). |
| T-22c-16 | Elevation of privilege | OAuth callback inserts users for any provider/sub combo | mitigate | upsert_user is keyed on `UNIQUE (provider, sub)`; provider is hardcoded per-route (cannot be influenced by a browser). An attacker who forges a callback with a made-up sub cannot collide with an existing user because they can't forge the Google/GitHub-signed token round-trip (state cookie is signed too). |
| T-22c-17 | DoS | Logout after logout | accept | Second logout with same cookie: no sessions row, DELETE is a no-op, response still 204. No server amplification. |
| T-22c-18 | Information disclosure | /v1/users/me leaks PII to the authenticated user | accept | User sees only their own row (query is `WHERE id = <session.user_id>`). No cross-user leak possible at this route. |
</threat_model>

<verification>
```bash
cd api_server && pytest tests/auth/ tests/routes/test_users_me.py tests/config/test_oauth_state_secret_fail_loud.py -m api_integration
```
All tests must pass. The app factory must import cleanly in dev and fail loud in prod without AP_OAUTH_STATE_SECRET.
</verification>

<success_criteria>
- `auth/deps.py`, `models/users.py`, `routes/auth.py`, `routes/users.py` all authored
- `main.py` middleware stack + router includes updated per D-22c-AUTH-01
- routes/auth.py uses EXACT match `e.error == "mismatching_state"` (no substring match)
- ≥13 integration tests green across 7 test files (including 2 new `test_oauth_failed_on_non_state_error`)
- Commit on main: `feat(22c-05): OAuth routes + /v1/users/me + logout + middleware wiring`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-05-SUMMARY.md` with:
- List of routes + their return shapes
- Test file -> REQ ID mapping (confirm every R1/R2/R4/R5 test row in 22c-VALIDATION.md is satisfied)
- Middleware stack final order (copy from main.py diff)
- Any amendments to require_user's interface that the next plans should know about
</output>
</output>
