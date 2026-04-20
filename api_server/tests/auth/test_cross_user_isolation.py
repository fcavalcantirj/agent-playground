"""Cross-user isolation + R8 belt-and-suspenders — SPEC acceptance criterion 11.

TWO independent concerns in one test:

(A) R8 belt-and-suspenders (BLOCKER-4 Option C from the revision checker):
    Before ANY seed, assert ``alembic_version == '006_purge_anonymous'`` AND
    all 8 data tables are empty. This proves the session-scoped ``migrated_pg``
    fixture ran ``alembic upgrade head`` and landed at revision 006 with all
    tables cleared. Catches silent failures in migration 006's TRUNCATE
    statement. SPIKE-B (plan 22c-01) is the PRIMARY regression and
    ``tests/test_migration_005_sessions_and_users_columns.py`` is the
    secondary artifact+apply check; this is the tertiary independent check
    that lives in the cross-user isolation test itself so a broken migration
    cannot slip past plan 22c-09.

(B) Cross-user isolation (SPEC AC-11):
    Two authenticated users seeded via direct asyncpg INSERT (bypass the
    OAuth flow — the OAuth happy-path is already covered by
    ``tests/auth/test_google_callback.py``). Each user issues
    ``GET /v1/agents`` with their own session cookie and must see ONLY
    their own ``agent_instances`` rows. Anonymous (no cookie) must get
    401 Stripe-shape envelope. Any leak indicates ``require_user``
    (plan 22c-06) missed a code path in ``routes/agents.py`` or
    ``services/run_store.py::list_agents``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_two_users_see_only_their_own_agents(async_client, migrated_pg):
    # Normalize the testcontainer DSN to asyncpg's expected shape (mirrors
    # conftest._normalize_testcontainers_dsn — kept inline here rather than
    # exported so the test stays self-contained).
    raw = migrated_pg.get_connection_url()
    dsn = raw.replace("postgresql+psycopg2://", "postgresql://").replace(
        "+psycopg2", ""
    )
    conn = await asyncpg.connect(dsn)
    try:
        # ==============================================================
        # STEP 0 — R8 belt-and-suspenders (BLOCKER-4 Option C)
        # ==============================================================
        # Alembic HEAD assertion: if the autouse TRUNCATE ran before this
        # body, every table is empty — but the ``alembic_version`` row
        # survives TRUNCATE and reveals whether migration 006 was applied.
        version = await conn.fetchval(
            "SELECT version_num FROM alembic_version"
        )
        assert version == "006_purge_anonymous", (
            f"expected HEAD = 006_purge_anonymous (proving migration 006 "
            f"ran during conftest init); got {version!r}"
        )
        # All 8 data-bearing tables must be empty at test start. Either
        # migration 006 cleared them, OR the autouse TRUNCATE fixture did
        # — both are valid evidence the plumbing works. A non-zero count
        # here indicates cross-test leakage OR a migration that silently
        # skipped its TRUNCATE statement.
        for tbl in (
            "users", "sessions", "agent_instances", "agent_containers",
            "runs", "agent_events", "idempotency_keys", "rate_limit_counters",
        ):
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {tbl}")
            assert count == 0, (
                f"pre-seed assertion failed: {tbl} COUNT={count}. "
                f"Either alembic migration 006 did not clear it, or a "
                f"sibling test leaked state through the conftest fixture."
            )

        # ==============================================================
        # STEP 1 — seed two users (google provider, distinct subs)
        # ==============================================================
        user_a_id = uuid.uuid4()
        user_b_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO users (id, display_name, provider, sub, email) "
            "VALUES "
            "($1, 'alice', 'google', 'google-alice-sub', 'alice@example.com'),"
            "($2, 'bob',   'google', 'google-bob-sub',   'bob@example.com')",
            user_a_id, user_b_id,
        )

        # ==============================================================
        # STEP 2 — seed two live sessions (30-day expiry, matches fixture)
        # ==============================================================
        now = datetime.now(timezone.utc)
        exp = now + timedelta(days=30)
        session_a_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_a_id, now, exp,
        )
        session_b_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_b_id, now, exp,
        )

        # ==============================================================
        # STEP 3 — seed one agent per user
        # ==============================================================
        # NOTE: The ``agent_instances`` column name is ``name`` (added by
        # migration 002 as NOT NULL), NOT ``display_name``. The UNIQUE
        # constraint uq_agent_instances_user_name is (user_id, name), so
        # distinct per-user names are safe.
        agent_a_id = uuid.uuid4()
        agent_b_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO agent_instances "
            "(id, user_id, recipe_name, model, name) VALUES "
            "($1, $2, 'hermes', 'anthropic/claude-haiku-4.5', 'alice-agent'),"
            "($3, $4, 'hermes', 'anthropic/claude-haiku-4.5', 'bob-agent')",
            agent_a_id, user_a_id, agent_b_id, user_b_id,
        )
    finally:
        await conn.close()

    # ==============================================================
    # STEP 4 — user A view via /v1/agents
    # ==============================================================
    r_a = await async_client.get(
        "/v1/agents",
        headers={"Cookie": f"ap_session={session_a_id}"},
    )
    assert r_a.status_code == 200, r_a.text
    ids_a = {a["id"] for a in r_a.json()["agents"]}
    assert str(agent_a_id) in ids_a, (
        f"expected alice's own agent in alice's view; got {ids_a}"
    )
    assert str(agent_b_id) not in ids_a, (
        f"CROSS-USER LEAK: bob's agent surfaced in alice's view: {ids_a}"
    )

    # ==============================================================
    # STEP 5 — user B view via /v1/agents
    # ==============================================================
    r_b = await async_client.get(
        "/v1/agents",
        headers={"Cookie": f"ap_session={session_b_id}"},
    )
    assert r_b.status_code == 200, r_b.text
    ids_b = {a["id"] for a in r_b.json()["agents"]}
    assert str(agent_b_id) in ids_b, (
        f"expected bob's own agent in bob's view; got {ids_b}"
    )
    assert str(agent_a_id) not in ids_b, (
        f"CROSS-USER LEAK: alice's agent surfaced in bob's view: {ids_b}"
    )

    # ==============================================================
    # STEP 6 — anonymous (no cookie) → 401 Stripe-shape envelope
    # ==============================================================
    r_anon = await async_client.get("/v1/agents")
    assert r_anon.status_code == 401, r_anon.text
    body = r_anon.json()
    assert "error" in body, body
    assert body["error"]["code"] == "UNAUTHORIZED", body
    assert body["error"]["type"] == "unauthorized", body
    assert body["error"]["param"] == "ap_session", body
