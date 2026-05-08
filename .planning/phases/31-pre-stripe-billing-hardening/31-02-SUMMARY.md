---
phase: 31-pre-stripe-billing-hardening
plan: 02
subsystem: middleware-rate-limit
tags: [rate-limit, auth, asgi, frozenset, composite-subject, fail-open, testcontainers, postgres]

requires:
  - phase: 19-shipped
    provides: RateLimitMiddleware ASGI body + _bucket_for + composite-subject pattern (chat:<user>:<agent>) at L164-168 + fail-open branch at L170-180 + Stripe-shape 429 envelope
  - phase: 22c.3-08-shipped
    provides: chat-bucket precedent for composite-subject derivation; test_chat_rate_limit.py blueprint shape
  - phase: 31-01-shipped
    provides: sentry-sdk pin + e2e_money_path marker + AMD-05 truncate (none directly consumed by 31-02 but they unblock parallel waves)
provides:
  - "auth bucket: 7 (method, path) tuples in module-level frozenset _AUTH_ROUTES (3 POST + 4 GET)"
  - "_AUTH_ROUTE_KEYS: 7 stable short aliases for D-02 path-rename decoupling"
  - "_LIMITS['auth'] = (5, 60) — 5 calls per IP per route per minute"
  - "_bucket_for: tuple-membership branch BEFORE the generic GET fallback so OAuth callbacks get the auth ceiling, not 300/min"
  - "Composite subject `auth:<ip>:<route_key>` mirroring chat-bucket pattern — per-route counters distinct"
  - "tests/middleware/test_auth_rate_limit.py — 4 real-Postgres tests covering AC1, AC2, AC3, AC4 + cross-bucket isolation"
affects:
  - "31-03 H6 api_server Sentry init (will write before_send filter that drops auth-bucket 429s — this plan delivers the 429 surface that test asserts on)"
  - "Phase B Stripe paywall (auth route is hardened against state-token spraying before billing surface lands)"

tech-stack:
  added: []
  patterns:
    - "Tuple-membership frozenset gate for fixed-route bucket selection — no regex on the hot path; greppable + extensible without _LIMITS dict surgery"
    - "Composite-subject derivation `<bucket>:<subject>:<route_key>` for per-route counter rows under a shared bucket ceiling"
    - "Pre-existing fail-open branch inherited unchanged for the new bucket — additive change, zero blast radius for T-31-01"
    - "Test fixture sets trusted_proxy=True + per-test x-forwarded-for=203.0.113.X header to isolate counter rows by IP without requiring autouse table truncation"

key-files:
  created:
    - "api_server/tests/middleware/test_auth_rate_limit.py — 4 real-testcontainers-Postgres integration tests (~238 lines)"
    - ".planning/phases/31-pre-stripe-billing-hardening/deferred-items.md — out-of-scope pre-existing failures discovered during regression check"
  modified:
    - "api_server/src/api_server/middleware/rate_limit.py — added _AUTH_ROUTES frozenset (7 entries) + _AUTH_ROUTE_KEYS dict (7 aliases) + _LIMITS['auth']=(5,60) + _bucket_for tuple-membership branch + composite-subject branch in __call__ (~47 net-added lines)"

key-decisions:
  - "trusted_proxy=True on _MiniSettings + per-test 203.0.113.X x-forwarded-for headers — gives each test its own subject IP without needing the autouse _truncate_tables fixture (which doesn't fire because tests don't request db_pool/async_client). Same isolation guarantee, simpler fixture."
  - "Composite subject branch placed AFTER the existing chat-bucket branch in __call__ rather than refactoring the two into a generic dispatcher — preserves the existing chat code unchanged, additive-only diff, lower regression risk."
  - "Pool-close-idempotent guard in fixture teardown (`if not pool._closed: await pool.close()`) — needed because test_pg_outage closes the pool deliberately to simulate the outage, and the fixture's finally block would double-close otherwise."

duration: ~25min
completed: 2026-05-08
---

# Phase 31 Plan 02: Auth-Bucket Rate-Limit Summary

**Added a new `auth` rate-limit bucket to `RateLimitMiddleware` covering all 7 auth route entry points (3 POSTs + 4 GETs) at 5/min/IP per route via composite subject `auth:<ip>:<route_key>`, preserving the existing fail-open semantic on Postgres outage — closes the H3 gap from the 2026-05-04 audit where auth POSTs were unrate-limited and OAuth GET callbacks fell into the generic 300/min get bucket.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-08T18:30:00Z (approx)
- **Completed:** 2026-05-08T18:55:00Z
- **Tasks:** 2
- **Files modified:** 1 (`rate_limit.py`)
- **Files created:** 2 (`test_auth_rate_limit.py`, `deferred-items.md`)

## Accomplishments

- `POST /v1/auth/google/mobile`, `POST /v1/auth/github/mobile`, `POST /v1/auth/logout`, `GET /v1/auth/google`, `GET /v1/auth/google/callback`, `GET /v1/auth/github`, `GET /v1/auth/github/callback` all now route to the `auth` bucket (5/min/IP per route).
- Composite subject `auth:<ip>:<route_key>` gives each route its own counter row — verified by `test_auth_rate_limit_per_route` (3 google_mobile + 3 github_mobile from the same IP all succeed).
- `test_auth_rate_limit_6th_in_60s_returns_429` empirically confirms AC1 + AC3: 5 POSTs succeed, 6th returns 429 + `Retry-After` header (≥1) + Stripe-shape envelope with `error.code = "RATE_LIMITED"` + `error.param = "auth"`.
- `test_auth_rate_limit_pg_outage_fail_open` empirically confirms AC4 + T-31-01: closing the asyncpg pool to simulate a Postgres outage causes the middleware to log + pass through (200 from the stub, NOT 429, NOT 5xx).
- `test_auth_rate_limit_does_not_affect_chat` confirms cross-bucket isolation: exhausting the auth bucket leaves the chat bucket counter at 0/4.
- The 3 chat-bucket regression tests still pass (`test_chat_rate_limit_5th_in_60s_returns_429`, `test_chat_rate_limit_per_agent`, `test_chat_rate_limit_does_not_affect_runs`) — no chat-path regression.
- All 5 plan-level `must_haves.truths` empirically verified.

## Task Commits

Each task was committed atomically with `--no-verify` (parallel worktree mode):

1. **Task 1: Extend RateLimitMiddleware with the `auth` bucket** — `d64d16f` (`feat`)
2. **Task 2: Create real-Postgres integration test `tests/middleware/test_auth_rate_limit.py` covering AC1-AC4** — `f775f32` (`test`)

## Files Created/Modified

- `api_server/src/api_server/middleware/rate_limit.py` — Inserted `_AUTH_ROUTES` frozenset (7 entries) + `_AUTH_ROUTE_KEYS` dict (7 aliases) immediately after `_AGENT_MESSAGES_PATTERN` (L45). Appended `"auth": (5, 60)` to `_LIMITS`. Inserted `if (method, path) in _AUTH_ROUTES: return "auth"` branch in `_bucket_for` BEFORE the generic GET fallback. Inserted composite-subject derivation `if bucket == "auth": subject = f"auth:{subject}:{route_key}"` in `__call__` AFTER the existing chat-bucket composite. Net delta: +47 lines, 0 modifications to existing logic, fail-open branch unchanged, 429 envelope unchanged. Subject derivation in `_subject_from_scope` unchanged (D-03 IDENTICAL to existing buckets).
- `api_server/tests/middleware/test_auth_rate_limit.py` — 238-line test file mirroring `test_chat_rate_limit.py` byte-for-byte for module marker, imports, mini-app fixture, and 429 envelope assertion shape. Substitutions: 3 auth POST stubs + 1 chat POST stub (for cross-bucket test). Tests use `trusted_proxy=True` + per-test `203.0.113.X` XFF headers for IP-isolation across tests. 4 tests: AC1+AC3 (6th-in-60s), AC2 (per-route), cross-bucket (chat unaffected), AC4+T-31-01 (PG outage fail-open). All 4 pass against testcontainers Postgres in 3.79s.
- `.planning/phases/31-pre-stripe-billing-hardening/deferred-items.md` — Logged 4 pre-existing failures in `tests/recipes/test_phase30_via_proxy_invariant.py` + `tests/test_run_recipe_telegram_invariant.py` discovered during regression run. They live in recipe-runner code paths (`tools/run_recipe.py:1311`), unrelated to rate-limit middleware. Out of scope per SCOPE BOUNDARY rule.

## Decisions Made

- **`trusted_proxy=True` in `_MiniSettings` + per-test XFF headers** — the `_MiniSettings` class in the existing `test_chat_rate_limit.py` uses `trusted_proxy=False`, but that's because chat tests rely on the user-cookie subject path (cookie is the isolation key, not IP). Auth tests use IP as the subject (no cookie), and the autouse `_truncate_tables` fixture only fires for tests that request `db_pool` / `async_client` (these don't). To get clean IP-based isolation between tests without buying into the autouse machinery, set `trusted_proxy=True` and give each test a distinct `203.0.113.X` XFF — the counter rows are then `auth:203.0.113.5:google_mobile`, `auth:203.0.113.6:google_mobile`, etc. — disjoint by construction.
- **Pool-close-idempotent guard** — `test_auth_rate_limit_pg_outage_fail_open` closes the pool inside the test body to simulate the PG outage, then the fixture's `finally: await pool.close()` would raise on the second close. Added `if not pool._closed:` guard. Future cleanup: replace the `_closed` private-attribute check with a try/except around the close, but this is the minimum-diff fix for now.
- **Composite-subject branch ordering in `__call__`** — placed the new `if bucket == "auth":` block AFTER the existing `if bucket == "chat":` block. Could have refactored both into a single dispatcher, but additive ordering preserves the chat code unchanged and minimizes regression surface. Future refactor opportunity if a third bucket needs composite-subject derivation.

## Deviations from Plan

None — plan executed exactly as written. All 5 surgical edits to `rate_limit.py` landed verbatim, the test file mirrors `test_chat_rate_limit.py` shape with the auth-route substitutions the plan called out, and the verification commands all pass.

The plan's note about Test 2 (line 344 of `31-02-PLAN.md`) flagged a potential need to set `trusted_proxy=True` if the per-route test failed with a shared-counter symptom; I made that flip proactively because the autouse-truncate-doesn't-fire reasoning was clear from reading `tests/conftest.py:184-220`. No plan-text change needed; the plan already permitted it.

## Issues Encountered

- **Pre-existing failures in non-integration suite** — `pytest -q -m "not api_integration and not e2e_money_path" --ignore=tests/spikes` reports 4 failures in `tests/recipes/test_phase30_via_proxy_invariant.py::test_all_recipes_flipped_count` + `tests/test_run_recipe_telegram_invariant.py::*` (3 tests). All 4 raise `RuntimeError: recipe 'openclaw' runtime.via_proxy=true requires channel='inapp' with INAPP_AUTH_TOKEN in activation_substitutions` from `tools/run_recipe.py:1311`. Not caused by rate-limit middleware changes — confirmed by reading the failure stack traces. Logged to `deferred-items.md`. Did NOT auto-fix (out of scope per SCOPE BOUNDARY rule).
- **Pool-close double-close** — As noted under Decisions, the `test_pg_outage` fixture path required a `_closed` guard to avoid double-close in the fixture teardown. Caught + fixed in the test file before the first run.

## User Setup Required

None — this plan modifies only middleware logic + adds tests. No environment variables, no service config, no migrations. The auth-bucket protection is automatically active for any FastAPI app that mounts `RateLimitMiddleware` (which is the default boot path via `main.create_app()`).

## Next Phase Readiness

Wave 2 plans can now build on the live auth-bucket surface:

- **31-03 (H6 api_server Sentry init)**: the Sentry `before_send` filter D-12 promises will drop auth-bucket 429s. The 429 surface this plan delivers is the load-bearing input the H6 transport-mock test asserts on (per AMD-06's tightened test obligation).
- **Phase B Stripe paywall**: the auth route surface is now hardened against state-token spraying before any billing surface lands.

The 7 auth routes are individually capped at 5/min/IP — sufficient hardening for the threat model captured in `31-SPEC.md` Requirement 1 + T-31-01 + T-31-04 residual.

## Self-Check

Verified against repository state:

- `api_server/src/api_server/middleware/rate_limit.py` exists and contains `_AUTH_ROUTES: frozenset[tuple[str, str]] = frozenset({` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` contains `"auth": (5, 60)` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` contains `if (method, path) in _AUTH_ROUTES:` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` contains `subject = f"auth:{subject}:{route_key}"` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` contains `rate_limit backend error; failing open` (fail-open preserved) — FOUND
- `api_server/tests/middleware/test_auth_rate_limit.py` exists and contains `pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]` — FOUND
- `api_server/tests/middleware/test_auth_rate_limit.py` contains 4 `async def test_auth_rate_limit_` tests — FOUND
- Commit `d64d16f` (Task 1: middleware extension) — FOUND
- Commit `f775f32` (Task 2: integration tests) — FOUND
- `pytest -m api_integration tests/middleware/test_auth_rate_limit.py` → 4/4 PASS in 3.79s — VERIFIED
- `pytest -m api_integration tests/middleware/test_chat_rate_limit.py` → 3/3 PASS (chat regression) — VERIFIED
- `python -c "from api_server.middleware.rate_limit import _AUTH_ROUTES, _AUTH_ROUTE_KEYS, _LIMITS; assert _LIMITS['auth'] == (5, 60); assert len(_AUTH_ROUTES) == 7; assert len(_AUTH_ROUTE_KEYS) == 7"` exits 0 — VERIFIED
- 5 plan-level truths from `must_haves.truths` empirically verified by inline Python script — VERIFIED

## Self-Check: PASSED

---
*Phase: 31-pre-stripe-billing-hardening*
*Plan: 02*
*Completed: 2026-05-08*
