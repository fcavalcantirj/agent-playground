"""Integration test for baseline Alembic migration.

Uses testcontainers to spin a real Postgres 17, runs `alembic upgrade head`,
asserts every table/column/constraint specified in CONTEXT.md D-06, then
downgrades + re-upgrades to verify idempotency.

Marked `api_integration` — skipped by default. Run with:

    cd api_server && pytest -m api_integration tests/test_migration.py -q
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.api_integration

API_SERVER_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        yield container


def _dsn_for_alembic(container: PostgresContainer) -> str:
    """Return a DSN suitable for passing to alembic.

    testcontainers returns a psycopg2-style URL by default. env.py
    normalizes postgres:// / postgresql:// (without the +asyncpg suffix)
    to postgresql+asyncpg://, so strip the driver suffix here and let
    env.py handle it.
    """
    raw = container.get_connection_url()
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _alembic(
    container: PostgresContainer, *args: str
) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": _dsn_for_alembic(container)}
    return subprocess.run(
        ["alembic", *args],
        cwd=API_SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture(scope="module")
def migrated(pg):
    _alembic(pg, "upgrade", "head")
    return pg


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    raw = container.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgres://").replace(
        "+psycopg2", ""
    )
    return await asyncpg.connect(dsn)


class TestBaselineMigration:
    @pytest.mark.asyncio
    async def test_upgrade_creates_all_tables(self, migrated):
        conn = await _connect(migrated)
        try:
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            names = {r["table_name"] for r in rows}
            assert {
                "users",
                "agent_instances",
                "runs",
                "idempotency_keys",
                "rate_limit_counters",
            }.issubset(names)
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_anonymous_user_seeded(self, migrated):
        conn = await _connect(migrated)
        try:
            row = await conn.fetchrow(
                "SELECT id::text AS id, display_name FROM users "
                "WHERE display_name = 'anonymous'"
            )
            assert row is not None, "anonymous user missing"
            assert row["id"] == "00000000-0000-0000-0000-000000000001"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_idempotency_has_request_body_hash_column(self, migrated):
        conn = await _connect(migrated)
        try:
            row = await conn.fetchrow(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name='idempotency_keys' "
                "AND column_name='request_body_hash'"
            )
            assert row is not None, "request_body_hash column missing"
            assert (
                row["is_nullable"] == "NO"
            ), "request_body_hash must be NOT NULL"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_runs_id_is_text_not_uuid(self, migrated):
        conn = await _connect(migrated)
        try:
            row = await conn.fetchrow(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name='runs' AND column_name='id'"
            )
            assert row is not None, "runs.id missing"
            assert row["data_type"] == "text", row["data_type"]
            # And a 26-char ULID-shape actually inserts
            await conn.execute(
                """INSERT INTO agent_instances (id, user_id, recipe_name, model)
                   VALUES (gen_random_uuid(),
                           '00000000-0000-0000-0000-000000000001',
                           'hermes-typecheck', 'm')"""
            )
            await conn.execute(
                """INSERT INTO runs (id, agent_instance_id, prompt)
                   VALUES ($1,
                           (SELECT id FROM agent_instances
                            WHERE recipe_name='hermes-typecheck'),
                           'p')""",
                "01HQZX9MZVJ5KQXYZ1234567890",
            )
        finally:
            await conn.execute(
                "DELETE FROM runs WHERE id = '01HQZX9MZVJ5KQXYZ1234567890'"
            )
            await conn.execute(
                "DELETE FROM agent_instances "
                "WHERE recipe_name = 'hermes-typecheck'"
            )
            await conn.close()

    @pytest.mark.asyncio
    async def test_agent_instances_unique_constraint(self, migrated):
        conn = await _connect(migrated)
        u = "00000000-0000-0000-0000-000000000001"
        try:
            await conn.execute(
                """INSERT INTO agent_instances (id, user_id, recipe_name, model)
                   VALUES (gen_random_uuid(), $1, 'hermes-uq', 'mA')""",
                u,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    """INSERT INTO agent_instances
                         (id, user_id, recipe_name, model)
                       VALUES (gen_random_uuid(), $1, 'hermes-uq', 'mA')""",
                    u,
                )
        finally:
            await conn.execute(
                "DELETE FROM agent_instances WHERE recipe_name = 'hermes-uq'"
            )
            await conn.close()

    @pytest.mark.asyncio
    async def test_idempotency_unique_constraint(self, migrated):
        conn = await _connect(migrated)
        u = "00000000-0000-0000-0000-000000000001"
        run_id = "01HQZX9MZVJ5KQXYZ1234567890"
        try:
            await conn.execute(
                """INSERT INTO agent_instances (id, user_id, recipe_name, model)
                   VALUES (gen_random_uuid(), $1, 'hermes-idem', 'm')""",
                u,
            )
            await conn.execute(
                """INSERT INTO runs (id, agent_instance_id, prompt)
                   VALUES ($1,
                           (SELECT id FROM agent_instances
                            WHERE recipe_name='hermes-idem'),
                           'p')""",
                run_id,
            )
            await conn.execute(
                """INSERT INTO idempotency_keys
                     (user_id, key, run_id, verdict_json,
                      request_body_hash, expires_at)
                   VALUES ($1, 'k1', $2, '{}'::jsonb, 'h1',
                           NOW() + INTERVAL '1 hour')""",
                u,
                run_id,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(
                    """INSERT INTO idempotency_keys
                         (user_id, key, run_id, verdict_json,
                          request_body_hash, expires_at)
                       VALUES ($1, 'k1', $2, '{}'::jsonb, 'h2',
                               NOW() + INTERVAL '1 hour')""",
                    u,
                    run_id,
                )
        finally:
            await conn.execute("DELETE FROM idempotency_keys WHERE key = 'k1'")
            await conn.execute("DELETE FROM runs WHERE id = $1", run_id)
            await conn.execute(
                "DELETE FROM agent_instances WHERE recipe_name = 'hermes-idem'"
            )
            await conn.close()

    def test_upgrade_is_idempotent_with_head(self, pg, migrated):
        # Running upgrade head again is a no-op — alembic returns 0.
        result = _alembic(pg, "upgrade", "head")
        assert result.returncode == 0

    def test_downgrade_then_upgrade(self, pg, migrated):
        _alembic(pg, "downgrade", "base")
        _alembic(pg, "upgrade", "head")


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_migration_005_sessions_and_users_columns(migrated_pg):
    """Phase 22c migration 005 — additive schema change.

    Asserts:
      * users has sub/avatar_url/last_login_at columns
      * users has partial unique index on (provider, sub) WHERE sub IS NOT NULL
      * sessions table exists with expected columns + FK + btree index
    """
    raw = migrated_pg.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgres://").replace(
        "+psycopg2", ""
    )
    conn = await asyncpg.connect(dsn)
    try:
        users_cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='users'"
            )
        }
        assert {"sub", "avatar_url", "last_login_at"}.issubset(users_cols), (
            f"users missing 22c columns; has {users_cols}"
        )

        sessions_cols = [
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='sessions' ORDER BY ordinal_position"
            )
        ]
        assert sessions_cols == [
            "id",
            "user_id",
            "created_at",
            "expires_at",
            "last_seen_at",
            "revoked_at",
            "user_agent",
            "ip_address",
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
        assert fk_rule == "CASCADE", (
            f"sessions FK delete rule is {fk_rule}, expected CASCADE"
        )

        user_id_idx = await conn.fetchval(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename='sessions' AND indexname='ix_sessions_user_id'"
        )
        assert user_id_idx == "ix_sessions_user_id", (
            "ix_sessions_user_id btree index missing"
        )

        version = await conn.fetchval(
            "SELECT version_num FROM alembic_version"
        )
        assert version == "005_sessions_and_oauth_users", (
            f"alembic HEAD is {version!r}; 005 not applied"
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Phase 22c — migration 006 (IRREVERSIBLE purge of all data-bearing tables)
# ---------------------------------------------------------------------------


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_migration_006_artifact_and_apply(migrated_pg):
    """Phase 22c migration 006 — artifact existence + apply-to-head succeeds.

    NOTE: The R8 BEHAVIORAL regression (seed → TRUNCATE → assert all 8 tables
    empty + alembic_version preserved) lives in SPIKE-B at
    ``tests/spikes/test_truncate_cascade.py`` per BLOCKER-4 Option A. That
    spike uses a dedicated function-scoped container because the
    session-scoped ``migrated_pg`` fixture here would skip the seed step once
    HEAD reaches 006.

    This test verifies:
    (1) The migration file contains the TRUNCATE text (artifact check).
    (2) ``alembic upgrade head`` on the session-scoped container reaches
        HEAD = 006_purge_anonymous.
    (3) Post-apply all 8 tables are empty (belt-and-suspenders — duplicates
        plan 22c-09 Task 1's pre-assertion; catches the case where the
        TRUNCATE text silently no-ops, e.g. table-name typo).
    """
    import subprocess
    import sys

    # (1) Artifact existence + structural contents.
    migration_path = (
        API_SERVER_DIR / "alembic" / "versions" / "006_purge_anonymous.py"
    )
    assert migration_path.exists(), "migration 006 file missing"
    body = migration_path.read_text()
    assert "TRUNCATE TABLE" in body
    assert "sessions" in body
    assert "users" in body
    assert "raise NotImplementedError" in body

    # (2) + (3) Apply + post-apply count check.
    dsn = _dsn_for_alembic(migrated_pg)
    # Note: the session-scoped ``migrated_pg`` fixture already ran
    # ``alembic upgrade head`` once; issuing it again is a no-op when HEAD
    # already matches, and advances by any new revisions added since.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_SERVER_DIR,
        env={**os.environ, "DATABASE_URL": dsn},
        check=True,
        capture_output=True,
        text=True,
    )

    conn = await _connect(migrated_pg)
    try:
        version = await conn.fetchval(
            "SELECT version_num FROM alembic_version"
        )
        assert version == "006_purge_anonymous", (
            f"HEAD != 006: got {version!r}"
        )

        # Belt-and-suspenders: post-006 all 8 tables empty (even if other
        # tests in this session had seeded rows before 006 ran).
        for tbl in (
            "agent_events", "runs", "agent_containers", "agent_instances",
            "idempotency_keys", "rate_limit_counters", "sessions", "users",
        ):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert count == 0, (
                f"{tbl} not cleared by migration 006: got count={count}"
            )
    finally:
        await conn.close()
