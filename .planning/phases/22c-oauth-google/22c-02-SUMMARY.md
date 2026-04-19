---
phase: 22c-oauth-google
plan: 02
subsystem: database
tags: [alembic, postgres, schema, sessions, oauth, additive-migration]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: plan 22c-01 Wave 0 spike gate (SPIKE-A respx+authlib PASS, SPIKE-B TRUNCATE-CASCADE PASS Mode B); CONTEXT §D-22c-MIG-02 + §D-22c-MIG-04
  - phase: 19-api-foundation
    provides: alembic baseline (001) + ANONYMOUS seed row at 00000000-0000-0000-0000-000000000001
  - phase: 22-channels-v0.2
    provides: alembic 002 (agent_instances.name) + 003 (agent_containers) + 004 (agent_events)
provides:
  - alembic migration 005 (sessions + users OAuth columns) applied on live deploy-postgres-1 — alembic_version=005_sessions_and_oauth_users
  - sessions table (8 columns, PK on id, btree on user_id, FK to users.id ON DELETE CASCADE) ready for 22c-04 SessionMiddleware SELECT/INSERT
  - users.sub + users.avatar_url + users.last_login_at (all nullable) ready for 22c-05 OAuth callback UPSERT
  - UNIQUE (provider, sub) partial index WHERE sub IS NOT NULL — lets 22c-05 upsert on (provider, sub) while preserving ANONYMOUS seed row's NULL sub
  - integration test test_migration_005_sessions_and_users_columns passes on host venv (testcontainers PG 17)
  - deferred-items.md tracking 3 pre-existing Phase 19 test failures + conftest DSN issue (all out of scope per plan pointer)
affects: [22c-04, 22c-05, 22c-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive-only schema migration convention: new columns default NULL, no backfill, fully reversible via op.drop_column + op.drop_index + op.drop_table (reverse order of upgrade)"
    - "Partial unique index for nullable composite key: UNIQUE (provider, sub) WHERE sub IS NOT NULL — lets a seeded NULL-sub row coexist with OAuth-populated (provider, sub) rows"
    - "Live-infra migration application: docker cp migration file into deploy-api_server-1 (bind-mounts only /app/recipes, not /app/api_server); run alembic upgrade head via docker exec against the running compose PG — image rebuild deferred until CI/prod deploy"

key-files:
  created:
    - api_server/alembic/versions/005_sessions_and_oauth_users.py
    - .planning/phases/22c-oauth-google/deferred-items.md
  modified:
    - api_server/tests/test_migration.py

key-decisions:
  - "Additive-only migration — no ALTER of existing columns, no data backfill; ANONYMOUS seed row (provider=NULL, sub=NULL) keeps passing the partial-unique-index predicate because WHERE sub IS NOT NULL excludes it"
  - "Ship the plan's snippet verbatim, keep the new test OUTSIDE the TestBaselineMigration class — TestBaselineMigration uses its own module-scoped pg+migrated fixtures; the new test uses the session-scoped migrated_pg from conftest.py to avoid spawning a second PG container"
  - "Do NOT modify conftest.py — plan line 39 explicitly says 'conftest.py fix happens in 22c-06'. Honor that pointer; integration test runs from host venv for now"
  - "Log pre-existing test failures to deferred-items.md instead of auto-fixing — 3 TestBaselineMigration tests (test_runs_id_is_text_not_uuid + two more) were already failing on main before 22c-02 started, rooted in a Phase-22 NOT-NULL column Phase-19 tests never got updated for"

patterns-established:
  - "Migration verification on live PG — upgrade → downgrade -1 → upgrade round-trip test BEFORE closing the task; ANONYMOUS preservation is the load-bearing check for any schema change touching users"
  - "deferred-items.md for phase-scoped out-of-scope discoveries — keeps the executor from expanding scope while keeping the backlog visible"

requirements-completed: [R2, R3, R4, R5, R8]

# Metrics
duration: 5min
completed: 2026-04-19
---

# Phase 22c-oauth-google Plan 02: Alembic 005 (sessions + users OAuth) Summary

**Alembic migration 005 (additive schema change) shipped and applied live. sessions table ready; users has sub/avatar_url/last_login_at columns; UNIQUE(provider, sub) partial index preserves the NULL-sub ANONYMOUS seed. Wave 1 for OAuth Google unblocks.**

## Performance

- **Duration:** 5 min (commit timestamps: 23:40Z → 23:45Z)
- **Started:** 2026-04-19T23:39:38Z
- **Completed:** 2026-04-19T23:45Z
- **Tasks:** 2 (both autonomous, no checkpoints)
- **Commits:** 2 (`ec19e7f` feat, `9e7db7e` test)
- **Files:** 2 created + 1 modified

## Accomplishments

- **Migration 005 authored, applied, and round-tripped against live Postgres 17** (`deploy-postgres-1`). upgrade → downgrade -1 → upgrade — clean both ways. alembic_version advanced to `005_sessions_and_oauth_users`.
- **sessions table live** — 8 columns in exact ordinal order: `id`, `user_id`, `created_at`, `expires_at`, `last_seen_at`, `revoked_at`, `user_agent`, `ip_address`. PK on `id` (UUID, server default `gen_random_uuid()`). FK `user_id → users.id ON DELETE CASCADE`. Non-unique btree `ix_sessions_user_id`. Nullable: `revoked_at`, `user_agent`, `ip_address`.
- **users extended** — 3 new nullable columns: `sub TEXT`, `avatar_url TEXT`, `last_login_at TIMESTAMPTZ`. Non-destructive — existing rows (including the ANONYMOUS seed) default to NULL in all three.
- **Partial unique index `uq_users_provider_sub`** — `UNIQUE (provider, sub) WHERE sub IS NOT NULL`. Confirmed with psql: `CREATE UNIQUE INDEX uq_users_provider_sub ON public.users USING btree (provider, sub) WHERE (sub IS NOT NULL)`. ANONYMOUS row (`id=00000000-0000-0000-0000-000000000001, provider=NULL, sub=NULL`) sits outside the predicate and stays valid.
- **Integration test green on host venv** — `test_migration_005_sessions_and_users_columns` PASSED in 3.55s against a fresh `postgres:17-alpine` testcontainer spun by conftest's `migrated_pg` fixture.
- **3 pre-existing test failures documented** in `deferred-items.md` (not caused by this plan, confirmed by stashing the 22c-02 change and re-running on clean main).

## Verification Evidence (live psql output, deploy-postgres-1)

### 1. alembic advanced to 005
```
         version_num
------------------------------
 005_sessions_and_oauth_users
(1 row)
```

### 2. sessions table schema
```
                              Table "public.sessions"
    Column    |           Type           | Collation | Nullable |      Default
--------------+--------------------------+-----------+----------+-------------------
 id           | uuid                     |           | not null | gen_random_uuid()
 user_id      | uuid                     |           | not null |
 created_at   | timestamp with time zone |           | not null | now()
 expires_at   | timestamp with time zone |           | not null |
 last_seen_at | timestamp with time zone |           | not null | now()
 revoked_at   | timestamp with time zone |           |          |
 user_agent   | text                     |           |          |
 ip_address   | inet                     |           |          |
Indexes:
    "sessions_pkey" PRIMARY KEY, btree (id)
    "ix_sessions_user_id" btree (user_id)
Foreign-key constraints:
    "sessions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
```

### 3. users extended columns
```
                                Table "public.users"
    Column     |           Type           | Collation | Nullable |      Default
---------------+--------------------------+-----------+----------+-------------------
 id            | uuid                     |           | not null | gen_random_uuid()
 email         | text                     |           |          |
 display_name  | text                     |           | not null |
 provider      | text                     |           |          |
 created_at    | timestamp with time zone |           | not null | now()
 sub           | text                     |           |          |
 avatar_url    | text                     |           |          |
 last_login_at | timestamp with time zone |           |          |
Indexes:
    "users_pkey" PRIMARY KEY, btree (id)
    "uq_users_provider_sub" UNIQUE, btree (provider, sub) WHERE sub IS NOT NULL
```

### 4. Partial-index predicate
```
       indexname       |                                                   indexdef
-----------------------+---------------------------------------------------------------------------------------------------------------
 users_pkey            | CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)
 uq_users_provider_sub | CREATE UNIQUE INDEX uq_users_provider_sub ON public.users USING btree (provider, sub) WHERE (sub IS NOT NULL)
```

### 5. ANONYMOUS seed row preserved (with new nullable columns)
```
                  id                  | display_name | provider | sub | avatar_url | last_login_at
--------------------------------------+--------------+----------+-----+------------+---------------
 00000000-0000-0000-0000-000000000001 | anonymous    |          |     |            |
(1 row)
```

### 6. FK delete rule
```
 delete_rule
-------------
 CASCADE
(1 row)
```

### 7. Downgrade clean
```
INFO  [alembic.runtime.migration] Running downgrade 005_sessions_and_oauth_users -> 004_agent_events, ...
   version_num
------------------
 004_agent_events
(1 row)

 sessions_table  ← to_regclass('public.sessions') after downgrade
----------------

(1 row)

 column_name     ← SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name IN ('sub','avatar_url','last_login_at')
-------------
(0 rows)

 indexname       ← uq_users_provider_sub after downgrade
-----------
(0 rows)
```

### 8. Re-upgrade (round-trip proof)
```
INFO  [alembic.runtime.migration] Running upgrade 004_agent_events -> 005_sessions_and_oauth_users, ...
         version_num
------------------------------
 005_sessions_and_oauth_users
(1 row)

 sessions_col_count
--------------------
                  8
(1 row)

                  id                  | display_name
--------------------------------------+--------------
 00000000-0000-0000-0000-000000000001 | anonymous
(1 row)
```

### 9. Python revision-presence assertion
```
$ docker exec deploy-api_server-1 python -c "from alembic.script import ScriptDirectory; ...; assert '005_sessions_and_oauth_users' in [s.revision for s in script.walk_revisions()]; print('OK')"
OK
```

### 10. Integration test run (host venv)
```
$ cd api_server && .venv/bin/python -m pytest tests/test_migration.py::test_migration_005_sessions_and_users_columns -x -v -m api_integration
...
tests/test_migration.py::test_migration_005_sessions_and_users_columns PASSED [100%]
============================== 1 passed in 3.55s ===============================
```

## Task Commits

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Migration 005 (sessions + users.{sub,avatar_url,last_login_at} + partial unique index) | `ec19e7f` | `api_server/alembic/versions/005_sessions_and_oauth_users.py` |
| 2 | Integration test + deferred-items log | `9e7db7e` | `api_server/tests/test_migration.py`, `.planning/phases/22c-oauth-google/deferred-items.md` |

## Decisions Made

- **Additive-only, no backfill** — per D-22c-MIG-02. Every new column is nullable. The ANONYMOUS seed row's `provider` and `sub` stay NULL; `WHERE sub IS NOT NULL` keeps the partial unique index happy. The destructive ANONYMOUS purge lives in plan 22c-06 migration 006, not here.
- **Partial unique index `uq_users_provider_sub`** — chosen over a regular UNIQUE constraint because (a) PG treats NULL as distinct in UNIQUE by default, which would admit multiple NULL-sub rows anyway, but a partial WHERE clause is the more explicit intent and (b) matches the 003_agent_containers.py idiom (`ix_agent_containers_agent_instance_running` is also a partial unique via `postgresql_where`). Index definition verified live: `CREATE UNIQUE INDEX uq_users_provider_sub ON public.users USING btree (provider, sub) WHERE (sub IS NOT NULL)`.
- **No data writes in the migration** — this is pure DDL. Seeding, backfill, and ANONYMOUS purge all belong to 22c-06.
- **Plan-snippet verbatim for the integration test** — new test sits at module-scope outside `TestBaselineMigration` so it can use `migrated_pg` from conftest.py instead of redefining its own `pg`/`migrated` pair. Existing baseline tests untouched.
- **No conftest.py edit** — plan line 39 reserves that for 22c-06. Verified live DSN-gateway issue exists (documented in deferred-items.md) but held off per the plan pointer.

## Deviations from Plan

**None.** Plan executed exactly as written. The snippet for migration 005 was transcribed verbatim; the integration test snippet was transcribed with one minor addition (inline DSN normalization matching the existing `_connect` helper in the same file, since `asyncpg.connect` rejects the `postgresql+psycopg2://` scheme testcontainers emits). That normalization already lives elsewhere in `test_migration.py` as `_connect` and was added to the new test body inline to keep the test self-contained — no semantic drift from the plan.

## Out-of-Scope Discoveries (deferred, not auto-fixed)

Logged to `.planning/phases/22c-oauth-google/deferred-items.md`:

1. **3 pre-existing Phase-19 test failures** in `TestBaselineMigration` — `test_runs_id_is_text_not_uuid`, `test_agent_instances_unique_constraint`, `test_idempotency_unique_constraint` all fail with `asyncpg.NotNullViolationError: null value in column "name" of relation "agent_instances"`. Phase 22's migration 002 added `agent_instances.name NOT NULL`; these Phase 19 INSERTs never got updated. Confirmed pre-existing by stashing 22c-02's change and re-running on clean main (same 3 tests fail). Scope: Phase 19 test-hygiene chore, not 22c.
2. **`_alembic()` helper hardcodes `alembic` on PATH** — fails with `FileNotFoundError: 'alembic'` when invoked without the venv on PATH. conftest.py's `migrated_pg` already solved this by using `[sys.executable, "-m", "alembic", ...]`. Same deferred batch as item 1.
3. **conftest.py `migrated_pg` can't reach its own testcontainer from inside `deploy_default`** — `PostgresContainer("postgres:17-alpine")` returns a `172.17.0.1:<ephemeral>` DSN that's unreachable from a container on `deploy_default`. Same issue Wave 0 SPIKE-B hit and fixed locally in its own function-scoped fixture. Plan line 39 reserves the conftest fix for 22c-06; integration tests run from host venv for now.

## Known Stubs

**None.** Every column and index defined in the migration is consumed by downstream plans (22c-04 SessionMiddleware reads + writes `sessions`; 22c-05 OAuth callback writes `users.sub/avatar_url/last_login_at` under the partial-unique predicate). No placeholder rows, no TODO comments, no hardcoded empty values.

## Self-Check: PASSED

- Task 1 file: `api_server/alembic/versions/005_sessions_and_oauth_users.py` — FOUND.
- Task 2 file: `api_server/tests/test_migration.py` — contains `test_migration_005_sessions_and_users_columns` (verified via grep).
- Deferred-items: `.planning/phases/22c-oauth-google/deferred-items.md` — FOUND.
- Commit `ec19e7f` (Task 1) — FOUND in git log.
- Commit `9e7db7e` (Task 2) — FOUND in git log.
- alembic_version on `deploy-postgres-1` = `005_sessions_and_oauth_users` — CONFIRMED.
- Integration test — PASSES from host venv (verified 2026-04-19, 3.55s wall).
- Round-trip (upgrade → downgrade -1 → upgrade) — CLEAN, ANONYMOUS row survives both directions.

---
*Phase: 22c-oauth-google*
*Completed: 2026-04-19*
