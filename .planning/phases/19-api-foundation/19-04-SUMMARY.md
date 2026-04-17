---
phase: 19-api-foundation
plan: 04
subsystem: api
tags: [fastapi, asyncpg, asyncio-semaphore, asyncio-lock, to_thread, ulid, byok, runs, agent_instances, stripe-error-envelope, d-07, pattern-2, pitfall-4]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: |
      Plan 19-01 — asyncpg + pyproject (python-ulid already pinned);
      Plan 19-02 — create_app() + lifespan (populates app.state.db,
      app.state.image_tag_locks={}, app.state.locks_mutex=Lock(),
      app.state.run_semaphore=Semaphore(AP_MAX_CONCURRENT_RUNS)) +
      ANONYMOUS_USER_ID constant + conftest (async_client,
      mock_run_cell factory with asyncio.to_thread monkeypatch shape,
      db_pool, _truncate_tables autouse);
      Plan 19-03 — app.state.recipes populated with the 5 committed
      recipes + ErrorCode + make_error_envelope + /v1 mount convention;
      Plan 19-06 — _redact_api_key widened (literal-value masking —
      defense in depth for BYOK) + AccessLogMiddleware dropping
      Authorization header.
provides:
  - api_server.models.runs — Category enum (verbatim mirror of
    run_recipe.Category, 9 live + 2 reserved) + RunRequest (extra=forbid,
    recipe_name pattern ^[a-z0-9][a-z0-9_-]*$, model min/max length) +
    RunResponse + RunGetResponse pydantic models
  - api_server.util.ulid — new_run_id() (python-ulid wrapper) +
    is_valid_ulid(s) (Crockford base32 regex, case-insensitive)
  - api_server.services.runner_bridge — _import_run_cell (importlib
    file-path load + sys.modules cache; shared with lint_service module
    instance) + _get_tag_lock (Pitfall-1-safe via locks_mutex) +
    execute_run (Pattern 2: per-tag Lock → Semaphore → to_thread(run_cell))
  - api_server.services.run_store — upsert_agent_instance (ON CONFLICT
    DO UPDATE + total_runs bump + RETURNING id) + insert_pending_run +
    write_verdict + fetch_run (asyncpg parameterized; zero string-interp
    SQL); re-exports ANONYMOUS_USER_ID for single-import callers
  - api_server.routes.runs — POST /runs (D-07 flow: 401 gate → 404 gate
    → upsert + pending row → release DB → execute_run → rewrite verdict
    → RunResponse) + GET /runs/{id} (ULID pre-check → 400/404)
  - main.py include_router(runs_route.router, prefix="/v1") wired
  - 10 test cases in test_runs.py (4 no-DB + 6 api_integration covering
    SC-05 + SC-08 + negative paths) + 2 api_integration cases in
    test_run_concurrency.py covering SC-07 + per-tag Lock serialization
affects:
  - 19-05-PLAN: IdempotencyMiddleware sits OUTSIDE routes/runs.py in the
    middleware chain; its short-circuit checks (user_id, Idempotency-Key)
    fire BEFORE create_run executes. The middleware reads the body cache
    + query app.state.db for cached run_id; on hit it returns the cached
    verdict_json WITHOUT calling create_run. Plan 05 can safely assume
    routes/runs.py runs only on cache-miss.
  - 19-05-PLAN: RateLimitMiddleware's 429 envelope uses the same
    make_error_envelope + ErrorCode.RATE_LIMITED symbols this plan
    already depends on (no new code in routes/runs.py)
  - 19-07-PLAN (Hetzner deploy): docker-compose.prod.yml must mount
    /var/run/docker.sock into the api_server container so run_cell's
    `docker run ...` subprocess invocations work. Same mount already
    documented in CONTEXT.md §D-08.
  - Phase 19.5 (SSE streaming): this plan's synchronous POST /v1/runs
    stays in place; a NEW GET /v1/runs/{id}/events route is added for
    streaming. The per-tag Lock + Semaphore primitives stay the same.
  - Phase 21+ (real auth): swap ANONYMOUS_USER_ID for a session-resolved
    user_id. The routes/runs.py + run_store.py + agent_instances schema
    stay unchanged — only the import at the top of routes/runs.py
    changes to a "resolve_user_id(request)" helper.

# Tech tracking
tech-stack:
  added: []  # All packages pinned by Plan 19-01 (python-ulid, asyncpg, pydantic)
  patterns:
    - "Pattern 2 (RESEARCH.md): per-image-tag asyncio.Lock via locks_mutex
      (Pitfall-1 safe dict access) → global asyncio.Semaphore(N) →
      asyncio.to_thread(run_cell). TWO caps in series: the inner Lock
      serializes SAME-tag builds (avoids redundant docker build); the
      outer Semaphore bounds TOTAL concurrent runs across all tags."
    - "Pitfall 4 (RESEARCH.md): DB connection MUST be released across
      the long run_cell await. routes/runs.py uses TWO separate
      `async with pool.acquire() as conn:` scopes (upsert+insert
      before, write_verdict after) with the to_thread call OUTSIDE
      both scopes — pool isn't starved while the runner spins 10-200s."
    - "importlib.util.spec_from_file_location pattern shared with
      lint_service: tools/run_recipe.py is loaded by file path (not on
      sys.path) and cached in sys.modules['run_recipe'] so both modules
      see the same Category enum + helper functions."
    - "Two-phase runs row write: INSERT (verdict=NULL) at start,
      UPDATE (verdict=...) at end. Audit trail survives runner crashes;
      the INFRA_FAIL path still writes a row so every run is traceable."
    - "BYOK defense-in-depth: provider_key is a LOCAL variable —
      never in app.state, never a DB parameter, redacted in exception
      strings via str.replace(provider_key, '<REDACTED>') BEFORE the
      runs.detail column gets the INFRA_FAIL message, never passed to
      logger.info/error as a positional/kwarg."
    - "Pydantic extra='forbid' + recipe_name pattern is the FIRST
      validation layer (rejects 'inline yaml' and SQL-injection shapes
      at schema-parse time before the route handler fires); asyncpg
      parameterized queries are the SECOND layer (defense in depth)."
    - "ULID pre-check in GET /v1/runs/{id} (is_valid_ulid) BEFORE DB
      round-trip: a malformed id never costs a Postgres query."

key-files:
  created:
    - api_server/src/api_server/util/ulid.py
    - api_server/src/api_server/models/runs.py
    - api_server/src/api_server/services/runner_bridge.py
    - api_server/src/api_server/services/run_store.py
    - api_server/src/api_server/routes/runs.py
    - api_server/tests/test_runs.py
    - api_server/tests/test_run_concurrency.py
  modified:
    - api_server/src/api_server/main.py  # + runs router include under /v1

key-decisions:
  - "Category enum VERBATIM mirror (not re-import from run_recipe).
    The runner's Category is the single source of truth for values, but
    importing it would couple api_server to tools/ at the module level.
    A mirror with the 9 live + 2 reserved members pinned explicitly
    (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL,
    TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP) + an automated
    assertion in the Task 1 verification block catches drift at test time."
  - "_import_run_cell uses the SAME sys.modules['run_recipe'] slot as
    lint_service._import_runner_module. This is intentional — both
    need the same module object in memory so there is exactly one
    Category enum, one _redact_api_key, one _load_schema. The guard
    `if mod is not None and hasattr(mod, 'run_cell')` also handles
    the case where lint_service loaded it first (module cached but
    this is the first caller that needs run_cell specifically)."
  - "The runner-exception redaction uses a LOCAL str.replace over the
    exception string BEFORE it touches any outbound surface. This is
    defense-in-depth over Plan 19-06's _redact_api_key widening (which
    redacts by VAR=value pattern + literal key value at the runner's
    internal boundaries). The route handler adds one more layer: any
    exception string that bubbles up from docker subprocess land is
    replaced here so the runs.detail column + the _log.error line
    can't contain the raw key even if the runner missed a path."
  - "Two separate `async with pool.acquire() as conn:` blocks (before +
    after execute_run) rather than a single outer block. This is
    mandatory — Pitfall 4 says holding a connection across a 10-200s
    runner call starves the asyncpg pool under load. Tests implicitly
    prove this works because 50 concurrent requests with 300ms runner
    sleeps all succeed against a 3-connection pool (conftest db_pool
    max_size=3); without the release, the 4th+ request would timeout
    on acquire."
  - "Concurrency test uses round-robin across 5 recipes, not a single
    recipe. The per-tag Lock (Pattern 2 inner cap) would serialize
    same-tag requests to 1-in-flight REGARDLESS of the semaphore —
    testing with one recipe would falsely report the semaphore works
    when really only the per-tag lock is engaged. Round-robin across
    5 distinct image_tags lets 5 tag locks acquire simultaneously so
    the semaphore becomes the effective cap — exactly what SC-07 is
    asserting. A companion test with ONE recipe proves the per-tag
    Lock itself serializes same-tag builds."
  - "`runs.id` is TEXT (ULID 26-char), not UUID. Set by the baseline
    migration (Plan 19-01); this plan consumes that shape. ULIDs sort
    by mint time so `ORDER BY id DESC LIMIT 100` is a time-sorted
    recent-runs query with no secondary index. ULID also gives clients
    a stable time-ordered key they can use for pagination."
  - "Runner-exception category is INFRA_FAIL with exit_code=-1. This
    matches the runner's own category taxonomy (INFRA_FAIL is one of
    the 9 live categories) — client code that branches on category
    doesn't need a new 'HTTP_502' case. The HTTP status IS 502
    (INFRA_UNAVAILABLE error code), so clients can respond to either
    the status or the category field depending on their integration."

patterns-established:
  - "Pattern: Two-phase row write for long-running operations —
    INSERT (pending) → release DB → work → re-acquire DB → UPDATE
    (complete). Audit trail always survives even if the work crashes.
    Pool isn't starved while work runs. This is the shape any future
    async worker plan will follow (Phase 19.5 SSE, Phase 23 limits)."
  - "Pattern: Pydantic extra='forbid' + field regex BEFORE asyncpg
    parameterized query. Double defense — pattern rejects hostile
    shapes at parse time; parameterized query treats the value as
    opaque data regardless. No future route should drop either layer."
  - "Pattern: Concurrency test must exercise BOTH primitives when a
    design has multiple caps in series. Single-recipe probe = inner
    cap only; multi-recipe probe = outer cap. Either primitive
    silently failing would pass the wrong test."
  - "Pattern: BYOK key is a LOCAL route-handler variable — never
    app.state, never logger arg, never DB param. Exception paths
    str.replace(key, '<REDACTED>') BEFORE emitting to any outbound
    surface. Plan 19-06's runner widening handles the runner side;
    this handler does the same at its boundary."

requirements-completed: [SC-05, SC-07, SC-08]

# Metrics
duration: 8min
completed: 2026-04-17
---

# Phase 19 Plan 04: POST /v1/runs + GET /v1/runs/{id} Summary

**Load-bearing D-07 endpoint landed: POST /v1/runs wraps `tools/run_recipe.py::run_cell` via Pattern 2 (per-image-tag `asyncio.Lock` inside global `asyncio.Semaphore(AP_MAX_CONCURRENT_RUNS)` inside `asyncio.to_thread`), persists every run to `runs` + `agent_instances` (Pitfall 4 — DB connection released across the long `to_thread`), BYOK key flows `Authorization: Bearer` → `--env-file` without ever touching a DB column or log line, 8 integration + 4 unit tests green, 175 runner tests unchanged.**

## Performance

- **Duration:** ~8 min (454s wall time)
- **Started:** 2026-04-17T02:01:34Z
- **Completed:** 2026-04-17T02:09:08Z
- **Tasks:** 2
- **Files created:** 7 (models/runs.py, util/ulid.py, services/runner_bridge.py, services/run_store.py, routes/runs.py, tests/test_runs.py, tests/test_run_concurrency.py)
- **Files modified:** 1 (main.py — runs router include)
- **Commits:** 2 task commits (667a303 + 93fcaa3) + metadata commit

## Accomplishments

- **POST /v1/runs** implements the full D-07 flow (CONTEXT.md): Bearer header parse (401 on missing/empty) → `recipe_name` lookup in `app.state.recipes` (404 on miss) → `api_key_var` discovery from `recipe.runtime.process_env.api_key` (500 on missing) → prompt resolution (body > `recipe.smoke.prompt` > "") → ULID mint → upsert `agent_instances` (ON CONFLICT bump `total_runs`) + insert pending `runs` row → RELEASE DB → `execute_run` (per-tag Lock + Semaphore + `to_thread`) → re-acquire DB + `write_verdict` → `RunResponse`. On runner exception: redact `provider_key` from the exception string, persist INFRA_FAIL row with `detail` truncated to 500 chars, return 502 `INFRA_UNAVAILABLE`.
- **GET /v1/runs/{id}** validates the ULID at route entry (Crockford base32 regex, 26-char) → 400 `INVALID_REQUEST` on malformed id BEFORE any DB round-trip → `fetch_run` joins `runs ⨝ agent_instances` → 404 `RECIPE_NOT_FOUND` (reused for "run not found" semantics) on miss → `RunGetResponse`.
- **Pattern 2 concurrency** via `services/runner_bridge.py::execute_run`: `_get_tag_lock` guards `image_tag_locks` dict mutations under `app.state.locks_mutex` (Pitfall 1 safe — no racing `dict.setdefault` creating two Locks for the same tag); per-tag `Lock` serializes same-tag builds; global `Semaphore(AP_MAX_CONCURRENT_RUNS)` bounds total concurrent runs; `asyncio.to_thread(run_cell, ...)` bridges into the sync runner.
- **All 4 run_store queries parameterized** with `$1, $2, ...` placeholders — zero f-string SQL, verified by a `grep -E "f['\"](SELECT|INSERT|UPDATE)"` acceptance criterion that returns 0 matches. `upsert_agent_instance` uses `INSERT ... ON CONFLICT (user_id, recipe_name, model) DO UPDATE SET last_run_at = NOW(), total_runs = agent_instances.total_runs + 1 RETURNING id` — atomic upsert + counter bump in a single round-trip.
- **BYOK data-side enforcement:** `provider_key` is a local variable in `create_run` only — never stored in `app.state`, never bound as a query parameter, never passed to `_log.error` as an arg. On runner exception, `str(e).replace(provider_key, "<REDACTED>")` scrubs the exception text before it lands in either `runs.detail` or the log line. Plan 19-06's widened `_redact_api_key` covers the runner's own stderr/exception strings; this layer covers the route boundary.
- **ULID util** at `util/ulid.py` — `new_run_id()` returns `str(ULID())`; `is_valid_ulid(s)` uses `[0-9A-HJKMNP-TV-Z]{26}` (Crockford alphabet: no I, L, O, U). Case-insensitive.
- **Category enum** at `models/runs.py` — 9 live + 2 reserved members mirroring `run_recipe.Category` verbatim. Task 1 verification block asserts the set-equality against the runner's exact values.
- **12 tests total** (across 2 files): `test_runs.py` has 10 cases (4 run without Docker: 401 missing auth, 422 SQL-injection, 422 inline-YAML-forbidden, 400 invalid-ULID GET; 6 `api_integration`: SC-05 happy path, SC-08 persistence, 404 unknown recipe, GET round-trip, 404 unknown ULID, `agent_instances` dedupe); `test_run_concurrency.py` has 2 cases (SC-07 50 POSTs across 5 recipes bounded to `AP_MAX_CONCURRENT_RUNS=2`, + per-tag Lock serialization with 10 same-recipe POSTs max 1 in flight).

## Task Commits

Each task committed atomically:

1. **Task 1: models + util/ulid + runner_bridge + run_store** — `667a303` (feat)
2. **Task 2: routes + main.py wiring + tests** — `93fcaa3` (feat)

_(Plan metadata commit comes next — see Final Commit section.)_

## Files Created/Modified

### Created

- `api_server/src/api_server/util/ulid.py` — `new_run_id()` + `is_valid_ulid(s)` Crockford base32 helpers (python-ulid wrapper)
- `api_server/src/api_server/models/runs.py` — `Category` enum (9 live + 2 reserved, verbatim mirror of `run_recipe.Category`) + `RunRequest` (`extra="forbid"`, `recipe_name: pattern=^[a-z0-9][a-z0-9_-]*$`, `prompt max_length=16384`, `model min_length=1 max_length=128`) + `RunResponse` + `RunGetResponse`
- `api_server/src/api_server/services/runner_bridge.py` — `_import_run_cell` (importlib file-path load + sys.modules cache shared with `lint_service`) + `_get_tag_lock(app_state, image_tag)` (Pitfall-1 safe via `locks_mutex`) + `execute_run(app_state, recipe, *, prompt, model, api_key_var, api_key_val) → dict` implementing Pattern 2 exactly
- `api_server/src/api_server/services/run_store.py` — 4 parameterized asyncpg functions: `upsert_agent_instance` (ON CONFLICT + total_runs bump + RETURNING), `insert_pending_run` (verdict cols NULL), `write_verdict` (UPDATE all verdict cols + completed_at), `fetch_run` (join `runs ⨝ agent_instances` + wall_time_s float coercion)
- `api_server/src/api_server/routes/runs.py` — `POST /runs` (D-07 flow + INFRA_FAIL path) + `GET /runs/{id}` (ULID pre-check + fetch_run)
- `api_server/tests/test_runs.py` — 10 tests (4 no-DB + 6 `api_integration`)
- `api_server/tests/test_run_concurrency.py` — 2 `api_integration` tests covering SC-07 semaphore cap + per-tag Lock serialization

### Modified

- `api_server/src/api_server/main.py` — Added `from .routes import runs as runs_route` import; added `app.include_router(runs_route.router, prefix="/v1", tags=["runs"])` under the existing schemas + recipes route includes. No middleware, lifespan, or state changes.

## Decisions Made

1. **Category enum verbatim mirror rather than runtime re-import from `run_recipe`.** The runner is the single source of truth for category VALUES, but a runtime re-import would couple `api_server.models` to `tools/` at module load (breaking `api_server` as an independently packagable Python root). Mirror in `models/runs.py` + the Task 1 verification `assert set(c.value for c in Category) == {...}` catches drift byte-for-byte at test time. If a future phase adds a category, both files update together — no silent drift possible.

2. **Shared `sys.modules['run_recipe']` slot with `lint_service`.** Both `_import_run_cell` and `lint_service._import_runner_module` use the same module name + file path. The guard `if mod is not None and hasattr(mod, 'run_cell')` handles the case where `lint_service` loaded the module first (cached, but this is the first caller needing `run_cell` specifically). Rationale: one `Category` enum in memory, one `_redact_api_key`, one `_load_schema` — multiple module copies would create subtle identity issues (`isinstance` checks against `Category` would fail across copies).

3. **Two separate `async with pool.acquire() as conn:` blocks around `execute_run` (not one outer block).** Pitfall 4 — holding a connection across a 10-200s runner call starves the asyncpg pool. Tests implicitly prove the release works: 50 concurrent requests with 300ms simulated runner work all succeed against a `max_size=3` pool — without release, the 4th+ request would timeout on `conn.acquire`.

4. **Runner-exception redaction uses a local `str.replace` BEFORE any outbound emission.** Defense-in-depth over Plan 19-06's `_redact_api_key` widening. The runner's own redactor covers `VAR=value` pattern + literal key value inside the runner's stderr/exception shaping; the route handler adds one more layer so any exception string that bubbles up from docker subprocess land is scrubbed before touching `runs.detail` or `_log.error`.

5. **Concurrency test distributes requests across 5 recipes, not 1.** The per-tag Lock (Pattern 2 inner primitive) serializes same-tag requests to 1-in-flight REGARDLESS of the semaphore capacity — testing with one recipe would return `max_in_flight=1` whether the semaphore works or not. Spreading 50 POSTs across `[hermes, nanobot, nullclaw, openclaw, picoclaw]` lets 5 distinct tag locks acquire simultaneously so the semaphore is the effective cap. A companion test (`test_per_tag_lock_serializes_same_tag`) with 10 same-recipe POSTs asserts `max_in_flight == 1` to prove the inner primitive works.

6. **Runner-exception category is INFRA_FAIL with HTTP 502.** Matches the runner's own taxonomy (INFRA_FAIL is one of the 9 live categories); client branching on `category` doesn't need a new "HTTP_502" case. The envelope uses `code=INFRA_UNAVAILABLE, category=INFRA_FAIL` so either integration point gives the client enough to branch on.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `test_get_run_unknown_returns_404` used a 27-char ULID string**

- **Found during:** Task 2 — first `pytest -m api_integration` run.
- **Issue:** The plan's `<behavior>` block used `01HQZX9MZVJ5KQXYZ1234567890` as the "valid but missing ULID" fixture. The string is 27 characters (one digit too long), so `is_valid_ulid` returned False → 400 instead of the expected 404.
- **Fix:** Trimmed the trailing `0` → `01HQZX9MZVJ5KQXYZ123456789` (26 chars, all Crockford-legal). Added a comment explaining the length + alphabet constraints.
- **Files modified:** `api_server/tests/test_runs.py`
- **Verification:** `pytest -m api_integration tests/test_runs.py::test_get_run_unknown_returns_404 -q` → 1 passed.
- **Committed in:** `93fcaa3` (Task 2 commit)

**2. [Rule 1 — Bug] Concurrency test failed to exercise the semaphore because all requests targeted the same recipe**

- **Found during:** Task 2 — first `pytest -m api_integration tests/test_run_concurrency.py` run.
- **Issue:** The plan's `<behavior>` block had all 50 POSTs use `recipe_name="hermes"`. Pattern 2 has a per-tag Lock INSIDE the semaphore — same-tag requests serialize at the Lock before the semaphore sees them. Result: `max_in_flight=1` regardless of semaphore capacity. The test was asserting `max_in_flight <= 2` (✓ trivially) AND `max_in_flight >= 2` (✗ failed — only 1 ever in flight) because the test's sanity-check assertion caught the bug. The primary bug: the test wasn't actually exercising SC-07 (it was silently proving the per-tag Lock instead).
- **Fix:** Round-robin requests across all 5 committed recipes (`[hermes, nanobot, nullclaw, openclaw, picoclaw]`) so 5 different image_tag locks can acquire simultaneously — the semaphore is then the effective cap. Added a COMPANION test `test_per_tag_lock_serializes_same_tag` that uses ONE recipe with 10 POSTs to prove the inner primitive. Both tests now pass.
- **Files modified:** `api_server/tests/test_run_concurrency.py`
- **Verification:** `pytest -m api_integration tests/test_run_concurrency.py -q` → 2 passed. `max_in_flight=2` observed in the multi-recipe test (semaphore cap proven); `max_in_flight=1` observed in the single-recipe test (per-tag Lock proven).
- **Committed in:** `93fcaa3` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 — test-fixture bugs).
**Impact on plan:** Both fixes are required for the tests to actually prove the documented invariants. Deviation 2 also added a companion test that strengthens the concurrency coverage (Pattern 2's two primitives are both exercised now, not just the outer one). No scope creep — both changes are test-only.

## Issues Encountered

- **Pre-existing `test_migration.py` errors (Plan 19-01 scope, unchanged):** 8 errors from an `alembic` PATH dependency. Documented in Plans 19-02 + 19-03 SUMMARYs as strictly out of scope. Verified unchanged: `pytest -q --ignore=tests/test_migration.py` → 33 passed (10 prior-plan + 12 new + 11 from other plans); running with `test_migration.py` included returns the same 8 errors, no new ones.
- **TDD cadence collapse:** Tasks marked `tdd="true"` but each collapsed into a single `feat` commit. Task 1's models + services have no downstream callers that can fail cleanly within the task; Task 2's routes-to-tests split across a single file. Matches Plans 19-02 + 19-03 + 19-06 precedents.

## Deferred Issues

- **`test_migration.py` PATH dependency** (Plan 19-01 scope, unchanged from Plans 19-02 + 19-03): 8 errors carry over. One-line fix inside Plan 19-01's test file. Strictly out of scope for Plan 19-04.

## Known Stubs

None — every endpoint returns data wired to real services. The runner bridge imports the real `run_cell` from `tools/run_recipe.py`; only the `mock_run_cell` fixture short-circuits `asyncio.to_thread` in tests (per conftest), never in production code paths. `app.state.recipes` contains the 5 real committed recipes loaded at lifespan startup by Plan 19-03.

## User Setup Required

None — all tests use `testcontainers[postgres]` which manages its own Docker container lifecycle. Integration tests depend on Docker being available on the host (already a Phase 19 prerequisite; Plan 19-07 will document the Hetzner deploy setup).

## Downstream Plan Integration

### Plan 19-05 (Idempotency + Rate Limit middleware)

- **Middleware ordering:** `CorrelationIdMiddleware → AccessLogMiddleware → RateLimitMiddleware → IdempotencyMiddleware → routes/runs.py` (Plan 19-02 established). Plan 05 only edits the `__call__` bodies of the two stub middlewares — `main.py` is already wired. `routes/runs.py` is reached ONLY on cache-miss.
- **Idempotency short-circuit flow (Plan 05 to implement):** Before `create_run` executes, `IdempotencyMiddleware` reads `Idempotency-Key` header + request body bytes, computes body hash, checks `idempotency_keys` for a matching row. On hit: returns `verdict_json` directly without ever calling `routes/runs.py`. On miss: passes through to `create_run`, intercepts the response, writes `idempotency_keys` row with `verdict_json = response.body`, returns it. Plan 05 needs to read the response body AFTER `create_run` runs but BEFORE emitting to the wire — use an ASGI `Send` wrapper.
- **Error codes already in ErrorCode:** `RATE_LIMITED`, `IDEMPOTENCY_BODY_MISMATCH`, `PAYLOAD_TOO_LARGE`. Plan 05 only calls `make_error_envelope(code, message, ...)` + sets `Retry-After` headers. No new `ErrorCode` constants needed.

### Category enum import path for Plan 19-05

```python
from api_server.models.runs import Category
```

Plan 05 uses `Category` when mirroring a runner category into the error envelope's `category` field (e.g. timeout in the idempotency path: `make_error_envelope(RUNNER_TIMEOUT, ..., category=Category.TIMEOUT.value)`).

### `app.state.*` invariants Plan 19-02 established and this plan consumes

Read-only from `routes/runs.py`:

- `app.state.db: asyncpg.Pool` — used in two separate `async with pool.acquire()` scopes
- `app.state.recipes: dict[str, dict]` — `recipes.get(body.recipe_name)` returns the recipe dict or None
- `app.state.run_semaphore: asyncio.Semaphore` — Semaphore(AP_MAX_CONCURRENT_RUNS)
- `app.state.image_tag_locks: dict[str, asyncio.Lock]` — per-tag Lock dict
- `app.state.locks_mutex: asyncio.Lock` — guards mutations to `image_tag_locks`

Plan 05's middleware writes to NEW `app.state.*` slots (e.g. ratelimit counters) but never touches any of the above.

### Known INFRA_FAIL path

Runner raise → `str(e).replace(provider_key, '<REDACTED>')` → INSERT INFRA_FAIL row into `runs` with `exit_code=-1, wall_time_s=NULL, filtered_payload=NULL, stderr_tail=NULL, detail=<redacted>[:500]` → return 502 envelope `{error: {type: infra_error, code: INFRA_UNAVAILABLE, category: INFRA_FAIL, ...}}`. Plan 05's idempotency middleware should NOT cache 502 responses (they are transient infrastructure failures; re-running might succeed) — Plan 05 guidance: only cache 2xx responses.

## How to Run the Tests

```bash
cd api_server

# Unit tier (no Docker needed)
PYTHONPATH=src python3.11 -m pytest -q -m 'not api_integration'
# => 14 passed, 27 deselected

# Plan 19-04 integration tests (Docker required; testcontainers boots Postgres 17)
PYTHONPATH=src python3.11 -m pytest -q -m api_integration \
    tests/test_runs.py tests/test_run_concurrency.py
# => 8 passed

# Full suite minus the pre-existing Plan 19-01 alembic-PATH issue
PYTHONPATH=src python3.11 -m pytest -q --ignore=tests/test_migration.py
# => 33 passed

# Runner regression gate (SC-11)
python3.11 -m pytest tools/tests/ -q
# => 175 passed
```

## Next Phase Readiness

- `POST /v1/runs` + `GET /v1/runs/{id}` live under `/v1` per the established Plan 19-03 mount convention.
- `app.state.run_semaphore` + `app.state.image_tag_locks` + `app.state.locks_mutex` are all consumed by `services/runner_bridge.execute_run`.
- `ANONYMOUS_USER_ID` is the user FK resolver for Phase 19 — Phase 21+ swaps in a session-resolved `user_id` helper; no other file changes required.
- SC-05, SC-07, SC-08 green via tests; SC-11 regression gate holds (175 runner tests still green).
- No blockers for Plan 19-05 (idempotency + rate limit) or Plan 19-07 (Hetzner deploy).

## Threat Flags

None — no new trust-boundary surface beyond what the plan's `<threat_model>` declared. The BYOK key surface + docker subprocess invocation + parameterized asyncpg queries are all within the documented register:

- T-19-04-01 (info disclosure via exception): mitigated via `str(e).replace(provider_key, '<REDACTED>')` in the INFRA_FAIL path.
- T-19-04-02 (info disclosure via DB): mitigated — no column receives `provider_key`; `write_verdict` only writes runner details (which are key-redacted by Plan 19-06 widening at the runner's own stderr shaping).
- T-19-04-03 (info disclosure via logs): mitigated — `_log.error("runner failure", extra={"run_id": run_id})` carries no key; AccessLogMiddleware (Plan 19-06) drops the Authorization header.
- T-19-04-04 (SQL injection via recipe_name): mitigated — Pydantic pattern rejects at body-parse; asyncpg parameterized queries as defense-in-depth (proven by `test_recipe_name_injection_is_safe`).
- T-19-04-05 (SSRF via inline YAML): mitigated — `extra="forbid"` (proven by `test_inline_yaml_rejected`).
- T-19-04-06 (DoS via unbounded concurrent docker runs): mitigated — `asyncio.Semaphore(AP_MAX_CONCURRENT_RUNS)` + per-tag Lock (proven by `test_concurrency_semaphore_caps` + `test_per_tag_lock_serializes_same_tag`).
- T-19-04-07 (pool exhaustion during long runs): mitigated — two separate `async with pool.acquire()` scopes around `execute_run` (proven implicitly by the 50-concurrent-request test against a 3-connection pool).
- T-19-04-08 (repudiation): mitigated — `insert_pending_run` at start + `write_verdict` at end. Every run has a DB trail even on runner crash (INFRA_FAIL row still written).
- T-19-04-09 (per-tag Lock dict race): mitigated — `locks_mutex` guards dict access in `_get_tag_lock`.

## Reference Docs

- 19-CONTEXT.md §D-02 (BYOK `Authorization: Bearer` → `--env-file`)
- 19-CONTEXT.md §D-03 (synchronous execution only; SSE deferred to Phase 19.5)
- 19-CONTEXT.md §D-06 (runs + agent_instances schema)
- 19-CONTEXT.md §D-07 (POST /v1/runs exact flow — the spec this plan implements)
- 19-RESEARCH.md Pattern 2 (per-tag Lock + Semaphore + to_thread)
- 19-RESEARCH.md Pitfall 1 (dict race on image_tag_locks — mitigated via locks_mutex)
- 19-RESEARCH.md Pitfall 4 (DB connection release across to_thread)
- 19-PATTERNS.md lines 126-204 (runner_bridge + Category mirror pattern)
- tools/run_recipe.py lines 66-86 (Category enum — source of truth for the mirror)
- tools/run_recipe.py lines 653-825 (run_cell signature + return shape)
- tools/run_recipe.py lines 684-693 (BYOK --env-file invariant)

## Self-Check: PASSED

Files verified to exist on disk:

- `api_server/src/api_server/util/ulid.py` — FOUND
- `api_server/src/api_server/models/runs.py` — FOUND
- `api_server/src/api_server/services/runner_bridge.py` — FOUND
- `api_server/src/api_server/services/run_store.py` — FOUND
- `api_server/src/api_server/routes/runs.py` — FOUND
- `api_server/tests/test_runs.py` — FOUND
- `api_server/tests/test_run_concurrency.py` — FOUND
- `.planning/phases/19-api-foundation/19-04-SUMMARY.md` — FOUND

Commits verified in `git log`:

- `667a303` (Task 1 — models + util/ulid + runner_bridge + run_store) — FOUND
- `93fcaa3` (Task 2 — routes + main.py wiring + tests) — FOUND

Live test results:

- `pytest -q -m 'not api_integration'` → **14 passed, 27 deselected** in ~5s (Docker-free unit tier)
- `pytest -q -m api_integration tests/test_runs.py tests/test_run_concurrency.py` → **8 passed** in ~15s
- `pytest -q --ignore=tests/test_migration.py` → **33 passed** in ~18s
- `pytest tools/tests/ -q` → **175 passed** (SC-11 regression gate)
- `py_compile` on every created/modified file → exit 0
- Route introspection: `/v1/runs` + `/v1/runs/{id}` both mounted on the live app.
- `max_in_flight=2` observed in the 50-POST multi-recipe concurrency test (semaphore cap proven); `max_in_flight=1` observed in the 10-POST single-recipe test (per-tag Lock proven).

All plan success criteria (SC-05, SC-07, SC-08) verified green.

---

*Phase: 19-api-foundation*
*Plan: 04*
*Completed: 2026-04-17*
