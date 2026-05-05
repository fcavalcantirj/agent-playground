# Phase 28 — Deferred Items (out-of-scope discoveries during execution)

These are pre-existing test failures or rot that were observed during plan
execution but are NOT directly caused by the plan's own changes. Log
captured per the executor SCOPE BOUNDARY rule (auto-fix only what the
current task introduces).

## Plan 28-05 (2026-05-05)

Discovered while running the full pre-existing pytest suite after applying
migration 011 (`011_phase28_workflow_id_idem`). All items below were already
failing at base commit `06458dd` (alembic head 010); migration 011 did NOT
introduce them.

### Pre-existing failures (NOT caused by 011)

1. **`tests/test_migration_007.py::test_migration_007_round_trip`** — the
   walkback logic only special-cases head=008. With heads 009/010/011 the
   test does `downgrade -1` once and asserts head==006, which fails. The
   ALLOWED_HEADS *allowlist* was updated as Rule-1 housekeeping (author's
   documented "append new HEADs as later migrations land" pattern); the
   deeper walkback bug is older. Fix: replace single `downgrade -1` with
   `downgrade 006_purge_anonymous`, OR loop until head=='006'.

2. **`tests/test_migration.py::test_migration_005_sessions_and_users_columns`** —
   hard-coded expected sessions schema does not include the
   `revoked_reason` column added by migration 009. Pre-existing at 009.
   Fix: append `revoked_reason` to the expected list.

3. **`tests/test_idempotency.py::test_same_key_different_users_isolated`** —
   `INSERT INTO agent_instances (id, user_id, recipe_name, model)` is
   missing the NOT NULL `name` column added by migration 002. Pre-existing
   for many migrations. Fix: add `name = $5` to the INSERT.

4. **`tests/test_runs.py::test_run_hermes_gpt4o_mini`,
   `test_persist_run_row`, `test_get_run_by_id_returns_persisted`** —
   live recipe runs against OpenRouter; failing on environmental config
   (likely OPENROUTER_API_KEY or network). Pre-existing — unrelated to
   migration 011.

5. **`tests/auth/test_oauth_mobile.py`** — three `test_github_*` failures.
   Pre-existing at 010 — unrelated to migration 011.

6. **`tests/test_busybox_tail_line_buffer.py`** — pre-existing.

7. **`tests/test_lint.py::test_lint_valid_recipe`** — pre-existing recipe
   lint failure.

8. **`tests/test_migration.py::TestBaselineMigration::*`** — 8 ERROR cases
   from missing `alembic` binary in PATH (test calls `["alembic", ...]`
   directly instead of `[sys.executable, "-m", "alembic", ...]`).
   Pre-existing — unrelated to migration 011.

### Plan 28-05 Rule-1 housekeeping (in scope, fixed during plan)

These ARE in scope because migration 011 advanced the alembic HEAD to a
value that prior tests' allowlists did not enumerate. Following the test
author's documented "append new HEADs here as later migrations land"
maintenance instructions, the following allowlists were updated to include
`009_auth_events_revoked_reason`, `010_usage_logs_cost_weights`, and
`011_phase28_workflow_id_idem`:

  * `tests/auth/test_cross_user_isolation.py:61` `ALLOWED_HEADS`
  * `tests/test_migration.py:322` `ALLOWED_HEADS_005_OR_LATER`
  * `tests/test_migration.py:399` `ALLOWED_HEADS_006_OR_LATER`
  * `tests/test_migration_007.py:362` (pre-round-trip head check)
  * `tests/test_migration_007.py:438` (post-re-upgrade head check)

These updates are mechanical and match the maintenance pattern explicitly
documented in each test's surrounding comment. They are committed as part
of the Plan 28-05 migration commit so the new HEAD is recognized
project-wide.

### Plan 28-05 Rule-1 deviation (in scope, fixed during plan)

The plan prescribed revision id `011_phase28_workflow_id_idempotency`
(35 chars). `alembic_version.version_num` is `varchar(32)` (Alembic
default). Writing the prescribed string fails at the
`UPDATE alembic_version SET version_num=...` step. The migration was
implemented with the abbreviated revision id `011_phase28_workflow_id_idem`
(28 chars) — same convention as `008_idempotency_relax_run_fk` (28 chars)
and `005_sessions_and_oauth_users` (28 chars). The FILE name keeps the
fully-spelled form (`011_phase28_workflow_id_idempotency.py`) for human
readability; only the DB-stored `revision` string is shortened. Documented
in the migration's module docstring + a NOTE in
`tests/test_migration_011_phase28.py`.
