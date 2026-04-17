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
