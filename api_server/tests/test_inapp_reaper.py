"""Phase 22c.3-06 — integration tests for ``inapp_reaper``.

Real PG17 via testcontainers (golden rule #1 — no mocks for core
substrate). The reaper is a background asyncio task that sweeps rows
stuck in ``status='forwarded'`` past the D-40 threshold (11 minutes)
DIRECTLY to ``status='failed'`` with ``last_error='reaper_timeout'``.

Per D-40 (no auto-retry): every stuck row, regardless of ``attempts``
count, transitions to ``failed`` — never re-queued to ``pending``. Each
transition writes an ``agent_events`` row kind=``inapp_outbound_failed``,
``error_type='reaper_timeout'`` with ``published=false`` (the column
default — Plan 07 outbox pump fans the row out).

Coverage matrix (6 tests):

  Functional sweep
   * ``test_reaper_marks_stuck_forwarded_as_failed``    happy path —
     12-min-old forwarded row → failed + agent_events row INSERTed
   * ``test_reaper_skips_fresh_forwarded``              5-min-old still
     within budget — left alone
   * ``test_reaper_skips_pending_and_done``             only forwarded
     rows are touched

  D-40 invariant
   * ``test_reaper_no_auto_retry_d40``                  5 stuck rows
     with attempts=1..5 all → failed (NOT pending)

  Concurrency / cancellation
   * ``test_reaper_skip_locked_isolation``              connection A
     locks a stuck row; reaper tick on connection B picks the OTHER
     stuck row only (D-32 multi-replica safety)
   * ``test_reaper_loop_responds_to_stop_event``        background task
     finishes within ~1s when stop_event is set
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import asyncpg
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Seeding helpers — mirror the test_inapp_messages_store.py shape so the
# reaper tests stay drift-free with the store tests as the schema evolves.
# ---------------------------------------------------------------------------


async def _seed_user_agent_container(
    pool: asyncpg.Pool,
    *,
    container_status: str = "running",
) -> tuple[UUID, UUID, UUID, str]:
    """Insert users + agent_instances + agent_containers; return tuple.

    Returns ``(user_id, agent_id, container_row_id, container_id_str)``.
    Each call seeds independent rows so concurrent tests don't collide.
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
            user_id, "inapp-reaper-test",
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
                 deploy_mode, container_status, container_id, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', $5, $6,
                    CASE WHEN $5 = 'running' THEN NOW() ELSE NULL END)
            """,
            container_row_id, agent_id, user_id, recipe_name,
            container_status, docker_container_id,
        )
    return user_id, agent_id, container_row_id, docker_container_id


async def _seed_stuck_forwarded(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_id: UUID,
    content: str,
    minutes_old: int,
    attempts: int = 1,
) -> UUID:
    """Insert a row directly in ``status='forwarded'`` with back-dated
    ``last_attempt_at`` so the reaper threshold check finds it.

    The reaper uses ``last_attempt_at < NOW() - INTERVAL '11 minutes'``.
    A test wanting "stuck" passes ``minutes_old=12``; "fresh" passes
    ``minutes_old=5``.
    """
    async with pool.acquire() as conn:
        message_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, status, attempts, last_attempt_at)
            VALUES ($1, $2, $3, 'forwarded', $4,
                    NOW() - make_interval(mins => $5))
            RETURNING id
            """,
            agent_id, user_id, content, attempts, minutes_old,
        )
    return message_id


async def _fetch_message(
    pool: asyncpg.Pool, message_id: UUID,
) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT status, last_error, attempts, completed_at
            FROM inapp_messages WHERE id=$1
            """,
            message_id,
        )
    assert row is not None, f"message {message_id} disappeared"
    return dict(row)


async def _fetch_agent_events_for_container(
    pool: asyncpg.Pool, container_row_id: UUID,
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT seq, kind, payload, published, correlation_id
            FROM agent_events
            WHERE agent_container_id=$1
            ORDER BY seq ASC
            """,
            container_row_id,
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 1. Happy path — stuck forwarded row transitions to failed
# ---------------------------------------------------------------------------


async def test_reaper_marks_stuck_forwarded_as_failed(db_pool: asyncpg.Pool):
    """12-min-old forwarded row → failed + matching agent_events row.

    Asserts:
      * inapp_messages.status='failed'
      * inapp_messages.last_error='reaper_timeout'
      * agent_events row exists, kind='inapp_outbound_failed',
        error_type='reaper_timeout', published=false
      * agent_events.correlation_id is the message id
    """
    from api_server.services import inapp_reaper

    user_id, agent_id, container_row_id, _ = await _seed_user_agent_container(
        db_pool,
    )
    message_id = await _seed_stuck_forwarded(
        db_pool, user_id=user_id, agent_id=agent_id,
        content="stuck-message", minutes_old=12,
    )

    state = SimpleNamespace(db=db_pool)
    swept = await inapp_reaper._sweep_once(state)

    assert swept == 1
    msg = await _fetch_message(db_pool, message_id)
    assert msg["status"] == "failed"
    assert msg["last_error"] == "reaper_timeout"
    assert msg["completed_at"] is not None

    events = await _fetch_agent_events_for_container(db_pool, container_row_id)
    assert len(events) == 1
    evt = events[0]
    assert evt["kind"] == "inapp_outbound_failed"
    assert evt["published"] is False
    assert evt["correlation_id"] == str(message_id)
    payload = evt["payload"]
    if isinstance(payload, str):
        import json as _json
        payload = _json.loads(payload)
    assert payload["error_type"] == "reaper_timeout"
    assert payload["message"] == "reaper_timeout"
    # The reaper observes the row's attempts count when computing
    # retry_count; the seed used attempts=1 by default.
    assert payload["retry_count"] == 1
    assert "captured_at" in payload


# ---------------------------------------------------------------------------
# 2. Fresh row — within threshold — left alone
# ---------------------------------------------------------------------------


async def test_reaper_skips_fresh_forwarded(db_pool: asyncpg.Pool):
    """5-min-old forwarded row stays untouched (threshold is 11 min).

    Per D-40 the reaper is the safety net for genuine api-crash-mid-forward
    rows; normal long inferences are bounded by the 600s httpx timeout in
    the dispatcher and must NOT be reaped while still in flight.
    """
    from api_server.services import inapp_reaper

    user_id, agent_id, container_row_id, _ = await _seed_user_agent_container(
        db_pool,
    )
    message_id = await _seed_stuck_forwarded(
        db_pool, user_id=user_id, agent_id=agent_id,
        content="still-running", minutes_old=5,
    )

    state = SimpleNamespace(db=db_pool)
    swept = await inapp_reaper._sweep_once(state)

    assert swept == 0
    msg = await _fetch_message(db_pool, message_id)
    assert msg["status"] == "forwarded"  # untouched
    assert msg["last_error"] is None
    assert msg["completed_at"] is None

    events = await _fetch_agent_events_for_container(db_pool, container_row_id)
    assert events == []  # no agent_events written


# ---------------------------------------------------------------------------
# 3. Pending + done rows — reaper does not touch them
# ---------------------------------------------------------------------------


async def test_reaper_skips_pending_and_done(db_pool: asyncpg.Pool):
    """The reaper ONLY targets ``status='forwarded'`` rows.

    Pending rows belong to the dispatcher; done rows are terminal.
    Even with a back-dated ``last_attempt_at``, the WHERE clause's
    ``status='forwarded'`` predicate must filter them out.
    """
    from api_server.services import inapp_reaper

    user_id, agent_id, _, _ = await _seed_user_agent_container(db_pool)
    async with db_pool.acquire() as conn:
        # pending row with a back-dated last_attempt_at — must NOT be reaped.
        pending_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, status, attempts, last_attempt_at)
            VALUES ($1, $2, 'pending-content', 'pending', 0,
                    NOW() - INTERVAL '20 minutes')
            RETURNING id
            """,
            agent_id, user_id,
        )
        # done row, also old — must NOT be reaped.
        done_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, status, attempts,
                 last_attempt_at, bot_response, completed_at)
            VALUES ($1, $2, 'done-content', 'done', 1,
                    NOW() - INTERVAL '20 minutes', 'reply',
                    NOW() - INTERVAL '20 minutes')
            RETURNING id
            """,
            agent_id, user_id,
        )

    state = SimpleNamespace(db=db_pool)
    swept = await inapp_reaper._sweep_once(state)

    assert swept == 0
    pending_after = await _fetch_message(db_pool, pending_id)
    done_after = await _fetch_message(db_pool, done_id)
    assert pending_after["status"] == "pending"
    assert done_after["status"] == "done"


# ---------------------------------------------------------------------------
# 4. D-40 — no auto-retry: every stuck row goes DIRECTLY to failed
# ---------------------------------------------------------------------------


async def test_reaper_no_auto_retry_d40(db_pool: asyncpg.Pool):
    """5 stuck rows with attempts=1..5 all → failed (NOT requeued to pending).

    Per D-40 (revised 2026-04-29): no auto-retry. The reaper does not
    inspect ``attempts`` — every stuck row is terminal. Client retries
    by sending a new message.
    """
    from api_server.services import inapp_reaper

    user_id, agent_id, container_row_id, _ = await _seed_user_agent_container(
        db_pool,
    )
    ids: list[UUID] = []
    for attempts in (1, 2, 3, 4, 5):
        mid = await _seed_stuck_forwarded(
            db_pool, user_id=user_id, agent_id=agent_id,
            content=f"stuck-{attempts}", minutes_old=15, attempts=attempts,
        )
        ids.append(mid)

    state = SimpleNamespace(db=db_pool)
    swept = await inapp_reaper._sweep_once(state)
    assert swept == 5

    # Every row must be failed — never pending. This is the D-40 invariant.
    for mid in ids:
        row = await _fetch_message(db_pool, mid)
        assert row["status"] == "failed", (
            f"row {mid} (attempts={row['attempts']}) was {row['status']}, "
            "expected 'failed' per D-40 no-auto-retry"
        )
        assert row["last_error"] == "reaper_timeout"

    # And 5 agent_events rows were INSERTed (one per stuck row).
    events = await _fetch_agent_events_for_container(db_pool, container_row_id)
    assert len(events) == 5
    for evt in events:
        assert evt["kind"] == "inapp_outbound_failed"
        assert evt["published"] is False


# ---------------------------------------------------------------------------
# 5. SKIP LOCKED isolation — D-32 multi-replica safety
# ---------------------------------------------------------------------------


async def test_reaper_skip_locked_isolation(db_pool: asyncpg.Pool):
    """Connection A locks one stuck row; reaper on B sees only the OTHER one.

    ``fetch_stuck_forwarded`` issues ``FOR UPDATE SKIP LOCKED``. This is
    the D-32 contract: two replicas (or a reaper + a dispatcher) cannot
    pick the same row. We prove it empirically — A holds row 1 inside an
    open tx; B's full reaper tick processes only row 2.
    """
    from api_server.services import inapp_reaper
    from api_server.services import inapp_messages_store as ims

    user_id, agent_id, container_row_id, _ = await _seed_user_agent_container(
        db_pool,
    )
    locked_id = await _seed_stuck_forwarded(
        db_pool, user_id=user_id, agent_id=agent_id,
        content="locked-row", minutes_old=12,
    )
    free_id = await _seed_stuck_forwarded(
        db_pool, user_id=user_id, agent_id=agent_id,
        content="free-row", minutes_old=12,
    )

    a_locked = asyncio.Event()
    a_release = asyncio.Event()
    b_swept_count: list[int] = []

    async def conn_a():
        # Hold a FOR UPDATE lock on the ``locked_id`` row inside an
        # explicit transaction. SKIP LOCKED on B's side must skip this one.
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id FROM inapp_messages
                    WHERE id=$1
                    FOR UPDATE
                    """,
                    locked_id,
                )
                assert row is not None
                a_locked.set()
                await a_release.wait()

    async def conn_b():
        await a_locked.wait()
        state = SimpleNamespace(db=db_pool)
        swept = await inapp_reaper._sweep_once(state)
        b_swept_count.append(swept)
        a_release.set()

    await asyncio.gather(conn_a(), conn_b())

    # B must have swept exactly 1 row (the unlocked one).
    assert b_swept_count == [1]

    locked_after = await _fetch_message(db_pool, locked_id)
    free_after = await _fetch_message(db_pool, free_id)
    # The locked row was skipped → still forwarded.
    assert locked_after["status"] == "forwarded"
    # The free row was reaped → failed.
    assert free_after["status"] == "failed"
    assert free_after["last_error"] == "reaper_timeout"

    # And only the free row produced an agent_events entry.
    events = await _fetch_agent_events_for_container(db_pool, container_row_id)
    assert len(events) == 1
    assert events[0]["correlation_id"] == str(free_id)

    # Sanity: the store agrees the locked row is still stuck (a follow-up
    # reaper tick would now reap it, since A has released).
    async with db_pool.acquire() as conn:
        rows = await ims.fetch_stuck_forwarded(conn, threshold_minutes=11, limit=10)
    remaining_ids = {r["id"] for r in rows}
    assert locked_id in remaining_ids
    assert free_id not in remaining_ids


# ---------------------------------------------------------------------------
# 6. stop_event responsiveness — graceful shutdown gate
# ---------------------------------------------------------------------------


async def test_reaper_loop_responds_to_stop_event(db_pool: asyncpg.Pool):
    """Background ``reaper_loop`` finishes within ~1s when stop_event is set.

    The lifespan handler (Plan 22c.3-09) cancels the reaper by setting
    its stop_event. The loop must observe the event during its 15s sleep
    (via ``asyncio.wait_for(stop_event.wait(), TICK_S)``) and return
    cleanly — NOT hang for the full tick.
    """
    from api_server.services import inapp_reaper

    state = SimpleNamespace(db=db_pool)
    stop_event = asyncio.Event()
    task = asyncio.create_task(inapp_reaper.reaper_loop(state, stop_event))

    # Let one tick start (the loop runs _sweep_once, which is a no-op
    # on an empty DB, then enters the wait_for sleep).
    await asyncio.sleep(0.1)
    assert not task.done()

    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()
    # The task must NOT have raised — clean exit, not an exception.
    assert task.exception() is None
