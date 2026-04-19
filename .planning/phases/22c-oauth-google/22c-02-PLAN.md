---
phase: 22c-oauth-google
plan: 02
type: execute
wave: 1
depends_on: [22c-01]
files_modified:
  - api_server/alembic/versions/005_sessions_and_oauth_users.py
autonomous: true
requirements: [R2, R3, R4, R5, R8]
must_haves:
  truths:
    - "sessions table exists in PG after `alembic upgrade head`"
    - "users table has new columns: sub TEXT, avatar_url TEXT, last_login_at TIMESTAMPTZ (all nullable)"
    - "UNIQUE(provider, sub) partial index exists on users WHERE sub IS NOT NULL (preserves ANONYMOUS row which has NULL sub)"
    - "sessions table has PK(id UUID) + FK(user_id→users.id ON DELETE CASCADE) + btree index on user_id"
    - "sessions.expires_at + sessions.revoked_at + sessions.last_seen_at + sessions.user_agent + sessions.ip_address (INET) all present"
    - "migration is fully reversible: `alembic downgrade -1` drops sessions + drops users columns + drops unique index"
  artifacts:
    - path: "api_server/alembic/versions/005_sessions_and_oauth_users.py"
      provides: "alembic migration 005 — sessions table + users.{sub,avatar_url,last_login_at} + UNIQUE(provider, sub) partial index"
      contains: "revision = \"005_sessions_and_oauth_users\""
      contains: "down_revision = \"004_agent_events\""
  key_links:
    - from: "sessions.user_id"
      to: "users.id"
      via: "ForeignKey ON DELETE CASCADE"
      pattern: "sa.ForeignKey.*users.id.*ondelete=.CASCADE"
    - from: "alembic upgrade head"
      to: "005_sessions_and_oauth_users"
      via: "sequential revision chain 001→002→003→004→005"
      pattern: "down_revision = \"004_agent_events\""
---

<objective>
Ship Alembic migration 005 — purely ADDITIVE schema change per D-22c-MIG-02: (a) new `sessions` table backing the server-side session store, (b) three new nullable columns on `users` (`sub`, `avatar_url`, `last_login_at`), (c) `UNIQUE (provider, sub) WHERE sub IS NOT NULL` partial index so the ANONYMOUS seed row (provider=NULL, sub=NULL) keeps working until migration 006 purges it.

Purpose: Provide the PG schema that plan 22c-04 (SessionMiddleware) SELECTs from and plan 22c-05 (auth routes) INSERTs into. Unblocks every downstream backend wave.
Output: One migration file that runs clean on a fresh testcontainers PG (the Wave-0 migrated_pg fixture will now stop at 005 after this plan lands; conftest.py fix happens in 22c-06).
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
@api_server/alembic/versions/001_baseline.py
@api_server/alembic/versions/002_agent_name_personality.py
@api_server/alembic/versions/003_agent_containers.py
@api_server/alembic/versions/004_agent_events.py

<interfaces>
<!-- Existing users table shape from 001_baseline.py (the anchor for additive columns): -->
```python
# users table (baseline):
#   id UUID PRIMARY KEY DEFAULT gen_random_uuid()
#   email TEXT (nullable)
#   display_name TEXT NOT NULL
#   provider TEXT (nullable)  # 'google'/'github' after OAuth; NULL for seeded ANONYMOUS
#   created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

# Seeded row (001_baseline.py line 51-54):
#   INSERT INTO users (id, display_name) VALUES
#     ('00000000-0000-0000-0000-000000000001', 'anonymous')
#   -- provider=NULL, email=NULL, sub=NULL (sub will be NULL after 005 too)
```

<!-- Canonical migration header (from 003_agent_containers.py lines 45-57): -->
```python
"""<short description>

<body>

Revision ID: <slug>
Revises: <prev>
Create Date: <date>
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "<slug>"
down_revision = "<prev>"
branch_labels = None
depends_on = None
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write migration 005 (sessions + users columns)</name>
  <files>api_server/alembic/versions/005_sessions_and_oauth_users.py</files>
  <read_first>
    - api_server/alembic/versions/003_agent_containers.py (exact migration header + create_table idiom + partial unique index)
    - api_server/alembic/versions/002_agent_name_personality.py (canonical `op.add_column` idiom)
    - api_server/alembic/versions/004_agent_events.py (revision pointer for down_revision + tests)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-MIG-02 + §D-22c-MIG-04
    - .planning/phases/22c-oauth-google/22c-SPEC.md §Constraints (sessions table shape)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §005_sessions_and_oauth_users.py (lines 49-115)
  </read_first>
  <action>
Create `api_server/alembic/versions/005_sessions_and_oauth_users.py` with the exact shape below. Each column placement, server_default, and index position is locked by D-22c-MIG-02 + D-22c-MIG-04. Copy + fill:

```python
"""Phase 22c — sessions table + OAuth-facing users columns.

Phase 22c (oauth-google) — this migration lays the DB substrate needed by
the OAuth callback handler, the SessionMiddleware, /v1/users/me, and
/v1/auth/logout.

ADDITIVE ONLY. Migration 006 (in the same phase) is the destructive data
purge of every data-bearing table — see `006_purge_anonymous.py`.

Adds:
  * users.sub TEXT (nullable) — OAuth provider's stable user identifier
  * users.avatar_url TEXT (nullable) — from provider's userinfo
  * users.last_login_at TIMESTAMPTZ (nullable) — updated per callback
  * UNIQUE (provider, sub) WHERE sub IS NOT NULL — partial index so the
    seeded ANONYMOUS row (provider=NULL, sub=NULL) keeps validating. Full
    UNIQUE including NULL-rows would conflict on the NULL-sub seed pair.
  * sessions table — opaque session_id cookie target.

Schema details (sessions):
  id              UUID PK DEFAULT gen_random_uuid()
  user_id         UUID NOT NULL FK → users.id ON DELETE CASCADE
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
  expires_at      TIMESTAMPTZ NOT NULL
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  revoked_at      TIMESTAMPTZ (nullable)
  user_agent      TEXT (nullable)
  ip_address      INET (nullable)

Index policy (D-22c-MIG-04):
  * PK on id covers the hot-path SELECT WHERE id = $1.
  * btree on user_id enables future "list my sessions" without a v2
    migration. No partial WHERE index — PG handles the expiry filter
    cheaply on the PK lookup.

Revision ID: 005_sessions_and_oauth_users
Revises: 004_agent_events
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_sessions_and_oauth_users"
down_revision = "004_agent_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: new columns ---
    op.add_column(
        "users",
        sa.Column("sub", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # --- users: UNIQUE (provider, sub) — partial so ANONYMOUS (sub=NULL) passes ---
    op.create_index(
        "uq_users_provider_sub",
        "users",
        ["provider", "sub"],
        unique=True,
        postgresql_where=sa.text("sub IS NOT NULL"),
    )

    # --- sessions table ---
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessions_user_id",
        "sessions",
        ["user_id"],
    )


def downgrade() -> None:
    # Reverse order of upgrade.
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_users_provider_sub", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "sub")
```

Notes for the executor:
- `INET` import comes from `sqlalchemy.dialects.postgresql` — that import is already in the stanza.
- `ondelete="CASCADE"` on `user_id` FK means deleting a users row will cascade-delete its sessions. Migration 006 relies on this (the TRUNCATE CASCADE on users will sweep sessions too — SPIKE-B confirmed the mechanism).
- The partial index condition `postgresql_where=sa.text("sub IS NOT NULL")` matches migration 003_agent_containers.py's `ix_agent_containers_agent_instance_running` idiom (partial unique index).
- DO NOT add a "DROP EXTENSION pgcrypto" or similar cleanup in downgrade — 001_baseline's extensions are system-level.
- DO NOT seed any rows in this migration. Migration 006 (plan 22c-06) purges all data wholesale.
  </action>
  <verify>
<automated>cd api_server && alembic -c alembic.ini upgrade head 2>&1 | tail -5 && alembic -c alembic.ini history | head -10 && python -c "from alembic.script import ScriptDirectory; from alembic.config import Config; script = ScriptDirectory.from_config(Config('alembic.ini')); assert '005_sessions_and_oauth_users' in [s.revision for s in script.walk_revisions()]; print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/alembic/versions/005_sessions_and_oauth_users.py` exists
    - File contains `revision = "005_sessions_and_oauth_users"` AND `down_revision = "004_agent_events"`
    - `cd api_server && alembic upgrade head` on a fresh testcontainers PG succeeds AND leaves `alembic_version.version_num = '005_sessions_and_oauth_users'`
    - `cd api_server && alembic downgrade -1` successfully rolls back (leaves `alembic_version = '004_agent_events'`) and re-upgrading to head succeeds again (round-trip)
    - psql query on post-upgrade DB: `SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name IN ('sub','avatar_url','last_login_at')` returns 3 rows
    - psql query: `SELECT indexname FROM pg_indexes WHERE tablename='users' AND indexname='uq_users_provider_sub'` returns 1 row
    - psql query: `SELECT column_name FROM information_schema.columns WHERE table_name='sessions' ORDER BY ordinal_position` returns `[id, user_id, created_at, expires_at, last_seen_at, revoked_at, user_agent, ip_address]`
    - psql query: `SELECT indexname FROM pg_indexes WHERE tablename='sessions'` returns `sessions_pkey` AND `ix_sessions_user_id`
    - A FK constraint exists from sessions.user_id to users.id with ON DELETE CASCADE: `SELECT rc.delete_rule FROM information_schema.referential_constraints rc JOIN information_schema.table_constraints tc ON rc.constraint_name = tc.constraint_name WHERE tc.table_name='sessions'` returns `CASCADE`
  </acceptance_criteria>
  <done>Migration 005 lands, reversible, applies cleanly on top of 004. Schema ready for SessionMiddleware (22c-04) + auth routes (22c-05) to consume.</done>
</task>

<task type="auto">
  <name>Task 2: Write migration 005 integration test</name>
  <files>api_server/tests/test_migration.py</files>
  <read_first>
    - api_server/tests/test_migration.py (existing migration tests — follow the same fixture + parametrize shape)
    - api_server/tests/conftest.py (`migrated_pg` session-scoped fixture)
    - api_server/alembic/versions/005_sessions_and_oauth_users.py (just authored)
  </read_first>
  <action>
Append a new test to `api_server/tests/test_migration.py` (preserve all existing tests). Follow the existing test style (grep `@pytest.mark.api_integration` + `@pytest.mark.asyncio` occurrences in the file for shape).

Add AT THE END of the file:

```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_migration_005_sessions_and_users_columns(migrated_pg):
    """Phase 22c migration 005 — additive schema change.

    Asserts:
      * users has sub/avatar_url/last_login_at columns
      * users has partial unique index on (provider, sub) WHERE sub IS NOT NULL
      * sessions table exists with expected columns + FK + btree index
    """
    dsn = migrated_pg.get_connection_url(driver="asyncpg")
    conn = await asyncpg.connect(dsn)
    try:
        users_cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
            )
        }
        assert {"sub", "avatar_url", "last_login_at"}.issubset(users_cols), (
            f"users missing 22c columns; has {users_cols}"
        )

        sessions_cols = [
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name='sessions' "
                "ORDER BY ordinal_position"
            )
        ]
        assert sessions_cols == [
            "id", "user_id", "created_at", "expires_at",
            "last_seen_at", "revoked_at", "user_agent", "ip_address",
        ], f"sessions schema drift: {sessions_cols}"

        idx = await conn.fetchrow(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename='users' AND indexname='uq_users_provider_sub'"
        )
        assert idx is not None, "uq_users_provider_sub index missing"
        assert "sub IS NOT NULL" in idx["indexdef"], (
            f"partial-index predicate missing: {idx['indexdef']}"
        )

        fk_rule = await conn.fetchval(
            "SELECT rc.delete_rule "
            "FROM information_schema.referential_constraints rc "
            "JOIN information_schema.table_constraints tc "
            "  ON rc.constraint_name = tc.constraint_name "
            "WHERE tc.table_name='sessions'"
        )
        assert fk_rule == "CASCADE", f"sessions FK delete rule is {fk_rule}, expected CASCADE"

        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert version == "005_sessions_and_oauth_users", (
            f"alembic HEAD is {version!r}; 005 not applied"
        )
    finally:
        await conn.close()
```

Add any missing imports (`import asyncpg`, `import pytest`) if they are not already at the top of the file — preserve all other existing imports and tests.

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/alembic/versions/005_sessions_and_oauth_users.py api_server/tests/test_migration.py
git commit -m "feat(22c-02): alembic 005 — sessions + users oauth columns"
```
  </action>
  <verify>
<automated>cd api_server && pytest tests/test_migration.py::test_migration_005_sessions_and_users_columns -x -v -m api_integration</automated>
  </verify>
  <acceptance_criteria>
    - New test `test_migration_005_sessions_and_users_columns` exists in `api_server/tests/test_migration.py`
    - `pytest tests/test_migration.py::test_migration_005_sessions_and_users_columns -m api_integration` exits 0
    - All prior tests in `test_migration.py` still pass: `pytest tests/test_migration.py -m api_integration` exits 0
    - Commit exists on main with message `feat(22c-02): alembic 005 — sessions + users oauth columns`
  </acceptance_criteria>
  <done>Migration 005 + its integration test are green. Downstream plans (22c-04 SessionMiddleware, 22c-05 auth routes) can now assume the sessions table + users.sub/avatar_url/last_login_at columns exist.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| alembic runner → PG | Migration DDL runs with owner privileges on all tables. Migration is pure DDL + partial index — no data writes. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-03 | Tampering | Migration 005 SQL | accept | Additive-only; reversible downgrade; schema changes gated by a single committed file reviewed pre-merge |
| T-22c-04 | DoS | Partial unique index on (provider, sub) | mitigate | Index has `WHERE sub IS NOT NULL` predicate — does not impact performance of the ANONYMOUS seed-row path; OAuth upserts hit a small index (O(log N) on row count ≤ # of users) |
</threat_model>

<verification>
```bash
cd api_server && alembic upgrade head
cd api_server && pytest tests/test_migration.py -m api_integration
```
</verification>

<success_criteria>
- `api_server/alembic/versions/005_sessions_and_oauth_users.py` committed
- `alembic upgrade head` on fresh testcontainers PG applies revision `005_sessions_and_oauth_users`
- `alembic downgrade -1` reverses cleanly (schema returns to 004 shape)
- `test_migration_005_sessions_and_users_columns` passes
- Commit on main: `feat(22c-02): alembic 005 — sessions + users oauth columns`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-02-SUMMARY.md` with:
- Final schema (columns + indexes + FK) for `sessions`
- New `users` columns confirmed
- Any deviations from D-22c-MIG-02 (there should be none)
- alembic version pin confirmed
</output>
