"""Phase 22c.3-02 — schema-DDL assertions for migration ``007_inapp_messages``.

Mirrors :mod:`tests.test_events_migration` style: a module-scoped Postgres
17 container (testcontainers), ``alembic upgrade head`` once, then per-test
asyncpg connections that assert table/column/constraint shape + round-trip
(downgrade -1 → upgrade head) preserves a clean schema.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

Asserts (per Plan 22c.3-02 must_haves.truths):
  * ``inapp_messages`` table exists with all 11 columns (id/agent_id/user_id/
    content/status/attempts/last_error/last_attempt_at/bot_response/
    created_at/completed_at) with the correct types and nullability.
  * ``ck_inapp_messages_status`` CHECK constraint accepts pending/forwarded/
    done/failed and rejects an arbitrary value.
  * ``ix_inapp_messages_agent_status`` btree index exists on (agent_id, status).
  * ``ix_inapp_messages_status_attempts`` partial index exists with the
    ``status IN ('pending','forwarded')`` predicate.
  * ``agent_events.published BOOLEAN NOT NULL DEFAULT FALSE`` column added.
  * ``ix_agent_events_published`` partial index exists with ``WHERE published = false``.
  * ``agent_containers.inapp_auth_token TEXT`` (nullable) column added.
  * ``ck_agent_events_kind`` accepts the 3 new kinds (inapp_inbound,
    inapp_outbound, inapp_outbound_failed) AND still accepts the 4 prior
    kinds (reply_sent, reply_failed, agent_ready, agent_error).
  * ``alembic upgrade head → downgrade -1 → upgrade head`` produces an
    identical schema (no orphan constraint, no leftover column, no leftover
    table). Verified via per-object existence checks.
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
TEST_USER_ID = "00000000-0000-0000-0000-000000000007"


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


async def _seed_user_and_agent(conn: asyncpg.Connection) -> tuple[str, str, str]:
    """Insert a minimal users + agent_instances + agent_containers triplet.

    Returns ``(user_id, agent_instance_id, agent_container_id)`` (all UUIDs as
    text). Idempotent on the user row — tests call this multiple times
    against the same module-scoped container.
    """
    recipe_name = f"mig007-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"  # agent_instances.name NOT NULL post-002.
    await conn.execute(
        """
        INSERT INTO users (id, display_name)
        VALUES ($1::uuid, 'mig007-owner')
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
    container_row = await conn.fetchrow(
        """
        INSERT INTO agent_containers
            (id, agent_instance_id, user_id, recipe_name,
             deploy_mode, container_status)
        VALUES (gen_random_uuid(), $1::uuid, $2, $3,
                'persistent', 'starting')
        RETURNING id::text
        """,
        instance_row["id"],
        TEST_USER_ID,
        recipe_name,
    )
    return TEST_USER_ID, instance_row["id"], container_row["id"]


@pytest.mark.asyncio
async def test_migration_007_creates_table_and_columns(migrated):
    """Full DDL shape assertion against the migrated schema."""
    conn = await _connect(migrated)
    try:
        # ---- inapp_messages table exists ----
        regclass = await conn.fetchval(
            "SELECT to_regclass('public.inapp_messages')::text"
        )
        assert regclass == "inapp_messages", "inapp_messages table missing"

        # ---- All 11 columns present with correct types & nullability ----
        cols = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='inapp_messages'
            """
        )
        col_map = {r["column_name"]: r for r in cols}
        expected = {
            "id": ("uuid", "NO"),
            "agent_id": ("uuid", "NO"),
            "user_id": ("uuid", "NO"),
            "content": ("text", "NO"),
            "status": ("text", "NO"),
            "attempts": ("integer", "NO"),
            "last_error": ("text", "YES"),
            "last_attempt_at": ("timestamp with time zone", "YES"),
            "bot_response": ("text", "YES"),
            "created_at": ("timestamp with time zone", "NO"),
            "completed_at": ("timestamp with time zone", "YES"),
        }
        for name, (dtype, nullable) in expected.items():
            assert name in col_map, f"inapp_messages missing column {name}"
            assert col_map[name]["data_type"] == dtype, (
                f"inapp_messages.{name} type "
                f"{col_map[name]['data_type']!r} != {dtype!r}"
            )
            assert col_map[name]["is_nullable"] == nullable, (
                f"inapp_messages.{name} nullable "
                f"{col_map[name]['is_nullable']!r} != {nullable!r}"
            )

        # ---- ck_inapp_messages_status constraint shape ----
        ck_def = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname='ck_inapp_messages_status'
            """
        )
        assert ck_def is not None, "ck_inapp_messages_status missing"
        for kind in ("pending", "forwarded", "done", "failed"):
            assert f"'{kind}'" in ck_def, (
                f"ck_inapp_messages_status missing status {kind!r}: {ck_def!r}"
            )

        # ---- ck_inapp_messages_status rejects junk + accepts each canonical value ----
        user_id, agent_id, _container_id = await _seed_user_and_agent(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO inapp_messages (agent_id, user_id, content, status)
                VALUES ($1::uuid, $2::uuid, 'junk', 'garbage')
                """,
                agent_id, user_id,
            )
        for kind in ("pending", "forwarded", "done", "failed"):
            await conn.execute(
                """
                INSERT INTO inapp_messages
                    (agent_id, user_id, content, status)
                VALUES ($1::uuid, $2::uuid, $3, $4)
                """,
                agent_id, user_id, f"hello-{kind}", kind,
            )

        # ---- ix_inapp_messages_agent_status btree exists ----
        idx_agent_status = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_agent_status'
            """
        )
        assert idx_agent_status is not None, (
            "ix_inapp_messages_agent_status index missing"
        )
        assert "agent_id" in idx_agent_status
        assert "status" in idx_agent_status

        # ---- ix_inapp_messages_status_attempts partial index w/ predicate ----
        idx_partial = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_status_attempts'
            """
        )
        assert idx_partial is not None, (
            "ix_inapp_messages_status_attempts partial index missing"
        )
        # Postgres normalizes the WHERE clause when storing it — the
        # canonical form is `WHERE (status = ANY (ARRAY['pending'::text,
        # 'forwarded'::text]))`. Assert each canonical fragment is present.
        assert "WHERE" in idx_partial.upper(), (
            f"ix_inapp_messages_status_attempts not partial: {idx_partial!r}"
        )
        assert "'pending'" in idx_partial and "'forwarded'" in idx_partial, (
            f"partial-index predicate missing pending/forwarded: {idx_partial!r}"
        )

        # ---- agent_events.published column shape ----
        published_col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='agent_events'
              AND column_name='published'
            """
        )
        assert published_col is not None, (
            "agent_events.published column missing"
        )
        assert published_col["data_type"] == "boolean"
        assert published_col["is_nullable"] == "NO"
        # Default is 'false' (PG renders the literal verbatim from the
        # CREATE statement). Don't pin exact string — substring match.
        assert "false" in (published_col["column_default"] or "").lower(), (
            f"published default not FALSE: {published_col['column_default']!r}"
        )

        # ---- ix_agent_events_published partial index ----
        idx_pub = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_agent_events_published'
            """
        )
        assert idx_pub is not None, "ix_agent_events_published index missing"
        assert "published" in idx_pub.lower()

        # ---- agent_containers.inapp_auth_token column shape ----
        token_col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='agent_containers'
              AND column_name='inapp_auth_token'
            """
        )
        assert token_col is not None, (
            "agent_containers.inapp_auth_token column missing"
        )
        assert token_col["data_type"] == "text"
        assert token_col["is_nullable"] == "YES"

        # ---- ck_agent_events_kind extended (3 new + 4 prior kinds) ----
        kind_def = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname='ck_agent_events_kind'
            """
        )
        assert kind_def is not None, "ck_agent_events_kind missing"
        for kind in (
            "reply_sent", "reply_failed", "agent_ready", "agent_error",
            "inapp_inbound", "inapp_outbound", "inapp_outbound_failed",
        ):
            assert f"'{kind}'" in kind_def, (
                f"ck_agent_events_kind missing kind {kind!r}: {kind_def!r}"
            )

        # ---- ck_agent_events_kind accepts inapp_inbound + rejects garbage ----
        _user_id, _agent_id, container_id = await _seed_user_and_agent(conn)
        await conn.execute(
            """
            INSERT INTO agent_events
                (agent_container_id, seq, kind, payload)
            VALUES ($1::uuid, 1, 'inapp_inbound', '{}'::jsonb)
            """,
            container_id,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload)
                VALUES ($1::uuid, 2, 'garbage', '{}'::jsonb)
                """,
                container_id,
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migration_007_round_trip(pg):
    """``upgrade head → downgrade -1 → upgrade head`` is clean.

    Reuses the module-scoped ``pg`` container shared with the first test
    (alembic is idempotent on already-up DBs, and we drain the inapp-kind
    rows from ``agent_events`` before downgrade so the rebuilt 4-kind
    CHECK doesn't trip on test-1's seeded ``inapp_inbound`` row). After
    the cycle completes, every object that the migration owns must exist
    again with the same shape.

    NOTE: this test depends on ``test_migration_007_creates_table_and_columns``
    exercising the full DDL shape against ``migrated``; here we only verify
    that the up→down→up cycle is idempotent.
    """
    # Initial upgrade — alembic is idempotent on already-up DBs so this
    # is a no-op when test 1 ran first; if this test runs alone it gets
    # a fresh upgrade head on the bare container.
    _alembic(pg, "upgrade", "head")

    conn = await _connect(pg)
    try:
        # Sanity: head is at 007 OR a later additive migration (e.g.
        # 008_idempotency_relax_run_fk landed in Phase 22c.3-08; it does
        # not touch any 007-owned object so the 007 round-trip below is
        # still well-defined).
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head in ("007_inapp_messages", "008_idempotency_relax_run_fk"), (
            f"pre-round-trip head {head!r} not in expected set"
        )
        # Test 1 (when run before this) inserts an agent_events row with
        # kind='inapp_inbound'. The downgrade rebuilds ck_agent_events_kind
        # as the 4-kind shape, which would reject that row. Drain new-kind
        # rows here so the downgrade exercises a clean schema-only revert
        # — exactly the contract the truths.bullet asks of the migration.
        await conn.execute(
            "DELETE FROM agent_events WHERE kind IN "
            "('inapp_inbound','inapp_outbound','inapp_outbound_failed')"
        )
    finally:
        await conn.close()

    # If we are sitting on 008, downgrade -1 to land back on 007 first;
    # the rest of the round-trip then proceeds from 007 → 006 → 007.
    if head == "008_idempotency_relax_run_fk":
        _alembic(pg, "downgrade", "-1")
    # Downgrade -1 → 006.
    _alembic(pg, "downgrade", "-1")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == "006_purge_anonymous", (
            f"post-downgrade head {head!r} != '006_purge_anonymous'"
        )
        # Migration objects must be GONE.
        assert await conn.fetchval(
            "SELECT to_regclass('public.inapp_messages')::text"
        ) is None, "inapp_messages still exists after downgrade"
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='agent_events' AND column_name='published'
            """
        ) is None, "agent_events.published still exists after downgrade"
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='agent_containers' AND column_name='inapp_auth_token'
            """
        ) is None, "agent_containers.inapp_auth_token still exists after downgrade"
        # ck_agent_events_kind must be the 4-kind shape again.
        kind_def_down = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname='ck_agent_events_kind'
            """
        )
        assert kind_def_down is not None, (
            "ck_agent_events_kind disappeared after downgrade"
        )
        for old in ("reply_sent", "reply_failed", "agent_ready", "agent_error"):
            assert f"'{old}'" in kind_def_down, (
                f"post-downgrade ck_agent_events_kind missing {old!r}: "
                f"{kind_def_down!r}"
            )
        for new in ("inapp_inbound", "inapp_outbound", "inapp_outbound_failed"):
            assert f"'{new}'" not in kind_def_down, (
                f"post-downgrade ck_agent_events_kind still has {new!r}: "
                f"{kind_def_down!r}"
            )
        # Partial index ix_agent_events_published must be gone.
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public' AND indexname='ix_agent_events_published'
            """
        ) is None, "ix_agent_events_published still exists after downgrade"
    finally:
        await conn.close()

    # Re-upgrade → 007 (or 008 if 008_idempotency_relax_run_fk has been
    # added on top of 007 — the additive 008 migration does not touch
    # any 007-owned object so the 007 invariants below are still valid).
    _alembic(pg, "upgrade", "head")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head in ("007_inapp_messages", "008_idempotency_relax_run_fk"), (
            f"post-re-upgrade head {head!r} not in expected set"
        )
        # Every migration-owned object must exist again with same shape.
        assert await conn.fetchval(
            "SELECT to_regclass('public.inapp_messages')::text"
        ) == "inapp_messages"
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='agent_events' AND column_name='published'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name='agent_containers' AND column_name='inapp_auth_token'
            """
        ) == 1
        kind_def_up = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname='ck_agent_events_kind'
            """
        )
        for kind in (
            "reply_sent", "reply_failed", "agent_ready", "agent_error",
            "inapp_inbound", "inapp_outbound", "inapp_outbound_failed",
        ):
            assert f"'{kind}'" in kind_def_up, (
                f"post-re-upgrade ck_agent_events_kind missing {kind!r}: "
                f"{kind_def_up!r}"
            )
        # Both new indexes must be back.
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_agent_status'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_inapp_messages_status_attempts'
            """
        ) == 1
        assert await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_agent_events_published'
            """
        ) == 1
    finally:
        await conn.close()
