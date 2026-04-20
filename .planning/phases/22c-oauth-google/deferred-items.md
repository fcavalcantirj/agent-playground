# Phase 22c — deferred items (out-of-scope discoveries)

Items discovered during Phase 22c execution that are **out of scope** for
this phase (per the executor scope-boundary rule: only auto-fix issues
DIRECTLY caused by the current task's changes). Logged here for a later
clean-up pass.

## 22c-02 (Wave 1, alembic migration 005)

### PRE-EXISTING: 3 Phase 19 baseline tests fail on current main

File: `api_server/tests/test_migration.py`
- `TestBaselineMigration::test_runs_id_is_text_not_uuid`
- `TestBaselineMigration::test_agent_instances_unique_constraint`
- `TestBaselineMigration::test_idempotency_unique_constraint`

Failure: `asyncpg.exceptions.NotNullViolationError: null value in column
"name" of relation "agent_instances" violates not-null constraint`.

Root cause: migration `002_agent_name_personality` (Phase 22) made
`agent_instances.name` NOT NULL, but the three Phase 19 baseline tests
still INSERT into `agent_instances` without supplying `name`. The tests
need a backfill like `name='hermes-uq'` in their INSERT statements.

Evidence of pre-existence: confirmed by stashing 22c-02's new test and
re-running on a clean `main` checkout — same 3 tests fail with the same
error (commit `ec19e7f` is the stashing baseline).

Scope: these tests are owned by Phase 19; their fix is a test-hygiene
chore, not part of the 22c OAuth work. Can be rolled into any later
"test-suite cleanup" touch on this file.

### PRE-EXISTING: `_alembic()` helper hardcodes `alembic` on PATH

File: `api_server/tests/test_migration.py` — `_alembic()` helper (line 46).

Failure: `FileNotFoundError: [Errno 2] No such file or directory:
'alembic'` when pytest is invoked via `python -m pytest` without the
project venv on `PATH`. conftest.py's `migrated_pg` fixture solved the
same issue by switching to `[sys.executable, "-m", "alembic", ...]` —
the baseline helper should adopt the same pattern.

Scope: baseline test-rig chore; not 22c-scoped. Same deferred batch as
the Phase-19 name-NOT-NULL fix.

### PRE-EXISTING: conftest.py `migrated_pg` fails inside the compose network

File: `api_server/tests/conftest.py` — `migrated_pg` fixture (line 53).

Failure: `ConnectionRefusedError: [Errno 111] Connect call failed
('172.17.0.1', <ephemeral>)` when pytest is invoked via
`docker exec deploy-api_server-1 pytest ...`.

Root cause: `PostgresContainer("postgres:17-alpine")` spawns on docker's
default bridge and `get_connection_url()` returns a DSN pointing at the
docker host gateway — unreachable from inside `deploy_default`.
Phase 22c Wave 0 SPIKE-B already fixed this for its own function-scoped
fixture by network-attaching to `deploy_default` and building the DSN
from the container's private IP. Conftest's session-scoped `migrated_pg`
needs the same treatment IF we want these integration tests to run
from inside `deploy-api_server-1`. Running them from the host venv
already works.

Scope: the plan text (line 39 of `22c-02-PLAN.md`) explicitly says
"conftest.py fix happens in 22c-06". Honoring that pointer — do not
touch conftest in this plan.

## 22c-02 execution path (not a deferred item — just documentation)

Per golden rule #5 + worktree-breaks-for-live-infra memory, the new
`test_migration_005_sessions_and_users_columns` integration test is
expected to be run from the **host** venv:

```bash
cd api_server && .venv/bin/python -m pytest \
  tests/test_migration.py::test_migration_005_sessions_and_users_columns \
  -v -m api_integration
```

That invocation passes (verified 2026-04-19 — 1 passed in 3.55s).
Running the test from inside `deploy-api_server-1` hits the conftest
DSN-gateway issue above and is deferred to 22c-06.

## 22c-06 (Wave 4, alembic 006 purge + ANONYMOUS cleanup) — 2026-04-20

### OBSOLETED: Phase 19 baseline test `test_anonymous_user_seeded`

File: `api_server/tests/test_migration.py`
Test: `TestBaselineMigration::test_anonymous_user_seeded`

Failure: `AssertionError: anonymous user missing`.

Root cause: migration 006 (this plan) TRUNCATEs the `users` table —
including the ANONYMOUS seed row. The baseline test asserts that row
still exists, which is correct for migration 001 in isolation but no
longer true post-006.

Scope: semantically this test is OBSOLETE, not broken. The right fix
is either (a) rename it to `test_anonymous_user_seeded_at_baseline` and
have it run against a DB upgraded only to 001 (not head), or (b) delete
the assertion entirely since post-22c the database model has zero seed
rows by design (AMD-04).

Deferring the rename / delete to a later test-hygiene pass; 22c-06's
own `test_migration_006_artifact_and_apply` covers the post-006 empty-
table invariant (belt-and-suspenders 8-table COUNT=0 check).

### OUT OF SCOPE: `test_events_lifecycle_cancel_on_stop.py` rename

Per the plan's Class B note, the file's local `ANONYMOUS_USER_ID` was
renamed to `TEST_USER_ID` (same UUID value `...000000000001`). Because
the UUID value is reused by multiple test files under the same fixed
value, inter-test ordering within a pool now relies on the ON CONFLICT
DO NOTHING idempotency — this is documented in each fixture's
docstring.

## 22c-05 (Wave 3, OAuth routes + tests) — 2026-04-20

### PRE-EXISTING: 3 integration tests fail on main (pre-22c-05)

Files + symptoms:

- `tests/test_recipes.py::test_list_recipes_returns_five` — `assert 'ap.recipe/v0.2' == 'ap.recipe/v0.1'`. The recipes on disk are v0.2 but the test asserts v0.1.
- `tests/test_idempotency.py::test_same_key_different_users_isolated` — cross-user isolation test already failing on main; unrelated to 22c-05.
- `tests/test_busybox_tail_line_buffer.py::test_busybox_tail_line_buffer` — "BusyBox tail -F did NOT line-buffer within 500ms". Environmental/Docker timing.

Evidence of pre-existence: confirmed by stashing the 22c-05 working tree
(10 new test files + conftest extension) and running the same three
tests against clean `main` at `eb2dcb6` — all three failed with the
same errors.

Scope: OUT OF SCOPE for 22c-05. Logged here for a later clean-up pass.
22c-05 does NOT modify any of those three files and does not touch the
recipes catalog, idempotency middleware, or the BusyBox tail fallback.

### TRUNCATE list extended to include ``sessions`` + non-anonymous ``users``

Intentional 22c-05 change, not a deferred item. `tests/conftest.py`'s
`_truncate_tables` autouse fixture was extended to:

1. Add `sessions` to the TRUNCATE CASCADE list.
2. After TRUNCATE, run `DELETE FROM users WHERE id !=
   '00000000-0000-0000-0000-000000000001'` to clear non-ANONYMOUS
   users while preserving the seeded row.

Rationale: every integration test in `tests/auth/` + `tests/routes/test_users_me.py`
seeds its own user + session rows and expects a clean slate between
tests. Without this, `authenticated_cookie` would leave a session behind
which could race with a subsequent test's revoked-session check.

Impact: verified against the full integration suite (`pytest -m
api_integration`) — no regression in any of the 109 previously-green
integration tests.
