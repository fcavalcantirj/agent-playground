---
phase: 22c-oauth-google
plan: 04
subsystem: auth
tags: [asgi-middleware, starlette, asyncpg, session-cookie, log-redaction]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: sessions table + users.sub/avatar_url/last_login_at columns (22c-02, alembic 005)
  - phase: 22c-oauth-google
    provides: get_oauth/upsert_user/mint_session helpers (22c-03)
provides:
  - SessionMiddleware class resolving request.state.user_id from ap_session cookie
  - Per-worker 60s last_seen_at throttle via in-memory dict (no Redis)
  - log_redact.py docstring documenting ap_session + ap_oauth_state redaction by construction
  - 10 middleware tests (6 R3 session-resolution + 2 D-22c-MIG-05 throttle + 2 cookie-redact)
affects: [22c-05, 22c-06, 22c-07, 22c-08, 22c-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ASGI middleware reads scope headers directly (no Request object construction) for cookie extraction"
    - "Per-worker in-memory cache keyed off asgi_app.state for cross-request shared state without Redis"
    - "scope.setdefault('state', {})['user_id'] = ... idiom to be Starlette-state compatible before routing"
    - "Counting-proxy pool wrapper pattern for asserting 'no PG query issued' in tests"

key-files:
  created:
    - api_server/src/api_server/middleware/session.py
    - api_server/tests/middleware/conftest.py
    - api_server/tests/middleware/test_session_middleware.py
    - api_server/tests/middleware/test_last_seen_throttle.py
    - api_server/tests/middleware/test_log_redact_cookies.py
  modified:
    - api_server/src/api_server/middleware/log_redact.py  # docstring only

key-decisions:
  - "Per-worker in-memory dict (not Redis) for last_seen_at throttle per D-22c-MIG-05"
  - "SessionMiddleware sets request.state.user_id = None for any non-valid session (no exception raised)"
  - "Malformed cookie short-circuits BEFORE PG lookup; T-22c-09 regression guard"
  - "PG outage fail-closed to anonymous (user_id = None) + log.exception; site stays up"
  - "log_redact.py code unchanged; allowlist already protects Cookie/Set-Cookie by construction"

patterns-established:
  - "SessionMiddleware placement: CorrelationId -> AccessLog -> StarletteSession -> OurSession -> RateLimit -> Idempotency (wired in 22c-05)"
  - "Tests mount a minimal FastAPI app with only SessionMiddleware + echo route to isolate behavior from the production main.py stack"
  - "Counting-proxy pool wrapper: stand-in for asyncpg.Pool with counting acquire() — asyncpg's real Pool has read-only attributes"
  - "_BrokenPool pattern for PG-outage fail-closed testing (raise from __aenter__)"

requirements-completed: [R3, D-22c-AUTH-01, D-22c-AUTH-02, D-22c-MIG-05]

# Metrics
duration: 5min
completed: 2026-04-20
---

# Phase 22c-oauth-google Plan 04: SessionMiddleware Summary

**ASGI SessionMiddleware resolving ap_session cookie → request.state.user_id via asyncpg SELECT on sessions (with 60s per-worker last_seen_at throttle via in-memory dict) — plus 10 middleware tests closing R3 + D-22c-AUTH-01/02 + D-22c-MIG-05.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-20T00:00:30Z
- **Completed:** 2026-04-20T00:05:05Z
- **Tasks:** 2
- **Files created:** 5
- **Files modified:** 1

## Accomplishments

- `api_server/src/api_server/middleware/session.py` — new ASGI SessionMiddleware class (147 lines). Reads `ap_session` cookie, coerces to UUID (malformed → None, no PG query), SELECTs `sessions` WHERE id = $1 AND revoked_at IS NULL AND expires_at > NOW(), sets `scope['state']['user_id'] = <UUID | None>`. Per-worker `app.state.session_last_seen: dict[UUID, datetime]` throttles `UPDATE sessions SET last_seen_at` to at most 1 UPDATE per session per 60s window (D-22c-MIG-05). Soft LRU eviction at 10k entries. Fail-closed to `user_id = None` + `log.exception` on PG outage.
- `log_redact.py` docstring extended with a Phase 22c §"Cookie redaction" paragraph explicitly naming `ap_session` + `ap_oauth_state` as redacted-by-construction. Code path (`_LOG_HEADERS` allowlist) unchanged — the allowlist already blocks Cookie/Set-Cookie lines.
- 10 tests, all green:
  - 6 R3 session-resolution cases: no-cookie, valid, expired (expires_at past), revoked (revoked_at set), malformed (non-UUID, proven no-PG-query via counting pool proxy), PG-outage (raises from acquire, fail-closed + log.exception).
  - 2 D-22c-MIG-05 last_seen throttle cases: rapid-dupe (2 requests → 1 UPDATE), 61s-rewind (cache backdated → 2nd UPDATE fires).
  - 2 cookie-redaction cases: `ap_session=<sentinel>` + `ap_oauth_state=<sentinel>` values absent from structlog output by construction.
- Pre-existing `test_log_redact.py` tests still green (verified) — no regression in the allowlist.

## Task Commits

Each task committed atomically on main (sequential executor; plan `wave: 2` runs solo, no parallelism concern):

1. **Task 1: middleware/session.py + log_redact docstring** — `08560d0` (feat)
2. **Task 2: 3 test files + conftest** — `9a954d3` (test)

## Files Created/Modified

- `api_server/src/api_server/middleware/session.py` — CREATED. ASGI SessionMiddleware class, per-worker last_seen_at throttle, helper functions (_extract_cookie, _coerce_uuid, _maybe_touch_last_seen, _get_or_init_cache, _maybe_evict).
- `api_server/src/api_server/middleware/log_redact.py` — MODIFIED (docstring only). Phase 22c cookie-redaction paragraph appended. No code change.
- `api_server/tests/middleware/conftest.py` — CREATED. `session_test_app` + `session_client` fixtures wiring a minimal FastAPI app with ONLY SessionMiddleware + `/_test/whoami` echo route against a fresh asyncpg pool on the session-scoped testcontainers PG.
- `api_server/tests/middleware/test_session_middleware.py` — CREATED. 6 R3 integration tests.
- `api_server/tests/middleware/test_last_seen_throttle.py` — CREATED. 2 D-22c-MIG-05 throttle tests.
- `api_server/tests/middleware/test_log_redact_cookies.py` — CREATED. 2 cookie-redaction unit tests (no DB, no Docker).

## Verification

Final pytest output captured live:

```
============================= test session starts ==============================
platform darwin -- Python 3.13.9, pytest-9.0.3
plugins: asyncio-1.3.0, respx-0.23.1, anyio-4.13.0

tests/middleware/test_last_seen_throttle.py::test_two_requests_in_same_worker_trigger_one_update PASSED
tests/middleware/test_last_seen_throttle.py::test_request_after_60s_triggers_second_update PASSED
tests/middleware/test_log_redact_cookies.py::test_ap_session_cookie_value_not_in_logs PASSED
tests/middleware/test_log_redact_cookies.py::test_ap_oauth_state_cookie_value_not_in_logs PASSED
tests/middleware/test_session_middleware.py::test_no_cookie_sets_user_id_none PASSED
tests/middleware/test_session_middleware.py::test_valid_cookie_resolves_user_id PASSED
tests/middleware/test_session_middleware.py::test_expired_session_returns_none PASSED
tests/middleware/test_session_middleware.py::test_revoked_session_returns_none PASSED
tests/middleware/test_session_middleware.py::test_malformed_cookie_returns_none PASSED
tests/middleware/test_session_middleware.py::test_pg_outage_fails_closed PASSED

============================== 10 passed in 3.61s ==============================
```

Regression check:

```
tests/test_log_redact.py::test_authorization_header_not_logged PASSED
tests/test_log_redact.py::test_cookie_header_not_logged PASSED
tests/test_log_redact.py::test_x_api_key_header_not_logged PASSED
tests/test_log_redact.py::test_request_body_not_logged PASSED
tests/test_log_redact.py::test_mask_known_prefixes PASSED
tests/test_log_redact.py::test_mask_known_prefixes_with_explicit_val PASSED

============================== 6 passed in 0.24s ===============================
```

## Behavior matrix (R3 proven)

| Cookie state | Expected user_id | Test | Verified |
|---|---|---|---|
| Absent | None | `test_no_cookie_sets_user_id_none` | ✅ |
| Valid UUID + row | row.user_id | `test_valid_cookie_resolves_user_id` | ✅ |
| Valid UUID + expires_at past | None | `test_expired_session_returns_none` | ✅ |
| Valid UUID + revoked_at set | None | `test_revoked_session_returns_none` | ✅ |
| Malformed (not a UUID) | None + no PG query | `test_malformed_cookie_returns_none` | ✅ |
| Valid UUID + PG outage | None + log.exception | `test_pg_outage_fails_closed` | ✅ |

## Throttle matrix (D-22c-MIG-05 proven)

| Scenario | Expected # UPDATEs | Test | Verified |
|---|---|---|---|
| Two rapid requests, same cookie, same worker | 1 | `test_two_requests_in_same_worker_trigger_one_update` | ✅ |
| Request after 61s (cache rewound) | 2nd UPDATE fires | `test_request_after_60s_triggers_second_update` | ✅ |

## Redaction matrix (CONTEXT §Established Patterns proven)

| Cookie name | Sentinel in logs? | Test | Verified |
|---|---|---|---|
| `ap_session` | NO | `test_ap_session_cookie_value_not_in_logs` | ✅ |
| `ap_oauth_state` | NO | `test_ap_oauth_state_cookie_value_not_in_logs` | ✅ |

## Decisions Made

None beyond what the plan + CONTEXT.md already locked. Plan executed as written, verbatim middleware body per `<action>` directive.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] asyncpg.Pool.acquire is read-only; replaced monkey-patch strategy with a counting-proxy pool wrapper**

- **Found during:** Task 2 (test_malformed_cookie_returns_none, first pytest run)
- **Issue:** The plan's test sketch directly reassigned `pool.acquire = _patched_acquire` on a live `asyncpg.Pool` instance. asyncpg 0.31 raises `AttributeError: 'Pool' object attribute 'acquire' is read-only` because `Pool.__slots__` pins the attribute. Test crashed before the middleware was exercised.
- **Fix:** Replaced with a `_CountingPoolProxy` wrapper — a plain Python object whose `.acquire()` increments a counter then delegates to the real pool. Swap `app.state.db = _CountingPoolProxy(pool)` for the test body, restore the real pool in the finally block. The middleware's `asgi_app.state.db.acquire()` sees the proxy transparently.
- **Files modified:** `api_server/tests/middleware/test_session_middleware.py`
- **Verification:** `test_malformed_cookie_returns_none` passes; `acquire_count['n']` stays at 0 as expected, proving the middleware short-circuits before the pool is touched.
- **Committed in:** `9a954d3` (part of Task 2 commit, since the failure surfaced in the same commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking test infrastructure issue, not a production-code issue).
**Impact on plan:** Zero impact on shipped production code. The plan's middleware body was copied verbatim; only the test harness needed a wrap-not-replace strategy to accommodate asyncpg.Pool's read-only slot.

## Issues Encountered

None beyond the deviation above. `uv.lock` file was regenerated by `uv run` during verification — kept untracked to match pre-existing state (`.gitignore` doesn't list it; no prior commit tracked it either).

## User Setup Required

None — this plan delivers the middleware CLASS only. Wiring into `main.py`'s middleware stack lives in plan 22c-05 per D-22c-AUTH-01. No env vars, no external services.

## Next Phase Readiness

- **Plan 22c-05 unblocked.** SessionMiddleware class importable at `api_server.middleware.session:SessionMiddleware`. Plan 22c-05's main.py patch will register BOTH Starlette's built-in SessionMiddleware (for authlib's CSRF state, keyed on `settings.oauth_state_secret`, AMD-07) AND our custom SessionMiddleware (for ap_session resolution).
- **R3 acceptance unblocked.** The behavior matrix + throttle + redaction are all proven live against real testcontainers PG 17 on alembic HEAD = 005.
- **Idempotency middleware user_id wiring (D-22c-AUTH-04) unblocked.** Plan 22c-05 will replace `idempotency.py:159`'s `user_id = ANONYMOUS_USER_ID` with `user_id = scope.get('state', {}).get('user_id')` now that the middleware-stack contract surfaces it.

## Self-Check: PASSED

**Files verified to exist:**
- `api_server/src/api_server/middleware/session.py` — FOUND
- `api_server/src/api_server/middleware/log_redact.py` — FOUND (modified)
- `api_server/tests/middleware/conftest.py` — FOUND
- `api_server/tests/middleware/test_session_middleware.py` — FOUND
- `api_server/tests/middleware/test_last_seen_throttle.py` — FOUND
- `api_server/tests/middleware/test_log_redact_cookies.py` — FOUND

**Commits verified to exist in `git log --oneline --all`:**
- `08560d0` feat(22c-04): SessionMiddleware class + log_redact docstring — FOUND
- `9a954d3` test(22c-04): SessionMiddleware + last_seen throttle + cookie-redact tests — FOUND

**Acceptance criteria (from PLAN.md):**
- `from api_server.middleware.session import SessionMiddleware` succeeds — VERIFIED (module-level import test in Task 1 verification block)
- `SESSION_COOKIE_NAME == "ap_session"` — VERIFIED
- `LAST_SEEN_THROTTLE.total_seconds() == 60` — VERIFIED
- `_LOG_HEADERS` contains neither `"cookie"` nor `"set-cookie"` — VERIFIED (no change)
- `grep "ap_session" api_server/src/api_server/middleware/log_redact.py` returns matches — VERIFIED (lines 21–22)
- 6 session-resolution tests pass — VERIFIED (6/6 PASSED)
- 2 last-seen throttle tests pass — VERIFIED (2/2 PASSED)
- 2 cookie-redaction tests pass — VERIFIED (2/2 PASSED)

---

*Phase: 22c-oauth-google*
*Plan: 04*
*Completed: 2026-04-20*
