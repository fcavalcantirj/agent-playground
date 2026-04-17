---
phase: 19-api-foundation
plan: 05
subsystem: api
tags: [fastapi, asgi-middleware, asyncpg, postgres, pg_advisory_xact_lock, rate-limit, idempotency, stripe-semantics, byok-adjacent, sc-06, sc-09, d-01, d-05, t-19-05-01, t-19-05-02, t-19-05-03]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: |
      Plan 19-01 — alembic baseline with `idempotency_keys` (UNIQUE
      user_id+key, `request_body_hash` NOT NULL, `expires_at`) and
      `rate_limit_counters` (PRIMARY KEY subject+bucket+window_start,
      `idx_rate_limit_gc`); Plan 19-02 — `create_app()` lifespan with
      `app.state.db` pool + `app.state.settings.trusted_proxy` +
      `ANONYMOUS_USER_ID` shared constant + middleware stack already
      wired (`CorrelationId → AccessLog → RateLimit stub → Idempotency
      stub → routes`); Plan 19-03 — `make_error_envelope` +
      `ErrorCode.RATE_LIMITED` + `ErrorCode.IDEMPOTENCY_BODY_MISMATCH`
      + `POST /v1/lint` mounted at `/v1/lint`; Plan 19-04 — `POST
      /v1/runs` route handler that emits `{run_id, verdict, ...}` on
      200 (the thing idempotency caches).
provides:
  - api_server.services.rate_limit.check_and_increment — Postgres-backed
    fixed-window counter keyed on (subject, bucket, window_start). Uses
    `pg_advisory_xact_lock` per-(subject,bucket) to serialize concurrent
    increments + `INSERT ... ON CONFLICT DO UPDATE` to upsert the counter
    row. Returns `(allowed: bool, retry_after_s: int)`.
  - api_server.services.idempotency.hash_body +
    .check_or_reserve + .write_idempotency. hash_body returns the
    SHA-256 hex digest of raw request bytes. check_or_reserve returns
    `("hit"|"miss"|"mismatch", cached_dict_or_None)` under an advisory
    lock keyed on sha256(user_id:key). write_idempotency inserts with
    `ON CONFLICT (user_id, key) DO NOTHING` and 24h default TTL.
  - api_server.middleware.rate_limit.RateLimitMiddleware — ASGI body:
    path→bucket map (POST /v1/runs → runs 10/min, POST /v1/lint → lint
    120/min, GET /v1/* → get 300/min); subject derivation gated by
    `AP_TRUSTED_PROXY` (default False → peer IP only; True → first
    X-Forwarded-For); 429 + `Retry-After` header on cap exceeded;
    fail-open on Postgres error.
  - api_server.middleware.idempotency.IdempotencyMiddleware — ASGI body
    scoped to POST /v1/runs only; drains + hashes request body; cache
    hit → replay cached verdict (200); mismatch → 422
    IDEMPOTENCY_BODY_MISMATCH; miss → pass through + capture response
    body via send-wrapper + write_idempotency on 200.
  - api_server/tests/test_rate_limit.py — 4 integration tests: SC-09
    (11th POST/runs → 429+Retry-After), lint 120/min, GET 300/min,
    T-19-05-01 XFF-spoof defense.
  - api_server/tests/test_idempotency.py — 4 integration tests: SC-06
    (same key returns cached run_id w/o re-running), body mismatch
    422, cross-user isolation via direct DB inserts, 24h TTL expiry
    forces re-run.
affects:
  - 19-07-PLAN (Hetzner deploy): a GC cron is needed against
    `idx_rate_limit_gc` and `idx_idempotency_expires` to prevent
    unbounded table growth. Recommended: `DELETE FROM
    rate_limit_counters WHERE window_start < NOW() - INTERVAL '1 hour'`
    every minute; `DELETE FROM idempotency_keys WHERE expires_at <
    NOW()` every hour.
  - 19-07-PLAN: The deploy must set `AP_TRUSTED_PROXY=true` when (and
    only when) Caddy is actually in front of api_server. Setting it
    True without a real trusted proxy in front would re-introduce
    T-19-05-01 (XFF-spoof bypass of the rate limiter).
  - Phase 19.5 (SSE streaming): the idempotency middleware currently
    only caches full JSON responses. When streaming lands, the cache
    semantics must change (either cache the terminal event + final
    JSON, or mark streaming responses as uncacheable). Documented as
    a known limitation in the middleware docstring.
  - Phase 21+ (real auth): `IdempotencyMiddleware` uses
    `ANONYMOUS_USER_ID` from `constants`. Swap for a
    `resolve_user_id(scope)` helper — no schema or query changes
    needed; `(user_id, key)` UNIQUE constraint already isolates.

# Tech tracking
tech-stack:
  added: []  # No new packages; everything was pinned by Plan 19-01
  patterns:
    - "Pattern 3 (RESEARCH.md): idempotency via pg_advisory_xact_lock
      on sha256(user_id:key). Advisory lock serializes concurrent
      first-use of the same key; the SELECT-then-INSERT under the lock
      is the canonical Stripe pattern for preventing N runs from N
      concurrent retries."
    - "Pattern 4 (RESEARCH.md, CORRECTED): fixed-window rate limit
      keyed on (subject, bucket, window_start). The original pattern
      sketch had a subtle SQL bug — ``date_trunc('second', NOW()) -
      (epoch::bigint % W) * 1s`` mis-computes window_start when the
      epoch fractional is ≥0.5 because ``::bigint`` rounds-to-nearest.
      Corrected formula: ``to_timestamp(floor(epoch / W) * W)``
      floors deterministically. This is Rule 1 deviation #1 below."
    - "ASGI body-capture + replay pattern: drain all ``http.request``
      messages into a buffer, hash it, then hand the downstream app a
      fresh ``receive`` callable that replays the captured bytes once
      and returns ``http.disconnect`` thereafter. Required for
      idempotency because the body is consumed by the read but the
      route handler still needs to deserialize it."
    - "ASGI send-wrapper response-capture pattern: wrap ``send`` so we
      see every ``http.response.start`` (captures status) and
      ``http.response.body`` chunk (captures body bytes) BEFORE they
      reach the wire. After the handler completes, if status==200 we
      can parse the captured body and write the idempotency cache
      row. Keeps the route handler untouched — no coupling between
      the route and the middleware."
    - "sha256-based lock key derivation (not Python's ``hash()``)
      because ``hash()`` is randomized per process via PYTHONHASHSEED;
      two uvicorn workers would compute DIFFERENT locks keys for the
      same (user_id, key) and the advisory lock would fail to
      serialize across them. sha256 is deterministic across processes."
    - "Fail-open on rate-limit backend error: a Postgres outage must
      NOT turn the whole site off. The middleware logs + passes
      through. Accepted per T-19-05-06. The alternative (fail-closed)
      would lock every user out during an infra hiccup."
    - "Trusted-proxy policy for XFF: ``AP_TRUSTED_PROXY=false``
      (default) IGNORES X-Forwarded-For entirely — anyone can spoof
      that header. Only when the deploy has a real trusted proxy
      (Caddy) in front should the flag flip. The plan's XFF-spoof
      test proves the default is safe."

key-files:
  created:
    - api_server/src/api_server/services/rate_limit.py
    - api_server/src/api_server/services/idempotency.py
    - api_server/tests/test_rate_limit.py
    - api_server/tests/test_idempotency.py
  modified:
    - api_server/src/api_server/middleware/rate_limit.py  # Overwrote Plan 19-02 pass-through stub with real body
    - api_server/src/api_server/middleware/idempotency.py  # Overwrote Plan 19-02 pass-through stub with real body
    - api_server/tests/test_run_concurrency.py  # Rate-limit bypass via distinct XFF per request + trusted_proxy=True

key-decisions:
  - "Window-start formula corrected during execution: the RESEARCH.md
    Pattern 4 sketch had a subtle SQL bug (30% flake rate on
    test_429_after_limit). ``EXTRACT(EPOCH FROM NOW())::bigint`` uses
    ROUND-TO-NEAREST when casting numeric→bigint, so at fractional
    epochs ≥ .5 the modulo computation is off by one second. Replaced
    with ``to_timestamp(floor(epoch / W) * W)`` which is deterministic.
    Verified: 10/10 consecutive runs pass after the fix."
  - "Advisory lock key uses ``hashlib.sha256`` (not Python ``hash()``).
    Python's built-in ``hash()`` is randomized per process via
    PYTHONHASHSEED — two uvicorn workers would compute different lock
    keys for the same (user_id, key). sha256 is deterministic across
    processes, so the advisory lock actually serializes multi-worker
    contention. Rate limiter uses ``hash()`` for the (subject, bucket)
    lock key — lower stakes because cross-worker collisions only
    serialize unrelated increments (never over- or under-count),
    documented as a future-hardening note in services/rate_limit.py."
  - "Only cache 200 responses in the idempotency middleware. 4xx and
    5xx are transient (auth failures, runner crashes, rate-limit
    hits) and caching them would lock in an error state for 24
    hours. Critically this also prevents the middleware from caching
    its own 429/422 responses — those come from outside the idempotency
    scope."
  - "Raw request bytes (not JSON-normalized) for ``hash_body``.
    Matches Stripe semantics: two byte-different payloads that happen
    to deserialize equivalently are still different requests from the
    client's perspective. Also cheaper: no re-parse + canonicalize
    pass per request. The mismatch detector gets stricter; legitimate
    clients sending the same body get identical hashes."
  - "Idempotency scope limited to POST /v1/runs. Caching GET responses
    would be confusing (clients don't send Idempotency-Key on GETs);
    caching POST /v1/lint would waste cache space (lint is
    deterministic on body, so redundant runs are cheap). D-01's spec
    explicitly targets /v1/runs."
  - "Test rate-limit-bypass for the concurrency tests. Plan 19-04's
    `test_concurrency_semaphore_caps` sends 50 POSTs from the same IP;
    with the new rate limiter that would 429 requests 11-50. Rather
    than disable the middleware in tests (a test-only path that
    silently diverges from prod), each request sends a distinct
    X-Forwarded-For with ``trusted_proxy=True`` flipped on the live
    app state for the duration of the test. The concurrency test still
    exercises the semaphore as designed, and the rate limiter's own
    coverage is the responsibility of test_rate_limit.py."
  - "Middleware class names + __init__ signatures are unchanged from
    the Plan 19-02 stubs. This preserves Wave 3's file-ownership
    contract — main.py was not touched in Plan 19-05, honoring the
    Wave 3 parallelism invariant. `git diff --stat
    api_server/src/api_server/main.py` returns empty."

patterns-established:
  - "Fixed-window rate limit with ``to_timestamp(floor(epoch / W) *
    W)`` — the ONLY SQL-only formula that produces deterministic
    window boundaries across arbitrary ``NOW()`` fractional parts.
    Any future rate-limit-like feature (Phase 22+ sliding window,
    burst detection, etc.) should start from this formulation, not
    the RESEARCH.md sketch which has the ``::bigint`` rounding bug."
  - "Stripe-shape idempotency: (a) scope the check to a UNIQUE
    constraint that mixes in the scope identifier (user_id here; in
    multi-tenant later, tenant_id + user_id), (b) hash the raw
    request body + store it for mismatch detection, (c) serialize
    first-use with ``pg_advisory_xact_lock`` on a deterministic key
    (sha256-based for multi-process correctness), (d) only cache
    2xx, (e) use ``ON CONFLICT DO NOTHING`` on the write so
    concurrent misses that both complete have a clear winner."
  - "ASGI middleware body-capture + replay: drain receive, hash,
    then hand the downstream app a fresh receive that replays once.
    Required whenever a middleware needs to both INSPECT the body
    AND let the route deserialize it."
  - "ASGI middleware response-capture: send-wrapper that pulls status
    + body chunks out of the stream before they reach the wire. The
    `send_wrapper` forwards every message unmodified so latency is
    unchanged; the captured chunks enable post-handler side effects
    (cache write, metric emission, audit log) without touching the
    route."

requirements-completed: [SC-06, SC-09]

# Metrics
duration: 17min
completed: 2026-04-17
---

# Phase 19 Plan 05: Rate-Limit + Idempotency Middleware Summary

**Replaced the Plan 19-02 pass-through middleware stubs with real bodies: Postgres-backed fixed-window rate limiter (10/min runs, 120/min lint, 300/min GETs per D-05) with XFF-spoof-safe subject derivation, and Stripe-shape idempotency on POST /v1/runs (24h TTL, UNIQUE (user_id, key) cross-user isolation, request_body_hash mismatch → 422, pg_advisory_xact_lock serializing concurrent first-use). Fixed a 30% flake in the RESEARCH.md window-start SQL formula (``::bigint`` rounds-to-nearest, not floor). Main.py untouched — Wave 3 file-ownership contract honored. 8 new integration tests green. 41/41 full suite stable across 5 consecutive runs.**

## Performance

- **Duration:** ~17 minutes (1048s wall time)
- **Started:** 2026-04-17T02:15:32Z
- **Completed:** 2026-04-17T02:33:00Z
- **Tasks:** 2
- **Files created:** 4 (services/rate_limit.py, services/idempotency.py, tests/test_rate_limit.py, tests/test_idempotency.py)
- **Files modified:** 3 (middleware/rate_limit.py, middleware/idempotency.py, tests/test_run_concurrency.py)
- **Commits:** 2 task commits (f8b5005 + 1c4ba36) + metadata commit

## Accomplishments

- **Rate limit middleware (SC-09).** `RateLimitMiddleware.__call__` maps (method, path) → bucket per D-05, derives subject as peer IP by default (XFF ignored unless `AP_TRUSTED_PROXY=true`, mitigating T-19-05-01), calls `check_and_increment` under `pg_advisory_xact_lock`, emits Stripe-shape 429 + `Retry-After` on cap exceeded, fails open on Postgres error. Class name + signature unchanged from Plan 19-02 stub — `main.py` stays wired.
- **Idempotency middleware (SC-06).** `IdempotencyMiddleware.__call__` scoped to `POST /v1/runs` only. Drains + SHA-256 hashes the raw request body, looks up `(user_id, key)` under `pg_advisory_xact_lock`. Three outcomes: `hit` → replay cached verdict as 200, `mismatch` → 422 `IDEMPOTENCY_BODY_MISMATCH` (T-19-05-03 mitigation via Pitfall 6 `request_body_hash`), `miss` → pass through via replay-receive, capture response via send-wrapper, write cache on 200. Caches only 200 responses — 4xx/5xx are transient and would lock in an error state.
- **Window-start SQL formula corrected.** The RESEARCH.md Pattern 4 sketch (`date_trunc('second', NOW()) - (epoch::bigint % W) * 1s`) had a subtle bug: `::bigint` uses round-to-nearest (not floor), so at fractional epochs ≥ .5 the computed `window_start` drifts by one second. Observed as a 30% flake on `test_429_after_limit` — two rows for the same logical window (one at `:59`, one at `:00`), 11 requests spread across them. Replaced with `to_timestamp(floor(epoch / W) * W)` which is deterministic for any NOW() value. Verified stable across 10 consecutive runs.
- **Services layer.** `services/rate_limit.check_and_increment(conn, subject, bucket, limit, window_s)` → `(allowed, retry_after_s)`. `services/idempotency.check_or_reserve(conn, user_id, key, body_hash)` → `("hit"|"miss"|"mismatch", cached_dict_or_None)`. `services/idempotency.write_idempotency(conn, user_id, key, body_hash, run_id, verdict_json, ttl_hours=24)`. All three functions accept a pre-acquired connection so the caller controls transaction scope. Parameters are passed via asyncpg `$1, $2, ...` placeholders — zero f-string SQL.
- **Threat register coverage.** T-19-05-01 (XFF-spoof) mitigated via `AP_TRUSTED_PROXY=false` default + regression test. T-19-05-02 (cross-user collision) proven via direct DB inserts with two `user_id`s using the same key `'abc'` — schema UNIQUE `(user_id, key)` makes it impossible. T-19-05-03 (body-mismatch reuse) mitigated via `request_body_hash` NOT NULL column + middleware 422 return. T-19-05-04 + T-19-05-05 (DoS via concurrent races) mitigated via `pg_advisory_xact_lock` in both services.
- **Wave 3 regression: 41/41 tests green across 5 consecutive runs.** The new middleware was required to not disrupt any of Plans 02/03/04's existing tests. Only `test_run_concurrency.py` needed a test-side adjustment (distinct XFF per request so the 10/min limit doesn't 429 the concurrency assertion). No runner regression: 175 runner tests still pass (SC-11 gate).

## Task Commits

Each task committed atomically:

1. **Task 1: services/rate_limit + services/idempotency** — `f8b5005` (feat)
2. **Task 2: middleware bodies + tests + SQL formula fix + concurrency-test bypass** — `1c4ba36` (feat)

_(Plan metadata commit comes next — see Final Commit section.)_

## Files Created/Modified

### Created

- `api_server/src/api_server/services/rate_limit.py` — `check_and_increment(conn, subject, bucket, limit, window_s) -> (allowed, retry_after_s)`. `pg_advisory_xact_lock` via `_lock_key(subject, bucket)` (positive int63 from Python `hash()`), then INSERT…ON CONFLICT DO UPDATE with corrected window-start formula and a RETURNING clause that exposes `count` + `age_s` for retry-after computation.
- `api_server/src/api_server/services/idempotency.py` — `hash_body(raw_bytes) -> str` (SHA-256 hex), `_lock_key(user_id, key) -> int` (SHA-256 digest first 8 bytes as signed int64 — cross-process deterministic), `check_or_reserve(conn, user_id, key, body_hash) -> CheckResult`, `write_idempotency(conn, user_id, key, body_hash, run_id, verdict_json, ttl_hours=24)`.
- `api_server/tests/test_rate_limit.py` — 4 `@api_integration` tests: `test_429_after_limit` (SC-09), `test_lint_bucket_allows_higher_rate` (120/min cap under test), `test_get_bucket_300_per_min` (300/min cap under test), `test_spoofed_xff_ignored_when_no_trusted_proxy` (T-19-05-01 XFF-spoof defense).
- `api_server/tests/test_idempotency.py` — 4 `@api_integration` tests: `test_same_key_returns_cache` (SC-06, counts runner invocations to prove zero re-run on replay), `test_body_mismatch_returns_422` (T-19-05-03), `test_same_key_different_users_isolated` (T-19-05-02 cross-user isolation via direct DB inserts staging a second user + agent_instance + run rows so FKs resolve), `test_expired_key_re_runs` (24h TTL: fast-forward `expires_at` into the past, then verify a new `run_id` is minted).

### Modified

- `api_server/src/api_server/middleware/rate_limit.py` — Overwrote the Plan 19-02 pass-through stub with a real body. Class name + `__init__` signature unchanged. Bucket derivation for POST /v1/runs, POST /v1/lint, GET /v1/*; all other paths (health, docs, openapi.json) pass through. XFF only honored when `app.state.settings.trusted_proxy` is true. 429 envelope emits `Retry-After` + `content-type: application/json` headers via direct ASGI `send` (doesn't construct a Starlette Response object — cheaper at the middleware layer).
- `api_server/src/api_server/middleware/idempotency.py` — Overwrote the Plan 19-02 pass-through stub with a real body. Scoped to POST /v1/runs only (early pass-through for every other method+path). Drains request body into a buffer, hashes with SHA-256, calls `check_or_reserve`. Uses `_replay_receive(body)` to rebuild an ASGI `receive` callable for the downstream app. On cache miss, wraps `send` to capture status + body chunks so `write_idempotency` can persist the verdict after a 200 completion. `ANONYMOUS_USER_ID` imported from `api_server.constants`.
- `api_server/tests/test_run_concurrency.py` — The plan's concurrency tests from Plan 19-04 make 50 + 10 POSTs from the same IP; the new 10/min limit would 429 requests 11-50. Adjusted both tests to set `async_client._transport.app.state.settings.trusted_proxy = True` and send a distinct `X-Forwarded-For` per request (`10.42.0.{i}` / `10.42.1.{i}`). Each request now has a distinct rate-limit subject — the rate limiter sees 50/10 single-subject counters of 1 each, never firing a 429. The semaphore + per-tag Lock assertions (the actual SC-07 targets) are unchanged.

## Decisions Made

1. **Window-start formula corrected in Task 2.** The RESEARCH.md Pattern 4 sketch had a subtle SQL bug: `date_trunc('second', NOW()) - (EXTRACT(EPOCH FROM NOW())::bigint % $3) * INTERVAL '1 second'`. The `::bigint` cast rounds-to-nearest (not floor), so at NOW() fractional epochs ≥ 0.5 the computed `window_start` drifts by one second. At runtime this manifested as two counter rows for the same logical window (one at `02:25:59`, one at `02:26:00`) — 11 POSTs in a burst spread across them, and the 11th lands on a fresh counter with count=1 instead of count=11. Replaced with `to_timestamp(floor(EXTRACT(EPOCH FROM NOW()) / $3) * $3)` which is deterministic. Verified 10/10 consecutive runs pass after the fix. (Documented inline in services/rate_limit.py.)

2. **sha256 for the idempotency advisory-lock key, `hash()` for the rate-limit advisory-lock key.** Python's `hash()` is randomized per process via `PYTHONHASHSEED`. For idempotency this is load-bearing: two uvicorn workers racing on the same `(user_id, key)` would compute different lock keys and the advisory lock wouldn't serialize them — so the key MUST be deterministic across processes. For rate limiting the stakes are lower: a cross-worker collision serializes unrelated `(subject, bucket)` pairs but never causes over- or under-counting, so Python `hash()` is acceptable. Documented as a future-hardening note in services/rate_limit.py.

3. **Only cache 200 responses in the idempotency middleware.** 4xx and 5xx are transient — auth failures, runner crashes, validation errors, rate-limit hits — and caching them would lock in an error state for 24 hours. Critically this also prevents the middleware from accidentally caching its own 429/422 responses, since those come from OUTSIDE the `idempotency` scope (the rate-limit middleware is wrapped outside `idempotency`).

4. **Raw request bytes for body hashing, not JSON-normalized.** Matches Stripe's semantics. Two byte-different payloads that deserialize equivalently are still different requests from the client's perspective. Also cheaper — no re-parse/canonicalize pass per request. The mismatch detector becomes stricter (legitimate clients sending the same bytes get the same hash), which is exactly the intended Stripe behavior.

5. **Fail-open on middleware backend error.** A Postgres outage must NOT turn the whole site off. Both middlewares log + pass through on DB exception. Accepted per T-19-05-06 (the rate-limit side) and the idempotency-docstring note. The alternative (fail-closed) would amplify transient infra hiccups into site-wide outages.

6. **Concurrency tests get a rate-limit bypass via distinct XFF, not a middleware disable.** Plan 19-04's `test_concurrency_semaphore_caps` sends 50 POSTs from the same IP — under the new 10/min limit, requests 11-50 would 429. Disabling the middleware for tests would silently diverge from prod. Instead both concurrency tests flip `app.state.settings.trusted_proxy = True` and send `X-Forwarded-For: 10.42.0.{i}` per request — each request has a distinct rate-limit subject, the limiter never fires, and the semaphore assertions stay the SC-07 target. The rate-limit coverage lives in `test_rate_limit.py` where it belongs.

7. **Middleware signatures preserved.** Both `RateLimitMiddleware` and `IdempotencyMiddleware` kept their class names + `__init__(self, app)` + `async def __call__(self, scope, receive, send)` signatures from Plan 19-02. `main.py` was not modified in this plan — proved by `git diff --stat api_server/src/api_server/main.py` returning empty. This honors the Wave 3 file-ownership contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] RESEARCH.md Pattern 4 SQL formula produced non-deterministic window_start values (30% flake rate on SC-09 test)**

- **Found during:** Task 2 live test run — `test_429_after_limit` intermittently reported all 11 requests returning 200 instead of the 11th 429-ing. Verified via a diagnostic `SELECT * FROM rate_limit_counters` dump during a failing run: two rows for what should have been one logical window (window_start `02:25:59` count=3, `02:26:00` count=8). The burst of 11 requests split across the two rows, so the 11th landed on a counter with count=8, below the 10 limit.
- **Root cause:** `EXTRACT(EPOCH FROM NOW())::bigint` uses round-to-nearest, not floor, when casting numeric→bigint. At `NOW() = 02:27:04.979927`: `EXTRACT(EPOCH)` = `1776392824.979927`, `::bigint` = `1776392825` (rounded UP from .98), `% 60` = `5`. But `date_trunc('second', NOW())` = `02:27:04`. `02:27:04 - 5 seconds` = `02:26:59`, which is NOT on a minute boundary. A request at `02:27:05.002` would compute `date_trunc` = `02:27:05`, `EXTRACT::bigint` = `1776392825`, `% 60` = `5`, `02:27:05 - 5s` = `02:27:00`. Different rows for requests 22ms apart.
- **Fix:** Replaced the formula with `to_timestamp(floor(EXTRACT(EPOCH FROM NOW()) / $3) * $3)`. `floor()` is deterministic on the float, and `to_timestamp()` converts back to a timestamptz aligned exactly on a `window_s`-second boundary. Verified stable across 10 consecutive runs (vs 3 failures in 10 before).
- **Files modified:** `api_server/src/api_server/services/rate_limit.py`
- **Verification:** 10 consecutive `pytest -m api_integration tests/test_rate_limit.py tests/test_idempotency.py` runs, all 8/8 green.
- **Committed in:** `1c4ba36` (Task 2 commit — the fix is inlined with the rest of the middleware work since the SQL lives in the service that the middleware calls).

**2. [Rule 3 — Blocking] Plan 19-04's concurrency tests 429'd under the new rate limiter**

- **Found during:** Wave 3 full-suite regression test — `test_concurrency_semaphore_caps` in `tests/test_run_concurrency.py` failed because 40 of its 50 POSTs returned 429 (correct behavior under the 10/min POST /v1/runs cap, but it broke the test's `all(c == 200 for c in codes)` assertion).
- **Root cause:** The concurrency test was written before the rate limiter existed; it assumed all 50 concurrent POSTs would succeed and only the semaphore would bound them. With the new limiter active, only the first 10 succeed per minute from any single subject.
- **Fix options considered:** (a) disable middleware in tests — rejected, diverges from prod, risks missing middleware-level regressions; (b) raise the limit via env — rejected, requires new config surface that only benefits tests; (c) use distinct subjects per request — selected, keeps the limiter active AND lets the concurrency test exercise 50 overlapping runs. Implemented via `app.state.settings.trusted_proxy = True` + distinct `X-Forwarded-For` per request (`10.42.0.{i}` / `10.42.1.{i}`). The rate limiter sees 50 single-subject counters (all count=1); never fires.
- **Files modified:** `api_server/tests/test_run_concurrency.py` (2 tests updated — outer and inner concurrency).
- **Verification:** Full 41-test suite (excluding the pre-existing alembic-PATH issue in Plan 19-01) passes 5/5 consecutive runs.
- **Committed in:** `1c4ba36` (Task 2 commit).

---

**Total deviations:** 2 auto-fixed (Rule 1 SQL bug + Rule 3 regression unblock).
**Impact on plan:** Both are mandatory to make the plan's own verification block pass + preserve Wave 3's cross-plan regression gate. No scope creep — both stay inside Plan 19-05's file-ownership boundary (services/rate_limit.py is this plan's file; the test_run_concurrency.py change is adjacent but fixes an issue DIRECTLY caused by this plan's middleware).

## Issues Encountered

- **Pre-existing `test_migration.py` errors (Plan 19-01 scope, unchanged):** 8 errors from an `alembic` PATH dependency. Documented as out of scope in Plans 19-02 / 19-03 / 19-04 SUMMARYs. Ran the suite with `--ignore=tests/test_migration.py` per prior-plan precedent; no new regressions introduced.
- **TDD cadence collapse:** Both tasks were marked `tdd="true"` but each collapsed into a single `feat` commit. Task 1's services have no downstream callers until Task 2 wires them, so a RED-first commit would be collection-time ImportError (not meaningful RED). Task 2's middleware-plus-tests lands as one unit because the tests import the middleware and the middleware imports the services — removing any layer breaks the other two. Matches Plans 19-02/03/04/06 precedents in this phase.
- **One Rule 1 bug (the SQL formula) had to be discovered via flake-hunting** rather than up-front analysis. I added a diagnostic DB-dump inline in the failing test, ran the suite ~15 times to catch a flake, captured the rate_limit_counters rows post-failure, saw two rows for one logical window, then computed the formula by hand with a microsecond-level fractional epoch to find the `::bigint`-rounds bug. Lesson for future phases: rate-limit-style tests SHOULD always include a DB-dump diagnostic on failure — otherwise the flake is opaque.

## Deferred Issues

- **GC for `rate_limit_counters` + `idempotency_keys`** is still not scheduled. Plan 19-07 (Hetzner deploy) is the natural place to add a cron:
  - `DELETE FROM rate_limit_counters WHERE window_start < NOW() - INTERVAL '1 hour'` every minute
  - `DELETE FROM idempotency_keys WHERE expires_at < NOW()` every hour
  - Both indexes (`idx_rate_limit_gc`, `idx_idempotency_expires`) are already in place from Plan 19-01. Without GC, both tables grow unbounded.
- **`test_migration.py` alembic-PATH dependency** (Plan 19-01 scope, unchanged from Plans 19-02/03/04): 8 errors carry over. Strictly out of scope for Plan 19-05. One-line fix inside Plan 19-01's test file (swap to `python -m alembic`).

## Known Stubs

None — every middleware path + every service function is wired to real Postgres-backed logic. No TODOs, no FIXMEs, no placeholder returns.

## User Setup Required

None. Integration tests use `testcontainers[postgres]` which manages its own Docker container lifecycle.

## Downstream Plan Integration

### Plan 19-07 (Hetzner deploy)

- **`AP_TRUSTED_PROXY`**: must be set to `true` in the prod `.env` ONLY after Caddy is actually in front of api_server. If set to `true` without a real trusted proxy, attackers can bypass the rate limiter via `X-Forwarded-For` spoofing (T-19-05-01 regresses). The default `false` in Plan 19-02's `config.py` is the safe default.
- **GC cron** for `rate_limit_counters` and `idempotency_keys`. See Deferred Issues above. Indexes already exist from Plan 19-01. Suggested one-liner for `deploy/deploy.sh` or a systemd timer.
- **Rate limit tuning**: current `(runs=10/min, lint=120/min, get=300/min)` values are hard-coded in `middleware/rate_limit.py::_LIMITS`. If prod telemetry shows the caps are too tight/loose, bump them — no code-architecture change needed, just an env-sourced dict if flexibility is wanted.

### Phase 19.5 (SSE streaming — deferred)

- The idempotency middleware currently only caches full JSON responses (the `send_wrapper` reconstructs `response_body_chunks` into a single `resp_body`). When `GET /v1/runs/{id}/events` lands, streaming responses cannot be cached the same way — either (a) mark streaming responses as uncacheable and skip the cache-write, or (b) cache the terminal event + a replay of the full stream (rebuilt from the DB, not from in-memory chunks). Option (a) is simpler and probably correct for Phase 19.5's scope; idempotency fundamentally fits one-shot request/response semantics.

### Phase 21+ (real auth)

- `IdempotencyMiddleware` uses `ANONYMOUS_USER_ID` from `api_server.constants`. When auth lands, swap for a `resolve_user_id(scope)` helper that reads the session cookie / Bearer token and resolves to a real user. The schema + queries are already user-scoped (`(user_id, key)` UNIQUE + `user_id` in the lock key); nothing else needs to change.
- `RateLimitMiddleware._subject_from_scope` currently always falls through to peer IP (no user is resolved yet). When auth lands, insert a check at the top: `if scope.get("state", {}).get("user_id"): return str(user_id)`. The Postgres counter table's `subject` column is already `TEXT` and accepts either a UUID-as-text or an IP string.

## How to Run the Tests

```bash
cd api_server

# Unit tier (no Docker, fast)
PYTHONPATH=src python3.11 -m pytest -q -m 'not api_integration'

# Plan 19-05 integration tests only (real Postgres via testcontainers)
PYTHONPATH=src python3.11 -m pytest -q -m api_integration \
    tests/test_rate_limit.py tests/test_idempotency.py
# => 8 passed

# Full phase-19 suite (everything except the pre-existing Plan 19-01
# alembic-PATH issue)
PYTHONPATH=src python3.11 -m pytest -q --ignore=tests/test_migration.py
# => 41 passed

# Runner regression gate (SC-11)
python3.11 -m pytest tools/tests/ -q
# => 175 passed
```

## Next Phase Readiness

- SC-06 + SC-09 green via integration tests; T-19-05-01, T-19-05-02, T-19-05-03 all exercised by tests that now live in `tests/test_rate_limit.py` + `tests/test_idempotency.py`.
- Middleware stack is complete for Phase 19. Plan 19-07 only needs to deploy the existing wiring — no new middleware classes expected.
- `main.py` remained untouched — Wave 3 file-ownership contract preserved through the final wave.
- Full test suite stable: 41/41 across 5 consecutive runs (the RESEARCH.md SQL-bug flake is fixed).
- 175 runner tests still pass — no regression to Phase 10/18 code paths.

## Threat Flags

None — no new threat surface beyond what the plan's `<threat_model>` declared. All T-19-05-01..07 mitigations are in place and verified (where applicable) by regression tests.

## Reference Docs

- 19-CONTEXT.md §D-01 (idempotency shape: 24h TTL, UNIQUE (user_id, key), Postgres from day 1)
- 19-CONTEXT.md §D-05 (rate limits: 10/min runs, 120/min lint, 300/min GETs; soft per-user/per-IP throttle)
- 19-CONTEXT.md §D-07 (POST /v1/runs flow — idempotency fires before create_run)
- 19-RESEARCH.md §Pattern 3 lines 289-332 (idempotency advisory-lock pattern)
- 19-RESEARCH.md §Pattern 4 lines 334-369 (rate-limit pattern — contains the SQL bug fixed here, see deviation #1)
- 19-RESEARCH.md §Pitfall 6 (request_body_hash for mismatch detection)
- 19-RESEARCH.md §Security Domain (XFF-spoof threat, AP_TRUSTED_PROXY gate)
- 19-02-SUMMARY.md (middleware stub contract + file-ownership contract for Wave 3)
- 19-04-SUMMARY.md (POST /v1/runs flow the idempotency middleware wraps)
- memory/feedback_no_mocks_no_stubs.md (real Postgres in tests via testcontainers)

## Self-Check: PASSED

Files verified to exist on disk:

- `api_server/src/api_server/services/rate_limit.py` — FOUND
- `api_server/src/api_server/services/idempotency.py` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` — FOUND (overwrite of Plan 19-02 stub)
- `api_server/src/api_server/middleware/idempotency.py` — FOUND (overwrite of Plan 19-02 stub)
- `api_server/tests/test_rate_limit.py` — FOUND
- `api_server/tests/test_idempotency.py` — FOUND
- `.planning/phases/19-api-foundation/19-05-SUMMARY.md` — FOUND (this file)

Commits verified in `git log`:

- `f8b5005` (Task 1 — services/rate_limit + services/idempotency) — FOUND
- `1c4ba36` (Task 2 — middleware bodies + tests + SQL formula fix + concurrency-test bypass) — FOUND

Live test results:

- `pytest -m api_integration tests/test_rate_limit.py tests/test_idempotency.py` → **8 passed** × 10 consecutive runs (flake eliminated)
- `pytest -q --ignore=tests/test_migration.py` → **41 passed** × 5 consecutive runs (Wave 3 regression green)
- `pytest tools/tests/ -q` → **175 passed** (SC-11 runner regression gate)
- `py_compile` on every created/modified file → exit 0
- `git diff --stat api_server/src/api_server/main.py` → empty (Wave 3 file-ownership contract preserved)
- Middleware class + signature assertions: `async def __call__` present in both; `check_and_increment` + `check_or_reserve` + `hash_body` + `write_idempotency` + `IDEMPOTENCY_BODY_MISMATCH` + `retry-after` + `x-forwarded-for` + `trusted_proxy` all present in expected files.

All plan success criteria (SC-06, SC-09) verified green via regression tests.

---

*Phase: 19-api-foundation*
*Plan: 05*
*Completed: 2026-04-17*
