---
phase: 19-api-foundation
plan: 02
subsystem: api
tags: [fastapi, pydantic-settings, asyncpg, structlog, lifespan, asgi, middleware, healthz, readyz, testcontainers, httpx, pytest-asyncio]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: |
      Plan 19-01 — api_server/ pyproject + Alembic baseline migration +
      PostgresContainer/asyncpg baseline; Plan 19-06 — CorrelationIdMiddleware
      re-export + AccessLogMiddleware + util/redaction.py + minimal /healthz
      stub (this plan overwrites the stub with the full D-04 split).
provides:
  - api_server.main:create_app() FastAPI factory + async lifespan (pool, recipes, image_tag_locks, locks_mutex, run_semaphore, settings) — the skeleton every downstream plan mounts onto
  - api_server.config:Settings (pydantic-settings BaseSettings, env-driven — AP_ENV, DATABASE_URL, AP_MAX_CONCURRENT_RUNS, AP_RECIPES_DIR, AP_TRUSTED_PROXY)
  - api_server.db:create_pool / close_pool / probe_postgres (asyncpg with DSN normalization stripping `+asyncpg` driver hint)
  - api_server.log:configure_logging (structlog JSON in prod, console in dev)
  - api_server.constants:ANONYMOUS_USER_ID (shared module unblocking Wave 3 parallelism for Plans 04 + 05)
  - api_server.middleware.rate_limit:RateLimitMiddleware (no-op stub; Plan 05 fills body)
  - api_server.middleware.idempotency:IdempotencyMiddleware (no-op stub; Plan 05 fills body)
  - api_server.routes.health:router — thin /healthz + rich /readyz per CONTEXT.md D-04 (docker_daemon + postgres + schema_version + recipes_count + concurrency_in_use)
  - api_server tests/conftest.py — full fixture set: postgres_container (session), migrated_pg (session), db_pool (function), _truncate_tables (autouse with lazy migrated_pg resolution), async_client, mock_run_cell factory
  - api_server tests/test_health.py — SC-02 unit + integration coverage
  - api_server tests/test_docs_gating.py — SC-12 unit coverage
affects:
  - 19-03-PLAN (recipe/lint routes mount onto this create_app; Plan 03 populates app.state.recipes at lifespan time)
  - 19-04-PLAN (POST /v1/runs uses app.state.run_semaphore + app.state.image_tag_locks + app.state.locks_mutex; imports ANONYMOUS_USER_ID from constants)
  - 19-05-PLAN (rate_limit + idempotency middleware stubs are already in the middleware stack — Plan 05 only edits the __call__ bodies; imports ANONYMOUS_USER_ID from constants)
  - 19-06-PLAN (retroactively consumed — this plan wires CorrelationIdMiddleware + AccessLogMiddleware into main.py)
  - 19-07-PLAN (deploy Dockerfile CMD targets api_server.main:app)

# Tech tracking
tech-stack:
  added: []  # Every package was already pinned by Plan 19-01's pyproject.toml
  patterns:
    - "create_app() factory + async lifespan + app.state (mutable process-wide state owned by the lifespan)"
    - "Middleware declared innermost-first via app.add_middleware so the last call is the outermost wrap — CorrelationId outermost, Idempotency innermost"
    - "DSN normalization at the asyncpg boundary (strip `+asyncpg` driver hint that Alembic uses but asyncpg rejects)"
    - "structlog bootstrap with env-switched renderer (JSONRenderer prod, ConsoleRenderer dev) + cache_logger_on_first_use"
    - "OpenAPI UI gating per D-10 (docs_url + redoc_url None in prod) with /openapi.json always public for frontend type-gen"
    - "Placeholder middleware stubs to lock file ownership for Wave 3 parallel execution — Plan 05 edits only the __call__ body, main.py is already wired"
    - "Fixture lazy-resolution via request.getfixturevalue() to prevent autouse cleanup fixtures from force-pulling session-scoped Postgres in unit tests"

key-files:
  created:
    - api_server/src/api_server/constants.py
    - api_server/src/api_server/config.py
    - api_server/src/api_server/db.py
    - api_server/src/api_server/log.py
    - api_server/src/api_server/main.py
    - api_server/src/api_server/middleware/rate_limit.py
    - api_server/src/api_server/middleware/idempotency.py
    - api_server/src/api_server/services/__init__.py
    - api_server/tests/test_health.py
    - api_server/tests/test_docs_gating.py
  modified:
    - api_server/src/api_server/routes/health.py  # Overwrote Plan 19-06's minimal /healthz stub with the full D-04 split (thin /healthz + rich /readyz)
    - api_server/tests/conftest.py  # Plan 19-01 shipped a placeholder; now holds the full fixture set

key-decisions:
  - "Middleware order honored the plan body (CorrelationId outermost, Idempotency innermost) — not the wave_context shorthand that said 'AccessLog outermost'. Rationale: CorrelationId must mint the X-Request-Id BEFORE AccessLog reads it, otherwise the access log record can't reflect the minted id. 19-06 SUMMARY's prose agrees despite its own terminology slip."
  - "Settings (pydantic-settings) read at create_app() time (not inside lifespan). Tests monkeypatch env before calling create_app(); tests would not observe the change if Settings() were cached or built at import."
  - "Invoke alembic via `python -m alembic` in migrated_pg (not the `alembic` console script) — works regardless of whether the console script is on PATH, which varies by install layout."
  - "Autouse _truncate_tables resolves migrated_pg LAZILY via request.getfixturevalue() rather than listing it as a fixture parameter. Listing as parameter forces pytest to realize the session-scoped container on every test, including Docker-free unit tests like test_docs_gating.py."
  - "Dropped reliance on asyncpg Pool internals for DSN extraction (the original plan sketch used db_pool._connect_kwargs['dsn'] which doesn't exist — the DSN actually lives in _connect_args[0]). async_client now requests migrated_pg directly and pulls the DSN from the testcontainers object instead."
  - "Intentional deletion of the minimal /healthz stub landed by Plan 19-06: the current file is a complete overwrite per that plan's own 'Downstream Plan Integration' note."

patterns-established:
  - "app.state is the canonical place for per-process mutable state owned by the lifespan — future plans reference app.state.{db,recipes,image_tag_locks,locks_mutex,run_semaphore,settings}"
  - "Environment-gated OpenAPI UI: docs_url/redoc_url conditional on AP_ENV; /openapi.json always exposed (frontend type-gen contract)"
  - "Thin routes/health.py split: /healthz is the LB-probe invariant (never touches deps), /readyz is the operator-facing rich envelope"
  - "conftest _truncate_tables autouse pattern — skips the DB request unless test's fixturenames include db_pool or async_client; resolves migrated_pg lazily to avoid eager container boot"

requirements-completed: [SC-02, SC-12, SC-10]

# Metrics
duration: 7min
completed: 2026-04-17
---

# Phase 19 Plan 02: FastAPI Foundation + Health/Readyz Summary

**FastAPI app factory with async lifespan owning the asyncpg pool + per-image-tag lock dict + global run semaphore + recipes cache; thin /healthz (never touches deps) and rich /readyz (docker_daemon + postgres + schema_version + recipes_count + concurrency_in_use) split per CONTEXT.md D-04; env-gated /docs per D-10; middleware stack wiring CorrelationId → AccessLog → RateLimit stub → Idempotency stub; testcontainers+asyncpg+httpx conftest with TRUNCATE-per-test isolation and a mock_run_cell factory ready for Wave 3.**

## Performance

- **Duration:** ~7 minutes (424s wall time)
- **Started:** 2026-04-17T01:36:22Z
- **Completed:** 2026-04-17T01:43:26Z
- **Tasks:** 2
- **Files created:** 10
- **Files modified:** 2 (routes/health.py overwrite + conftest.py replacement)

## Accomplishments

- `api_server.main:create_app()` + `app` module-level target for `uvicorn api_server.main:app`. Lifespan owns `app.state.db` (asyncpg pool verified via SELECT 1), `app.state.recipes` (dict to be filled by Plan 03), `app.state.image_tag_locks` (dict), `app.state.locks_mutex` (asyncio.Lock), `app.state.run_semaphore` (asyncio.Semaphore bound by `AP_MAX_CONCURRENT_RUNS`), `app.state.settings` (frozen Settings snapshot).
- `GET /healthz` — thin LB probe, returns `{"ok": true}` unconditionally, `include_in_schema=False`. Verified at import level that it has NO asyncpg or docker reference, proving the D-04 no-deps invariant.
- `GET /readyz` — rich envelope `{"ok", "docker_daemon", "postgres", "schema_version", "recipes_count", "concurrency_in_use"}`, `schema_version="ap.recipe/v0.1"`, `concurrency_in_use = max_concurrent_runs - semaphore._value` (in-use count, not remaining capacity). Docker probe wraps `subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], timeout=5)` in `asyncio.to_thread` to keep the event loop responsive.
- `AP_ENV`-gated OpenAPI UI: `/docs` + `/redoc` present iff `AP_ENV=dev`, both 404 in `prod`. `/openapi.json` always present (frontend type-gen contract per D-10).
- Placeholder middleware modules `rate_limit.py` + `idempotency.py` installed as no-op ASGI pass-throughs; main.py wires them into the stack already. Plan 19-05 will ONLY edit the `__call__` bodies — main.py stays untouched when Wave 3 lands.
- `ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")` lives in `api_server.constants`. Plans 04 and 05 both import from there — the shared module unblocks Wave 3 file ownership without either plan touching the other's files.
- `tests/conftest.py` now exposes the full fixture set promised by Plan 19-01: `postgres_container`, `migrated_pg`, `db_pool`, autouse `_truncate_tables`, `async_client`, and `mock_run_cell` factory. Unit tests still run Docker-free thanks to lazy `migrated_pg` resolution.
- `tests/test_health.py` (2 tests, 1 unit + 1 integration) and `tests/test_docs_gating.py` (3 tests, all unit): 5/5 green.

## Task Commits

Each task committed atomically. No TDD RED cycle ran because the tests collected in each task import modules that must exist at import time — a strict RED commit would be collection-time ModuleNotFoundError, not a clean red test. This matches the Plan 19-06 Task 2 precedent and its TDD-gate observation.

1. **Task 1: config + db + log + main + middleware stubs + constants** — `14632e7` (feat)
2. **Task 2: routes/health.py D-04 expansion + conftest full fixtures + test_health + test_docs_gating** — `f244634` (feat)

_(Plan metadata commit comes next — see Final Commit section.)_

## Files Created/Modified

### Created

- `api_server/src/api_server/constants.py` — `ANONYMOUS_USER_ID` UUID literal matching the Alembic-seeded `users` row. Shared module owned by this plan; imported by Plans 04 + 05 in Wave 3.
- `api_server/src/api_server/config.py` — `Settings` (pydantic-settings v2) + `get_settings()`. Fields: `database_url` (no prefix), `env`, `max_concurrent_runs`, `recipes_dir`, `trusted_proxy` (all `AP_`-prefixed).
- `api_server/src/api_server/db.py` — `create_pool` (asyncpg `create_pool` + DSN normalization + `SELECT 1` verify), `close_pool` (None-tolerant), `probe_postgres` (2s timeout, swallows exceptions).
- `api_server/src/api_server/log.py` — `configure_logging(env)` structlog bootstrap; shared processor list, env-switched final renderer.
- `api_server/src/api_server/main.py` — `lifespan` ctx manager + `create_app()` factory + module-level `app = create_app()`. Middleware declaration bottom-up: `IdempotencyMiddleware` (innermost), `RateLimitMiddleware`, `AccessLogMiddleware`, `CorrelationIdMiddleware` (outermost). Includes `health.router` only; Plans 03/04 include their own routers under `/v1`.
- `api_server/src/api_server/middleware/rate_limit.py` — ASGI stub `RateLimitMiddleware`; `__call__` body is `await self.app(scope, receive, send)` with `TODO(plan 19-05)` marker.
- `api_server/src/api_server/middleware/idempotency.py` — ASGI stub `IdempotencyMiddleware`; same pass-through shape with `TODO(plan 19-05)` marker.
- `api_server/src/api_server/services/__init__.py` — package marker for the services subtree (Plans 03/04 populate).
- `api_server/tests/test_health.py` — `test_healthz_is_trivial` (no fixtures, bare FastAPI with just the router, proves no-deps invariant) + `test_readyz_live` (`@api_integration`, full envelope shape assertion against migrated Postgres).
- `api_server/tests/test_docs_gating.py` — 3 unit tests proving SC-12 contract (dev: `/docs`+`/redoc`+`/openapi.json` present; prod: only `/openapi.json`).

### Modified

- `api_server/src/api_server/routes/health.py` — Overwrote Plan 19-06's minimal-/healthz-only stub with the full D-04 shape. `ReadyzResponse` pydantic model, `_probe_docker_sync`/`_probe_docker` helpers (subprocess + `asyncio.to_thread`), `DOCKER_DAEMON_PROBE_TIMEOUT_S = 5` constant mirrored from the runner. The intentional rewrite was flagged in 19-06 SUMMARY §"Downstream Plan Integration".
- `api_server/tests/conftest.py` — Plan 19-01 shipped a placeholder docstring; this plan populates it with the full fixture set.

## Decisions Made

1. **Middleware order matches the plan body, not the wave_context shorthand.** The spawn prompt said "AccessLogMiddleware outermost, CorrelationIdMiddleware inside"; the plan body said the opposite. The plan body is right: CorrelationId must mint `X-Request-Id` BEFORE AccessLog reads it off scope headers, otherwise the access-log record's `x-request-id` allowlisted field cannot reflect the minted id. 19-06 SUMMARY's prose also agrees despite its own terminology slip.
2. **`Settings()` is constructed at `create_app()` time**, not at module import time or inside the lifespan. Tests monkeypatch env before calling the factory; caching Settings at import (e.g. via `@lru_cache`) would break that contract. No cache is used.
3. **`python -m alembic` rather than the `alembic` console script** in `migrated_pg`. The script isn't always on PATH depending on how the dev extras were installed (user-site vs system-site vs venv). Module invocation always works as long as the package is importable.
4. **Lazy `migrated_pg` resolution in autouse `_truncate_tables`.** Listing `migrated_pg` as a fixture parameter forces pytest to realize the session-scoped Postgres container on every test — including `test_docs_gating.py` which has no DB needs. Using `request.getfixturevalue("migrated_pg")` inside the body only triggers the realization when the test actually requested `db_pool` or `async_client`.
5. **`async_client` accepts `migrated_pg` directly for DSN extraction.** The plan sketch accessed `db_pool._connect_kwargs["dsn"]` which doesn't exist in the installed asyncpg version — the DSN lives in `_connect_args[0]`. Pulling from the testcontainers object instead avoids asyncpg-version-dependent internals.
6. **Documentation-only note about the 19-06 → 19-02 health.py handoff.** The overwrite was already documented in 19-06 SUMMARY; this plan honored that contract exactly. Post-commit deletion check verified no unexpected file deletions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Autouse `_truncate_tables` force-pulled session-scoped Postgres into unit tests**

- **Found during:** Task 2 verification (`pytest tests/test_docs_gating.py -q`)
- **Issue:** The first pass of conftest declared `async def _truncate_tables(request, migrated_pg)` — listing `migrated_pg` as a parameter forces pytest to realize the session-scoped Postgres container + run alembic for every single test, including `test_docs_gating.py` which is a pure unit test with no DB needs. The test crashed with `FileNotFoundError: [Errno 2] No such file or directory: 'alembic'` because `alembic` is not on PATH in this dev environment (only `python -m alembic` is).
- **Fix:** Two-part fix: (a) `migrated_pg` now invokes `alembic` via `sys.executable -m alembic upgrade head` so it works regardless of PATH state; (b) `_truncate_tables` drops the `migrated_pg` parameter and resolves it lazily via `request.getfixturevalue("migrated_pg")` only when the test's `fixturenames` include `db_pool` or `async_client`.
- **Files modified:** `api_server/tests/conftest.py`
- **Verification:** `pytest tests/test_docs_gating.py -q` → 3 passed in 0.20s (no Postgres container started — fast unit run). `pytest -m api_integration tests/test_health.py -q` → 1 passed in 4.08s (container boots on demand).
- **Committed in:** `f244634` (Task 2 commit — fix landed inline with the conftest creation).

**2. [Rule 3 — Blocking] `db_pool._connect_kwargs["dsn"]` raises KeyError in `async_client`**

- **Found during:** First run of `pytest -m api_integration tests/test_health.py::test_readyz_live`
- **Issue:** The plan's sketch had `async_client` pull the DSN out of `db_pool._connect_kwargs["dsn"]`. In the asyncpg version pinned by 19-01 (`asyncpg>=0.31,<0.32`), `Pool._connect_kwargs` is an empty dict — the DSN actually lives in `Pool._connect_args[0]` (positional arg). The result was `KeyError: 'dsn'` at fixture setup and the integration test never ran.
- **Fix:** Added `migrated_pg` as a direct fixture dependency on `async_client` and pulled the DSN from `migrated_pg.get_connection_url()` via `_normalize_testcontainers_dsn`. The testcontainers object is the canonical source of truth for the connection URL anyway — sidesteps asyncpg internals entirely.
- **Files modified:** `api_server/tests/conftest.py`
- **Verification:** `pytest -m api_integration tests/test_health.py::test_readyz_live -q` → 1 passed in 4.08s. Full integration envelope assertions green.
- **Committed in:** `f244634` (Task 2 commit).

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking issues preventing test verification from passing).
**Impact on plan:** Both deviations are required to make the plan's own `<acceptance_criteria>` + `<verification>` blocks pass. No scope creep — both are in-task fixes to conftest.py, the file Task 2 owns. No change to the production code paths.

## Issues Encountered

- **`test_migration.py` (owned by Plan 19-01) fails under the current local environment** with `FileNotFoundError: 'alembic'`. Its `_alembic` helper shells out to the `alembic` console script directly rather than `python -m alembic`; the console script is not on PATH in this environment (only importable as a Python module). This is NOT a regression introduced by Plan 19-02 — the file is unchanged — and fixing it is out of scope per the deviation rule "only auto-fix issues DIRECTLY caused by the current task's changes". Logged as a Deferred Issue below so the verifier can see it was observed but not addressed here. **No impact on Plan 19-02 success criteria** — all 11 tests owned by 19-02 + 19-06 pass cleanly.
- **TDD cadence:** Both tasks are marked `tdd="true"` in the plan but neither produced a clean RED→GREEN split. Task 1's files are imports-only (Task 2's tests import them) so a test-first commit would have nothing to fail against. Task 2's tests import `main.create_app` and `routes.health.router` — collection-time ModuleNotFoundError is not a meaningful RED cycle. Both tasks collapse into single `feat` commits, matching the Plan 19-06 Task 2 precedent documented in that plan's TDD Gate Compliance section. The spawn prompt did not require strict TDD gate enforcement; neither does the plan's `<verification>` block.

## Deferred Issues

- **test_migration.py alembic-binary PATH dependency (pre-existing, Plan 19-01 scope):** 8 of the 9 errors from `pytest -q` (integration tier) are `FileNotFoundError: 'alembic'` from `tests/test_migration.py::TestBaselineMigration`. The file invokes `subprocess.run(["alembic", ...])` rather than `[sys.executable, "-m", "alembic", ...]`. When 19-01 executed, the environment had `alembic` on PATH (likely via a site-packages shim that has since vanished or a different virtualenv). Fix is a one-line change inside 19-01's test file — strictly out of scope for Plan 19-02. Recommended next-plan or housekeeping commit: swap to `python -m alembic` following the pattern established by 19-02's conftest.

## User Setup Required

None — no external service configuration required. The integration tier uses `testcontainers[postgres]` which manages its own Docker container lifecycle. The `DATABASE_URL` env for local dev is documented in `api_server/README.md` (unchanged from Plan 19-01).

## Downstream Plan Integration

- **Plan 19-03 (Wave 3):** Imports `from api_server.main import create_app`; adds a `routes.schemas`, `routes.recipes`, `routes.lint` router suite; populates `app.state.recipes` inside the lifespan (this plan initializes it to `{}`). Tests mount their router onto the app factory and reuse the `async_client` fixture established here.
- **Plan 19-04 (Wave 3):** Imports `ANONYMOUS_USER_ID` from `api_server.constants`. Uses `app.state.run_semaphore`, `app.state.image_tag_locks`, `app.state.locks_mutex` inside the runner bridge. Uses `mock_run_cell` fixture from conftest for unit tests of the POST /v1/runs route.
- **Plan 19-05 (Wave 3):** Edits ONLY `middleware/rate_limit.py::RateLimitMiddleware.__call__` and `middleware/idempotency.py::IdempotencyMiddleware.__call__` — main.py is already wired. Imports `ANONYMOUS_USER_ID` from `api_server.constants`. Uses the `async_client` fixture + a new `rate_limit_test_helpers` fixture it adds itself.
- **Plan 19-07:** `CMD ["uvicorn", "api_server.main:app", ...]` targets the module-level `app` created here. The healthcheck invariant `curl -sf http://localhost:8000/healthz` is exactly what this plan delivered.

## How to Run the Tests

```bash
cd api_server

# Quick tier (no Docker needed, runs in ~0.3s)
PYTHONPATH=src python3.11 -m pytest -q -m 'not api_integration'
# => 10 passed, 9 deselected

# Integration tier (requires Docker; testcontainers boots Postgres 17)
PYTHONPATH=src python3.11 -m pytest -q -m api_integration tests/test_health.py
# => 1 passed, 1 deselected (test_readyz_live)

# Full plan-02 coverage (unit + integration for files owned by this plan + 19-06)
PYTHONPATH=src python3.11 -m pytest -q tests/test_health.py tests/test_docs_gating.py tests/test_log_redact.py
# => 11 passed in ~4s
```

## Next Phase Readiness

- `api_server.main:create_app()` is a stable contract. Plans 03/04/05 import from it unchanged.
- `app.state` keys established: `db`, `recipes`, `image_tag_locks`, `locks_mutex`, `run_semaphore`, `settings`. Plans 03/04/05 read/write these; no one else owns main.py.
- Middleware slots for rate-limit + idempotency are pre-wired. Plan 05 edits `__call__` bodies only.
- `ANONYMOUS_USER_ID` shared import path is live (`api_server.constants`).
- Conftest fixture set is ready for Wave 3: `async_client`, `db_pool`, `mock_run_cell`, `_truncate_tables` autouse isolation.
- **No blockers for Wave 3.** Plan 19-01's `test_migration.py` PATH issue is a pre-existing environmental quirk that does not affect any Wave 3 plan's dependencies.

## Threat Flags

None — no new threat surface beyond the threats already declared in the plan's `<threat_model>`.

## Reference Docs

- 19-CONTEXT.md §D-04 (health + readiness split shape — verbatim in this plan)
- 19-CONTEXT.md §D-10 (env-gated /docs + always-on /openapi.json)
- 19-PATTERNS.md lines 287-321 (health.py pattern), lines 349-375 (main.py analog), lines 381-430 (conftest fixture shape)
- 19-RESEARCH.md §Pattern 1 (lifespan + app.state), §Pitfall 4 (release DB conn before long work)
- 19-06-SUMMARY.md §Downstream Plan Integration (the 19-02 overwrite contract for routes/health.py)
- memory/feedback_no_mocks_no_stubs.md (real Postgres via testcontainers; no in-memory shortcuts for the DB layer)

## Self-Check: PASSED

Files verified to exist on disk:

- `api_server/src/api_server/constants.py` — FOUND
- `api_server/src/api_server/config.py` — FOUND
- `api_server/src/api_server/db.py` — FOUND
- `api_server/src/api_server/log.py` — FOUND
- `api_server/src/api_server/main.py` — FOUND
- `api_server/src/api_server/middleware/rate_limit.py` — FOUND
- `api_server/src/api_server/middleware/idempotency.py` — FOUND
- `api_server/src/api_server/services/__init__.py` — FOUND
- `api_server/src/api_server/routes/health.py` — FOUND (overwritten from 19-06 stub)
- `api_server/tests/conftest.py` — FOUND (replaced 19-01 placeholder)
- `api_server/tests/test_health.py` — FOUND
- `api_server/tests/test_docs_gating.py` — FOUND

Commits verified in `git log`:

- `14632e7` (Task 1 — factory + config + db + log + middleware stubs) — FOUND
- `f244634` (Task 2 — routes/health D-04 overwrite + conftest + tests) — FOUND

Live test results:

- `pytest -q -m 'not api_integration'` → **10 passed, 9 deselected in 0.23s** (unit tier, Docker-free)
- `pytest -q -m api_integration tests/test_health.py` → **1 passed, 1 deselected in 4.08s** (live Postgres envelope)
- `pytest -q tests/test_health.py tests/test_docs_gating.py tests/test_log_redact.py` → **11 passed in ~4s**
- `python3.11 -m py_compile` on every created file → exit 0
- Middleware order assertion: `CorrelationIdMiddleware (outermost) → AccessLogMiddleware → RateLimitMiddleware → IdempotencyMiddleware (innermost)` — matches the plan body.
- Environment-gated /docs check: `AP_ENV=dev` → routes contain `/docs, /redoc, /openapi.json`; `AP_ENV=prod` → routes contain only `/healthz, /openapi.json`.

All plan success criteria (SC-02, SC-12, SC-10) verified green.

---

*Phase: 19-api-foundation*
*Plan: 02*
*Completed: 2026-04-17*
