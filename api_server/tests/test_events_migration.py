"""Phase 22b-02 — schema-DDL assertions for migration ``004_agent_events``.

Mirrors :mod:`tests.test_migration` style: a session-scoped Postgres 17
container (testcontainers), ``alembic upgrade head`` once, then per-test
asyncpg connections that assert table existence + CHECK constraint
behavior + UNIQUE constraint behavior + CASCADE FK behavior.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.

These tests SHOULD FAIL until ``api_server/alembic/versions/004_agent_events.py``
lands (TDD RED). Once the migration is in place, all four assertions
become live regression coverage for the agent_events DDL contract.
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

ANON_USER_ID = "00000000-0000-0000-0000-000000000001"


def _normalize(raw: str) -> str:
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


@pytest.fixture(scope="module")
def pg():
    with PostgresContainer("postgres:17-alpine") as container:
        yield container


@pytest.fixture(scope="module")
def migrated(pg):
    dsn = _normalize(pg.get_connection_url())
    env = {**os.environ, "DATABASE_URL": dsn}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_SERVER_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return pg


async def _connect(container: PostgresContainer) -> asyncpg.Connection:
    dsn = _normalize(container.get_connection_url()).replace(
        "postgresql://", "postgres://"
    )
    return await asyncpg.connect(dsn)


async def _seed_agent_container(conn: asyncpg.Connection) -> str:
    """Insert a minimal agent_instance + agent_container row.

    Returns the new ``agent_containers.id`` (UUID as text). Uses the
    seeded anonymous user from migration 001 so the FK chain is valid
    without touching the ``users`` table.
    """
    recipe_name = f"events-mig-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"  # NOT NULL per migration 002
    instance_row = await conn.fetchrow(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
        VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
        RETURNING id
        """,
        ANON_USER_ID,
        recipe_name,
        name,
    )
    container_row = await conn.fetchrow(
        """
        INSERT INTO agent_containers
            (id, agent_instance_id, user_id, recipe_name,
             deploy_mode, container_status)
        VALUES (gen_random_uuid(), $1, $2, $3,
                'persistent', 'starting')
        RETURNING id
        """,
        instance_row["id"],
        ANON_USER_ID,
        recipe_name,
    )
    return str(container_row["id"])


@pytest.mark.asyncio
async def test_agent_events_table_exists(migrated):
    conn = await _connect(migrated)
    try:
        row = await conn.fetchrow(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'agent_events'"
        )
        assert row is not None, "agent_events table missing after upgrade head"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_kind_check_constraint_rejects_bogus(migrated):
    conn = await _connect(migrated)
    try:
        cid = await _seed_agent_container(conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO agent_events "
                "(agent_container_id, seq, kind, payload) "
                "VALUES ($1, 1, 'bogus', '{}'::jsonb)",
                cid,
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_unique_agent_seq(migrated):
    conn = await _connect(migrated)
    try:
        cid = await _seed_agent_container(conn)
        await conn.execute(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload) "
            "VALUES ($1, 1, 'reply_sent', '{}'::jsonb)",
            cid,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO agent_events "
                "(agent_container_id, seq, kind, payload) "
                "VALUES ($1, 1, 'reply_sent', '{}'::jsonb)",
                cid,
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_cascade_delete(migrated):
    conn = await _connect(migrated)
    try:
        cid = await _seed_agent_container(conn)
        # Seed two events on the container.
        for seq in (1, 2):
            await conn.execute(
                "INSERT INTO agent_events "
                "(agent_container_id, seq, kind, payload) "
                "VALUES ($1, $2, 'reply_sent', '{}'::jsonb)",
                cid,
                seq,
            )
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            cid,
        )
        assert before == 2

        # Delete the parent agent_containers row → CASCADE wipes events.
        await conn.execute(
            "DELETE FROM agent_containers WHERE id=$1", cid
        )
        after = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            cid,
        )
        assert after == 0, (
            f"CASCADE FK failed: {after} events still present after parent delete"
        )
    finally:
        await conn.close()
