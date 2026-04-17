---
phase: 19-api-foundation
plan: 01
subsystem: database
tags: [fastapi, alembic, asyncpg, postgres, sqlalchemy, pydantic, python-ulid, testcontainers]

# Dependency graph
requires:
  - phase: 18-schema-maturity
    provides: recipe schema v0.1.1 + run_recipe.py that Plan 19-04 will wrap
provides:
  - api_server/ Python package (pyproject.toml with all Phase 19 deps pinned)
  - Alembic async migration runtime (env.py reading DATABASE_URL, normalizing DSN to postgresql+asyncpg://)
  - 5 platform tables: users, agent_instances, runs, idempotency_keys, rate_limit_counters
  - Anonymous user row seeded (id=00000000-0000-0000-0000-000000000001)
  - pgcrypto extension installed (gen_random_uuid())
  - request_body_hash NOT NULL column on idempotency_keys (Pitfall 6 mitigation)
  - api_integration pytest marker registered
  - Integration test harness using testcontainers[postgres] Postgres 17
affects:
  - 19-02-PLAN (FastAPI skeleton + /readyz probes this schema)
  - 19-03-PLAN (recipe/lint endpoints)
  - 19-04-PLAN (POST /v1/runs reads/writes runs + agent_instances)
  - 19-05-PLAN (rate_limit_counters + idempotency_keys middleware)
  - 19-06-PLAN (log redaction middleware uses pytest fixtures planted here)
  - 19-07-PLAN (Hetzner deploy runs alembic upgrade head)

# Tech tracking
tech-stack:
  added:
    - fastapi==0.136.0
    - uvicorn[standard]>=0.44.0,<0.45
    - asyncpg>=0.31.0,<0.32
    - sqlalchemy>=2.0.49,<2.1
    - greenlet>=3.0 (Rule 2 deviation — required by SQLAlchemy async run_sync)
    - alembic>=1.18.4,<1.19
    - pydantic>=2.11
    - pydantic-settings>=2.0
    - python-ulid>=3.1.0,<4
    - structlog>=25.5.0,<26
    - asgi-correlation-id>=4.3.4,<5
    - ruamel.yaml>=0.17.21
    - jsonschema>=4.23
    - dev extras: pytest>=8, pytest-asyncio>=0.23, testcontainers[postgres]>=4.14.2, httpx>=0.27
  patterns:
    - Alembic async env.py using sqlalchemy.ext.asyncio.async_engine_from_config + pool.NullPool
    - DSN normalization (postgres:// / postgresql:// → postgresql+asyncpg://) at env.py layer so callers can pass whichever shape
    - Bare MetaData() (no ORM models) — DDL authored via op.create_table for full control
    - request_body_hash idempotency mitigation (Pitfall 6): same key + different body → 422, not replay
    - api_integration pytest marker — parallel to runner's integration marker; skipped by default

key-files:
  created:
    - api_server/pyproject.toml
    - api_server/src/api_server/__init__.py
    - api_server/tests/__init__.py
    - api_server/tests/conftest.py
    - api_server/README.md
    - api_server/alembic.ini
    - api_server/alembic/env.py
    - api_server/alembic/script.py.mako
    - api_server/alembic/README
    - api_server/alembic/versions/001_baseline.py
    - api_server/tests/test_migration.py
  modified: []

key-decisions:
  - "Pin greenlet>=3.0 explicitly rather than rely on sqlalchemy[asyncio] extra — pip on darwin-arm64 does not auto-install the extra, and SQLAlchemy's async run_sync requires greenlet at runtime"
  - "Plain (untyped) revision/down_revision assignments in 001_baseline.py to satisfy the plan's literal grep acceptance criteria; mako template retains Alembic's default typed annotations for future revisions"
  - "DSN normalization lives in env.py (not in the calling code) so both testcontainers' psycopg2-shaped URL and operator-supplied postgres:// URLs work without caller changes"
  - "Downgrade does NOT drop pgcrypto extension — treated as shared infrastructure other databases/schemas may depend on"

patterns-established:
  - "Alembic async env.py: async_engine_from_config + NullPool + DSN normalization + offline-mode rejection"
  - "Module-scoped testcontainers Postgres fixture with inline cleanup in constraint tests (full per-test TRUNCATE deferred to Plan 19-02 conftest)"
  - "api_integration marker for opt-in real-Postgres tests (session default is 'not api_integration')"

requirements-completed: [SC-08, SC-10]

# Metrics
duration: 6min
completed: 2026-04-17
---

# Phase 19 Plan 01: Database Schema + Alembic Migration Summary

**Async Alembic baseline applies 5 platform tables (users, agent_instances, runs, idempotency_keys, rate_limit_counters) to Postgres 17 with pgcrypto + anonymous user seed + Pitfall-6 request_body_hash NOT NULL column; verified end-to-end via testcontainers (8/8 integration tests green).**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-04-17T01:17:03Z
- **Completed:** 2026-04-17T01:23:09Z
- **Tasks:** 3
- **Files created:** 11
- **Files modified:** 0 (pure greenfield under `api_server/`)

## Accomplishments

- `api_server/` Python package bootstrapped (pyproject.toml, src layout, tests dir, README)
- Alembic async migration runtime set up (env.py + alembic.ini + script template + README)
- Single baseline revision (`001_baseline.py`) creates all 5 tables per CONTEXT.md D-06 with correct FK dependency ordering, unique constraints, indexes, and the pgcrypto extension
- Anonymous user row seeded inline (id=00000000-0000-0000-0000-000000000001) — Phase 19 has no auth yet; every request is attributed to this row until Phase 21 lands OAuth
- Pitfall 6 mitigation column (`idempotency_keys.request_body_hash TEXT NOT NULL`) present, asserted by test
- `api_integration` pytest marker declared, mirroring runner's `integration` marker convention
- Integration test (`tests/test_migration.py`) asserts the full schema shape against a real Postgres 17 container via testcontainers — 8/8 tests green (5.06s wall time when image cached)
- Schema invariants validated: upgrade-head is idempotent, downgrade-base → upgrade-head round-trips cleanly, unique constraints raise `asyncpg.UniqueViolationError`, `runs.id` accepts 26-char ULIDs

## Task Commits

Each task committed atomically:

1. **Task 1: Bootstrap api_server/pyproject.toml + package skeleton + tests directory** — `5c14be9` (feat)
2. **Task 2: Initialize Alembic async template + write 001_baseline.py migration with 5-table DDL + pgcrypto + anonymous seed** — `5275d08` (feat)
3. **Task 3: Write integration test that applies the baseline migration against a real testcontainers Postgres + asserts full schema shape** — `d8a4971` (test; includes Rule 2 deviation: greenlet pin amendment to pyproject.toml)

_(Plan metadata commit comes next — see Final Commit section.)_

## Files Created/Modified

### Created

- `api_server/pyproject.toml` — package metadata + all pinned runtime/dev dependencies + `api_integration` pytest marker
- `api_server/src/api_server/__init__.py` — package marker; exports `__version__ = "0.1.0"`
- `api_server/tests/__init__.py` — empty package marker for pytest discovery
- `api_server/tests/conftest.py` — placeholder commenting that Wave 2 (Plan 19-02) will populate with `postgres_container`, `db_pool`, `async_client`, `mock_run_cell` fixtures
- `api_server/README.md` — install/tests/migration command reference
- `api_server/alembic.ini` — Alembic config; `sqlalchemy.url` left empty (env.py injects at runtime)
- `api_server/alembic/env.py` — async env using `async_engine_from_config` + `pool.NullPool`; rejects offline mode; normalizes `postgres://` / `postgresql://` → `postgresql+asyncpg://`
- `api_server/alembic/script.py.mako` — stock async template for future `alembic revision` calls
- `api_server/alembic/README` — one-line pointer back to `api_server/README.md`
- `api_server/alembic/versions/001_baseline.py` — the 5-table baseline migration (189 lines)
- `api_server/tests/test_migration.py` — 8 test functions marked `@pytest.mark.api_integration`

### Modified

None (all files above were greenfield).

## Decisions Made

1. **Pin `greenlet>=3.0` explicitly** — SQLAlchemy's async `run_sync` pathway (which Alembic's async env.py uses) requires greenlet at runtime. SQLAlchemy exposes it via the `[asyncio]` extra, but pip on darwin-arm64 silently does NOT install the extra's deps when requested via the base package, so the pin is load-bearing.
2. **Plain untyped `revision = "..."` / `down_revision = None`** in `001_baseline.py` — chosen to satisfy the plan's literal grep-based acceptance criteria (`grep -q 'revision = "001_baseline"'` and `grep -q 'down_revision = None'`). The mako template retains Alembic's default typed annotations so future `alembic revision` calls produce canonical output.
3. **DSN normalization in env.py** (not in callers) — testcontainers emits a psycopg2-shaped URL, operators emit `postgres://` or `postgresql://`, Plan 19-02+ app code will emit `postgresql+asyncpg://`. Normalizing inside env.py keeps every call site simple.
4. **pgcrypto NOT dropped on downgrade** — it is shared infrastructure; other databases/schemas may depend on it. Downgrade reverses only the Plan-19-created tables.
5. **Module-scoped `pg` fixture** (not function-scoped) — testcontainers Postgres boot is ~3-5s; amortizing it across the 8 tests keeps the full integration suite under 6s. Per-test isolation is achieved via explicit cleanup in each constraint test's `finally` block; full TRUNCATE-per-test comes in Plan 19-02's conftest.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Missing Critical] Added `greenlet>=3.0` dependency**
- **Found during:** Task 3 (running the live integration test)
- **Issue:** `alembic upgrade head` failed with `ValueError: the greenlet library is required to use this function. No module named 'greenlet'`. SQLAlchemy 2.x's async `run_sync` (used by our async env.py) requires greenlet at runtime. The base `sqlalchemy` install on darwin-arm64 does not pull it in automatically.
- **Fix:** Added `greenlet>=3.0` to `api_server/pyproject.toml` `[project].dependencies` with an explanatory comment referencing the pitfall.
- **Files modified:** `api_server/pyproject.toml`
- **Verification:** `python3.11 -m pip install --user 'greenlet>=3.0'` + re-ran `pytest -m api_integration tests/test_migration.py -q` → 8 passed in 5.06s.
- **Committed in:** `d8a4971` (part of Task 3 commit)

**2. [Rule 3 — Blocking] Baseline revision uses untyped assignments**
- **Found during:** Task 2 (verification step)
- **Issue:** Plan's automated `<verify>` AST check validates `revision` and `down_revision` via `ast.literal_eval`, but the plan's `<acceptance_criteria>` uses `grep -q 'revision = "001_baseline"'` and `grep -q 'down_revision = None'` as literal strings. Alembic's stock async template generates typed annotations (`revision: str = "..."` / `down_revision: Union[str, None] = None`) which pass the AST check but fail the literal-grep criteria.
- **Fix:** Rewrote the identifier block at the top of `001_baseline.py` using plain assignments (no `: str` / `: Union[str, None]` annotations). Both the AST check and the literal grep pass. Mako template retains the typed annotations so future migrations are standard-shaped.
- **Files modified:** `api_server/alembic/versions/001_baseline.py`
- **Verification:** `grep -q 'revision = "001_baseline"' api_server/alembic/versions/001_baseline.py` → exit 0. Full AST + acceptance block re-run → all 14 criteria pass.
- **Committed in:** `5275d08` (Task 2 commit — in the initial file as written)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** Both auto-fixes necessary for completing the plan's success criteria. No scope creep — both changes were strictly required to make the plan's own verification blocks pass.

## Issues Encountered

- On first `pytest -m api_integration` run, all 8 tests errored at fixture setup with a greenlet ImportError from alembic's async run_sync path. Root-caused (per `memory/feedback_root_cause_first.md` — investigate before fixing) to SQLAlchemy's optional async extra not being pulled in by default on darwin-arm64. Fixed at the dependency-pin layer (Rule 2) rather than patching the env.py to avoid async — async is load-bearing for the rest of Phase 19.

## User Setup Required

None — no external service configuration required. The integration test uses `testcontainers[postgres]` which manages its own Docker container lifecycle.

## Downstream Plan Integration

- **Plan 19-02** (FastAPI skeleton + /healthz + /readyz): imports from `api_server` package, uses `DATABASE_URL` the same way env.py does. Will populate `tests/conftest.py` with the full fixture set. Will add an `alembic upgrade head` call to the session-scoped Postgres fixture so every integration test starts with a migrated DB.
- **Plan 19-03** (recipe/lint endpoints): no direct dependency on this schema — reads recipes from filesystem.
- **Plan 19-04** (POST /v1/runs): inserts into `runs` + upserts into `agent_instances`. Must use parameterized asyncpg queries (threat register T-19-03 mitigation).
- **Plan 19-05** (rate_limit + idempotency middleware): reads/writes `rate_limit_counters` and `idempotency_keys`; must write `request_body_hash` on every new idempotency row and compare on replay attempts (threat register T-19-02, Pitfall 6).
- **Plan 19-06** (log redaction middleware): no direct schema dependency.
- **Plan 19-07** (Hetzner deploy): deploy script runs `cd api_server && alembic upgrade head` after the Postgres compose service is healthy, before starting the api_server container.

## Next Phase Readiness

- `api_server/` package is importable and installable via `pip install -e 'api_server/[dev]'`.
- `alembic upgrade head` against any Postgres 17 (or compatible) database with `DATABASE_URL` set applies the baseline cleanly.
- `alembic downgrade base` reverses cleanly; `upgrade head` can then be replayed with no side effects.
- `pytest -m api_integration tests/test_migration.py -q` is a standing regression gate for future schema changes.
- No blockers for Plan 19-02.

## Self-Check: PASSED

Files verified to exist on disk:
- `api_server/pyproject.toml` — FOUND
- `api_server/src/api_server/__init__.py` — FOUND
- `api_server/tests/__init__.py` — FOUND
- `api_server/tests/conftest.py` — FOUND
- `api_server/README.md` — FOUND
- `api_server/alembic.ini` — FOUND
- `api_server/alembic/env.py` — FOUND
- `api_server/alembic/script.py.mako` — FOUND
- `api_server/alembic/README` — FOUND
- `api_server/alembic/versions/001_baseline.py` — FOUND
- `api_server/tests/test_migration.py` — FOUND

Commits verified in `git log`:
- `5c14be9` (Task 1) — FOUND
- `5275d08` (Task 2) — FOUND
- `d8a4971` (Task 3 + Rule 2 deviation) — FOUND

Live integration test: `pytest -m api_integration tests/test_migration.py -q` → **8 passed in 5.06s** (exit 0) against `postgres:17-alpine`.

---

*Phase: 19-api-foundation*
*Plan: 01*
*Completed: 2026-04-17*
