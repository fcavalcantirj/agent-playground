"""Phase 28 Plan 28-05 — schema-DDL assertions for migration ``011_phase28_workflow_id_idem``.

Mirrors :mod:`tests.test_migration_007` style: a module-scoped Postgres
17 container (testcontainers), ``alembic upgrade head`` once, then per-test
asyncpg connections that assert column/index/constraint shape + round-trip
(downgrade -1 → upgrade head) preserves a clean schema.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

Asserts (per Plan 28-05 must_haves.truths):
  * ``inapp_messages.workflow_id`` (text, nullable=True) added.
  * ``ix_inapp_messages_workflow_id`` partial btree exists with
    ``WHERE workflow_id IS NOT NULL`` predicate.
  * ``inapp_messages.idempotency_key`` (text, nullable=True) added —
    Option A column-add path (007 did NOT include this column).
  * ``ix_inapp_messages_idempotency_key_unique`` UNIQUE partial btree
    on ``(user_id, idempotency_key)`` with
    ``WHERE idempotency_key IS NOT NULL`` predicate.
  * INSERT with NULL workflow_id succeeds; INSERT with a workflow_id
    succeeds.
  * Two INSERTs with the same ``(user_id, idempotency_key)`` raise
    ``UniqueViolationError`` — Option A defense-in-depth gate.
  * Round-trip (``upgrade head → downgrade -1 → upgrade head``)
    leaves an identical schema (no orphan column, no leftover index).

NOTE on revision id: the file is named
``011_phase28_workflow_id_idempotency.py`` for human readability but the
DB-stored revision string is the abbreviated ``011_phase28_workflow_id_idem``
(28 chars) because ``alembic_version.version_num`` is ``varchar(32)``.
The 35-char fully-spelled form fails to write at the
``UPDATE alembic_version SET version_num=...`` step. See the migration's
module docstring NOTE for the full rationale.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.api_integration

API_SERVER_DIR = Path(__file__).resolve().parent.parent

# Phase 22c-06 purged the seeded ANONYMOUS row — we seed our own user FK
# target inside the helper instead of relying on the legacy id constant.
TEST_USER_ID = "00000000-0000-0000-0000-000000000028"

REVISION_ID = "011_phase28_workflow_id_idem"
PRIOR_REVISION_ID = "010_usage_logs_cost_weights"


def _normalize(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _alembic(container: PostgresContainer, *args: str) -> None:
    dsn = _normalize(container.get_connection_url())
    env = {**os.environ, "DATABASE_URL": dsn}
    subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_SERVER_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        yield container


@pytest.fixture(scope="module")
def migrated(pg):
    """Run ``alembic upgrade head`` once for this module."""
    _alembic(pg, "upgrade", "head")
    return pg


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    dsn = _normalize(container.get_connection_url()).replace(
        "postgresql://", "postgres://"
    )
    return await asyncpg.connect(dsn)


async def _seed_user_and_agent(conn: asyncpg.Connection) -> tuple[str, str]:
    """Insert a minimal users + agent_instances pair.

    Returns ``(user_id, agent_instance_id)`` (both UUIDs as text).
    Idempotent on the user row — tests call this multiple times against
    the same module-scoped container.
    """
    recipe_name = f"mig011-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    await conn.execute(
        """
        INSERT INTO users (id, display_name)
        VALUES ($1::uuid, 'mig011-owner')
        ON CONFLICT (id) DO NOTHING
        """,
        TEST_USER_ID,
    )
    instance_row = await conn.fetchrow(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
        VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
        RETURNING id::text
        """,
        TEST_USER_ID,
        recipe_name,
        name,
    )
    return TEST_USER_ID, instance_row["id"]


@pytest.mark.asyncio
async def test_migration_011_adds_workflow_id_and_idempotency_key(migrated):
    """Schema shape assertions for the migrated DB."""
    conn = await _connect(migrated)
    try:
        # ---- alembic head sits at 011 ----
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, (
            f"alembic head {head!r} != {REVISION_ID!r}"
        )

        # ---- workflow_id column exists, type=text, nullable=True ----
        wf_col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='inapp_messages'
              AND column_name='workflow_id'
            """
        )
        assert wf_col is not None, "inapp_messages.workflow_id column missing"
        assert wf_col["data_type"] == "text"
        assert wf_col["is_nullable"] == "YES"

        # ---- idempotency_key column exists, type=text, nullable=True ----
        idem_col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='inapp_messages'
              AND column_name='idempotency_key'
            """
        )
        assert idem_col is not None, (
            "inapp_messages.idempotency_key column missing"
        )
        assert idem_col["data_type"] == "text"
        assert idem_col["is_nullable"] == "YES"

        # ---- ix_inapp_messages_workflow_id partial index w/ predicate ----
        wf_idx = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_workflow_id'
            """
        )
        assert wf_idx is not None, (
            "ix_inapp_messages_workflow_id partial index missing"
        )
        assert "WHERE" in wf_idx.upper(), (
            f"ix_inapp_messages_workflow_id not partial: {wf_idx!r}"
        )
        assert "workflow_id" in wf_idx.lower()
        assert "is not null" in wf_idx.lower(), (
            f"workflow_id index predicate missing IS NOT NULL: {wf_idx!r}"
        )

        # ---- ix_inapp_messages_idempotency_key_unique UNIQUE partial ----
        idem_idx = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_idempotency_key_unique'
            """
        )
        assert idem_idx is not None, (
            "ix_inapp_messages_idempotency_key_unique index missing"
        )
        assert "UNIQUE" in idem_idx.upper(), (
            f"idempotency_key index not UNIQUE: {idem_idx!r}"
        )
        assert "user_id" in idem_idx.lower()
        assert "idempotency_key" in idem_idx.lower()
        assert "WHERE" in idem_idx.upper(), (
            f"idempotency_key index not partial: {idem_idx!r}"
        )
        assert "is not null" in idem_idx.lower()

        # ---- INSERT NULL workflow_id + NULL idempotency_key succeeds ----
        user_id, agent_id = await _seed_user_and_agent(conn)
        await conn.execute(
            """
            INSERT INTO inapp_messages (agent_id, user_id, content)
            VALUES ($1::uuid, $2::uuid, 'hello-null-cols')
            """,
            agent_id, user_id,
        )

        # ---- INSERT with non-null workflow_id succeeds ----
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, workflow_id)
            VALUES ($1::uuid, $2::uuid, 'hello-with-wf', $3)
            """,
            agent_id, user_id, f"msg-{user_id}-{uuid4()}",
        )

        # ---- INSERT with non-null idempotency_key succeeds (first time) ----
        first_key = f"idem-{uuid4().hex}"
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, idempotency_key)
            VALUES ($1::uuid, $2::uuid, 'hello-with-idem', $3)
            """,
            agent_id, user_id, first_key,
        )

        # ---- Two INSERTs with same (user_id, idempotency_key) → UniqueViolation ----
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                """
                INSERT INTO inapp_messages
                    (agent_id, user_id, content, idempotency_key)
                VALUES ($1::uuid, $2::uuid, 'duplicate-attempt', $3)
                """,
                agent_id, user_id, first_key,
            )

        # ---- Different user_id with same idempotency_key MUST succeed ----
        # Confirms the UNIQUE constraint is scoped to (user_id, key), not key alone.
        other_user = "00000000-0000-0000-0000-000000000128"
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1::uuid, 'mig011-other')
            ON CONFLICT (id) DO NOTHING
            """,
            other_user,
        )
        other_instance = await conn.fetchval(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
            RETURNING id::text
            """,
            other_user,
            f"mig011-other-{uuid4().hex[:8]}",
            f"agent-other-{uuid4().hex[:8]}",
        )
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, idempotency_key)
            VALUES ($1::uuid, $2::uuid, 'cross-user-same-key', $3)
            """,
            other_instance, other_user, first_key,
        )

        # ---- NULL idempotency_key rows do NOT collide (partial index) ----
        # Two rows with NULL idempotency_key must coexist for the same user.
        await conn.execute(
            """
            INSERT INTO inapp_messages (agent_id, user_id, content)
            VALUES ($1::uuid, $2::uuid, 'null-1')
            """,
            agent_id, user_id,
        )
        await conn.execute(
            """
            INSERT INTO inapp_messages (agent_id, user_id, content)
            VALUES ($1::uuid, $2::uuid, 'null-2')
            """,
            agent_id, user_id,
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migration_011_round_trip(pg):
    """``upgrade head → downgrade -1 → upgrade head`` is clean.

    Reuses the module-scoped ``pg`` container — alembic is idempotent on
    already-up DBs, so this proceeds whether test 1 ran first or not.
    """
    # Ensure we're at head before round-tripping.
    _alembic(pg, "upgrade", "head")

    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, (
            f"pre-round-trip head {head!r} != {REVISION_ID!r}"
        )
    finally:
        await conn.close()

    # Downgrade -1 → 010.
    _alembic(pg, "downgrade", "-1")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == PRIOR_REVISION_ID, (
            f"post-downgrade head {head!r} != {PRIOR_REVISION_ID!r}"
        )
        # Migration objects must be GONE.
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='inapp_messages' AND column_name='workflow_id'
            """
        ) is None, "inapp_messages.workflow_id still exists after downgrade"
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='inapp_messages' AND column_name='idempotency_key'
            """
        ) is None, "inapp_messages.idempotency_key still exists after downgrade"
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_workflow_id'
            """
        ) is None, "ix_inapp_messages_workflow_id still exists after downgrade"
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_idempotency_key_unique'
            """
        ) is None, (
            "ix_inapp_messages_idempotency_key_unique still exists after "
            "downgrade"
        )
    finally:
        await conn.close()

    # Re-upgrade → head.
    _alembic(pg, "upgrade", "head")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, (
            f"post-re-upgrade head {head!r} != {REVISION_ID!r}"
        )
        # Every migration-owned object must exist again with same shape.
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='inapp_messages' AND column_name='workflow_id'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='inapp_messages' AND column_name='idempotency_key'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_workflow_id'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_idempotency_key_unique'
            """
        ) == 1
    finally:
        await conn.close()
