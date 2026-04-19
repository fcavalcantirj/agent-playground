"""SPIKE B (Wave 0 gate) — TRUNCATE CASCADE on the full FK graph.

Per BLOCKER-4 Option A, this spike is the RUNNABLE REGRESSION TEST for R8
(migration 006 acceptance criterion). The in-repo migration-006 test is
weakened by session-fixture scope — it skips when HEAD is already 006.
This spike uses a dedicated function-scoped container and applies
migrations 001..005 (Mode A) or 001..004 (Mode B — fallback when
22c-02's migration 005 hasn't shipped yet), so the TRUNCATE-then-assert
path is always exercised.

Mode A (8 tables, when 005 is present):
  users, sessions, agent_instances, agent_containers, runs,
  agent_events, idempotency_keys, rate_limit_counters

Mode B (7 tables, current state as of Wave 0 — 005 is delivered by
plan 22c-02):
  users, agent_instances, agent_containers, runs, agent_events,
  idempotency_keys, rate_limit_counters
  (no `sessions` — table doesn't exist yet)

PASS criterion (both modes):
  (1) alembic HEAD = expected revision after apply
  (2) Seed 1 row into EACH in-scope data table — pre-truncate COUNT >= 1
  (3) Post-TRUNCATE: COUNT = 0 in all in-scope tables
  (4) alembic_version still holds the expected revision
      (TRUNCATE did NOT clobber the schema-version bookkeeping table)

FAIL -> plan 22c-06 (migration 006) must fall back to sequential
DELETE FROM in FK-aware order, and the phase goes back to discuss.
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import pytest
from testcontainers.postgres import PostgresContainer

API_SERVER_DIR = Path(__file__).resolve().parent.parent.parent  # api_server/


# Detect mode at import time so the test output reflects which scenario ran.
_ALEMBIC_005_PATH = (
    API_SERVER_DIR / "alembic" / "versions" / "005_sessions_and_oauth_users.py"
)
_MODE_A = _ALEMBIC_005_PATH.exists()
_EXPECTED_REV = "005_sessions_and_oauth_users" if _MODE_A else "004_agent_events"


def _normalize_dsn(raw: str) -> str:
    """testcontainers emits postgresql+psycopg2://; asyncpg and alembic
    want a plain postgresql:// DSN."""
    return raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )


def _pg_creds(pg: PostgresContainer) -> tuple[str, str, str]:
    """Return (user, password, dbname) for the testcontainer."""
    return pg.username, pg.password, pg.dbname


# Network the spawned PostgresContainer should join — so the api_server
# container (from which this test runs when the spike is executed via
# `docker exec deploy-api_server-1 pytest ...`) can reach it directly
# on the Docker bridge. Override via env for dev laptops / CI with
# different network names.
_DOCKER_NETWORK = os.environ.get("SPIKE_DOCKER_NETWORK", "deploy_default")


@pytest.fixture
def fresh_pg_at_target_rev():
    """Function-scoped PG container at alembic HEAD = _EXPECTED_REV.

    Dedicated container — not sharing the session-scoped ``migrated_pg``
    from conftest.py because that fixture's HEAD may be beyond this
    spike's target revision (e.g. after 22c-02 ships 005, or after
    22c-06 ships 006, this spike still needs to pin to ``005``).

    Joins the api_server's Docker network (`SPIKE_DOCKER_NETWORK`,
    default `deploy_default`) so container-to-container DNS + port 5432
    reachability work. When executed from a host shell with a venv on
    the host (Linux + Docker Desktop on macOS), the default bridge
    network + host-mapped port still work — the ``with_kwargs(network=...)``
    call is silently fine when the network is reachable from the caller.
    """
    with (
        PostgresContainer("postgres:17-alpine")
        .with_kwargs(network=_DOCKER_NETWORK)
    ) as pg:
        # When inside the api_server container, the testcontainer's
        # exposed port via `.get_connection_url()` points at the docker
        # host gateway (172.17.0.1:<ephemeral>) which isn't reachable
        # from the api_server's deploy_default-attached network. Build
        # the DSN from the PG container's network-attached IP on
        # SPIKE_DOCKER_NETWORK instead.
        pg_container_name = pg.get_wrapped_container().name
        network_ip = pg.get_docker_client().client.api.inspect_container(
            pg_container_name
        )["NetworkSettings"]["Networks"][_DOCKER_NETWORK]["IPAddress"]
        user, password, dbname = _pg_creds(pg)
        dsn = f"postgresql://{user}:{password}@{network_ip}:5432/{dbname}"
        # Stash for the test body to reuse.
        pg._spike_dsn = dsn  # type: ignore[attr-defined]
        env = {**os.environ, "DATABASE_URL": dsn}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", _EXPECTED_REV],
            cwd=API_SERVER_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        yield pg


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_truncate_cascade_clears_all_tables_preserves_alembic_version(
    fresh_pg_at_target_rev,
):
    # Use the network-attached DSN the fixture stashed. Falls back to
    # the standard get_connection_url() when the stash is absent (e.g.
    # running from a host shell with a local venv + default bridge).
    dsn = getattr(fresh_pg_at_target_rev, "_spike_dsn", None) or _normalize_dsn(
        fresh_pg_at_target_rev.get_connection_url()
    )
    conn = await asyncpg.connect(dsn)
    try:
        # --- CONFIRM target alembic revision ---
        actual_rev = await conn.fetchval(
            "SELECT version_num FROM alembic_version"
        )
        assert actual_rev == _EXPECTED_REV, (
            f"alembic HEAD mismatch: got {actual_rev!r}, "
            f"expected {_EXPECTED_REV!r}"
        )

        # --- SEED ONE ROW PER DATA-BEARING TABLE ---
        # Column sets + NOT-NULL invariants sourced directly from the
        # alembic migration files (001 baseline, 002 name/personality,
        # 003 agent_containers, 004 agent_events, [005 sessions when
        # Mode A]).
        user_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        container_id = uuid.uuid4()
        run_id = "01HQZX9MZVJ5KQZSPIKE22C01B"  # 26-char ULID-shape

        # users — id + display_name (NOT NULL); email optional.
        await conn.execute(
            "INSERT INTO users (id, display_name, email) VALUES ($1, $2, $3)",
            user_id,
            "spike-seed-user",
            "spike@example.com",
        )

        # agent_instances — per 001 + 002: id, user_id, recipe_name,
        # model all NOT NULL; `name` NOT NULL after 002 (migration
        # backfills from recipe_name+model). Post-002 the unique is
        # (user_id, name) not (user_id, recipe_name, model).
        await conn.execute(
            "INSERT INTO agent_instances "
            "(id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, $4, $5)",
            instance_id,
            user_id,
            "hermes",
            "anthropic/claude-haiku-4.5",
            "spike-instance",
        )

        # agent_containers — per 003: id, agent_instance_id, user_id,
        # recipe_name, deploy_mode (default 'persistent'),
        # container_status (default 'starting'). channel_config_enc is
        # NULLABLE; channel_type is NULLABLE. Container_id is NULLABLE
        # (filled after docker-run).
        await conn.execute(
            "INSERT INTO agent_containers "
            "(id, agent_instance_id, user_id, recipe_name) "
            "VALUES ($1, $2, $3, $4)",
            container_id,
            instance_id,
            user_id,
            "hermes",
        )

        # runs — per 001: id (TEXT, 26-char ULID), agent_instance_id,
        # prompt all NOT NULL.
        await conn.execute(
            "INSERT INTO runs (id, agent_instance_id, prompt) "
            "VALUES ($1, $2, $3)",
            run_id,
            instance_id,
            "spike prompt",
        )

        # agent_events — per 004: id BIGSERIAL auto, agent_container_id,
        # seq, kind (CHECK: reply_sent|reply_failed|agent_ready|
        # agent_error), payload JSONB (default {}), ts (default NOW()).
        await conn.execute(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload) "
            "VALUES ($1, $2, $3, $4::jsonb)",
            container_id,
            1,
            "agent_ready",
            '{"spike": true}',
        )

        # idempotency_keys — per 001: id UUID auto, user_id, key,
        # run_id (FK), verdict_json JSONB, request_body_hash TEXT,
        # expires_at TIMESTAMPTZ all NOT NULL.
        await conn.execute(
            "INSERT INTO idempotency_keys "
            "(user_id, key, run_id, verdict_json, request_body_hash, "
            "expires_at) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            user_id,
            "spike-idem-key",
            run_id,
            '{"verdict": "PASS"}',
            "spike-request-hash",
            datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # rate_limit_counters — per 001: subject, bucket, window_start
        # (composite PK — all NOT NULL); count has server_default.
        await conn.execute(
            "INSERT INTO rate_limit_counters "
            "(subject, bucket, window_start, count) "
            "VALUES ($1, $2, $3, $4)",
            "1.2.3.4",
            "m",
            datetime.now(timezone.utc),
            1,
        )

        # sessions row only exists in Mode A — shape driven by 22c-02
        # migration 005 (CONTEXT D-22c-MIG-02 + 22c-SPEC R3).
        if _MODE_A:
            now = datetime.now(timezone.utc)
            # Minimal shape from SPEC R3: id (PK), user_id, created_at,
            # expires_at, last_seen_at. Planner may add more columns;
            # this INSERT uses only the mandatory columns.
            await conn.execute(
                "INSERT INTO sessions "
                "(user_id, created_at, expires_at, last_seen_at) "
                "VALUES ($1, $2, $3, $2)",
                user_id,
                now,
                now + timedelta(days=30),
            )

        # --- Assert pre-truncate row counts >= 1 for each seeded table ---
        tables_seeded = [
            "users",
            "agent_instances",
            "agent_containers",
            "runs",
            "agent_events",
            "idempotency_keys",
            "rate_limit_counters",
        ]
        if _MODE_A:
            tables_seeded.append("sessions")

        pre_counts = {}
        for tbl in tables_seeded:
            pre = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            pre_counts[tbl] = pre
            assert pre >= 1, f"seed failed: {tbl} COUNT={pre}"

        # --- ACT: issue the migration-006 TRUNCATE statement ---
        # The table list mirrors what plan 22c-06's migration 006 will
        # run verbatim (D-22c-MIG-03 + AMD-04). In Mode B we drop
        # `sessions` because it doesn't exist yet.
        if _MODE_A:
            truncate_sql = (
                "TRUNCATE TABLE "
                "agent_events, runs, agent_containers, agent_instances, "
                "idempotency_keys, rate_limit_counters, sessions, users "
                "CASCADE"
            )
        else:
            truncate_sql = (
                "TRUNCATE TABLE "
                "agent_events, runs, agent_containers, agent_instances, "
                "idempotency_keys, rate_limit_counters, users "
                "CASCADE"
            )
        await conn.execute(truncate_sql)

        # --- ASSERT all tables empty ---
        post_counts = {}
        for tbl in tables_seeded:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            post_counts[tbl] = count
            assert count == 0, f"{tbl} not cleared: COUNT={count}"

        # --- ASSERT alembic_version preserved ---
        # TRUNCATE must NOT clobber the schema-version bookkeeping table.
        version_after = await conn.fetchval(
            "SELECT version_num FROM alembic_version"
        )
        assert version_after == _EXPECTED_REV, (
            f"alembic_version clobbered: "
            f"got {version_after!r}, expected {_EXPECTED_REV!r}"
        )

        # Emit the pre/post matrix + mode flag as a deliberate pytest
        # stdout line (captured into the evidence markdown by the
        # executor's tee).
        print(
            f"\n[SPIKE-B] mode={'A' if _MODE_A else 'B'} "
            f"target_rev={_EXPECTED_REV} "
            f"tables={len(tables_seeded)} "
            f"pre={pre_counts} post={post_counts} "
            f"alembic_version_preserved=True"
        )

        if not _MODE_A:
            import logging

            logging.getLogger(__name__).warning(
                "SPIKE-B ran in Mode B (7 tables, no `sessions`). "
                "8-table Mode A coverage will be auto-enabled once plan "
                "22c-02 ships alembic migration 005 (sessions table). "
                "Re-run this spike post-22c-02 to upgrade to Mode A."
            )
    finally:
        await conn.close()
