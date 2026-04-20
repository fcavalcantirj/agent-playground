---
phase: 22c-oauth-google
plan: 05
subsystem: auth
tags: [oauth2, authlib, fastapi, session-cookie, respx, integration-tests]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: sessions table + users.sub/avatar_url/last_login_at (22c-02, alembic 005)
  - phase: 22c-oauth-google
    provides: get_oauth + upsert_user + mint_session helpers + OAuth config (22c-03)
  - phase: 22c-oauth-google
    provides: SessionMiddleware resolving request.state.user_id (22c-04)
provides:
  - "5 OAuth HTTP endpoints: GET /v1/auth/{google,github}[/callback] + POST /v1/auth/logout"
  - "GET /v1/users/me returning SessionUserResponse"
  - "require_user(request) -> JSONResponse | UUID inline auth helper"
  - "Starlette SessionMiddleware (CSRF state) + ApSessionMiddleware wired into main.py"
  - "authenticated_cookie + second_authenticated_cookie + respx_oauth_providers fixtures in tests/conftest.py"
  - "20 integration tests: 13+ plan-mandated, 7 extras covering WARNING-3 regression trap"
affects: [22c-06, 22c-07, 22c-08, 22c-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline require_user early-return (returns JSONResponse | UUID) — mirrors routes/agent_events.py::_err; avoids FastAPI Depends double-wrap"
    - "EXACT-match on authlib OAuthError.error == 'mismatching_state' (not substring) — WARNING-3 regression trap"
    - "respx_oauth_providers context-manager factory — pre-stubs Google discovery + JWKS; exposes token / userinfo / user / user_emails routes for per-test mocking"
    - "Monkeypatch authorize_access_token to force canned token dicts — avoids the state-cookie + discovery + JWKS dance in happy-path tests"
    - "Mutate app.state.settings in-place for per-test env overrides when the async_client fixture is already built"
    - "Starlette's built-in SessionMiddleware stores authlib CSRF nonce; our ApSessionMiddleware handles ap_session lookup — both wired in main.py (outermost last declaration order)"
    - "204 No Content returned via Response(status_code=204) NOT JSONResponse(None, 204) — honors HTTP spec of no body on 204"

key-files:
  created:
    - api_server/src/api_server/auth/deps.py
    - api_server/src/api_server/models/users.py
    - api_server/src/api_server/routes/auth.py
    - api_server/src/api_server/routes/users.py
    - api_server/tests/auth/test_google_authorize.py
    - api_server/tests/auth/test_google_callback.py
    - api_server/tests/auth/test_github_authorize.py
    - api_server/tests/auth/test_github_callback.py
    - api_server/tests/auth/test_logout.py
    - api_server/tests/routes/__init__.py
    - api_server/tests/routes/test_users_me.py
    - api_server/tests/config/__init__.py
    - api_server/tests/config/test_oauth_state_secret_fail_loud.py
  modified:
    - api_server/src/api_server/main.py
    - api_server/tests/conftest.py
    - .planning/phases/22c-oauth-google/deferred-items.md

key-decisions:
  - "Logout returns Response(status_code=204) with NO body (not JSONResponse(None, 204)). Empirically cleaner; HTTP spec mandates no body for 204. (Task 2 deviation from plan text; accepted at checkpoint.)"
  - "Both callback routes key EXACT-match on e.error == 'mismatching_state' (not substring on description)"
  - "Happy-path tests monkeypatch authorize_access_token rather than driving full respx state-cookie round-trip — the behavior we test is 'given this token dict, does the route upsert + mint session correctly', not authlib's CSRF validation (spike A already covered that)"
  - "conftest.py _truncate_tables extended: sessions added to TRUNCATE list + non-ANONYMOUS users deleted per-test — required for test isolation; verified no regression in the 109-test integration suite"
  - "Per-test app.state.settings mutation for redirect_uri — async_client fixture is a single construction; easier than tearing down + rebuilding to pick up env changes"
  - "Google OIDC discovery + JWKS pre-stubbed in respx_oauth_providers so authlib's load_server_metadata() never hits public internet"

patterns-established:
  - "EXACT-match OAuthError key (e.error == 'mismatching_state') + catch-all → oauth_failed; non-state errors (invalid_grant, invalid_client) verified to NOT misroute to state_mismatch"
  - "Authorize tests set app.state.settings.oauth_<provider>_redirect_uri in-place to exercise the redirect_uri= query param"
  - "respx context-manager factory pattern — single fixture returns a callable that yields a dict of pre-registered routes; tests call .mock(return_value=...) on the specific route they need"
  - "TRUNCATE sessions + DELETE users WHERE id != ANONYMOUS_USER_ID for per-test auth-layer isolation"

requirements-completed:
  - R1
  - R2
  - R4
  - R5
  - AMD-01
  - AMD-02
  - AMD-07
  - D-22c-AUTH-01
  - D-22c-AUTH-03
  - D-22c-OAUTH-01
  - D-22c-OAUTH-02
  - D-22c-OAUTH-03
  - D-22c-OAUTH-04
  - D-22c-OAUTH-05
  - D-22c-FE-03
  - D-22c-FE-04

# Metrics
duration: 65min
completed: 2026-04-20
tasks_completed: 4
files_created: 13
files_modified: 3
commits: 4
tests_added: 20
---

# Phase 22c-oauth-google Plan 05: OAuth Routes + /users/me + Logout + Middleware Wiring Summary

Backend OAuth loop closed end-to-end: Google + GitHub authorize + callback + logout routes, the `/v1/users/me` surface, the `require_user` inline auth helper, Starlette SessionMiddleware + ApSessionMiddleware wired into `main.py`, and 20 integration tests covering every code path including 2 NEW WARNING-3 regression traps.

## What Landed

### 5 OAuth HTTP endpoints (`routes/auth.py`)

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/v1/auth/google` | 302 to `accounts.google.com/o/oauth2/v2/auth` with `client_id`, `state`, `redirect_uri`, scope `openid email profile`. Sets `ap_oauth_state` cookie. |
| `GET` | `/v1/auth/google/callback` | `?error=access_denied` → 302 `/login?error=access_denied`. `OAuthError(error="mismatching_state")` → 302 `/login?error=state_mismatch` (EXACT match). Any other OAuthError → 302 `/login?error=oauth_failed`. Happy path: `upsert_user` + `mint_session` + Set-Cookie `ap_session` + 302 `/dashboard`. |
| `GET` | `/v1/auth/github` | 302 to `github.com/login/oauth/authorize` with `client_id`, `state`, `redirect_uri`, scope `read:user user:email`. |
| `GET` | `/v1/auth/github/callback` | Same error matrix as Google. Happy path: fetch `/user`; if email null, fallback to `/user/emails` and pick first primary+verified; if still null, 302 `oauth_failed`. Otherwise upsert + session + `/dashboard`. |
| `POST` | `/v1/auth/logout` | `require_user` gate → 401 if no session. DELETEs `sessions WHERE id = <cookie>`. Returns `Response(status_code=204)` + `Set-Cookie: ap_session=; Max-Age=0`. |

### `GET /v1/users/me` (`routes/users.py`)

Returns `SessionUserResponse { id, email, display_name, avatar_url, provider, created_at }` via `require_user` → `SELECT users WHERE id = <user_id>`. 401 Stripe-shape envelope on no cookie / expired session / revoked session / deleted-user. Schema mirrors `frontend/lib/api.ts::SessionUser` with `created_at` added for "member since" display.

### `require_user` inline helper (`auth/deps.py`)

```python
def require_user(request: Request) -> JSONResponse | UUID:
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        return JSONResponse(401, content=make_error_envelope(
            ErrorCode.UNAUTHORIZED, "Authentication required", param="ap_session"))
    if isinstance(user_id, UUID):
        return user_id
    try:
        return UUID(str(user_id))
    except (ValueError, AttributeError):
        return JSONResponse(401, content=...)
```

Matches `routes/agent_events.py::_err()` pattern; NOT FastAPI `Depends` (D-22c-AUTH-03). Callers do `result = require_user(request); if isinstance(result, JSONResponse): return result; user_id = result`.

### Middleware stack (main.py)

Declaration order outermost-last; effective request-in order:

```
CorrelationId -> AccessLog -> StarletteSession -> ApSession -> RateLimit -> Idempotency -> route
```

```python
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ApSessionMiddleware)                # ap_session -> user_id
app.add_middleware(StarletteSessionMiddleware,         # ap_oauth_state (authlib CSRF)
    secret_key=(settings.oauth_state_secret or "dev-oauth-state-key-not-for-prod-0000000000000000"),
    session_cookie="ap_oauth_state", max_age=600, same_site="lax",
    https_only=(settings.env == "prod"), path="/")
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

`get_oauth(settings)` called eagerly in `create_app()` BEFORE `add_middleware` so prod boot fails loud on missing envs (verified by `test_prod_fails_boot_without_state_secret`). `app.state.session_last_seen = {}` initialized for the 22c-04 throttle cache.

## Tests (20 total)

| File | Tests | REQ ID | Notes |
| --- | --- | --- | --- |
| `tests/auth/test_google_authorize.py` | 1 | R1 | 302 + client_id + state + redirect_uri + `ap_oauth_state` cookie |
| `tests/auth/test_github_authorize.py` | 1 | R1 | 302 + same query params + cookie |
| `tests/auth/test_google_callback.py` | 5 | R2, D-22c-FE-03 | state_mismatch, access_denied, **non-state-error → oauth_failed (WARNING-3)**, happy_path (upserts user + session + cookie), missing_sub |
| `tests/auth/test_github_callback.py` | 5 | R2, D-22c-OAUTH-03 | state_mismatch, **non-state-error → oauth_failed (WARNING-3)**, public_email happy_path, /user/emails fallback, no_verified_email → oauth_failed |
| `tests/auth/test_logout.py` | 2 | R5 | 204 + invalidates (sessions row DELETEd + same cookie now 401), 401 without cookie |
| `tests/routes/test_users_me.py` | 4 | R4 | 200 with valid session, 401 no cookie, 401 expired session, 401 revoked session |
| `tests/config/test_oauth_state_secret_fail_loud.py` | 2 | AMD-07 | prod raises on missing AP_OAUTH_STATE_SECRET, dev boots without any OAuth envs |

### Test execution evidence

```
$ pytest tests/auth/ tests/routes/test_users_me.py tests/config/test_oauth_state_secret_fail_loud.py -m 'api_integration or not api_integration'
============================= test session starts ==============================
platform darwin -- Python 3.13.9, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/fcavalcanti/dev/agent-playground/api_server
configfile: pyproject.toml
plugins: asyncio-1.3.0, respx-0.23.1, anyio-4.13.0
collected 32 items

tests/auth/test_github_authorize.py .                                    [  3%]
tests/auth/test_github_callback.py .....                                 [ 18%]
tests/auth/test_google_authorize.py .                                    [ 21%]
tests/auth/test_google_callback.py .....                                 [ 37%]
tests/auth/test_logout.py ..                                             [ 43%]
tests/auth/test_oauth_config.py ............                             [ 81%]  # 22c-03 pre-existing
tests/routes/test_users_me.py ....                                       [ 93%]
tests/config/test_oauth_state_secret_fail_loud.py ..                     [100%]

============================== 32 passed in 8.82s ==============================
```

20 NEW + 12 pre-existing (22c-03 `test_oauth_config.py`) = 32 total green.

## Test -> REQ ID mapping (22c-VALIDATION.md coverage)

| REQ | Covered by |
| --- | --- |
| R1 (authorize 302) | test_google_authorize, test_github_authorize |
| R2 (callback flows) | test_google_callback (5), test_github_callback (5) |
| R4 (/users/me) | test_users_me (4) |
| R5 (logout) | test_logout (2) |
| AMD-01 (dual-provider) | test_github_*, test_google_* |
| AMD-02 (no refresh tokens) | implicit — scope omits access_type=offline |
| AMD-07 (state secret fail-loud) | test_oauth_state_secret_fail_loud (2) |
| D-22c-AUTH-01 (middleware order) | main.py add_middleware declaration block |
| D-22c-AUTH-03 (require_user shape) | auth/deps.py (covered by test_users_me_401_no_cookie + test_logout_without_cookie_returns_401) |
| D-22c-OAUTH-01..05 (cookie flags, redirects) | test_logout (cookie clear + 204), test_*_callback (302 /dashboard) |
| D-22c-FE-03 (error codes) | test_oauth_failed_on_non_state_error (both providers) + test_access_denied_redirects + test_state_mismatch_redirects (both providers) |
| D-22c-FE-04 (happy-path → /dashboard) | test_happy_path_* (both providers) |

## Deviations from Plan

### Rule 1 — Plan text adjustment: logout returns Response(204) not JSONResponse(None, 204)

- **Found during:** Task 2 (routes/auth.py construction)
- **Issue:** Plan template specified `JSONResponse(content=None, status_code=204)`. HTTP 204 mandates no body; `JSONResponse(None, ...)` serializes `null` (4 bytes) and emits `Content-Length: 4`.
- **Fix:** Changed to `Response(status_code=204)` (empty body, no Content-Length). Test `test_logout_204_invalidates_session` asserts `r.content == b""`.
- **Files modified:** `api_server/src/api_server/routes/auth.py`
- **Commit:** `d47e303`
- **Checkpoint status:** Auto-approved at the human-verify gate between T3/T4.

### Rule 3 — Truncate list extended for auth-layer test isolation

- **Found during:** Task 4 (conftest.py extension)
- **Issue:** `_truncate_tables` autouse fixture did not include `sessions` or `users`. Any test that seeds a session via `authenticated_cookie` would leave state behind for the next test, causing flakes when multiple tests use overlapping session IDs or when a logout test DELETEs a session another test is mid-way through using.
- **Fix:** Added `sessions` to the TRUNCATE CASCADE list; appended `DELETE FROM users WHERE id != '00000000-0000-0000-0000-000000000001'` to preserve ANONYMOUS seed while clearing test-created users.
- **Files modified:** `api_server/tests/conftest.py`
- **Commit:** `eea754a`
- **Regression check:** Full `pytest -m api_integration` run — 109 previously-green tests still green (3 failures were pre-existing; see deferred-items.md).

### Rule 2 — Per-test redirect_uri override for authorize tests

- **Found during:** Task 4 (test_google_authorize + test_github_authorize)
- **Issue:** The `async_client` fixture sets `AP_ENV=dev` but leaves `AP_OAUTH_*_REDIRECT_URI` unset. The dev path in `_resolve_or_fail` does NOT backfill `settings.oauth_google_redirect_uri` with a placeholder (only the ones passed into `oauth.register` are backfilled; redirect_uris are READ from `settings` at authorize_redirect time). Result: `settings.oauth_google_redirect_uri is None` and the Location header had no `redirect_uri=` param.
- **Fix:** Test mutates `async_client._transport.app.state.settings.oauth_<provider>_redirect_uri` to a localhost URL before driving the authorize request. Non-invasive; no production code change.
- **Files modified:** `api_server/tests/auth/test_google_authorize.py`, `api_server/tests/auth/test_github_authorize.py`
- **Commit:** `eea754a`

## Auth Gates

None — zero human-action checkpoints triggered. The one `checkpoint:human-verify` between T3 and T4 was auto-approved in auto mode.

## Known Stubs

None. Every new file wires real code to real infra; tests hit a real Postgres via testcontainers and real ASGI via httpx.

## Threat Flags

None beyond the plan's registered T-22c-13 through T-22c-18. The landed code strictly tracks that register — no new network surface, no new auth paths, no new file access, no schema changes. Test-layer additions (the two fixtures) are local to `tests/` and do not widen prod surface.

## Deferred Issues

Pre-existing failures on `main` (verified by git-stash + clean-main run):

- `tests/test_recipes.py::test_list_recipes_returns_five` — asserts `apiVersion == 'ap.recipe/v0.1'` but recipes on disk are v0.2
- `tests/test_idempotency.py::test_same_key_different_users_isolated`
- `tests/test_busybox_tail_line_buffer.py::test_busybox_tail_line_buffer` — BusyBox tail -F line-buffering timing

Logged to `.planning/phases/22c-oauth-google/deferred-items.md` under the 22c-05 section.

## Commits

| Commit | Scope |
| --- | --- |
| `e989bd4` | T1 — `auth/deps.py::require_user` + `models/users.py::SessionUserResponse` + `routes/users.py::GET /v1/users/me` |
| `d47e303` | T2 — `routes/auth.py` — 5 endpoints (google + github authorize/callback + logout) with EXACT OAuthError match |
| `eb2dcb6` | T3 — `main.py` — StarletteSessionMiddleware + ApSessionMiddleware wiring + router includes + app.state.settings + eager get_oauth() |
| `eea754a` | T4 — 20 integration tests + conftest fixtures (authenticated_cookie, second_authenticated_cookie, respx_oauth_providers) + TRUNCATE list extension + deferred-items.md update |

## Next Plans

- **22c-06** (Wave 4) — alembic 006: ANONYMOUS purge. DELETE from 8 data-bearing tables. Conftest PG-network-attach fix scheduled here per plan-level pointer.
- **22c-07** (Wave 4) — Next.js 16.2 login page. Wires buttons to `GET /v1/auth/google` + `/v1/auth/github`.
- **22c-08** (Wave 4) — `frontend/lib/proxy.ts` for cookie-preserving fetch; frontend `useSession` hook calls `GET /v1/users/me`.
- **22c-09** (Wave 5) — Cross-user isolation e2e + manual smoke + STATE close-out. `second_authenticated_cookie` fixture is already seeded for it in `tests/conftest.py`.

## Self-Check: PASSED

All claims verified against the live repo at commit `eea754a`:

- [x] `api_server/src/api_server/auth/deps.py` exists (e989bd4)
- [x] `api_server/src/api_server/models/users.py` exists (e989bd4)
- [x] `api_server/src/api_server/routes/auth.py` exists (d47e303)
- [x] `api_server/src/api_server/routes/users.py` exists (e989bd4)
- [x] `api_server/src/api_server/main.py` updated (eb2dcb6)
- [x] `api_server/tests/auth/test_google_authorize.py` exists
- [x] `api_server/tests/auth/test_google_callback.py` exists
- [x] `api_server/tests/auth/test_github_authorize.py` exists
- [x] `api_server/tests/auth/test_github_callback.py` exists
- [x] `api_server/tests/auth/test_logout.py` exists
- [x] `api_server/tests/routes/__init__.py` + `test_users_me.py` exist
- [x] `api_server/tests/config/__init__.py` + `test_oauth_state_secret_fail_loud.py` exist
- [x] `api_server/tests/conftest.py` extended with 3 new fixtures + truncate extension
- [x] Commit `e989bd4` in git log
- [x] Commit `d47e303` in git log
- [x] Commit `eb2dcb6` in git log
- [x] Commit `eea754a` in git log
- [x] 20 new tests pass (32 total including the 12 22c-03 unit tests in the same discovery path)
- [x] 2 WARNING-3 regression tests (test_oauth_failed_on_non_state_error for both providers) present + green
