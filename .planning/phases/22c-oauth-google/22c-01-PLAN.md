---
phase: 22c-oauth-google
plan: 01
type: execute
wave: 0
depends_on: []
files_modified:
  - api_server/pyproject.toml
  - api_server/tests/spikes/__init__.py
  - api_server/tests/spikes/test_respx_authlib.py
  - api_server/tests/spikes/test_truncate_cascade.py
  - .planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md
  - .planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md
  - api_server/tests/auth/__init__.py
  - api_server/tests/middleware/__init__.py
autonomous: true
requirements: [SPIKE-A, SPIKE-B, AMD-05]
must_haves:
  truths:
    - "authlib + itsdangerous + respx installed via `pip install -e .[dev]` in api_server/"
    - "Spike A (respx × authlib 1.6.11 interop) PASSES — respx intercepts authlib's httpx token-exchange call; no network call escapes"
    - "Spike B (TRUNCATE CASCADE on FULL 8-table FK graph — revised per BLOCKER-4 Option A) PASSES — applies alembic 001..005, seeds one row into EACH of the 8 data tables (users, sessions, agent_instances, agent_containers, runs, agent_events, idempotency_keys, rate_limit_counters), runs `TRUNCATE TABLE <8 tables> CASCADE`, asserts all 8 tables COUNT=0, asserts alembic_version still holds '005_sessions_and_oauth_users'"
    - "Spike-evidence markdown artifacts committed with pytest output"
    - "Empty test directory scaffolds exist for auth/ and middleware/ (so Wave 1/2 plans can drop tests in without repo-layout scramble)"
  artifacts:
    - path: "api_server/pyproject.toml"
      contains: "authlib>=1.6.11"
    - path: "api_server/pyproject.toml"
      contains: "itsdangerous>=2.2.0"
    - path: "api_server/pyproject.toml"
      contains: "respx"
    - path: "api_server/tests/spikes/test_respx_authlib.py"
      provides: "SPIKE-A test"
    - path: "api_server/tests/spikes/test_truncate_cascade.py"
      provides: "SPIKE-B test (8-table version — regression covers R8)"
    - path: ".planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md"
      provides: "Spike A evidence"
    - path: ".planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md"
      provides: "Spike B evidence (8-table)"
  key_links:
    - from: "api_server/pyproject.toml"
      to: "authlib + itsdangerous + respx PyPI packages"
      via: "pip install -e .[dev]"
      pattern: "authlib>=1.6.11"
    - from: "SPIKE-B 8-table test"
      to: "R8 acceptance criterion (post-006 all 8 data tables empty + alembic_version preserved)"
      via: "exercise FULL FK graph post-alembic-005 → regression cover migration 006"
      pattern: "TRUNCATE TABLE.*sessions"
---

<objective>
Wave 0 hard gate (golden rule 5 + D-22c-TEST-03). Add the three new deps (authlib, itsdangerous, respx) to `api_server/pyproject.toml`, scaffold the `tests/spikes/` + `tests/auth/` + `tests/middleware/` directories, and PROVE two gray-area mechanisms with real tests against real infra BEFORE any downstream wave touches code:

1. **SPIKE-A — respx × authlib 1.6.11 interop.** Per RESEARCH Open Question 5, respx-intercepts-httpx-from-inside-authlib is historically flaky and was ONLY fully fixed in modern versions. If this breaks, the entire D-22c-TEST-01 test strategy (AMD-05-revised) collapses and the phase goes back to discuss.

2. **SPIKE-B — TRUNCATE CASCADE on the FULL 8-table FK graph (REVISED per BLOCKER-4 Option A).** Migration 006 (in plan 22c-06) issues ONE `TRUNCATE ... CASCADE` over `agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users`. This spike now applies migrations 001..005 (so `sessions` exists), seeds a row into EACH of the 8 tables, runs the TRUNCATE statement that migration 006 will run verbatim, and asserts all 8 tables are empty + alembic_version still holds '005_sessions_and_oauth_users'. **This spike IS the regression test for R8 (migration-006 acceptance criterion)** — plan 22c-06's own `test_migration_006_truncates_all_data_tables` is weakened by session-scoped fixture issues (will skip in practice when HEAD is already 006), so this spike carries the runnable proof.

If SPIKE-B fails, migration 006 must fall back to sequential `DELETE FROM` in FK-aware order, and the phase returns to discuss.

No downstream wave (22c-02..22c-09) executes until both spikes return GREEN.

Purpose: Close the two gray areas flagged in RESEARCH §Open Questions 3 and 5, make respx available to every downstream test file, AND produce a runnable regression test that covers R8 end-to-end.
Output: Two green spike tests + two evidence markdowns + deps installed + empty test-dir scaffolds for Wave 1+2 plans to drop files into.
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
@.planning/phases/22c-oauth-google/22c-VALIDATION.md
@api_server/pyproject.toml
@api_server/tests/conftest.py
@api_server/tests/test_migration.py

<interfaces>
<!-- Key fixtures the spike tests will reuse, extracted from conftest.py L46-73. -->

From api_server/tests/conftest.py:
```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
def migrated_pg(postgres_container):
    # Runs `alembic upgrade head` against postgres_container, returns the container.
    # Env injection: DATABASE_URL = postgres_container.get_connection_url(driver="asyncpg")
```

From authlib 1.6.11 (`authlib.integrations.starlette_client`):
- `OAuth()` — registry; no state
- `oauth.register(name="google", client_id=..., client_secret=..., server_metadata_url="https://accounts.google.com/.well-known/openid-configuration", client_kwargs={"scope": "openid email profile"})`
- After registration: `oauth.google` is a `StarletteOAuth2App` with `.fetch_token(url, grant_type="authorization_code", code=..., redirect_uri=..., state=...)` and `.get(url, token=...)` methods

From respx ^0.21:
- `@respx.mock` decorator OR `with respx.mock: ...` context manager
- `respx.post(url).mock(return_value=httpx.Response(200, json=...))`
- `respx.calls.assert_called_once()` to assert the stub fired
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add authlib + itsdangerous + respx to pyproject.toml</name>
  <files>api_server/pyproject.toml</files>
  <read_first>
    - api_server/pyproject.toml (current deps block L10-46)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §api_server/pyproject.toml (lines 603-633; exact deps to append)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Standard Stack (L122-152)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §AMD-05 + §AMD-07
  </read_first>
  <action>
Append 2 entries to the `dependencies = [...]` block (AFTER the `cryptography>=42` line, BEFORE the closing `]`):
```toml
  "authlib>=1.6.11,<1.7",
  "itsdangerous>=2.2.0,<3",
```
Append 1 entry to the `[project.optional-dependencies].dev = [...]` block (AFTER `"httpx>=0.27"`, BEFORE closing `]`):
```toml
  "respx>=0.21,<0.22",
```
Rationale (per AMD-05 + AMD-07 + RESEARCH):
- `authlib>=1.6.11` is the OAuth2/OIDC client (ships StarletteOAuth2App with httpx backend)
- `itsdangerous>=2.2.0` is REQUIRED by Starlette's built-in SessionMiddleware (signs the `ap_oauth_state` cookie — the authlib CSRF state store, per AMD-07). It's already present as a transitive dep (`pip show itsdangerous` → 2.2.0) but must be pinned explicitly now that we're load-bearing on it.
- `respx>=0.21` supersedes CONTEXT D-22c-TEST-01's `responses` per AMD-05 — `responses` only intercepts the `requests` library; authlib uses `httpx`, so `respx` is the httpx-native equivalent.

Then install the deps IN THE VIRTUALENV USED BY THE API TESTS:
```bash
cd api_server && pip install -e ".[dev]"
```
(Or equivalent `uv sync --dev` / project-local venv command — use whatever `api_server/tests/conftest.py` and `test_migration.py` rely on; grep for `pytest` invocations in prior plan SUMMARYs if unsure.)

Verify all three imports resolve:
```bash
cd api_server && python -c "import authlib; import itsdangerous; import respx; print(authlib.__version__, itsdangerous.__version__, respx.__version__)"
```
  </action>
  <verify>
<automated>cd api_server && grep -q 'authlib>=1.6.11,<1.7' pyproject.toml && grep -q 'itsdangerous>=2.2.0,<3' pyproject.toml && grep -q 'respx>=0.21,<0.22' pyproject.toml && python -c "import authlib, itsdangerous, respx"</automated>
  </verify>
  <acceptance_criteria>
    - `grep -E 'authlib|itsdangerous|respx' api_server/pyproject.toml` returns 3 matching lines with pinned versions
    - `python -c "import authlib, itsdangerous, respx"` exits 0 (all three importable after `pip install -e .[dev]`)
    - `authlib.__version__` ≥ `1.6.11`; `respx.__version__` ≥ `0.21`
  </acceptance_criteria>
  <done>Three deps pinned, installed, importable. AMD-05 and AMD-07 prerequisites satisfied.</done>
</task>

<task type="auto">
  <name>Task 2: Scaffold test directories + SPIKE-A (respx × authlib interop)</name>
  <files>api_server/tests/spikes/__init__.py, api_server/tests/spikes/test_respx_authlib.py, api_server/tests/auth/__init__.py, api_server/tests/middleware/__init__.py, .planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md</files>
  <read_first>
    - api_server/tests/test_rate_limit.py (minimal test harness pattern — `@pytest.mark.api_integration` + `@pytest.mark.asyncio` usage)
    - api_server/tests/conftest.py (fixture shape; `migrated_pg` is NOT needed for SPIKE-A — pure in-process authlib + respx)
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Open Question 5 (lines 854-859) + §Code Examples (L771-799)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-TEST-03 Spike A
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §api_server/tests/spikes/test_respx_authlib.py (lines 942-951)
  </read_first>
  <action>
Create empty `__init__.py` in three new test directories:
- `api_server/tests/spikes/__init__.py` — empty
- `api_server/tests/auth/__init__.py` — empty
- `api_server/tests/middleware/__init__.py` — empty

Create `api_server/tests/spikes/test_respx_authlib.py`:
```python
"""SPIKE A (Wave 0 gate) — respx × authlib 1.6.11 interop.

Proves that `respx` correctly intercepts authlib's outbound httpx calls to
Google's OAuth endpoints BEFORE any downstream test authors a real OAuth
integration test against respx stubs. Per D-22c-TEST-03 + AMD-05 + RESEARCH
§Open Question 5.

PASS criterion: the stubbed Google /token endpoint fires exactly once and
authlib parses the canned payload without a network call escaping.

FAIL → phase goes back to discuss-phase; respx + authlib combination
is not compatible and the test strategy must be revisited (pytest-httpx
fallback per RESEARCH Alternatives Considered).
"""
from __future__ import annotations

import httpx
import pytest
import respx
from authlib.integrations.starlette_client import OAuth


@pytest.mark.asyncio
@respx.mock
async def test_respx_intercepts_authlib_token_exchange():
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id="spike-client-id",
        client_secret="spike-client-secret",
        access_token_url="https://oauth2.googleapis.com/token",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        client_kwargs={"scope": "openid email profile"},
    )

    token_route = respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ya29.spike",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "openid email profile",
            },
        )
    )

    # Exercise authlib's token-exchange path directly (no Starlette request needed).
    token = await oauth.google.fetch_access_token(
        code="spike-auth-code",
        redirect_uri="http://localhost:8000/v1/auth/google/callback",
    )

    assert token_route.called, "respx did not intercept authlib's token call"
    assert token["access_token"] == "ya29.spike"
    assert token["token_type"] == "Bearer"
```

Create evidence artifact at `.planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md`:
```markdown
# Spike A — respx × authlib 1.6.11 interop

**Run date:** <executor fills>
**Command:** `cd api_server && pytest tests/spikes/test_respx_authlib.py -x -v`
**Result:** <PASS / FAIL>

## Rationale
RESEARCH §Open Question 5 flagged that historical versions of authlib+respx+httpx
had an interop bug (respx issue #46 through authlib 0.15.0). Modern versions
(authlib 1.6.11 + respx 0.21 + httpx 0.27) are expected to work but had not
been empirically verified in this repo. Per golden rule 5, spike it before
downstream plans commit to the pattern.

## Version pins verified
- authlib: <version>
- respx: <version>
- httpx: <version>

## Test output (captured)
```
<paste `pytest -v` output here>
```

## Decision
- PASS → AMD-05 stands; all downstream OAuth integration tests use `@respx.mock`.
- FAIL → return to discuss-phase; evaluate `pytest-httpx` fallback.
```

Run the spike:
```bash
cd api_server && pytest tests/spikes/test_respx_authlib.py -x -v 2>&1 | tee /tmp/spike-a.log
```

Paste the full `pytest -v` stdout (including authlib + respx + httpx versions) into the evidence markdown's "Test output" section. If the test FAILS, STOP and return `## BLOCKER: SPIKE-A FAILED` to the orchestrator — do NOT proceed to Task 3.
  </action>
  <verify>
<automated>cd api_server && pytest tests/spikes/test_respx_authlib.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/spikes/test_respx_authlib.py` exits 0 (1 passed)
    - `token_route.called` assertion passes inside the test
    - Evidence markdown exists and contains non-empty `## Test output` section with the pytest stdout pasted in
    - `test -d api_server/tests/spikes && test -d api_server/tests/auth && test -d api_server/tests/middleware` all true
  </acceptance_criteria>
  <done>SPIKE-A green; respx intercepts authlib's httpx token-exchange call; test dirs scaffolded for Wave 1/2 plans. D-22c-TEST-03 Spike A clears.</done>
</task>

<task type="auto">
  <name>Task 3: SPIKE-B — TRUNCATE CASCADE on FULL 8-table FK graph (regression covers R8)</name>
  <files>api_server/tests/spikes/test_truncate_cascade.py, .planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md</files>
  <read_first>
    - api_server/tests/conftest.py (lines 46-73 — `postgres_container` + `migrated_pg` fixtures; note: SPIKE-B needs a FRESH container because `migrated_pg` is session-scoped and HEAD may already be beyond 005)
    - api_server/tests/test_migration.py (migration-aware test patterns — how to run alembic subprocess-style against a testcontainer at a SPECIFIC revision)
    - api_server/alembic/versions/001_baseline.py (5 baseline tables: users + agent_instances + runs + idempotency_keys + rate_limit_counters)
    - api_server/alembic/versions/003_agent_containers.py (adds agent_containers with FK to users + agent_instances)
    - api_server/alembic/versions/004_agent_events.py (adds agent_events with FK to agent_containers ON DELETE CASCADE)
    - api_server/alembic/versions/005_sessions_and_oauth_users.py (**will be shipped by plan 22c-02 — this spike runs AFTER 22c-02 completes, per Wave 0 → Wave 1 ordering. If 22c-02 is not yet shipped at the time this plan runs, SPIKE-B runs against 004 only and plan 22c-06 adds the sessions-table coverage retroactively. See implementation note in the action block.**)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-TEST-03 Spike B + §D-22c-MIG-03
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Open Question 3 (lines 846-848) + §Pattern 6 (destructive migration shape)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §api_server/tests/spikes/test_truncate_cascade.py (lines 953-981)
  </read_first>
  <action>
**ORDERING NOTE — BLOCKER-4 Option A implementation:**

The 8-table regression test NEEDS the `sessions` table, which is added by migration 005 (plan 22c-02). Since this is plan 22c-01 (Wave 0) and migrations 001-004 are currently HEAD, we have two execution modes:

- **Mode A (PREFERRED — if plan 22c-02 has shipped):** Spike runs the full 8-table TRUNCATE against alembic HEAD = 005.
- **Mode B (FALLBACK — if 22c-02 has NOT shipped):** Spike runs the 7-table TRUNCATE against alembic HEAD = 004 (no `sessions`). At the end, the test emits a `pytest.skip` branch that reminds the executor: "8-table coverage deferred to plan 22c-06 Task 1 via an expanded test_migration_006_truncates_all_data_tables".

**The executor detects which mode applies by checking for the existence of `api_server/alembic/versions/005_sessions_and_oauth_users.py` BEFORE writing the test body.** If it exists, write Mode A. If not, write Mode B with a comment noting the deferral.

Regardless of mode, the spike uses a **DEDICATED function-scoped PG container** (NOT the session-scoped `migrated_pg` fixture), because:
- We need to control the exact alembic revision on this container (apply 001 → 005 then seed → TRUNCATE → assert).
- The session-scoped `migrated_pg` may already be at HEAD ≥ 006 in later runs, which would invalidate the seed step.

---

**Create `api_server/tests/spikes/test_truncate_cascade.py`:**

```python
"""SPIKE B (Wave 0 gate) — TRUNCATE CASCADE on the FULL 8-table FK graph.

Per BLOCKER-4 Option A, this spike is the RUNNABLE REGRESSION TEST for R8
(migration 006 acceptance criterion). The in-repo migration-006 test is
weakened by session-fixture scope — it skips when HEAD is already 006.
This spike uses a dedicated function-scoped container and applies migrations
001..005 exactly, so the TRUNCATE-then-assert path is always exercised.

PASS criterion (Mode A, 005 shipped):
  (1) alembic HEAD = '005_sessions_and_oauth_users' after apply
  (2) Seed 1 row into EACH of: users, sessions, agent_instances,
      agent_containers, runs, agent_events, idempotency_keys,
      rate_limit_counters — pre-truncate COUNT ≥ 1 per table
  (3) Post-TRUNCATE: COUNT = 0 in all 8 tables
  (4) alembic_version still holds '005_sessions_and_oauth_users'
      (TRUNCATE did NOT clobber the schema-version bookkeeping table)

PASS criterion (Mode B, 005 not yet shipped — fallback):
  Same shape but over 7 tables (no `sessions`); alembic_version = '004_agent_events'.
  Emits a WARNING log line pointing to plan 22c-06 Task 1 for 8-table coverage.

FAIL → plan 22c-06 (migration 006) must fall back to sequential DELETE FROM
in FK-aware order, and the phase goes back to discuss to revise 22c-06.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer


API_SERVER_DIR = Path(__file__).resolve().parent.parent.parent  # api_server/


# Detect mode at import time so the test output reflects which scenario ran.
_ALEMBIC_005_PATH = API_SERVER_DIR / "alembic" / "versions" / "005_sessions_and_oauth_users.py"
_MODE_A = _ALEMBIC_005_PATH.exists()


@pytest.fixture
def fresh_pg_005():
    """Function-scoped PG container at alembic HEAD = 005 (or 004 in Mode B).

    Dedicated container — not sharing the session-scoped `migrated_pg` because
    that fixture's HEAD may be beyond this spike's target revision.
    """
    target_rev = "005_sessions_and_oauth_users" if _MODE_A else "004_agent_events"
    with PostgresContainer("postgres:17-alpine") as pg:
        dsn = pg.get_connection_url()  # sync-style DSN for alembic subprocess
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target_rev],
            cwd=API_SERVER_DIR,
            env={**os.environ, "DATABASE_URL": dsn},
            check=True,
            capture_output=True,
            text=True,
        )
        yield pg


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_truncate_cascade_clears_all_tables_preserves_alembic_version(fresh_pg_005):
    dsn = fresh_pg_005.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
    # asyncpg wants a clean postgresql:// DSN
    if "+asyncpg" not in dsn and "postgresql://" not in dsn:
        dsn = fresh_pg_005.get_connection_url(driver="asyncpg")

    conn = await asyncpg.connect(dsn)
    try:
        # --- CONFIRM target alembic revision ---
        expected_rev = "005_sessions_and_oauth_users" if _MODE_A else "004_agent_events"
        actual_rev = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert actual_rev == expected_rev, f"alembic HEAD mismatch: got {actual_rev!r}, expected {expected_rev!r}"

        # --- SEED ONE ROW PER DATA-BEARING TABLE ---
        # Columns exact schema comes from migration files; executor reads the
        # alembic versions dir to fill NOT-NULL columns with realistic values.
        user_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        container_row_id = uuid.uuid4()
        run_id_text = f"01ARZ3NDEKTSV4RRFFQ69G5FAV{uuid.uuid4().hex[:6]}"[:26]  # 26-char ULID-shaped
        event_id = uuid.uuid4()

        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "spike-seed-user",
        )
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, display_name) "
            "VALUES ($1, $2, $3, $4, $5)",
            instance_id, user_id, "hermes", "claude-haiku-4.5", "spike-instance",
        )
        # agent_containers — schema from 003_agent_containers.py. Fill ALL NOT-NULL columns:
        await conn.execute(
            "INSERT INTO agent_containers "
            "(id, user_id, agent_instance_id, channel, container_id, image, tag, channel_config_enc) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            container_row_id, user_id, instance_id, "openrouter", "docker-cid-xxx",
            "alpine", "latest", b"\x00\x01spike-encrypted-config",
        )
        # runs — id is TEXT per 001 baseline
        await conn.execute(
            "INSERT INTO runs (id, agent_instance_id, prompt, status) VALUES ($1, $2, $3, $4)",
            run_id_text, instance_id, "spike prompt", "pending",
        )
        # agent_events — FK to agent_containers
        await conn.execute(
            "INSERT INTO agent_events (id, agent_container_id, seq, kind, payload) "
            "VALUES ($1, $2, $3, $4, $5)",
            event_id, container_row_id, 1, "stdout", b'{"ok":true}',
        )
        # idempotency_keys — FK to users
        await conn.execute(
            "INSERT INTO idempotency_keys "
            "(user_id, key, body_hash, run_id, status_code, response_body_json) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            user_id, "spike-idem-key", "spike-hash", run_id_text, 200, b'{}',
        )
        # rate_limit_counters — no FK
        await conn.execute(
            "INSERT INTO rate_limit_counters (subject, bucket, count, window_start) "
            "VALUES ($1, $2, $3, $4)",
            "1.2.3.4", "m", 1, datetime.now(timezone.utc),
        )

        # sessions row only exists in Mode A
        if _MODE_A:
            now = datetime.now(timezone.utc)
            await conn.execute(
                "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
                "VALUES ($1, $2, $3, $2)",
                user_id, now, now + timedelta(days=30),
            )

        # --- Assert pre-truncate row counts ≥ 1 for each seeded table ---
        tables_seeded = [
            "users", "agent_instances", "agent_containers", "runs", "agent_events",
            "idempotency_keys", "rate_limit_counters",
        ]
        if _MODE_A:
            tables_seeded.append("sessions")

        for tbl in tables_seeded:
            pre = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert pre >= 1, f"seed failed: {tbl} COUNT={pre}"

        # --- ACT: issue the migration-006 TRUNCATE statement ---
        if _MODE_A:
            truncate_sql = (
                "TRUNCATE TABLE "
                "agent_events, runs, agent_containers, agent_instances, "
                "idempotency_keys, rate_limit_counters, sessions, users "
                "CASCADE"
            )
        else:
            # Mode B: omit sessions (doesn't exist yet).
            truncate_sql = (
                "TRUNCATE TABLE "
                "agent_events, runs, agent_containers, agent_instances, "
                "idempotency_keys, rate_limit_counters, users "
                "CASCADE"
            )
        await conn.execute(truncate_sql)

        # --- ASSERT all tables empty ---
        for tbl in tables_seeded:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert count == 0, f"{tbl} not cleared: COUNT={count}"

        # --- ASSERT alembic_version preserved (TRUNCATE didn't clobber it) ---
        version_after = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version_after == expected_rev, (
            f"alembic_version clobbered: got {version_after!r}, expected {expected_rev!r}"
        )

        if not _MODE_A:
            # Mode B warning — 8-table coverage deferred.
            import logging
            logging.getLogger(__name__).warning(
                "SPIKE-B ran in Mode B (7 tables, no sessions). "
                "8-table coverage deferred to plan 22c-06 Task 1 expanded migration test."
            )
    finally:
        await conn.close()
```

Implementation notes for the executor:
- The seed INSERT statements for each table MUST satisfy every NOT NULL + CHECK constraint. Read the alembic migration files and adjust columns/values as needed. Use realistic values that don't short-circuit (no `ON CONFLICT DO NOTHING`, no try/except around INSERTs).
- `fresh_pg_005` spawns a NEW PostgresContainer per test — this test is slow (one full alembic run), but it's the only way to guarantee HEAD control. Acceptable cost for a Wave-0 gate.
- The subprocess alembic run uses the sync DSN (`postgresql+psycopg2://` or `postgresql://`), not `postgresql+asyncpg://`.
- If Mode A (005 exists) and alembic_version ends up at something OTHER than `005_sessions_and_oauth_users`, the test fails at the "CONFIRM target alembic revision" assertion — this is INTENTIONAL: it protects against a future migration 006+ landing before this spike and silently skipping the regression.

Run the spike:
```bash
cd api_server && pytest tests/spikes/test_truncate_cascade.py -x -v -m api_integration 2>&1 | tee /tmp/spike-b.log
```

Create `.planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md`:
```markdown
# Spike B — TRUNCATE CASCADE on 8-table FK graph (BLOCKER-4 Option A regression)

**Run date:** <executor fills>
**Command:** `cd api_server && pytest tests/spikes/test_truncate_cascade.py -x -v -m api_integration`
**Mode:** <A (005 shipped, 8 tables) / B (005 pending, 7 tables)>
**Result:** <PASS / FAIL>
**alembic revision at test start:** <version>
**alembic revision at test end:** <same version, TRUNCATE must not clobber>

## Rationale

Per BLOCKER-4 Option A from the revision checker: the in-repo
`test_migration_006_truncates_all_data_tables` (plan 22c-06 Task 1) weakens
to an artifact-existence check when HEAD is already 006 in the session-scoped
fixture. This spike carries the runnable regression — fresh container, applies
alembic 001..005, seeds a row into EACH of the 8 data tables, runs the same
TRUNCATE statement migration 006 will run, asserts all 8 tables COUNT=0
AND alembic_version is preserved.

## Version pins verified
- postgres testcontainer: postgres:17-alpine
- asyncpg: <version>
- alembic: <version>

## Tables seeded + cleared (Mode A)

| Table | Pre-truncate COUNT | Post-truncate COUNT |
|---|---|---|
| users | 1 | 0 |
| sessions | 1 | 0 |
| agent_instances | 1 | 0 |
| agent_containers | 1 | 0 |
| runs | 1 | 0 |
| agent_events | 1 | 0 |
| idempotency_keys | 1 | 0 |
| rate_limit_counters | 1 | 0 |

alembic_version before: `005_sessions_and_oauth_users`
alembic_version after:  `005_sessions_and_oauth_users` (preserved)

## Test output (captured)

```
<paste `pytest -v` output here>
```

## Decision
- PASS → migration 006 (plan 22c-06) uses the single TRUNCATE CASCADE statement as written.
  R8 regression-covered by this spike + a lighter artifact check in 22c-06.
- FAIL → return to discuss-phase; revise migration 006 to sequential DELETE FROM in FK-aware order.
```

If spike FAILS, STOP and return `## BLOCKER: SPIKE-B FAILED` to the orchestrator.

Finally commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/pyproject.toml api_server/tests/spikes/ api_server/tests/auth/__init__.py api_server/tests/middleware/__init__.py .planning/phases/22c-oauth-google/spike-evidence/
git commit -m "test(22c-01): Wave 0 spikes — respx×authlib + 8-table TRUNCATE CASCADE regression"
```
  </action>
  <verify>
<automated>cd api_server && pytest tests/spikes/test_truncate_cascade.py -x -v -m api_integration && pytest tests/spikes/test_respx_authlib.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/spikes/test_truncate_cascade.py -m api_integration` exits 0 (1 passed)
    - Mode A: all 8 tables seeded (COUNT ≥ 1 each); post-truncate all 8 tables COUNT = 0; alembic_version = '005_sessions_and_oauth_users' preserved
    - Mode B (fallback): 7 tables seeded + cleared; evidence markdown notes "Mode B — 8-table coverage deferred to 22c-06 Task 1"
    - Evidence markdown exists with pytest stdout pasted in + table of pre/post counts + alembic revision before/after
    - Commit exists on main branch with message `test(22c-01): Wave 0 spikes — respx×authlib + 8-table TRUNCATE CASCADE regression`
  </acceptance_criteria>
  <done>Both Wave 0 spikes PASS. SPIKE-B now carries R8 regression coverage end-to-end. D-22c-TEST-03 gate cleared. Downstream waves (22c-02..22c-09) authorized to execute.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pyproject.toml → PyPI | Spike tasks install `authlib`, `itsdangerous`, `respx` from PyPI. Supply-chain trust: PyPI + pinned major+minor. |
| Spike tests → real PG | Spike-B runs `TRUNCATE CASCADE` on a testcontainer. No production data, fully ephemeral. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-01 | Tampering | pyproject.toml | accept | Deps pinned to min-version + upper bound (authlib>=1.6.11,<1.7); PyPI is the trusted source consistent with all other repo deps |
| T-22c-02 | Information disclosure | Spike test stdout | accept | No secrets in spike tests; `client_id="spike-client-id"` + `client_secret="spike-client-secret"` are placeholders; `respx` stubs prevent any live network call to Google |
</threat_model>

<verification>
Wave 0 gate: both spike tests return exit 0.
```bash
cd api_server && pytest tests/spikes/ -x -v -m api_integration
cd api_server && pytest tests/spikes/test_respx_authlib.py -x -v
```
Every downstream plan depends on this plan. If either spike fails, the orchestrator returns the phase to discuss-phase for revision — do NOT execute Wave 1+.
</verification>

<success_criteria>
- Three deps pinned + installed + importable: `authlib`, `itsdangerous`, `respx`
- `api_server/tests/spikes/test_respx_authlib.py` PASSES (SPIKE-A)
- `api_server/tests/spikes/test_truncate_cascade.py` PASSES with `-m api_integration` (SPIKE-B — 8-table Mode A preferred, 7-table Mode B acceptable fallback)
- Two evidence markdowns committed with pytest stdout pasted + 8-table count matrix
- `api_server/tests/auth/__init__.py` + `api_server/tests/middleware/__init__.py` exist (scaffold for Wave 1+)
- Commit on main with message `test(22c-01): Wave 0 spikes — respx×authlib + 8-table TRUNCATE CASCADE regression`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-01-SUMMARY.md` with:
- Both spike test results (PASS/FAIL)
- SPIKE-B mode (A = 8-table, B = 7-table fallback)
- Version pins: authlib, respx, httpx, itsdangerous
- Any NOT-NULL constraints discovered while writing spike-B seed INSERTs (these inform 22c-02 migration 005 shape + 22c-06 migration 006 shape)
- Green-light confirmation for Waves 1+
</output>
</output>
