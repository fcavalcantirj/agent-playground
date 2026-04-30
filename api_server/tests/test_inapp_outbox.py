"""Phase 22c.3-07 — integration tests for ``inapp_outbox`` pump.

Real PG17 + Real Redis 7 via testcontainers (golden rule #1 — no mocks
for core substrate). The outbox pump is a 100ms-tick lifespan-managed
asyncio task that:

  1. Picks up to PUMP_BATCH_LIMIT (=100) ``agent_events`` rows where
     ``published=false`` AND ``ts > NOW() - INTERVAL '1 hour'`` (D-35
     abandon-after-1h).
  2. Publishes each row to Redis channel ``agent:inapp:<agent_id>``
     with a JSON envelope ``{seq, kind, payload, correlation_id, ts}``
     (D-09 channel naming + D-34 envelope shape).
  3. Marks all successfully-published rows ``published=true`` in a
     SINGLE bulk UPDATE — atomic per batch.

Strategy (RESEARCH §Pitfall 3 strategy 2 — optimistic batch):

  * On any ``redis.RedisError`` mid-batch, abort the batch — the
    transaction rolls back so the UPDATE never runs and ALL rows stay
    ``published=false``. Next tick retries the entire batch.
  * SSE consumers dedupe by seq if a partial-batch retry produces a
    few duplicates (D-10 idempotent client-side handling).

Multi-replica safety (D-32): ``FOR UPDATE OF e SKIP LOCKED`` ensures
two pump replicas can run concurrently without double-publish.

Coverage matrix (8 tests):

  Functional pump
   * ``test_pump_publishes_unpublished_events`` — happy path: 3 unpublished
     rows → 3 redis publishes + 3 published=true updates
   * ``test_pump_skips_published_rows`` — already-published rows untouched
   * ``test_pump_skips_old_unpublished_d35`` — D-35 abandon-after-1h: rows
     older than 1h with published=false are FILTERED OUT (stay
     published=false; pump emits nothing)
   * ``test_pump_envelope_shape`` — published JSON has 5 keys (seq, kind,
     payload, correlation_id, ts); seq is int; payload is dict; ts is ISO8601
   * ``test_pump_publishes_to_per_agent_channel`` — per-agent channel
     fanout: 2 rows for A + 1 for B → A channel gets 2; B gets 1

  Failure / safety
   * ``test_pump_redis_failure_rolls_back_uncommitted`` — on Redis error
     mid-batch, no rows mark as published; retry tick (mock cleared)
     publishes all + marks all
   * ``test_pump_skip_locked_two_pumps`` — two _pump_once calls via
     asyncio.gather process disjoint subsets; all 5 published exactly once

  Lifecycle
   * ``test_pump_loop_responds_to_stop_event`` — background task cancels
     within ~1s when stop_event.set()
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import asyncpg
import pytest
import redis.asyncio as redis_async


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Seeding helpers — mirror test_inapp_reaper.py shape so the outbox tests
# stay drift-free with the reaper + store test discipline.
# ---------------------------------------------------------------------------


async def _seed_user_agent_container(
    pool: asyncpg.Pool,
) -> tuple[UUID, UUID, UUID, str]:
    """Insert users + agent_instances + agent_containers; return tuple.

    Returns ``(user_id, agent_id, container_row_id, container_id_str)``.
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
            user_id, "inapp-outbox-test",
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
            VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, NOW())
            """,
            container_row_id, agent_id, user_id, recipe_name,
            docker_container_id,
        )
    return user_id, agent_id, container_row_id, docker_container_id


async def _insert_event(
    pool: asyncpg.Pool,
    container_row_id: UUID,
    *,
    seq: int,
    kind: str = "inapp_outbound",
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
    published: bool = False,
    ts_offset_seconds: int = 0,
) -> int:
    """Insert one agent_events row.

    ``ts_offset_seconds``: ``0`` = NOW(); ``-3600`` = 1h ago; positive
    values are not normally useful but supported for completeness.

    The seq is caller-supplied so a single test can queue multiple rows
    without racing the per-container advisory lock the production
    insert_agent_event uses.
    """
    if payload is None:
        payload = {"content": "hello", "source": "agent"}
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO agent_events
                (agent_container_id, seq, kind, payload, correlation_id,
                 published, ts)
            VALUES ($1, $2, $3, $4::jsonb, $5, $6,
                    NOW() + make_interval(secs => $7))
            RETURNING id
            """,
            container_row_id, seq, kind, json.dumps(payload),
            correlation_id, published, ts_offset_seconds,
        )
    return int(row_id)


async def _fetch_event(pool: asyncpg.Pool, event_id: int) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, seq, kind, payload, correlation_id, published, ts
            FROM agent_events WHERE id=$1
            """,
            event_id,
        )
    assert row is not None, f"event {event_id} disappeared"
    return dict(row)


async def _subscribe_and_collect(
    redis_url: str,
    channel: str,
    n: int,
    timeout: float = 5.0,
) -> list[dict]:
    """Open a fresh subscriber, wait for ``n`` messages, return parsed dicts.

    Uses a NEW Redis client (not the per-test ``redis_client`` fixture) so
    the subscriber and the publisher live in separate connections — closer
    to the production fan-out shape, and avoids the asyncio quirk where a
    single client can't both publish and consume from a pubsub channel
    inside the same coroutine.
    """
    sub_client = redis_async.from_url(redis_url, decode_responses=False)
    try:
        async with sub_client.pubsub() as pubsub:
            await pubsub.subscribe(channel)
            collected: list[dict] = []
            end = asyncio.get_event_loop().time() + timeout
            while (
                len(collected) < n
                and asyncio.get_event_loop().time() < end
            ):
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5,
                )
                if msg is None:
                    continue
                data = msg["data"]
                if isinstance(data, (bytes, bytearray)):
                    data = data.decode("utf-8")
                collected.append(json.loads(data))
            return collected
    finally:
        await sub_client.aclose()


def _redis_url_for(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


# ---------------------------------------------------------------------------
# 1. Happy path — 3 unpublished events get published + marked
# ---------------------------------------------------------------------------


async def test_pump_publishes_unpublished_events(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Happy path: 3 unpublished rows → 3 redis publishes + UPDATE.

    Subscribes BEFORE running the pump so the Redis broker has the
    subscriber registered when the publishes happen — Redis Pub/Sub is
    fire-and-forget; a subscriber attaching after the publish would miss
    the messages (this is the durability gap covered by D-25 SSE
    Last-Event-Id replay in production; the outbox itself does not promise
    catch-up via Pub/Sub).
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)

    # Seed 3 unpublished rows BEFORE starting the subscriber so the
    # SELECT clearly finds them on the first pump tick.
    event_ids = []
    for seq in (1, 2, 3):
        eid = await _insert_event(
            db_pool, container_row_id,
            seq=seq, kind="inapp_outbound",
            payload={"content": f"reply-{seq}", "source": "agent"},
            correlation_id=str(uuid4()),
        )
        event_ids.append(eid)

    # Start subscriber + pump concurrently. The subscriber runs first
    # (it awaits at pubsub.subscribe before the pump starts publishing).
    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=3, timeout=5.0),
    )
    # Give the subscriber a tick to register with the broker.
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 3

    messages = await sub_task
    assert len(messages) == 3
    contents = sorted(m["payload"]["content"] for m in messages)
    assert contents == ["reply-1", "reply-2", "reply-3"]

    # All 3 rows must be marked published=true.
    for eid in event_ids:
        row = await _fetch_event(db_pool, eid)
        assert row["published"] is True


# ---------------------------------------------------------------------------
# 2. Skip already-published rows
# ---------------------------------------------------------------------------


async def test_pump_skips_published_rows(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """A row with published=true must never be re-published.

    Pre-007 backfilled all existing rows to published=true; pump must
    treat them as terminal.
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    eid = await _insert_event(
        db_pool, container_row_id,
        seq=1, kind="inapp_outbound",
        payload={"content": "already-pub", "source": "agent"},
        published=True,
    )
    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)

    # Subscribe with a short timeout — we EXPECT zero messages.
    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=1, timeout=1.5),
    )
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 0

    messages = await sub_task
    assert messages == []  # nothing published

    # Row stays published=true (pump didn't touch it).
    row = await _fetch_event(db_pool, eid)
    assert row["published"] is True


# ---------------------------------------------------------------------------
# 3. D-35 abandon-after-1h — rows older than 1h are filtered out
# ---------------------------------------------------------------------------


async def test_pump_skips_old_unpublished_d35(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Per D-35: rows with published=false older than 1h are FILTERED OUT.

    They stay published=false (Last-Event-Id replay against agent_events
    directly handles them, bypassing Redis). The pump's WHERE clause
    has ``ts > NOW() - INTERVAL '1 hour'`` — a 2h-old row is excluded.

    This test confirms:
      1. The 2h-old row is NOT published to Redis.
      2. The 2h-old row stays published=false (NOT marked terminal).
      3. The pump emits 0 (no work to do for that row).
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    # Old row — ts = NOW() - 2h, beyond the 1h abandon threshold.
    old_eid = await _insert_event(
        db_pool, container_row_id,
        seq=1, kind="inapp_outbound",
        payload={"content": "old-message", "source": "agent"},
        ts_offset_seconds=-7200,  # 2h ago
    )
    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)

    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=1, timeout=1.5),
    )
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 0

    messages = await sub_task
    assert messages == []  # NOT published — D-35 filters it out.

    # Row stays published=false — the pump did not mark it as terminal.
    row = await _fetch_event(db_pool, old_eid)
    assert row["published"] is False


# ---------------------------------------------------------------------------
# 4. Redis-failure mid-batch — Pitfall 3 strategy 2 (optimistic rollback)
# ---------------------------------------------------------------------------


async def test_pump_redis_failure_rolls_back_uncommitted(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Per RESEARCH §Pitfall 3 strategy 2: Redis error mid-batch → rollback.

    The pump's contract: if ANY redis.publish raises ``RedisError``, the
    transaction MUST roll back (no UPDATE runs); ALL rows stay
    published=false. The next tick retries the entire batch.

    Implementation note: the original publishes that succeeded BEFORE the
    failure are duplicated on the retry tick — SSE clients dedupe by seq
    (D-10 idempotent client-side handling). This test does NOT assert
    "no duplicate publishes" because they are an explicit and accepted
    consequence of the rollback strategy.
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    event_ids = []
    for seq in (1, 2, 3):
        eid = await _insert_event(
            db_pool, container_row_id,
            seq=seq, kind="inapp_outbound",
            payload={"content": f"rb-{seq}", "source": "agent"},
        )
        event_ids.append(eid)

    # Counting wrapper — fail on the SECOND publish call.
    call_count = {"n": 0}
    real_publish = redis_client.publish

    async def flaky_publish(channel: str, msg: bytes | str) -> int:
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise redis_async.RedisError("simulated mid-batch failure")
        return await real_publish(channel, msg)

    with patch.object(redis_client, "publish", side_effect=flaky_publish):
        swept = await inapp_outbox._pump_once(db_pool, redis_client)

    # The pump aborted mid-batch — swept count is 0 (transaction rolled back,
    # UPDATE never ran).
    assert swept == 0

    # All 3 rows stay published=false despite the first publish having
    # actually reached Redis. This is the core Pitfall 3 strategy 2
    # invariant: NO row marks as published until the WHOLE batch succeeds.
    for eid in event_ids:
        row = await _fetch_event(db_pool, eid)
        assert row["published"] is False, (
            f"event {eid} was marked published=true despite mid-batch "
            "Redis failure — rollback contract violated"
        )

    # Retry tick (real publish path) — all 3 rows now publish + mark.
    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)
    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=3, timeout=5.0),
    )
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 3

    messages = await sub_task
    assert len(messages) == 3
    contents = sorted(m["payload"]["content"] for m in messages)
    assert contents == ["rb-1", "rb-2", "rb-3"]

    for eid in event_ids:
        row = await _fetch_event(db_pool, eid)
        assert row["published"] is True


# ---------------------------------------------------------------------------
# 5. SKIP LOCKED — two pump ticks process disjoint subsets
# ---------------------------------------------------------------------------


async def test_pump_skip_locked_two_pumps(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Concurrent _pump_once calls partition the work via SKIP LOCKED.

    D-32 multi-replica safety: ``FOR UPDATE OF e SKIP LOCKED``. Two
    coroutines invoking _pump_once() at the same time must not double-
    publish — each picks a DISJOINT subset.

    Total rows seeded: 5. Combined swept count must be exactly 5 (no
    duplicates from concurrent ticks). Redis must receive exactly 5
    messages.
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    event_ids = []
    for seq in range(1, 6):
        eid = await _insert_event(
            db_pool, container_row_id,
            seq=seq, kind="inapp_outbound",
            payload={"content": f"sl-{seq}", "source": "agent"},
        )
        event_ids.append(eid)

    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)
    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=5, timeout=5.0),
    )
    await asyncio.sleep(0.2)

    swept_a, swept_b = await asyncio.gather(
        inapp_outbox._pump_once(db_pool, redis_client),
        inapp_outbox._pump_once(db_pool, redis_client),
    )

    # Combined work covers all 5 rows (no double-publish).
    assert swept_a + swept_b == 5
    # Each side may have grabbed any partition (e.g. 3+2, 4+1, 5+0).
    # The only invariant is the combined total.

    messages = await sub_task
    assert len(messages) == 5
    contents = sorted(m["payload"]["content"] for m in messages)
    assert contents == [f"sl-{i}" for i in range(1, 6)]

    for eid in event_ids:
        row = await _fetch_event(db_pool, eid)
        assert row["published"] is True


# ---------------------------------------------------------------------------
# 6. Per-agent channel fan-out — D-09 channel naming
# ---------------------------------------------------------------------------


async def test_pump_publishes_to_per_agent_channel(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Per D-09: channel name is ``agent:inapp:<agent_instance_id>``.

    Two distinct agents → two distinct channels. Subscribers per agent
    only see THEIR agent's messages.

    Seeds 2 rows for agent A and 1 row for agent B; subscribes to both
    channels; A receives 2; B receives 1.
    """
    from api_server.services import inapp_outbox

    _, agent_a_id, container_a, _ = await _seed_user_agent_container(db_pool)
    _, agent_b_id, container_b, _ = await _seed_user_agent_container(db_pool)

    # 2 events for A, 1 for B.
    await _insert_event(
        db_pool, container_a, seq=1, payload={"content": "A-1", "source": "agent"},
    )
    await _insert_event(
        db_pool, container_a, seq=2, payload={"content": "A-2", "source": "agent"},
    )
    await _insert_event(
        db_pool, container_b, seq=1, payload={"content": "B-1", "source": "agent"},
    )

    channel_a = f"agent:inapp:{agent_a_id}"
    channel_b = f"agent:inapp:{agent_b_id}"
    redis_url = _redis_url_for(redis_container)
    sub_a = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel_a, n=2, timeout=5.0),
    )
    sub_b = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel_b, n=1, timeout=5.0),
    )
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 3

    msgs_a = await sub_a
    msgs_b = await sub_b
    assert len(msgs_a) == 2
    assert len(msgs_b) == 1

    contents_a = sorted(m["payload"]["content"] for m in msgs_a)
    contents_b = [m["payload"]["content"] for m in msgs_b]
    assert contents_a == ["A-1", "A-2"]
    assert contents_b == ["B-1"]


# ---------------------------------------------------------------------------
# 7. stop_event responsiveness — graceful shutdown gate
# ---------------------------------------------------------------------------


async def test_pump_loop_responds_to_stop_event(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis,
):
    """``outbox_pump_loop`` finishes within ~1s when stop_event is set.

    Mirrors the reaper's stop_event responsiveness contract — Plan 09
    lifespan cancels the pump by setting state.inapp_stop. The loop must
    observe the event during its sleep (via wait_for(stop_event.wait(),
    PUMP_TICK_S | PUMP_IDLE_TICK_S)) and return cleanly.
    """
    from api_server.services import inapp_outbox

    state = SimpleNamespace(db=db_pool, redis=redis_client)
    stop_event = asyncio.Event()
    task = asyncio.create_task(
        inapp_outbox.outbox_pump_loop(state, stop_event),
    )

    # Let one tick run on an empty DB — the loop enters the idle sleep.
    await asyncio.sleep(0.1)
    assert not task.done()

    stop_event.set()
    await asyncio.wait_for(task, timeout=2.0)
    assert task.done()
    assert task.exception() is None


# ---------------------------------------------------------------------------
# 8. Envelope shape — D-34 published JSON keys + types
# ---------------------------------------------------------------------------


async def test_pump_envelope_shape(
    db_pool: asyncpg.Pool, redis_client: redis_async.Redis, redis_container,
):
    """Per D-34: published JSON has 5 keys: seq, kind, payload, correlation_id, ts.

    Type contract:
      * seq         -> int (the per-container monotonic seq)
      * kind        -> str (one of the agent_events kind enum values)
      * payload     -> dict (NOT a JSON-encoded string)
      * correlation_id -> str | None
      * ts          -> str (ISO-8601)

    SSE consumers (Plan 22c.3-08) deserialize this envelope and pass
    payload through to the client; mis-shaping it breaks the contract.
    """
    from api_server.services import inapp_outbox

    _, agent_id, container_row_id, _ = await _seed_user_agent_container(db_pool)
    correlation_id = str(uuid4())
    await _insert_event(
        db_pool, container_row_id,
        seq=42, kind="inapp_outbound",
        payload={"content": "envelope-test", "source": "agent"},
        correlation_id=correlation_id,
    )

    channel = f"agent:inapp:{agent_id}"
    redis_url = _redis_url_for(redis_container)
    sub_task = asyncio.create_task(
        _subscribe_and_collect(redis_url, channel, n=1, timeout=5.0),
    )
    await asyncio.sleep(0.2)

    swept = await inapp_outbox._pump_once(db_pool, redis_client)
    assert swept == 1

    messages = await sub_task
    assert len(messages) == 1
    msg = messages[0]

    # Exact 5-key contract — D-34.
    assert set(msg.keys()) == {"seq", "kind", "payload", "correlation_id", "ts"}, (
        f"envelope keys drifted: got {sorted(msg.keys())}"
    )
    # Type contract.
    assert isinstance(msg["seq"], int)
    assert msg["seq"] == 42
    assert isinstance(msg["kind"], str)
    assert msg["kind"] == "inapp_outbound"
    assert isinstance(msg["payload"], dict)
    assert msg["payload"] == {"content": "envelope-test", "source": "agent"}
    assert msg["correlation_id"] == correlation_id
    assert isinstance(msg["ts"], str)
    # ISO-8601 sanity check — datetime.fromisoformat must parse it.
    parsed_ts = datetime.fromisoformat(msg["ts"])
    assert parsed_ts is not None
