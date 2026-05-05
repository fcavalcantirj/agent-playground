---
phase: 28-temporal-dispatch
plan: 05
subsystem: api_server / tools
tags: [alembic, idempotency, defense-in-depth, cutover, temporal]
requires:
  - alembic head 010_usage_logs_cost_weights
  - asyncpg in api_server runtime image
  - tools/ COPY'd into api_server image (per tools/Dockerfile.api)
provides:
  - inapp_messages.workflow_id (text, nullable) + ix_inapp_messages_workflow_id
  - inapp_messages.idempotency_key (text, nullable) + UNIQUE partial index
    ix_inapp_messages_idempotency_key_unique on (user_id, idempotency_key)
  - tools/migrate_phase28_stuck_rows.py — one-shot cutover sweep script
  - alembic head advances to 011_phase28_workflow_id_idem
affects:
  - api_server/alembic/versions/ (new 011 migration file)
  - api_server/tests/ (new integration test + 3 housekeeping updates)
  - tools/ (new cutover sweep script)
  - .planning/phases/28-temporal-dispatch/ (new deferred-items.md)
tech-stack:
  added: []
  patterns:
    - Option A column-add path for defense-in-depth UNIQUE partial index
    - Pre-step inspection before destructive DDL (Plan 28-05 truths)
    - Stdlib + asyncpg-only standalone tool (no FastAPI/no temporalio dep)
    - Canonical "docker cp + docker exec alembic upgrade head" deploy pattern
key-files:
  created:
    - api_server/alembic/versions/011_phase28_workflow_id_idempotency.py
    - api_server/tests/test_migration_011_phase28.py
    - tools/migrate_phase28_stuck_rows.py
    - .planning/phases/28-temporal-dispatch/deferred-items.md
  modified:
    - api_server/tests/auth/test_cross_user_isolation.py
    - api_server/tests/test_migration.py
    - api_server/tests/test_migration_007.py
decisions:
  - "Revision id shortened to 011_phase28_workflow_id_idem (28 chars) to fit alembic_version.version_num varchar(32)"
  - "Pre-step inspection confirmed 007 did NOT include idempotency_key — Option A column-add executed (NOT skipped)"
  - "Defense-in-depth (D-14) confirmed: column-level UNIQUE partial index AND IdempotencyMiddleware 24h TTL coexist post-migration"
metrics:
  duration: "13m"
  completed: "2026-05-05"
  tasks: 2
  files_created: 4
  files_modified: 3
  commits: 2
---

# Phase 28 Plan 05: Schema + Cutover Sweep Prep — Summary

**One-liner:** alembic 011 adds inapp_messages.workflow_id + idempotency_key with a UNIQUE partial index for defense-in-depth, plus a standalone cutover sweep script for legacy stuck-forwarded rows.

## What Shipped

### Task 1 — alembic 011 migration (`1c97dbc`)

Three additive schema changes on `inapp_messages`:

1. **`workflow_id text` (nullable)** + partial btree index `ix_inapp_messages_workflow_id WHERE workflow_id IS NOT NULL`. Plan 28-06's route handler will populate this for ops correlation between Temporal UI workflow IDs (`msg-{user_id}-{message_uuid}` per D-08) and `inapp_messages` rows.

2. **`idempotency_key text` (nullable)** — Option A column-add path. **Pre-step inspection result:** verified 007 did NOT include this column (`\d+ inapp_messages` against `deploy-postgres-1` while head sat at `010_usage_logs_cost_weights` showed columns id/agent_id/user_id/content/status/attempts/last_error/last_attempt_at/bot_response/created_at/completed_at — no `idempotency_key`). Therefore Option A's `op.add_column` IS executed; downgrade drops it.

3. **`UNIQUE` partial index `ix_inapp_messages_idempotency_key_unique`** on `(user_id, idempotency_key) WHERE idempotency_key IS NOT NULL` — the primary defense-in-depth gate for RESEARCH §7 R3.

**Defense-in-depth (D-14) confirmed live:**
- **Layer 1 (Option A — this migration):** column-level UNIQUE constraint. Duplicate Idempotency-Key inserts that bypass middleware cache fire `UniqueViolationError` at insert time. Plan 28-06's `insert_pending` will catch and return the pre-existing row.
- **Layer 2 (Option B — existing):** `IdempotencyMiddleware` 24h TTL (`services/idempotency.py:23` documented + `write_idempotency` parameter `ttl_hours: int = 24`). 24h ≥ 5min D-13 workflow `execution_timeout` floor — confirmed by reading `services/idempotency.py` end-to-end during Pre-step.

Both layers coexist post-migration ("AND", not "OR").

**Migration applied to deploy-postgres-1 via canonical pattern:**
```
docker cp alembic/versions/011_phase28_workflow_id_idempotency.py \
    deploy-api_server-1:/app/api_server/alembic/versions/
docker exec deploy-api_server-1 alembic upgrade head
```

**Round-trip verified:**
- `upgrade head → downgrade -1 → upgrade head` runs cleanly
- Post-downgrade: workflow_id + idempotency_key columns gone, both indexes gone
- Post-re-upgrade: all 4 artifacts back with same shape

**Integration test `tests/test_migration_011_phase28.py`** uses module-scoped testcontainers Postgres 17, mirrors `tests/test_migration_007.py` style. Asserts:
- `workflow_id` text, nullable=True
- `idempotency_key` text, nullable=True
- `ix_inapp_messages_workflow_id` partial index with correct WHERE predicate
- `ix_inapp_messages_idempotency_key_unique` UNIQUE partial index
- INSERT with NULL workflow_id + NULL idempotency_key succeeds
- INSERT with non-null workflow_id succeeds
- INSERT with first idempotency_key succeeds; duplicate (user_id, idempotency_key) raises `UniqueViolationError`
- Cross-user same-key permitted (UNIQUE is scoped to (user_id, key))
- Two NULL-idempotency_key rows for same user coexist (partial index excludes NULLs)
- Round-trip clean (downgrade -1 → upgrade head leaves identical schema)

Both test cases PASS:
```
tests/test_migration_011_phase28.py::test_migration_011_adds_workflow_id_and_idempotency_key PASSED
tests/test_migration_011_phase28.py::test_migration_011_round_trip PASSED
```

### Task 2 — `tools/migrate_phase28_stuck_rows.py` (`54d40c6`)

Standalone Python script (stdlib + asyncpg only — no FastAPI, no temporalio). Scans `inapp_messages` WHERE `status='forwarded' AND last_attempt_at < NOW() - INTERVAL '11 minutes'` (matches the legacy reaper's D-30 threshold) and transitions matching rows to `status='failed'` with `last_error='phase28_cutover_swept'` and `completed_at=NOW()`.

Features:
- `--dry-run` flag prints up to 50 affected rows + total count, no mutation
- `--limit` (default 10000) safety cap aborts before mutation if more rows match
- DATABASE_URL env var required; auto-strips SQLAlchemy `+asyncpg` driver hint
- Transactional UPDATE with pre-count guard inside the same transaction
- Idempotent: re-running matches zero rows + exits 0
- `chmod +x` for direct invocation

**Live-tested against deploy-postgres-1** via canonical post-cutover invocation:
```
docker exec deploy-api_server-1 python /app/tools/migrate_phase28_stuck_rows.py
```

Test sequence (synthetic stuck row inserted + cleaned up):
1. Empty DB dry-run: `row_count=0` exit 0 ✓
2. Insert synthetic forwarded row with `last_attempt_at = NOW() - 15min`
3. Dry-run sees 1 row, prints id/user_id/agent_id/last_attempt_at ✓
4. Live sweep: `swept row_count=1`, row transitions to `status='failed' last_error='phase28_cutover_swept' completed_at=2026-05-05T21:30:39.968+00` ✓
5. Re-run live: `swept row_count=0` exit 0 (idempotent) ✓
6. Re-run dry-run: `row_count=0` exit 0 ✓
7. Synthetic row deleted; DB clean

Plan 28-06 cutover sequence will invoke this script as the FIRST step before the api_server roll, so any rows the legacy dispatcher orphaned see a terminal `failed` state instead of perpetual "typing".

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Alembic 011 — workflow_id column + unique idempotency_key index | `1c97dbc` | `api_server/alembic/versions/011_phase28_workflow_id_idempotency.py`, `api_server/tests/test_migration_011_phase28.py`, 3 stale-allowlist housekeeping updates |
| 2 | `tools/migrate_phase28_stuck_rows.py` — one-shot cutover sweep | `54d40c6` | `tools/migrate_phase28_stuck_rows.py` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Plan-prescribed revision id exceeds varchar(32)**
- **Found during:** Task 1 first apply attempt
- **Issue:** Plan prescribed `revision = "011_phase28_workflow_id_idempotency"` (35 chars). `alembic_version.version_num` is `varchar(32)` (Alembic default). The DDL runs successfully, but the final `UPDATE alembic_version SET version_num='011_phase28_workflow_id_idempotency'` fails with `asyncpg.exceptions.StringDataRightTruncationError: value too long for type character varying(32)`. The migration's transactional DDL rolls back cleanly.
- **Fix:** Shortened the DB-stored `revision` string to `011_phase28_workflow_id_idem` (28 chars) — same convention as `008_idempotency_relax_run_fk` (28 chars) and `005_sessions_and_oauth_users` (28 chars). The FILE name keeps the fully-spelled `011_phase28_workflow_id_idempotency.py` for human readability. Documented in the migration's module docstring NOTE block + integration test docstring.
- **Files modified:** `api_server/alembic/versions/011_phase28_workflow_id_idempotency.py`
- **Commit:** `1c97dbc`
- **Acceptance-criteria impact:** the plan's grep `grep -c 'revision = "011_phase28_workflow_id_idempotency"' returns 1` now returns 0; replaced semantically by `grep -c 'revision = "011_phase28_workflow_id_idem"' returns 1` (matches the abbreviated DB identity). Behavior identical.

**2. [Rule 1 — Bug] Stale `ALLOWED_HEADS` allowlists across 3 test files**
- **Found during:** Task 1 post-apply pytest run
- **Issue:** `tests/auth/test_cross_user_isolation.py:61`, `tests/test_migration.py:322`, `tests/test_migration.py:399`, and `tests/test_migration_007.py:362+449` each carry a hardcoded set of "valid current alembic heads". Last update was for migration 008. Migrations 009 and 010 already advanced HEAD past these allowlists — i.e. the tests were already broken at base commit `06458dd`. Migration 011 advances HEAD again and re-trips the same assertion.
- **Fix:** Each test author's surrounding comment explicitly says "Append new HEADs here as later migrations land". Followed those instructions: added `009_auth_events_revoked_reason`, `010_usage_logs_cost_weights`, and `011_phase28_workflow_id_idem` to all five sets. This is mechanical maintenance documented by the test authors themselves; included in Task 1's commit since 011 is what triggered the re-check.
- **Files modified:** `api_server/tests/auth/test_cross_user_isolation.py`, `api_server/tests/test_migration.py`, `api_server/tests/test_migration_007.py`
- **Commit:** `1c97dbc`
- **Verification:** post-fix `tests/auth/test_cross_user_isolation.py` + `tests/test_migration.py::test_migration_006_artifact_and_apply` PASS.

### Pre-existing failures NOT caused by 011 (deferred)

Logged in `.planning/phases/28-temporal-dispatch/deferred-items.md` per the executor SCOPE BOUNDARY rule. Each item was already failing at base commit `06458dd` (alembic head 010); migration 011 did NOT introduce them:

- `tests/test_migration_007.py::test_migration_007_round_trip` — walkback logic only special-cases head=008. With heads 009/010/011 the test does `downgrade -1` once and asserts head==006, which fails. The Rule-1 allowlist update (above) is mechanically correct and matches author intent; the deeper walkback bug is pre-existing.
- `tests/test_migration.py::test_migration_005_sessions_and_users_columns` — hardcoded sessions schema does not include `revoked_reason` from migration 009.
- `tests/test_idempotency.py::test_same_key_different_users_isolated` — INSERT into `agent_instances` missing NOT NULL `name` column from migration 002.
- `tests/test_runs.py` — three live recipe runs against OpenRouter, environmental config issue.
- `tests/auth/test_oauth_mobile.py` — three pre-existing GitHub-OAuth failures.
- `tests/test_busybox_tail_line_buffer.py` — pre-existing.
- `tests/test_lint.py::test_lint_valid_recipe` — pre-existing recipe lint failure.
- `tests/test_migration.py::TestBaselineMigration::*` — 8 ERROR cases, missing `alembic` binary in PATH.

## Verification Status

- [x] Migration 011 applied to deploy-postgres-1
- [x] Migration 011 reversible (round-trip clean)
- [x] Integration test `test_migration_011_phase28.py` 2/2 PASS — including UniqueViolation, cross-user same-key, NULL-rows-coexist, and round-trip
- [x] In-scope housekeeping tests PASS: `test_cross_user_isolation`, `test_migration_006_artifact_and_apply`
- [x] Cutover script tested — empty DB, synthetic row, live sweep, idempotency
- [x] Both commits made atomically; no shared orchestrator artifacts modified
- [x] Deferred items logged for follow-up
- [x] Defense-in-depth (D-14) live: Option A column-level UNIQUE partial index AND Option B IdempotencyMiddleware 24h TTL coexist

## Schema Snapshot Post-Migration

```
                                    Table "public.inapp_messages"
     Column      |           Type           | Nullable |      Default      
-----------------+--------------------------+----------+-------------------
 id              | uuid                     | not null | gen_random_uuid()
 agent_id        | uuid                     | not null | 
 user_id         | uuid                     | not null | 
 content         | text                     | not null | 
 status          | text                     | not null | 'pending'::text
 attempts        | integer                  | not null | 0
 last_error      | text                     |          | 
 last_attempt_at | timestamp with time zone |          | 
 bot_response    | text                     |          | 
 created_at      | timestamp with time zone | not null | now()
 completed_at    | timestamp with time zone |          | 
 workflow_id     | text                     |          |    -- NEW
 idempotency_key | text                     |          |    -- NEW
Indexes:
    "inapp_messages_pkey" PRIMARY KEY, btree (id)
    "ix_inapp_messages_agent_status" btree (agent_id, status)
    "ix_inapp_messages_idempotency_key_unique" UNIQUE, btree (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL  -- NEW
    "ix_inapp_messages_status_attempts" btree (status, last_attempt_at) WHERE status = ANY (ARRAY['pending'::text, 'forwarded'::text])
    "ix_inapp_messages_workflow_id" btree (workflow_id) WHERE workflow_id IS NOT NULL  -- NEW

alembic_version.version_num = 011_phase28_workflow_id_idem
```

## Plan 28-06 Handoff

Plan 28-06 (cutover) can now:
1. Use `inapp_messages.workflow_id` as a NOT NULL parameter to `insert_pending` (Plan 28-06 owns the wiring; no code change in this plan).
2. Catch `asyncpg.UniqueViolationError` on duplicate `(user_id, idempotency_key)` insert and return the pre-existing row instead of orphaning a workflow.
3. Invoke `tools/migrate_phase28_stuck_rows.py` as the FIRST step of the cutover sequence (BEFORE the api_server roll) — script is idempotent + safety-capped so re-running is safe.

## Self-Check: PASSED

Files exist:
- ✓ `api_server/alembic/versions/011_phase28_workflow_id_idempotency.py`
- ✓ `api_server/tests/test_migration_011_phase28.py`
- ✓ `tools/migrate_phase28_stuck_rows.py`
- ✓ `.planning/phases/28-temporal-dispatch/deferred-items.md`

Commits exist:
- ✓ `1c97dbc` — feat(28-05): alembic 011 — workflow_id + idempotency_key defense-in-depth
- ✓ `54d40c6` — feat(28-05): add Phase 28 cutover sweep tools/migrate_phase28_stuck_rows.py
