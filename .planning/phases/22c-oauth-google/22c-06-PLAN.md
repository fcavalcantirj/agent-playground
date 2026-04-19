---
phase: 22c-oauth-google
plan: 06
type: execute
wave: 4
depends_on: [22c-05]
files_modified:
  - api_server/alembic/versions/006_purge_anonymous.py
  - api_server/src/api_server/constants.py
  - api_server/src/api_server/services/run_store.py
  - api_server/src/api_server/routes/runs.py
  - api_server/src/api_server/routes/agents.py
  - api_server/src/api_server/routes/agent_lifecycle.py
  - api_server/src/api_server/routes/agent_events.py
  - api_server/src/api_server/middleware/idempotency.py
  - api_server/src/api_server/middleware/rate_limit.py
  - api_server/tests/conftest.py
  - api_server/tests/middleware/test_idempotency_user_id.py
  - api_server/tests/test_migration.py
  - api_server/tests/test_events_auth.py
  - api_server/tests/test_events_inject_test_event.py
  - api_server/tests/test_events_long_poll.py
  - api_server/tests/test_events_lifespan_reattach.py
  - api_server/tests/test_events_lifecycle_cancel_on_stop.py
  - api_server/tests/test_events_watcher_backpressure.py
  - api_server/tests/test_idempotency.py
autonomous: true
requirements: [R3, R8, AMD-03, AMD-04, D-22c-AUTH-04, D-22c-MIG-03, D-22c-MIG-06]
must_haves:
  truths:
    - "alembic migration 006 exists; upgrade runs TRUNCATE CASCADE on 8 tables; downgrade raises NotImplementedError"
    - "After `alembic upgrade head` on a previously-populated DB: all 8 data-bearing tables have COUNT=0; alembic_version contains 006_purge_anonymous"
    - "api_server/src/api_server/constants.py no longer exports ANONYMOUS_USER_ID (AP_SYSADMIN_TOKEN_ENV stays)"
    - "api_server/src/api_server/services/run_store.py no longer re-exports ANONYMOUS_USER_ID (import line removed, __all__ entry removed, docstring mention removed)"
    - "routes/runs.py, routes/agents.py, routes/agent_lifecycle.py, routes/agent_events.py use require_user(request) inline check and resolve user_id from request.state — zero ANONYMOUS_USER_ID references"
    - "7 cross-test files migrated: 5 to use authenticated_cookie/literal UUID seed, 2 with local re-definitions renamed to TEST_USER_ID"
    - "middleware/idempotency.py reads request.state.user_id; when None the request passes through without an idempotency lookup (Option A from RESEARCH Pitfall 4)"
    - "middleware/rate_limit.py _subject_from_scope prepends a user_id check — when request.state.user_id is a UUID the rate-limit subject is the stringified UUID; otherwise falls back to IP"
    - "routes/agent_lifecycle.py::agent_status now uses require_user (gap from PATTERNS.md closed per D-22c-AUTH-03 `/v1/agents/:id/*` scope)"
    - "middleware/idempotency.py docstring updated — no longer claims 'no middleware change needed in Phase 21+'"
    - "api_server/tests/conftest.py TRUNCATE list in the test isolation fixture covers sessions + agent_containers + agent_events + users"
    - "Post-task-4: `grep -rn ANONYMOUS_USER_ID api_server/` returns 0 hits across src/ AND tests/"
  artifacts:
    - path: "api_server/alembic/versions/006_purge_anonymous.py"
      provides: "alembic migration 006 — destructive data purge"
      contains: "TRUNCATE TABLE"
      contains: "raise NotImplementedError"
    - path: "api_server/src/api_server/middleware/idempotency.py"
      provides: "user_id-aware idempotency; passes through on anonymous"
  key_links:
    - from: "Every protected route"
      to: "auth/deps.py require_user"
      via: "inline isinstance(result, JSONResponse) check then user_id assignment"
      pattern: "result = require_user.*isinstance.*JSONResponse"
    - from: "middleware/rate_limit.py subject resolution"
      to: "scope state user_id"
      via: "check scope['state']['user_id'] first; fall back to IP"
      pattern: "scope.get.state"
---

<objective>
Close out the backend half of Phase 22c by:

1. Landing the IRREVERSIBLE migration 006 that TRUNCATEs all 8 data-bearing tables (per AMD-04 + D-22c-MIG-03).
2. Deleting the `ANONYMOUS_USER_ID` constant from `constants.py` (D-22c-MIG-06 — forcing function for complete cleanup).
3. **Deleting the `ANONYMOUS_USER_ID` re-export from `services/run_store.py`** (BLOCKER-1 fix): the module imports the constant on L25 and re-exports it on `__all__` L28 and mentions it in the L441 docstring. Missing this re-export would cause a silent import-chain success for tests even after the forcing-function delete — the "zero grep hits" verify would fail.
4. Migrating all 4 route files + idempotency + rate_limit middleware to read `request.state.user_id` via the `require_user` pattern from plan 22c-05.
5. Extending `agent_lifecycle.py::agent_status` to require auth (gap closure per PATTERNS.md).
6. Fixing the stale TRUNCATE list in `conftest.py` so test isolation keeps working after 006 removes the ANONYMOUS seed row.
7. **Migrating 7 test files that currently import or locally redefine `ANONYMOUS_USER_ID`** (BLOCKER-2 fix): without these fixes, the tests break at IMPORT time after constants.py is deleted.

Migration 006 is the FIRST destructive migration in the repo — its docstring must scream about irreversibility. The `alembic downgrade` path raises `NotImplementedError`.

Purpose: End the "single ANONYMOUS bucket" era. Post-plan, every DB row is owned by a real OAuth user (or was wiped by 006), AND the entire codebase — src + tests — is free of `ANONYMOUS_USER_ID` references.
Output: 1 new migration + constants.py line-delete + run_store.py re-export delete + 6 file migrations + one test fixture fix + 7 test-file migrations + 1 new idempotency-user-id test + 1 new migration-006 test.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22c-oauth-google/22c-SPEC.md
@.planning/phases/22c-oauth-google/22c-CONTEXT.md
@.planning/phases/22c-oauth-google/22c-RESEARCH.md
@.planning/phases/22c-oauth-google/22c-PATTERNS.md
@api_server/src/api_server/constants.py
@api_server/src/api_server/services/run_store.py
@api_server/src/api_server/routes/runs.py
@api_server/src/api_server/routes/agents.py
@api_server/src/api_server/routes/agent_lifecycle.py
@api_server/src/api_server/routes/agent_events.py
@api_server/src/api_server/middleware/idempotency.py
@api_server/src/api_server/middleware/rate_limit.py
@api_server/tests/conftest.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Migration 006 (destructive) + migration test + conftest TRUNCATE fix</name>
  <files>api_server/alembic/versions/006_purge_anonymous.py, api_server/tests/test_migration.py, api_server/tests/conftest.py</files>
  <read_first>
    - api_server/alembic/versions/001_baseline.py (docstring idiom + op.execute usage)
    - api_server/alembic/versions/005_sessions_and_oauth_users.py (plan 22c-02; referenced via down_revision)
    - api_server/tests/conftest.py (lines 99-124 — existing TRUNCATE fixture; preserve every pre-existing behavior except the stale table list)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §AMD-03 + §AMD-04 + §D-22c-MIG-03
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pattern 6 (lines 501-558 — exact migration 006 body)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §006_purge_anonymous.py (lines 119-151)
    - Wave-0 spike evidence at `.planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md` (8-table regression test — per BLOCKER-4 Option A, SPIKE-B now carries R8's runnable regression; this task's migration test is a LIGHTER artifact+apply check)
  </read_first>
  <action>
**BLOCKER-4 context:** Plan 22c-01's SPIKE-B was extended (per Option A) to exercise the FULL 8-table FK graph post-alembic-005: seed, TRUNCATE, assert all 8 tables COUNT=0, assert alembic_version preserved. That spike IS the runnable regression for R8. This task's `test_migration_006_truncates_all_data_tables` is intentionally a LIGHTER check — it validates that migration 006's text contains the TRUNCATE statement and that `alembic upgrade head` succeeds. The heavy behavioral coverage lives in SPIKE-B + plan 22c-09 Task 1 pre-assertion (belt-and-suspenders per BLOCKER-4 Option C).

---

**File 1: `api_server/alembic/versions/006_purge_anonymous.py`**

Copy RESEARCH Pattern 6 body verbatim (lines 501-558). Exact contents:

```python
"""006_purge_anonymous — IRREVERSIBLE data purge.

Phase 22c AMD-04: all current DB data is dev mock from Phase 19/22 execution.
Zero real customer data exists. This migration TRUNCATEs every data-bearing
table so OAuth users start with a clean slate.

PRESERVED:
  - Schema (all tables, columns, indexes, FKs stay)
  - alembic_version table (this very migration's row lands here on upgrade)

DESTROYED (CASCADE order not strictly needed with TRUNCATE ... CASCADE, but
document the FK graph for the reader):
  - agent_events (FK -> agent_containers ON DELETE CASCADE)
  - runs (FK -> agent_instances)
  - agent_containers (FK -> agent_instances + users)
  - agent_instances (FK -> users, UNIQUE user_id + recipe_name + model)
  - idempotency_keys (FK -> users + runs)
  - rate_limit_counters (no FK)
  - sessions (FK -> users, added in 005)
  - users (includes ANONYMOUS row; post-AMD-03)

IRREVERSIBLE: downgrade() raises NotImplementedError. Restore from backup
if needed. (Dev/mock-only data; no backup strategy.)

Revision ID: 006_purge_anonymous
Revises: 005_sessions_and_oauth_users
Create Date: 2026-04-19
"""
from alembic import op

revision = "006_purge_anonymous"
down_revision = "005_sessions_and_oauth_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TRUNCATE ... CASCADE is transactional + fast. One statement covers the
    # full dependency graph because every data table's FKs either point
    # into this set or aren't enforced (rate_limit_counters).
    op.execute(
        "TRUNCATE TABLE "
        "agent_events, runs, agent_containers, agent_instances, "
        "idempotency_keys, rate_limit_counters, sessions, users "
        "CASCADE"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "006_purge_anonymous is irreversible. "
        "Data was dev-mock only; restore from PG dump if truly needed."
    )
```

**File 2: `api_server/tests/test_migration.py` — append a new integration test (LIGHTER check; R8 behavioral regression lives in SPIKE-B)**

Append (preserve all existing tests):

```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_migration_006_artifact_and_apply(migrated_pg):
    """Phase 22c migration 006 — artifact existence + apply-to-head succeeds.

    NOTE: The R8 BEHAVIORAL regression (seed → TRUNCATE → assert all 8 tables
    empty + alembic_version preserved) lives in SPIKE-B at
    `tests/spikes/test_truncate_cascade.py` per BLOCKER-4 Option A. That spike
    uses a dedicated function-scoped container because the session-scoped
    `migrated_pg` fixture here would skip the seed step once HEAD reaches 006.

    This test verifies:
    (1) The migration file contains the TRUNCATE text (artifact check).
    (2) `alembic upgrade head` on a session-scoped container reaches HEAD = 006.
    (3) After the session-scoped migrated_pg has been upgraded, all 8 tables
        are empty (belt-and-suspenders — duplicates plan 22c-09 Task 1's
        pre-assertion; catches the case where the TRUNCATE text silently
        no-ops, e.g., table name typo).
    """
    import subprocess
    import sys
    from pathlib import Path

    # (1) Artifact existence
    api_server_dir = Path(__file__).resolve().parent.parent
    migration_path = api_server_dir / "alembic" / "versions" / "006_purge_anonymous.py"
    assert migration_path.exists(), "migration file missing"
    body = migration_path.read_text()
    assert "TRUNCATE TABLE" in body
    assert "sessions" in body
    assert "users" in body
    assert "raise NotImplementedError" in body

    # (2) + (3) Apply + post-apply count check
    dsn = migrated_pg.get_connection_url(driver="asyncpg")
    conn = await asyncpg.connect(dsn)
    try:
        # Force apply-to-head in case the session-scoped fixture is behind.
        sync_dsn = dsn.replace("+asyncpg", "")
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=api_server_dir,
            env={**__import__("os").environ, "DATABASE_URL": sync_dsn},
            check=True,
            capture_output=True,
            text=True,
        )

        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "006_purge_anonymous", f"HEAD != 006: got {version!r}"

        # Belt-and-suspenders: post-006 all 8 tables empty (even if other
        # tests in this session had seeded rows before 006 ran).
        for tbl in (
            "agent_events", "runs", "agent_containers", "agent_instances",
            "idempotency_keys", "rate_limit_counters", "sessions", "users",
        ):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert count == 0, f"{tbl} not cleared by 006: {count}"
    finally:
        await conn.close()
```

**File 3: `api_server/tests/conftest.py`** — fix the stale TRUNCATE list.

Locate the existing TRUNCATE fixture near L120-124. Current:
```python
await conn.execute(
    "TRUNCATE TABLE rate_limit_counters, idempotency_keys, runs, "
    "agent_instances RESTART IDENTITY CASCADE"
)
```

Replace with (exact list — include every data-bearing table from migration 006):
```python
await conn.execute(
    "TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, "
    "idempotency_keys, rate_limit_counters, sessions, users "
    "RESTART IDENTITY CASCADE"
)
```

**Also**: locate the docstring at L99-102 that says `users` is intentionally NOT truncated to preserve the anonymous seed row. Delete or rewrite that paragraph — after migration 006 the anonymous seed no longer exists. Replacement docstring:

```python
# Post-22c: the anonymous seed row is gone (migration 006). Every integration
# test is responsible for creating its own user(s) via the authenticated_cookie
# fixture (see plan 22c-05).
```

If downstream tests (pre-22c) were relying on the anonymous seed row being auto-present, those tests are migrated in Task 4 of this plan.

Commit this task separately:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/alembic/versions/006_purge_anonymous.py api_server/tests/test_migration.py api_server/tests/conftest.py
git commit -m "feat(22c-06 Task1): alembic 006 purge + test fixture TRUNCATE coverage"
```
  </action>
  <verify>
<automated>cd api_server && grep -q "TRUNCATE TABLE agent_events, runs, agent_containers" alembic/versions/006_purge_anonymous.py && grep -q "raise NotImplementedError" alembic/versions/006_purge_anonymous.py && python -c "from alembic.script import ScriptDirectory; from alembic.config import Config; script = ScriptDirectory.from_config(Config('alembic.ini')); assert '006_purge_anonymous' in [s.revision for s in script.walk_revisions()]; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/alembic/versions/006_purge_anonymous.py` exists; `revision = "006_purge_anonymous"`; `down_revision = "005_sessions_and_oauth_users"`
    - Upgrade executes a single TRUNCATE on 8 tables; downgrade raises NotImplementedError
    - New `test_migration_006_artifact_and_apply` test passes AND includes a post-apply 8-table COUNT=0 assertion
    - `conftest.py` TRUNCATE fixture includes `sessions, agent_containers, agent_events, users` in addition to the pre-existing tables
    - Stale comment about "anonymous seed row preservation" removed
    - `alembic upgrade head` on a fresh migrated_pg applies revision `006_purge_anonymous`
  </acceptance_criteria>
  <done>Destructive migration lands; alembic HEAD advances to 006; test fixtures updated to match the new zero-seed reality. R8 behavioral regression coverage deferred to SPIKE-B (plan 22c-01) per BLOCKER-4 Option A.</done>
</task>

<task type="auto">
  <name>Task 2: constants.py + services/run_store.py cleanup + all 4 route handlers migrated to require_user (6 call-sites enumerated)</name>
  <files>api_server/src/api_server/constants.py, api_server/src/api_server/services/run_store.py, api_server/src/api_server/routes/runs.py, api_server/src/api_server/routes/agents.py, api_server/src/api_server/routes/agent_lifecycle.py, api_server/src/api_server/routes/agent_events.py</files>
  <read_first>
    - api_server/src/api_server/constants.py (preserve AP_SYSADMIN_TOKEN_ENV; delete only ANONYMOUS_USER_ID)
    - api_server/src/api_server/services/run_store.py (L25 import, L28 __all__ entry `"ANONYMOUS_USER_ID"`, L441 docstring reference — ALL three must go)
    - api_server/src/api_server/routes/runs.py (L38 import + L173 call-site — find exact grep before editing)
    - api_server/src/api_server/routes/agents.py (L12 import + L23 call-site)
    - api_server/src/api_server/routes/agent_lifecycle.py (7 ANONYMOUS_USER_ID refs across 4 handlers — see enumeration below)
    - api_server/src/api_server/routes/agent_events.py (L76 import + L190 call-site; KEEP sysadmin bypass at L183-184 unchanged — the bypass short-circuits BEFORE require_user)
    - api_server/src/api_server/auth/deps.py (require_user — returns JSONResponse | UUID)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-AUTH-03 + §D-22c-AUTH-04 + §D-22c-MIG-06
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §Routes section (lines 487-502) + §Shared Patterns require_user snippet (lines 1027-1035)
  </read_first>
  <action>
**Step 1: Delete `ANONYMOUS_USER_ID` from `api_server/src/api_server/constants.py`.**

Remove the line that defines `ANONYMOUS_USER_ID`. Preserve every other export (including `AP_SYSADMIN_TOKEN_ENV`). After this edit, `grep ANONYMOUS_USER_ID api_server/src/api_server/constants.py` returns nothing.

---

**Step 2 (BLOCKER-1 FIX): Delete the `ANONYMOUS_USER_ID` re-export from `api_server/src/api_server/services/run_store.py`.**

This module re-exports the constant so routes could import it from a single site. Three edits:

(a) Delete line 25:
```python
from ..constants import ANONYMOUS_USER_ID  # re-export so routes can use a single import site
```

(b) Remove the `"ANONYMOUS_USER_ID"` entry from the `__all__` list at L27-42 (specifically L28). After edit, `__all__` no longer contains that string.

(c) Update the docstring at L440-446 inside `fetch_agent_instance`. Current text mentions `ANONYMOUS_USER_ID`:
```
"""Return the ``agent_instances`` row for ``(agent_id, user_id)`` or None.

The ``user_id`` parameter is the multi-tenancy seam for Phase 21+:
today it's always ``ANONYMOUS_USER_ID`` in the caller, but keeping
the signature user-scoped means the migration to real session
resolution is a one-line change in the route layer, not a query
rewrite here. ..."""
```

Replace with:
```
"""Return the ``agent_instances`` row for ``(agent_id, user_id)`` or None.

The ``user_id`` parameter is the multi-tenancy seam: the route layer
resolves it via ``require_user`` (plan 22c-05) from the authenticated
session cookie. Defense in depth: even if the route forgets to pass
the correct user_id, the query can't leak cross-user rows because
``user_id`` is always in the WHERE clause. ..."""
```

Verify:
```bash
grep -n "ANONYMOUS_USER_ID" api_server/src/api_server/services/run_store.py
```
Expected: zero matches.

---

**Step 3: Migrate each route file.** For each of `runs.py`, `agents.py`, `agent_lifecycle.py`, `agent_events.py`:

1. Delete the line `from ..constants import ANONYMOUS_USER_ID`.
2. Add `from ..auth.deps import require_user` near the other imports.
3. If not already imported, add `from uuid import UUID` (for annotating the resolved user_id).
4. Find every handler function that uses `ANONYMOUS_USER_ID`. At the TOP of each handler body (after Bearer parse where applicable — agent_events sysadmin bypass runs BEFORE), insert the inline check:

```python
result = require_user(request)
if isinstance(result, JSONResponse):
    return result
user_id: UUID = result
```

5. Replace every `ANONYMOUS_USER_ID` reference within the handler with the newly-introduced `user_id` local.

---

**File-specific enumeration (WARNING-6 fix — no more "4+" hand-waving):**

- `routes/runs.py` — L38 import + L173 call-site. One handler (`create_run`) touches ANONYMOUS_USER_ID. Add `require_user` at the TOP, AFTER the existing Bearer parse check but BEFORE the DB acquire. Update the call-site to `upsert_agent_instance(conn, user_id=user_id, ...)`.

- `routes/agents.py` — simplest. One handler (`list_user_agents`); add require_user at top; replace `ANONYMOUS_USER_ID` on L23 with `user_id`.

- `routes/agent_lifecycle.py` — **6 call-sites across 4 handlers (WARNING-6 enumeration; executor must grep at task start to confirm exact line numbers since prior plans may shift them):**
  - `start_agent` (line 191 fn def) — 4 refs at L242, L245, L320, L338
  - `stop_agent` (line 530 fn def) — 1 ref at L558
  - `agent_status` (line 651 fn def) — 1 ref at L679 (AND this handler currently has NO Bearer check — adding require_user is a behavior change per D-22c-AUTH-03)
  - `pair_channel` (line 746 fn def) — 1 ref at L791
  - The docstring mentions (e.g. L14, L662) describing "Phase 19's ANONYMOUS_USER_ID" should also be updated to reflect the new session-resolved user_id model.
  - Each of the 4 handlers gets the `require_user` prelude. Total: 4 `result = require_user(request)` insertions.

- `routes/agent_events.py` — KEEP the sysadmin bypass at L183-184 UNCHANGED. The bypass path short-circuits BEFORE require_user runs (Bearer token == AP_SYSADMIN_TOKEN ⇒ return early with access granted). For the non-bypass path (L190 area), add the require_user check AFTER the Bearer parse fails the sysadmin check. Same pattern for `inject_test_event` if it exists in the same file.

---

**After every file edit, run:**
```bash
grep -rn "ANONYMOUS_USER_ID" api_server/src/
```
Expected result: **ZERO matches**. Includes `constants.py`, `services/run_store.py`, all 4 route files, and any middleware file. If any remain, the edit is incomplete.

Also verify the specific handler-level grep:
```bash
grep -c ANONYMOUS_USER_ID api_server/src/api_server/routes/agent_lifecycle.py
```
Expected: 0.

**Tests to run locally:** ensure the SOURCE files compile:
```bash
cd api_server && python -c "from api_server.routes import runs, agents, agent_lifecycle, agent_events; from api_server.services import run_store; print('OK')"
```

The existing test suite will still break at this point because the TESTS import ANONYMOUS_USER_ID — that's fixed in Task 4 of this plan.

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/src/api_server/constants.py api_server/src/api_server/services/run_store.py api_server/src/api_server/routes/
git commit -m "feat(22c-06 Task2): delete ANONYMOUS_USER_ID from constants + run_store re-export + migrate 4 route files to require_user"
```
  </action>
  <verify>
<automated>! grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/ && cd api_server && python -c "from api_server.routes import runs, agents, agent_lifecycle, agent_events; from api_server.services import run_store; assert 'ANONYMOUS_USER_ID' not in run_store.__all__; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/constants.py` returns 0 matches
    - `grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/services/run_store.py` returns 0 matches (BLOCKER-1 fix)
    - `"ANONYMOUS_USER_ID" in run_store.__all__` is False
    - `grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/routes/` returns 0 matches
    - `grep -c "result = require_user" api_server/src/api_server/routes/*.py` shows ≥7 hits (runs once, agents once, agent_lifecycle 4 = start+stop+status+pair, agent_events ≥1)
    - agent_events.py sysadmin bypass logic preserved (grep `AP_SYSADMIN_TOKEN` in the file — still present in the pre-require_user path)
    - agent_lifecycle.py::agent_status now begins with the require_user prelude
    - All 4 route modules + run_store import cleanly (no ImportError)
  </acceptance_criteria>
  <done>ANONYMOUS_USER_ID constant + re-export + every route-level reference deleted. All 4 route files use require_user for protected endpoints. Sysadmin bypass preserved. 6 call-sites across 4 handlers enumerated and migrated.</done>
</task>

<task type="auto">
  <name>Task 3: Middleware migration (idempotency + rate_limit) + idempotency test (CLEAN user_id resolution)</name>
  <files>api_server/src/api_server/middleware/idempotency.py, api_server/src/api_server/middleware/rate_limit.py, api_server/tests/middleware/test_idempotency_user_id.py</files>
  <read_first>
    - api_server/src/api_server/middleware/idempotency.py (L18-21 docstring + L36 + L43 import + L159 call-site)
    - api_server/src/api_server/middleware/rate_limit.py (lines 70-91 — `_subject_from_scope`)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-AUTH-04 + §Code Context integration-points
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pitfall 4 Option A (lines 686-691 — pass-through on None)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §middleware/idempotency.py (lines 217-241) + §middleware/rate_limit.py (lines 244-267)
  </read_first>
  <action>
**Step 1: `middleware/idempotency.py` — swap ANONYMOUS_USER_ID for request.state.user_id + update docstring.**

Find the existing import (L43-ish):
```python
from ..constants import ANONYMOUS_USER_ID
```
Delete it.

Find the existing assignment at L159-ish:
```python
user_id = ANONYMOUS_USER_ID  # Phase 19 — Phase 21+ resolves real user
```

Replace with the PATTERNS.md-recommended CLEAN form (WARNING-4 fix — no opaque `getattr + lambda` expression):

```python
# SessionMiddleware (plan 22c-04) sets scope['state']['user_id']. When None,
# the request is anonymous — protected routes will 401 via require_user a
# few layers later. We skip the idempotency reservation entirely so anonymous
# replays don't touch the idempotency_keys table (avoiding a NOT-NULL
# violation on user_id).
state = scope.get("state") or {}
user_id = state.get("user_id")
if user_id is None:
    await self.app(scope, _replay_receive(body), send)
    return
```

Note the two-line extraction (`state = ...; user_id = state.get("user_id")`) — cleaner and easier to trace than a nested getattr+lambda chain.

Find the module docstring at L18-21:
```python
"...Phase 21+ swaps ``ANONYMOUS_USER_ID`` for a session-resolved user id; no middleware change needed."
```
Replace with:
```python
"...Phase 22c (plan 22c-06): ``user_id`` is resolved from ``scope['state']``
set by the upstream SessionMiddleware. Anonymous requests (None user_id)
pass through without an idempotency lookup — they will 401 downstream via
``require_user``."
```

---

**Step 2: `middleware/rate_limit.py` — prefer user_id over IP.**

Find `_subject_from_scope` at lines 70-91. CURRENT code walks `scope['headers']` for `x-forwarded-for` then falls back to `scope['client']`. Prepend a user_id check using the SAME clean two-line form:

```python
def _subject_from_scope(scope: Scope, trusted_proxy: bool) -> str:
    # Phase 22c: user-scoped rate limit takes precedence when
    # SessionMiddleware has resolved a UUID.
    state = scope.get("state") or {}
    user_id = state.get("user_id")
    if user_id is not None:
        return f"user:{user_id}"
    # ... existing IP-based fallback kept verbatim ...
    if trusted_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode(errors="ignore").split(",")[0].strip()
                if first:
                    return first
                break
    client = scope.get("client")
    return client[0] if client else "unknown"
```

Preserve the `trusted_proxy` branch and all other functions in the file unchanged.

---

**Step 3: New integration test — `api_server/tests/middleware/test_idempotency_user_id.py`**

Assert the behaviors:
1. `test_anonymous_pass_through` — POST /v1/runs without cookie + with `Idempotency-Key: foo` → 401 from require_user (the route layer); no row in idempotency_keys table
2. `test_authenticated_caches` — POST /v1/runs with valid cookie + with `Idempotency-Key: bar` → succeeds; 2nd POST with same key returns same response; ONE row exists in idempotency_keys with user_id matching the cookie's user

Use fixtures from 22c-05's conftest extensions (`authenticated_cookie`, respx OAuth stubs). For the "route succeeds" path, the test may need to monkeypatch `run_cell` similar to `test_idempotency.py::test_same_key_returns_cache` — follow that pattern.

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/src/api_server/middleware/ api_server/tests/middleware/test_idempotency_user_id.py
git commit -m "feat(22c-06 Task3): idempotency + rate_limit read request.state.user_id"
```
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.middleware.idempotency import IdempotencyMiddleware; from api_server.middleware.rate_limit import _subject_from_scope; s = {'state': {'user_id': __import__('uuid').uuid4()}}; assert _subject_from_scope(s, False).startswith('user:'); s2 = {'state': {'user_id': None}, 'client': ('1.2.3.4', 0), 'headers': []}; assert _subject_from_scope(s2, False) == '1.2.3.4'; print('OK')" && pytest api_server/tests/middleware/test_idempotency_user_id.py -x -v -m api_integration</automated>
  </verify>
  <acceptance_criteria>
    - `middleware/idempotency.py` imports `ANONYMOUS_USER_ID` nowhere; docstring updated
    - `grep -n "getattr(scope.get('state') or {}, 'get', lambda" api_server/src/api_server/middleware/idempotency.py` returns 0 matches (WARNING-4 — no opaque chain form)
    - `grep -c "state = scope.get" api_server/src/api_server/middleware/idempotency.py` returns ≥1 (clean form present)
    - Anonymous requests through IdempotencyMiddleware pass through without touching idempotency_keys
    - `middleware/rate_limit.py::_subject_from_scope` returns `user:<uuid>` when user_id present; IP when None
    - `test_idempotency_user_id.py::test_anonymous_pass_through` passes
    - `test_idempotency_user_id.py::test_authenticated_caches` passes; idempotency_keys row owned by the authenticated user
  </acceptance_criteria>
  <done>Middleware layer fully user-aware with CLEAN two-line user_id extraction. Anonymous POSTs no longer corrupt the idempotency cache. Rate limits are per-user when authenticated.</done>
</task>

<task type="auto">
  <name>Task 4 (BLOCKER-2 FIX): Migrate 7 test files from ANONYMOUS_USER_ID to authenticated_cookie / literal UUID seed / TEST_USER_ID</name>
  <files>api_server/tests/test_events_auth.py, api_server/tests/test_events_inject_test_event.py, api_server/tests/test_events_long_poll.py, api_server/tests/test_events_lifespan_reattach.py, api_server/tests/test_events_lifecycle_cancel_on_stop.py, api_server/tests/test_events_watcher_backpressure.py, api_server/tests/test_idempotency.py</files>
  <read_first>
    - api_server/tests/conftest.py (authenticated_cookie fixture shipped in plan 22c-05 Task 4)
    - api_server/tests/test_events_auth.py L20 + L158 + L259 (import + fixture docstring + test docstring)
    - api_server/tests/test_events_inject_test_event.py L46 + L179 + L212 + L224 (import + 3 usages as user_id arg)
    - api_server/tests/test_events_long_poll.py L27 (import only — usage search needed; run `grep -n ANONYMOUS_USER_ID api_server/tests/test_events_long_poll.py`)
    - api_server/tests/test_events_lifespan_reattach.py L33 + L59 + L71 + L93 + L105 (import + 4 usages as user_id arg)
    - api_server/tests/test_events_lifecycle_cancel_on_stop.py L37 + L52 + L64 (LOCAL redef + 2 usages)
    - api_server/tests/test_events_watcher_backpressure.py L49 + L75 + L87 (LOCAL redef + 2 usages)
    - api_server/tests/test_idempotency.py L107 (DOCSTRING mention only)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §test migration patterns (if present)
  </read_first>
  <action>
**Context (BLOCKER-2):** After Task 2 deletes `ANONYMOUS_USER_ID` from `constants.py` and `run_store.py`, these 7 test files break at IMPORT time:

```
ImportError: cannot import name 'ANONYMOUS_USER_ID' from 'api_server.constants'
```

Two classes of fix:

**Class A — files with `from api_server.constants import ANONYMOUS_USER_ID` (5 files):**
- `test_events_auth.py` (L20 import, L158 + L259 docstring mentions)
- `test_events_inject_test_event.py` (L46 import + L179/L212/L224 as user_id fn arg)
- `test_events_long_poll.py` (L27 import)
- `test_events_lifespan_reattach.py` (L33 import + L59/L71/L93/L105 as user_id fn arg)
- `test_idempotency.py` (L107 docstring mention only — no import, but docstring mentions the constant)

Replacement strategy: these tests seed data directly via asyncpg for OWN-purposes; they don't exercise the HTTP auth surface. The cleanest fix is a **literal UUID seed** at module level:
```python
# Deterministic seed user id for DB-layer tests that do not exercise HTTP auth.
# Post-22c, no "anonymous" constant exists — this UUID is just a placeholder
# the test uses to satisfy the user_id FK. Real HTTP-layer tests use
# authenticated_cookie from conftest.py (plan 22c-05).
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")
```

Substitute every usage:
- `ANONYMOUS_USER_ID,` → `TEST_USER_ID,`  (in fn arg positions)
- Docstring "ANONYMOUS_USER_ID" → "a test placeholder user id" or "TEST_USER_ID"

**Executable before/after for the 2 files with multiple usages (WARNING-B fix explicit diffs):**

---

### Diff for `test_events_inject_test_event.py`

**BEFORE (L46):**
```python
from api_server.constants import ANONYMOUS_USER_ID
```
**AFTER (L46):**
```python
# Phase 22c: ANONYMOUS_USER_ID constant deleted. Use a deterministic local
# seed UUID for DB-layer fixtures that don't exercise the HTTP auth surface.
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")
```
(`UUID` import at L40 already present.)

**BEFORE (L179, L212, L224 — all of the form `ANONYMOUS_USER_ID,` as a fn arg):**
```python
            ANONYMOUS_USER_ID,
```
**AFTER:**
```python
            TEST_USER_ID,
```

---

### Diff for `test_events_lifespan_reattach.py`

**BEFORE (L33):**
```python
from api_server.constants import ANONYMOUS_USER_ID
```
**AFTER (L33):**
```python
# Phase 22c: ANONYMOUS_USER_ID constant deleted. Use a deterministic local
# seed UUID for DB-layer fixtures that don't exercise the HTTP auth surface.
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")
```

**BEFORE (L59, L71, L93, L105):**
```python
            ANONYMOUS_USER_ID,
```
**AFTER:**
```python
            TEST_USER_ID,
```

---

For single-usage files (`test_events_auth.py`, `test_events_long_poll.py`), apply the same pattern: replace the import with `TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")` and rename any usages.

For `test_idempotency.py`, docstring-only mention at L107 — just change the text from:
```
Phase 19 has a single HTTP-visible user (``ANONYMOUS_USER_ID``), so
```
to:
```
Pre-22c the codebase had a single HTTP-visible ANONYMOUS user; post-22c
each test seeds its own user via direct DB insert. This test operates at
the DB layer, so
```

---

**Class B — files with LOCAL redefinitions (2 files):**

- `test_events_lifecycle_cancel_on_stop.py` (L37: `ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")`)
- `test_events_watcher_backpressure.py` (L49: same local redefinition)

These files do NOT import from constants — they define their own local constant with a DIFFERENT UUID (`...001`, not the `...042` placeholder above). The name collision with the deleted global is a semantic hazard — a reader would think these tests rely on the deleted ANONYMOUS_USER_ID.

**Fix:** rename the local symbol to `TEST_USER_ID` to signal it's a test placeholder, not a reference to the (now-deleted) global constant. Keep the UUID value unchanged (so the test behavior is identical).

**BEFORE (both files):**
```python
ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
```
**AFTER (both files):**
```python
# Local test placeholder user id (NOT the deleted global ANONYMOUS_USER_ID).
# The UUID value is unchanged from the pre-22c local redef so fixture
# behavior is identical; only the name changed to avoid confusion.
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
```

Rename the 2 downstream usages in each file:
- `test_events_lifecycle_cancel_on_stop.py`: L52 + L64 `ANONYMOUS_USER_ID,` → `TEST_USER_ID,`
- `test_events_watcher_backpressure.py`: L75 + L87 `ANONYMOUS_USER_ID,` → `TEST_USER_ID,`

Also note there are 2 more files with local redefinitions that the grep survey surfaced but the BLOCKER-2 checklist did not flag explicitly:
- `test_events_lifecycle_spawn_on_start.py` (L50 local redef + L70/L82 usages)
- `test_events_watcher_teardown.py` (L37 local redef + L58/L70 usages)

These show the SAME pattern as Class B. The executor MUST include these in the Task 4 sweep as well — they are dead sibling tests to the 2 the checker flagged, not unrelated files. Apply the same rename.

---

**Final verification:**

```bash
grep -rn "ANONYMOUS_USER_ID" api_server/tests/
```
Expected: **zero matches** across the entire test directory.

```bash
grep -rn "ANONYMOUS_USER_ID" api_server/
```
Expected: **zero matches** across the entire repo.

Run the affected tests to confirm they still pass:
```bash
cd api_server && pytest tests/test_events_auth.py tests/test_events_inject_test_event.py tests/test_events_long_poll.py tests/test_events_lifespan_reattach.py tests/test_events_lifecycle_cancel_on_stop.py tests/test_events_watcher_backpressure.py tests/test_events_lifecycle_spawn_on_start.py tests/test_events_watcher_teardown.py tests/test_idempotency.py -x -v -m api_integration
```

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/tests/
git commit -m "feat(22c-06 Task4): migrate 7+2 test files off ANONYMOUS_USER_ID to TEST_USER_ID local seed"
```
  </action>
  <verify>
<automated>! grep -rn "ANONYMOUS_USER_ID" api_server/ && cd api_server && python -c "from tests.test_events_auth import *; from tests.test_events_inject_test_event import *; from tests.test_events_long_poll import *; from tests.test_events_lifespan_reattach import *; from tests.test_events_lifecycle_cancel_on_stop import *; from tests.test_events_watcher_backpressure import *; from tests.test_idempotency import *; print('imports OK')" 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -rn "ANONYMOUS_USER_ID" api_server/` returns 0 matches ACROSS THE ENTIRE REPO (src + tests)
    - 5 Class-A test files use module-level `TEST_USER_ID = UUID(...)` literal seed instead of the deleted global import
    - 4 Class-B test files (2 flagged + 2 discovered in sweep) renamed their local `ANONYMOUS_USER_ID` → `TEST_USER_ID` (UUID value preserved, only name changed)
    - `test_idempotency.py` docstring updated (no code change beyond the docstring text)
    - All 9 affected test files import cleanly (no ImportError)
    - pytest run of the 9 files exits 0 — the tests themselves still pass (no behavior change, only name changes)
    - Commit on main: `feat(22c-06 Task4): migrate 7+2 test files off ANONYMOUS_USER_ID to TEST_USER_ID local seed`
  </acceptance_criteria>
  <done>BLOCKER-2 closed. Entire repo is free of `ANONYMOUS_USER_ID` references. Tests use `TEST_USER_ID` as a clearly-signalled test placeholder.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Alembic runner -> PG | Migration 006 runs TRUNCATE CASCADE with owner privileges. Irreversible. |
| route -> require_user | Every protected handler trusts `request.state.user_id` set by SessionMiddleware. The chain (cookie -> SessionMiddleware -> require_user) is the auth boundary. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-19 | Tampering | Migration 006 run on a prod DB with real users | mitigate | Docstring screams "IRREVERSIBLE". Zero real users exist today (verified per CONTEXT §Specific Ideas). Operator confirmation lives in the pre-deploy rotation checklist. |
| T-22c-20 | Elevation of privilege | Route missed during ANONYMOUS_USER_ID sweep | mitigate | Deleting the constant from constants.py AND the re-export from run_store.py turns any residual reference into an ImportError — the compiler IS the safety net. Grep-based verify across entire repo enforces coverage. |
| T-22c-21 | DoS | Anonymous flood of POST /v1/runs creates millions of idempotency rows | mitigate | Anonymous branch now pass-through; no idempotency_keys rows created from anonymous traffic. Rate-limit middleware still fires on IP. |
| T-22c-22 | Information disclosure | Rate-limit counter leaks user-ID through cross-user timing | accept | `user:<uuid>` is the rate-limit key; the UUID is not returned to the user. No cross-channel timing oracle. |
</threat_model>

<verification>
```bash
cd api_server && alembic upgrade head
! grep -rn "ANONYMOUS_USER_ID" api_server/
cd api_server && pytest tests/middleware/test_idempotency_user_id.py tests/test_migration.py tests/test_events_auth.py tests/test_events_inject_test_event.py tests/test_events_long_poll.py tests/test_events_lifespan_reattach.py tests/test_events_lifecycle_cancel_on_stop.py tests/test_events_watcher_backpressure.py tests/test_idempotency.py -m api_integration
```
</verification>

<success_criteria>
- Migration 006 applies; HEAD = `006_purge_anonymous`; `alembic downgrade` raises NotImplementedError
- `grep ANONYMOUS_USER_ID` against `api_server/` returns 0 hits (src + tests, ENTIRE REPO)
- `services/run_store.py` no longer imports or re-exports ANONYMOUS_USER_ID (BLOCKER-1 closed)
- All 4 route files use `require_user` for protected endpoints
- `agent_lifecycle.py::agent_status` now protected
- IdempotencyMiddleware uses clean two-line user_id extraction (no opaque getattr+lambda) — WARNING-4 closed
- RateLimitMiddleware keys on user_id when present
- `conftest.py` TRUNCATE list updated (sessions + agent_containers + agent_events + users included)
- 7+2 test files migrated off ANONYMOUS_USER_ID (BLOCKER-2 closed)
- 4 commits on main: Task 1, Task 2, Task 3, Task 4 (acceptable to squash into one `feat(22c-06): ...` if CI runs)
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-06-SUMMARY.md` with:
- Migration 006 application confirmed; alembic_version HEAD verified
- Exact grep result for `ANONYMOUS_USER_ID` across whole repo (expect: 0 hits)
- List of protected routes + which ones are NEW additions (agent_status)
- List of 9 test files migrated (7 flagged + 2 discovered) with before/after name mapping
- Any remaining follow-ups discovered during the sweep (escalate to 22c-09 if found)
</output>
</output>
