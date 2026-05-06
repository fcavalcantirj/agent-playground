"""Phase 29 Plan 29-02 — schema-DDL assertions for migration ``013_phase29_proxy_columns``.

Mirrors :mod:`tests.test_migration_011_phase28` style: a module-scoped Postgres
17 container (testcontainers), ``alembic upgrade head`` once, then per-test
asyncpg connections that assert column/index/constraint shape + the unknown-row
DELETE side effect + the round-trip
(downgrade -1 → upgrade head) preserves a clean schema for the additive columns.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

Asserts (per Plan 29-02 must_haves.truths):
  * ``agent_containers.bridge_ip`` (inet, nullable=True) added.
  * ``agent_containers.upstream_provider`` (text, nullable=True) added.
  * ``agent_containers.provider_key_enc`` (bytea, nullable=True) added.
  * ``usage_logs.proxy_latency_ms`` (integer, nullable=True) added.
  * ``usage_logs.upstream_latency_ms`` (integer, nullable=True) added.
  * ``ck_usage_logs_status`` widened to allow ``'failed'`` — INSERT with
    ``status='failed'`` succeeds (no constraint violation).
  * ``idempotency_keys.status`` (text, NOT NULL DEFAULT 'success') added with
    ``ck_idempotency_keys_status`` allowing ('success','failed','in_flight') —
    INSERT with ``status='in_flight'`` succeeds.
  * ``idempotency_keys.verdict_json`` is NULLABLE post-upgrade (AMD-03 places
    in-flight reservations BEFORE the upstream call lands; verdict_json is
    NULL until the success/failed transition stores the cached response).
  * ``ix_agent_containers_bridge_ip_running`` partial btree exists with
    predicate ``container_status='running' AND bridge_ip IS NOT NULL``.
  * Pre-existing ``usage_logs.status='unknown'`` rows are DELETEd by the
    upgrade (D-06).
  * Round-trip (``upgrade head → downgrade -1 → upgrade head``) leaves
    identical schema for the additive columns. The DELETE is non-reversible
    by design — the test documents that pre-upgrade ``unknown`` rows do
    NOT return on downgrade, which is correct (NOT a regression).

NOTE on revision id: the migration is ``013_phase29_proxy_columns`` (25 chars,
fits the ``alembic_version.version_num`` ``varchar(32)`` constraint). The prior
revision in this chain is ``012_cost_weights_extra`` (the abbreviated DB-stored
identity from migration 012's file ``012_cost_weights_extra_models.py``).
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

REVISION_ID = "013_phase29_proxy_columns"
PRIOR_REVISION_ID = "012_cost_weights_extra"


def _normalize(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _alembic(container: PostgresContainer, *args: str) -> None:
    dsn = _normalize(container.get_connection_url())
    env = {**os.environ, "DATABASE_URL": dsn}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"alembic {args} exited {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        yield container


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    dsn = _normalize(container.get_connection_url()).replace(
        "postgresql://", "postgres://"
    )
    return await asyncpg.connect(dsn)


async def _seed_user_and_agent(conn: asyncpg.Connection) -> tuple[str, str]:
    """Insert a minimal users + agent_instances pair for FK targets."""
    user_id = "00000000-0000-0000-0000-000000000029"
    recipe_name = f"mig013-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    await conn.execute(
        """
        INSERT INTO users (id, display_name)
        VALUES ($1::uuid, 'mig013-owner')
        ON CONFLICT (id) DO NOTHING
        """,
        user_id,
    )
    instance_row = await conn.fetchrow(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
        VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
        RETURNING id::text
        """,
        user_id,
        recipe_name,
        name,
    )
    return user_id, instance_row["id"]


@pytest.fixture(scope="module")
def migrated(pg):
    """Stamp at 012, INSERT a synthetic ``status='unknown'`` row, then
    upgrade to head (013) so the D-06 wipe assertion is meaningful.
    """
    # Stop one before 013 so we can seed an unknown-row first.
    _alembic(pg, "upgrade", PRIOR_REVISION_ID)

    import asyncio

    async def _seed_unknown_row():
        conn = await _connect(pg)
        try:
            user_id, agent_id = await _seed_user_and_agent(conn)
            # Insert a row with status='unknown' BEFORE 013 widens the
            # check-constraint — must succeed because 010's check still
            # allows 'unknown' and 013 hasn't run yet.
            await conn.execute(
                """
                INSERT INTO usage_logs
                    (id, user_id, agent_instance_id, provider, model, status)
                VALUES (gen_random_uuid(), $1::uuid, $2::uuid,
                        'openrouter', 'pre-013-doomed', 'unknown')
                """,
                user_id, agent_id,
            )
        finally:
            await conn.close()

    asyncio.run(_seed_unknown_row())

    # Now upgrade through 013 — the upgrade's DELETE wipes the unknown row.
    _alembic(pg, "upgrade", "head")
    return pg


@pytest.mark.asyncio
async def test_agent_containers_columns(migrated):
    """``agent_containers`` gains ``bridge_ip`` (INET), ``upstream_provider`` (text),
    ``provider_key_enc`` (bytea) — all nullable.
    """
    conn = await _connect(migrated)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, f"alembic head {head!r} != {REVISION_ID!r}"

        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='agent_containers'
              AND column_name IN ('bridge_ip', 'upstream_provider', 'provider_key_enc')
            ORDER BY column_name
            """
        )
        by_name = {r["column_name"]: r for r in rows}

        assert "bridge_ip" in by_name, "agent_containers.bridge_ip column missing"
        assert by_name["bridge_ip"]["data_type"] == "inet", (
            f"expected inet, got {by_name['bridge_ip']['data_type']!r}"
        )
        assert by_name["bridge_ip"]["is_nullable"] == "YES"

        assert "upstream_provider" in by_name, "upstream_provider missing"
        assert by_name["upstream_provider"]["data_type"] == "text"
        assert by_name["upstream_provider"]["is_nullable"] == "YES"

        assert "provider_key_enc" in by_name, "provider_key_enc missing"
        assert by_name["provider_key_enc"]["data_type"] == "bytea"
        assert by_name["provider_key_enc"]["is_nullable"] == "YES"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_usage_logs_proxy_and_upstream_latency_columns(migrated):
    """``usage_logs.proxy_latency_ms`` + ``upstream_latency_ms`` (int, nullable)."""
    conn = await _connect(migrated)
    try:
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='usage_logs'
              AND column_name IN ('proxy_latency_ms', 'upstream_latency_ms')
            ORDER BY column_name
            """
        )
        by_name = {r["column_name"]: r for r in rows}
        assert "proxy_latency_ms" in by_name, "proxy_latency_ms missing"
        assert by_name["proxy_latency_ms"]["data_type"] == "integer"
        assert by_name["proxy_latency_ms"]["is_nullable"] == "YES"

        assert "upstream_latency_ms" in by_name, "upstream_latency_ms missing"
        assert by_name["upstream_latency_ms"]["data_type"] == "integer"
        assert by_name["upstream_latency_ms"]["is_nullable"] == "YES"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_usage_logs_status_check_allows_failed(migrated):
    """The widened ``ck_usage_logs_status`` accepts ``'failed'``."""
    conn = await _connect(migrated)
    try:
        user_id, agent_id = await _seed_user_and_agent(conn)
        # If the migration didn't widen the check, this INSERT raises
        # CheckViolationError; the assertion is "no exception".
        await conn.execute(
            """
            INSERT INTO usage_logs
                (id, user_id, agent_instance_id, provider, model, status)
            VALUES (gen_random_uuid(), $1::uuid, $2::uuid,
                    'openrouter', 'mig013-failed-test', 'failed')
            """,
            user_id, agent_id,
        )
        # Sanity — row landed.
        cnt = await conn.fetchval(
            """
            SELECT COUNT(*) FROM usage_logs
            WHERE status = 'failed' AND model = 'mig013-failed-test'
            """
        )
        assert cnt == 1
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_idempotency_keys_status_column_with_in_flight(migrated):
    """``idempotency_keys.status`` accepts ``'in_flight'``; verdict_json is NULLABLE."""
    conn = await _connect(migrated)
    try:
        # Column exists, NOT NULL, default 'success'.
        col = await conn.fetchrow(
            """
            SELECT data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='idempotency_keys'
              AND column_name='status'
            """
        )
        assert col is not None, "idempotency_keys.status column missing"
        assert col["data_type"] == "text"
        assert col["is_nullable"] == "NO", (
            f"status should be NOT NULL, got is_nullable={col['is_nullable']!r}"
        )
        assert col["column_default"] is not None and "success" in col["column_default"], (
            f"status default should be 'success', got {col['column_default']!r}"
        )

        # AMD-03 verdict_json relaxation — must be NULLABLE post-013.
        vj_col = await conn.fetchrow(
            """
            SELECT is_nullable
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='idempotency_keys'
              AND column_name='verdict_json'
            """
        )
        assert vj_col is not None, "idempotency_keys.verdict_json column missing"
        assert vj_col["is_nullable"] == "YES", (
            f"verdict_json should be NULLABLE post-013 (AMD-03 in-flight "
            f"reservation pattern), got is_nullable={vj_col['is_nullable']!r}"
        )

        # Seed a user FK target.
        user_id = "00000000-0000-0000-0000-00000000002A"
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1::uuid, 'mig013-idem')
            ON CONFLICT (id) DO NOTHING
            """,
            user_id,
        )

        # INSERT with status='in_flight' must succeed (the new check
        # constraint allows it). verdict_json is NULL — the in-flight
        # reservation pattern.
        await conn.execute(
            """
            INSERT INTO idempotency_keys
                (id, user_id, key, request_body_hash, status, expires_at)
            VALUES (gen_random_uuid(), $1::uuid,
                    $2, 'fake-hash', 'in_flight', NOW() + INTERVAL '1 hour')
            """,
            user_id, f"mig013-{uuid4().hex}",
        )

        # INSERT with status='failed' must also succeed.
        await conn.execute(
            """
            INSERT INTO idempotency_keys
                (id, user_id, key, request_body_hash, status,
                 verdict_json, expires_at)
            VALUES (gen_random_uuid(), $1::uuid, $2, 'fake-hash-2',
                    'failed', '{}'::jsonb, NOW() + INTERVAL '1 hour')
            """,
            user_id, f"mig013-{uuid4().hex}",
        )

        # INSERT with bogus status must FAIL the check.
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO idempotency_keys
                    (id, user_id, key, request_body_hash, status, expires_at)
                VALUES (gen_random_uuid(), $1::uuid, $2,
                        'fake-hash-3', 'bogus', NOW() + INTERVAL '1 hour')
                """,
                user_id, f"mig013-{uuid4().hex}",
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_partial_index_bridge_ip_running(migrated):
    """``ix_agent_containers_bridge_ip_running`` partial index exists."""
    conn = await _connect(migrated)
    try:
        idx = await conn.fetchval(
            """
            SELECT indexdef FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_agent_containers_bridge_ip_running'
            """
        )
        assert idx is not None, (
            "ix_agent_containers_bridge_ip_running index missing"
        )
        assert "WHERE" in idx.upper(), f"index not partial: {idx!r}"
        assert "container_status" in idx.lower()
        assert "running" in idx.lower()
        assert "bridge_ip" in idx.lower()
        assert "is not null" in idx.lower()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_unknown_status_rows_deleted(migrated):
    """D-06: pre-existing ``usage_logs.status='unknown'`` rows wiped by upgrade."""
    conn = await _connect(migrated)
    try:
        # The module fixture seeded one synthetic 'unknown' row at revision
        # 012, then ran ``alembic upgrade head`` which DELETEd it.
        cnt = await conn.fetchval(
            "SELECT COUNT(*) FROM usage_logs WHERE status = 'unknown'"
        )
        assert cnt == 0, (
            f"D-06 wipe failed: {cnt} usage_logs rows still have "
            f"status='unknown' after migration 013"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_round_trip_clean(pg):
    """``upgrade head → downgrade -1 → upgrade head`` preserves additive cols."""
    # Ensure we're at head before round-tripping (the module fixture has
    # already run, so this is idempotent).
    _alembic(pg, "upgrade", "head")

    # Snapshot column lists for the three tables we touch (additive cols only).
    additive_columns_query = """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='public'
          AND table_name IN ('agent_containers','usage_logs','idempotency_keys')
        ORDER BY table_name, column_name
    """

    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == REVISION_ID, (
            f"pre-round-trip head {head!r} != {REVISION_ID!r}"
        )
        before = await conn.fetch(additive_columns_query)
        before_set = {(r["table_name"], r["column_name"]) for r in before}

        # Clean up state placed by sibling tests that uses values which
        # the downgrade's narrower constraints don't accept. In a
        # production downgrade the operator would purge equivalent rows
        # first (the watchdog already does this for in-flight idempotency
        # reservations, and 'failed' usage_logs rows would be migrated to
        # 'error' or deleted depending on intent — see migration 013
        # downgrade() docstring).
        #
        # 1. NULL-verdict_json idempotency rows (in-flight reservations)
        #    would violate the post-downgrade NOT NULL on verdict_json.
        await conn.execute(
            "DELETE FROM idempotency_keys WHERE verdict_json IS NULL"
        )
        # 2. usage_logs rows with status='failed' (introduced by 013's
        #    widened check) would violate the post-downgrade narrower
        #    check `status IN ('success','error','unknown')`.
        await conn.execute(
            "DELETE FROM usage_logs WHERE status = 'failed'"
        )
    finally:
        await conn.close()

    # downgrade -1 → 012
    _alembic(pg, "downgrade", "-1")
    conn = await _connect(pg)
    try:
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == PRIOR_REVISION_ID, (
            f"post-downgrade head {head!r} != {PRIOR_REVISION_ID!r}"
        )
        # The five additive columns must be GONE.
        for table, col in [
            ("agent_containers", "bridge_ip"),
            ("agent_containers", "upstream_provider"),
            ("agent_containers", "provider_key_enc"),
            ("usage_logs", "proxy_latency_ms"),
            ("usage_logs", "upstream_latency_ms"),
            ("idempotency_keys", "status"),
        ]:
            still_there = await conn.fetchval(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name=$1 AND column_name=$2
                """,
                table, col,
            )
            assert still_there is None, (
                f"{table}.{col} still exists after downgrade"
            )
        # Partial index must be GONE.
        idx_still = await conn.fetchval(
            """
            SELECT 1 FROM pg_indexes
            WHERE schemaname='public'
              AND indexname='ix_agent_containers_bridge_ip_running'
            """
        )
        assert idx_still is None, (
            "ix_agent_containers_bridge_ip_running still exists after downgrade"
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
        after = await conn.fetch(additive_columns_query)
        after_set = {(r["table_name"], r["column_name"]) for r in after}
        # The set of (table, column) tuples must match the pre-downgrade
        # snapshot — additive columns are restored identically. The DELETE
        # of pre-existing unknown rows is non-reversible by design and is
        # NOT a regression (rows do not return on downgrade; they stay
        # gone after re-upgrade — this is correct).
        missing = before_set - after_set
        assert not missing, (
            f"round-trip lost columns: {missing!r}"
        )
        extra = after_set - before_set
        assert not extra, f"round-trip introduced unexpected columns: {extra!r}"
    finally:
        await conn.close()
