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

## Plan 28-07 (2026-05-05)

Discovered while running the post-cutover pytest suite. Plan 28-07 reworked
the legacy ``tests/services/test_inapp_dispatcher.py`` and added 5 new files
under ``tests/temporal/`` (Tasks 1-3). The autouse Temporal-client patch
(Task 5 Rule 3 fix) unmasked one additional pre-existing failure that the
plan does NOT remediate:

### Plan 28-07 Rule-3 + Rule-1 fixes (in scope, fixed during plan)

* **Rule 3 — autouse Temporal-client patch** (`tests/conftest.py`).
  Plan 28-06 added a 5×5s lifespan retry against ``localhost:7233``; without
  a Temporal cluster every test that boots the app via ``lifespan_context``
  raised ``RuntimeError: temporal client connect retries exhausted``. The
  autouse fixture monkey-patches ``api_server.temporal.client.make_client``
  to return an ``AsyncMock`` so the lifespan boots cleanly. Workflow body
  coverage stays at ``tests/temporal/test_dispatch_message_workflow.py``
  which uses ``WorkflowEnvironment.start_time_skipping`` (real Temporal
  Server, not a mock — Golden Rule #1 compliant).

* **Rule 1 — `tests/test_main_lifespan_inapp.py` post-cutover update**.
  The test asserted 3 inapp tasks {inapp_dispatcher, inapp_reaper,
  inapp_outbox}. Plan 28-06 D-06 deleted ``inapp_dispatcher`` at cutover
  (DispatchMessageWorkflow owns orchestration). Renamed test to
  ``test_lifespan_attaches_two_inapp_tasks``; updated assertion to
  ``{inapp_reaper, inapp_outbox}``; added a defensive
  ``inapp_dispatcher must NOT come back`` invariant.

### NEW pre-existing failure unmasked (NOT caused by 28-07)

9. **`tests/test_events_inject_test_event.py::test_inject_test_event_prod_returns_404`** —
   the ``prod_app_and_client`` fixture sets ``AP_ENV=prod`` but does NOT
   provide the ``AP_OAUTH_GOOGLE_CLIENT_ID`` (or other OAuth values) that
   ``create_app()`` in prod mode validates at lifespan-init via the eager
   OAuth registry. Result: ``RuntimeError: OAUTH_GOOGLE_CLIENT_ID (env
   AP_OAUTH_GOOGLE_CLIENT_ID) required when AP_ENV=prod``. This was masked
   at base by the Temporal connect-retry exhaustion (the lifespan never
   reached the OAuth init). Pre-existing — out of Plan 28-07 scope. Fix:
   the prod-mode fixture needs to inject placeholder OAuth values via
   ``monkeypatch.setenv``, mirror of the dev-mode fixture's wiring.

### Test gate evidence (Plan 28-07 Task 5)

The Plan 28-07 acceptance criterion `pytest -x` fully green is BLOCKED by
the 13 pre-existing failures items #1-8 above plus item #9 unmasked here.
With those deferred, the focused pytest run is GREEN:

```
$ uv run pytest tests/ --tb=no -q \
    --deselect tests/spikes \
    --deselect tests/auth/test_oauth_mobile.py \
    --deselect tests/test_idempotency.py \
    --deselect tests/test_migration.py \
    --deselect tests/test_migration_007.py \
    --deselect tests/test_lint.py \
    --deselect tests/test_busybox_tail_line_buffer.py \
    --deselect tests/test_runs.py \
    --deselect tests/e2e
322 passed, 15 skipped, 61 deselected, 14 warnings in 178.64s
```

The 5 new Phase 28-07 test files (workflow + 3 activities + route) pass
in isolation:

```
$ uv run pytest tests/temporal/ --tb=no -q
19 passed in 55.64s
```

Plus the post-cutover `tests/services/test_inapp_dispatcher.py`:

```
$ uv run pytest tests/services/test_inapp_dispatcher.py -v -m api_integration
1 passed in 0.03s
```

Plan 28-07's own test surface is fully green. Pre-existing failures are
documented for a future "test-suite hygiene" plan.

## Plan 28-09 (2026-05-06)

Discovered while running the exit-gate verification. None of these are
Phase 28 code defects; all are out-of-scope per the SCOPE BOUNDARY rule.

10. **`make e2e-inapp-docker` is stale post-Plan-06 cutover** — the harness's
    `tests/e2e/_helpers.py::drive_dispatcher_once` imports
    `from api_server.services.inapp_dispatcher import _handle_row`, a
    function Plan 28-06 D-06 DELETED. All 5 cells (hermes, nanobot,
    openclaw, nullclaw, zeroclaw) ERROR at fixture setup with
    `ImportError: cannot import name '_handle_row'`. Fix: rewrite
    `drive_dispatcher_once` to drive the workflow path
    (POST `/v1/agents/:id/messages` → poll `inapp_messages.status`)
    instead of importing the deleted helper. The Phase 22c.3 SC-03 surface
    that the harness was originally written for is replaced by the new
    `tests/temporal/` suite (19 tests). Owner: a future Phase 22c.3
    hygiene / Phase 28 follow-up plan.

11. **`tests/test_run_recipe_persistent_inapp.py::test_data_dir_hoisted_before_pre_start`**
    — Phase 22c.3.1 D-34 test, fails on Docker container teardown timing
    with `No such container: <id>` (the test container was force-removed
    before the daemon-logs check ran). Authored at commit `ca9bb19`
    (Phase 22c.3.1 wave 0). Pre-existing flake; NOT a Phase 28 regression.
    Fix: add a small wait + `docker logs` retry loop OR snapshot the
    daemon logs before the teardown call.

12. **temporal-worker bind-mount can become stale after worktree cleanup**
    — when an executor worktree gets deleted (each parallel agent runs in
    `.claude/worktrees/agent-<hash>/`), any deploy-stack container that
    started its lifetime under that worktree retains the now-defunct
    bind-mount path. Symptom observed during Plan 28-09: `temporal-worker`
    had `/Users/.../worktrees/agent-a53355f1/recipes` bound to
    `/app/recipes`, but `agent-a53355f1` had been cleaned up by the prior
    Plan 06 executor; result: `/app/recipes` was empty inside the worker
    and `forward_to_agent` raised `recipe_lacks_inapp_channel`. Workaround
    used: force-recreate the affected services from the canonical project
    root with `--force-recreate`. Long-term fix: the deploy stack should
    bind-mount from a stable path (the canonical project root, not the
    worktree that booted it). Owner: deploy/orchestration follow-up.
