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
