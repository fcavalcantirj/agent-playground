"""Phase 22c.3-04 Task 2 — integration tests for ``inapp_messages_store``.

Real PG17 via testcontainers (no mocks — golden rule #1). Every test is
marked ``@pytest.mark.api_integration`` and seeds its own users +
agent_instances + agent_containers via ``_seed_user_agent_container``
before exercising the store function under test.

Coverage matrix (15 tests):

  CRUD basics
   * ``test_insert_pending_returns_id``                         insert_pending happy path
   * ``test_insert_pending_fk_violation_for_unknown_agent``     PG FK guard
   * ``test_fetch_by_id_filters_by_user``                       defense-in-depth user_id filter

  Dispatcher pump (``fetch_pending_for_dispatch``)
   * ``test_fetch_pending_for_dispatch_orders_by_created_at``   FIFO order
   * ``test_fetch_pending_for_dispatch_skips_locked_rows``      SKIP LOCKED concurrency
   * ``test_fetch_pending_joins_agent_containers``              non-running container surfaces
   * ``test_fetch_pending_includes_inapp_auth_token``           bearer-token JOIN

  State transitions
   * ``test_mark_forwarded_increments_attempts``                attempts bump + last_attempt_at
   * ``test_mark_done_writes_bot_response``                     forwarded → done
   * ``test_mark_failed_writes_error``                          forwarded → failed

  Reaper + restart sweeps
   * ``test_fetch_stuck_forwarded``                             threshold sensitivity
   * ``test_restart_sweep_resets_old_forwarded_to_pending``     UPDATE count return value

  History endpoints
   * ``test_fetch_history_for_agent_filters_by_user``           cross-tenant isolation
   * ``test_delete_history_for_agent_user``                     leaves agent_instances + agent_containers
   * ``test_mark_forwarded_handles_empty_list_noop``            defensive guard
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Seeding helper — every test uses this to satisfy the FK chain
# (users → agent_instances → agent_containers → inapp_messages).
# ---------------------------------------------------------------------------


async def _seed_user_agent_container(
    pool: asyncpg.Pool,
    *,
    inapp_auth_token: str | None = None,
    container_status: str = "running",
) -> tuple[UUID, UUID, UUID, str]:
    """Insert users + agent_instances + agent_containers; return tuple.

    Returns ``(user_id, agent_id, container_row_id, container_id_str)``.
    Each call seeds independent rows (UUIDs minted fresh) so concurrent
    tests don't collide on unique constraints.

    The ``container_status`` defaults to ``running`` because the dispatcher
    JOIN tests exercise the live path; tests probing readiness gates
    override to ``starting`` etc.
    """
    user_id = uuid4()
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "inapp-store-test",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, 'm-test', $4)
            """,
            agent_id, user_id, recipe_name, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id,
                 inapp_auth_token, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', $5, $6, $7,
                    CASE WHEN $5 = 'running' THEN NOW() ELSE NULL END)
            """,
            container_row_id, agent_id, user_id, recipe_name,
            container_status, docker_container_id, inapp_auth_token,
        )
    return user_id, agent_id, container_row_id, docker_container_id


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------


async def test_insert_pending_returns_id(db_pool: asyncpg.Pool):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="hi",
        )
        assert isinstance(message_id, UUID)

        row = await conn.fetchrow(
            "SELECT status, attempts, content, agent_id, user_id "
            "FROM inapp_messages WHERE id=$1",
            message_id,
        )
    assert row is not None
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["content"] == "hi"
    assert row["agent_id"] == agent_id
    assert row["user_id"] == user_id


async def test_insert_pending_fk_violation_for_unknown_agent(
    db_pool: asyncpg.Pool,
):
    """Inserting for a non-existent agent_id triggers the FK constraint."""
    from api_server.services import inapp_messages_store as store

    user_id, _, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await store.insert_pending(
                conn, agent_id=uuid4(), user_id=user_id, content="oops",
            )


async def test_fetch_by_id_filters_by_user(db_pool: asyncpg.Pool):
    """Defense in depth: user_id filter at SQL layer prevents cross-user leak."""
    from api_server.services import inapp_messages_store as store

    user_a, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    user_b, _, _, _ = await _seed_user_agent_container(db_pool)

    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_a, content="A's secret",
        )

        as_a = await store.fetch_by_id(conn, message_id, user_a)
        as_b = await store.fetch_by_id(conn, message_id, user_b)

    assert as_a is not None
    assert as_a["content"] == "A's secret"
    assert as_b is None


# ---------------------------------------------------------------------------
# fetch_pending_for_dispatch — FIFO ordering + SKIP LOCKED + JOIN
# ---------------------------------------------------------------------------


async def test_fetch_pending_for_dispatch_orders_by_created_at(
    db_pool: asyncpg.Pool,
):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        ids = []
        for content in ("first", "second", "third"):
            mid = await store.insert_pending(
                conn, agent_id=agent_id, user_id=user_id, content=content,
            )
            ids.append(mid)
            # 10ms gap — enough for created_at to monotonically advance.
            await conn.execute("SELECT pg_sleep(0.01)")

        rows = await store.fetch_pending_for_dispatch(conn, limit=10)

    contents = [r["content"] for r in rows]
    assert contents == ["first", "second", "third"]
    fetched_ids = [r["id"] for r in rows]
    assert fetched_ids == ids


async def test_fetch_pending_for_dispatch_skips_locked_rows(
    db_pool: asyncpg.Pool,
):
    """SKIP LOCKED proof — connection A locks row 1; B sees only 2,3.

    The two coroutines share the same pool but acquire independent
    connections (and therefore independent transactions). A starts a
    tx, fetches limit=1, holds the lock; B then runs its own
    fetch_pending(limit=10) — must return rows 2,3 only. A finally
    commits; the visibility of B's result is unchanged.
    """
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as seed_conn:
        ids = []
        for content in ("row-1", "row-2", "row-3"):
            mid = await store.insert_pending(
                seed_conn, agent_id=agent_id, user_id=user_id, content=content,
            )
            ids.append(mid)
            await seed_conn.execute("SELECT pg_sleep(0.01)")

    a_locked = asyncio.Event()
    a_release = asyncio.Event()
    b_seen: list[asyncpg.Record] = []

    async def conn_a():
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                rows = await store.fetch_pending_for_dispatch(conn, limit=1)
                assert len(rows) == 1
                assert rows[0]["content"] == "row-1"
                a_locked.set()
                # Hold the row lock until B has done its read.
                await a_release.wait()

    async def conn_b():
        await a_locked.wait()
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                rows = await store.fetch_pending_for_dispatch(conn, limit=10)
                b_seen.extend(rows)
        a_release.set()

    await asyncio.gather(conn_a(), conn_b())

    b_contents = [r["content"] for r in b_seen]
    assert b_contents == ["row-2", "row-3"]
    # Crucially, "row-1" must NOT appear — it was locked by A.
    assert "row-1" not in b_contents


async def test_fetch_pending_joins_agent_containers(db_pool: asyncpg.Pool):
    """Pending row whose container is in 'starting' still surfaces.

    Readiness gate is dispatcher's call (D-37), not the store's. The
    store hands the dispatcher the joined view of (message, container)
    so it has every field needed to decide whether to forward.
    """
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, container_row_id, container_id = (
        await _seed_user_agent_container(
            db_pool, container_status="starting",
        )
    )
    async with db_pool.acquire() as conn:
        await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="hi",
        )
        rows = await store.fetch_pending_for_dispatch(conn, limit=10)

    assert len(rows) == 1
    row = rows[0]
    assert row["container_status"] == "starting"
    assert row["container_row_id"] == container_row_id
    assert row["container_id"] == container_id
    # ``ready_at`` IS NULL because container_status='starting' in the seed.
    assert row["ready_at"] is None


async def test_fetch_pending_includes_inapp_auth_token(db_pool: asyncpg.Pool):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(
        db_pool, inapp_auth_token="secret-bearer",
    )
    async with db_pool.acquire() as conn:
        await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="hi",
        )
        rows = await store.fetch_pending_for_dispatch(conn, limit=10)

    assert len(rows) == 1
    assert rows[0]["inapp_auth_token"] == "secret-bearer"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def test_mark_forwarded_increments_attempts(db_pool: asyncpg.Pool):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="hi",
        )

        await store.mark_forwarded(conn, [message_id])
        row1 = await conn.fetchrow(
            "SELECT status, attempts, last_attempt_at FROM inapp_messages WHERE id=$1",
            message_id,
        )
        assert row1["status"] == "forwarded"
        assert row1["attempts"] == 1
        assert row1["last_attempt_at"] is not None

        await store.mark_forwarded(conn, [message_id])
        row2 = await conn.fetchrow(
            "SELECT attempts FROM inapp_messages WHERE id=$1", message_id,
        )
        assert row2["attempts"] == 2


async def test_mark_forwarded_handles_empty_list_noop(db_pool: asyncpg.Pool):
    """Defensive guard: an empty batch must not run a SQL statement."""
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="x",
        )
        await store.mark_forwarded(conn, [])  # should not raise
        row = await conn.fetchrow(
            "SELECT status, attempts FROM inapp_messages WHERE id=$1",
            message_id,
        )
        assert row["status"] == "pending"
        assert row["attempts"] == 0


async def test_mark_done_writes_bot_response(db_pool: asyncpg.Pool):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="ping",
        )
        await store.mark_forwarded(conn, [message_id])
        await store.mark_done(conn, message_id, "pong")

        row = await conn.fetchrow(
            "SELECT status, bot_response, completed_at FROM inapp_messages WHERE id=$1",
            message_id,
        )
    assert row["status"] == "done"
    assert row["bot_response"] == "pong"
    assert row["completed_at"] is not None


async def test_mark_failed_writes_error(db_pool: asyncpg.Pool):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        message_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="ping",
        )
        await store.mark_forwarded(conn, [message_id])
        await store.mark_failed(conn, message_id, "bot_timeout")

        row = await conn.fetchrow(
            "SELECT status, last_error, completed_at FROM inapp_messages WHERE id=$1",
            message_id,
        )
    assert row["status"] == "failed"
    assert row["last_error"] == "bot_timeout"
    assert row["completed_at"] is not None


# ---------------------------------------------------------------------------
# Reaper + restart sweeps
# ---------------------------------------------------------------------------


async def test_fetch_stuck_forwarded(db_pool: asyncpg.Pool):
    """Threshold sensitivity — 12-min-old surfaces; 5-min-old does not."""
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        old_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="old",
        )
        recent_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="recent",
        )
        # Promote both to forwarded, then back-date last_attempt_at.
        await store.mark_forwarded(conn, [old_id, recent_id])
        await conn.execute(
            "UPDATE inapp_messages SET last_attempt_at = NOW() - INTERVAL '12 minutes' WHERE id=$1",
            old_id,
        )
        await conn.execute(
            "UPDATE inapp_messages SET last_attempt_at = NOW() - INTERVAL '5 minutes' WHERE id=$1",
            recent_id,
        )

        # Threshold 11min — old (12min back) IN, recent (5min back) OUT.
        rows = await store.fetch_stuck_forwarded(
            conn, threshold_minutes=11, limit=10,
        )
    ids = {r["id"] for r in rows}
    assert old_id in ids
    assert recent_id not in ids


async def test_restart_sweep_resets_old_forwarded_to_pending(
    db_pool: asyncpg.Pool,
):
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        old_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="old",
        )
        recent_id = await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_id, content="recent",
        )
        await store.mark_forwarded(conn, [old_id, recent_id])
        await conn.execute(
            "UPDATE inapp_messages SET last_attempt_at = NOW() - INTERVAL '16 minutes' WHERE id=$1",
            old_id,
        )
        await conn.execute(
            "UPDATE inapp_messages SET last_attempt_at = NOW() - INTERVAL '7 minutes' WHERE id=$1",
            recent_id,
        )

        affected = await store.restart_sweep(conn, threshold_minutes=15)
        assert affected == 1

        old_row = await conn.fetchrow(
            "SELECT status FROM inapp_messages WHERE id=$1", old_id,
        )
        recent_row = await conn.fetchrow(
            "SELECT status FROM inapp_messages WHERE id=$1", recent_id,
        )
    assert old_row["status"] == "pending"
    assert recent_row["status"] == "forwarded"


# ---------------------------------------------------------------------------
# History endpoints
# ---------------------------------------------------------------------------


async def test_fetch_history_for_agent_filters_by_user(db_pool: asyncpg.Pool):
    """User A sees their 2 messages; user B sees their 1 — no cross-leak."""
    from api_server.services import inapp_messages_store as store

    # Same agent_id, but a different user — we have to seed agent_containers
    # for user_a, then insert an agent_instances row for user_b separately.
    user_a, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    user_b = uuid4()
    async with db_pool.acquire() as conn:
        # Seed user_b row only — re-using agent_id (user_a's agent) is the
        # cross-tenant probe shape: even if a route gives B a wrong agent_id,
        # the user_id filter blocks the leak.
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_b, "inapp-store-test-b",
        )
        # Insert messages: 2 for A, 1 for B (against A's agent — the user_id
        # filter is the only thing that should keep them disjoint).
        await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_a, content="A1",
        )
        await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_a, content="A2",
        )
        await store.insert_pending(
            conn, agent_id=agent_id, user_id=user_b, content="B1",
        )

        rows_a = await store.fetch_history_for_agent(
            conn, agent_id=agent_id, user_id=user_a,
        )
        rows_b = await store.fetch_history_for_agent(
            conn, agent_id=agent_id, user_id=user_b,
        )

    assert len(rows_a) == 2
    assert {r["content"] for r in rows_a} == {"A1", "A2"}
    assert len(rows_b) == 1
    assert rows_b[0]["content"] == "B1"


async def test_delete_history_for_agent_user(db_pool: asyncpg.Pool):
    """D-43: deleting messages must NOT touch agent_instances or agent_containers."""
    from api_server.services import inapp_messages_store as store

    user_id, agent_id, container_row_id, _ = await _seed_user_agent_container(
        db_pool,
    )
    async with db_pool.acquire() as conn:
        for content in ("m1", "m2"):
            await store.insert_pending(
                conn, agent_id=agent_id, user_id=user_id, content=content,
            )

        affected = await store.delete_history_for_agent_user(
            conn, agent_id=agent_id, user_id=user_id,
        )
        assert affected == 2

        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM inapp_messages WHERE agent_id=$1 AND user_id=$2",
            agent_id, user_id,
        )
        assert remaining == 0

        # Crucial: parent rows untouched.
        agent_count = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_instances WHERE id=$1", agent_id,
        )
        container_count = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_containers WHERE id=$1", container_row_id,
        )
    assert agent_count == 1
    assert container_count == 1
