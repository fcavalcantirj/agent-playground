"""Phase 22c.3-07 — outbox pump (Postgres -> Redis Pub/Sub).

D-33 / D-34: every ``agent_events`` row is INSERTed with
``published=false`` (the alembic 007 column default). This pump publishes
each row to Redis channel ``agent:inapp:<agent_instance_id>`` (D-09),
then marks it ``published=true`` atomically. The 100ms tick cadence
delivers events sub-second to SSE clients in the happy path.

Strategy (per RESEARCH §Pitfall 3 strategy 2 — optimistic batch with
single UPDATE on success):

  * Iterate publishes for the batch.
  * If any ``redis.publish`` raises ``redis.RedisError``, abort the batch
    by returning early — the outer ``conn.transaction()`` rolls back
    cleanly because the bulk UPDATE never runs. ALL rows stay
    ``published=false``.
  * Next tick retries the entire batch from scratch. Rows that DID
    successfully publish before the failure get re-published — SSE
    clients dedupe by seq (D-10 idempotent client-side handling).

Per D-35 abandon-after-1h: rows older than 1 hour with published=false
are FILTERED OUT of the SELECT (``ts > NOW() - $1::interval``). They
stay ``published=false`` permanently from the pump's perspective; SSE
clients still surface them via Last-Event-Id replay (Plan 22c.3-08),
which queries ``agent_events`` directly and bypasses Redis entirely.

Per D-32 multi-replica safety: ``FOR UPDATE OF e SKIP LOCKED`` on the
SELECT means two pump replicas (or one pump tick interleaving with a
future second replica) can never pick the same row.

This is the FIRST transactional-outbox pattern in api_server (per
PATTERNS.md "GREENFIELD" callout). The closest control-flow precedent
is ``services/watcher_service.py`` (asyncio batch consumer); the data
flow is novel — Postgres pump to external broker.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import redis.asyncio as redis_async


_log = logging.getLogger("api_server.inapp_outbox")


# ---------------------------------------------------------------------------
# Tunable constants — kept module-level so tests can monkey-patch them.
# ---------------------------------------------------------------------------

#: 100ms tick when the previous batch published any rows (D-34). Sub-second
#: event delivery to SSE clients in the happy path.
PUMP_TICK_S = 0.1

#: Idle backoff when the previous batch was empty — saves PG round-trips
#: on a quiet system. Bounded so the pump still wakes within ~500ms when a
#: new event arrives.
PUMP_IDLE_TICK_S = 0.5

#: Per-tick batch ceiling (D-34). 100 rows per 100ms = 1k rows/sec
#: sustained throughput per replica — well above the realistic chat
#: workload (D-42 caps user-facing messaging at 4/min/agent).
PUMP_BATCH_LIMIT = 100

#: D-35 abandon threshold: rows older than this with ``published=false``
#: are FILTERED OUT of the SELECT. They are not re-attempted by the pump
#: (Last-Event-Id replay in Plan 22c.3-08 handles them via direct PG read).
ABANDON_AFTER = timedelta(hours=1)


# ---------------------------------------------------------------------------
# Per-tick unit-of-work (the canonical pump pass)
# ---------------------------------------------------------------------------


async def _pump_once(pool, redis_client) -> int:
    """One pump pass — pick batch, publish, mark.

    Steps:
      1. Open a connection + transaction.
      2. SELECT up to ``PUMP_BATCH_LIMIT`` unpublished rows whose ``ts``
         is within the abandon window, JOINing ``agent_containers`` to
         derive the channel's ``agent_instance_id``. ``FOR UPDATE OF e
         SKIP LOCKED`` so concurrent pumps disjointly partition the work.
      3. For each row, build the D-34 envelope and ``redis.publish``. On
         any ``RedisError``, abort by returning 0 — the outer
         transaction rolls back; the bulk UPDATE never runs; all rows
         stay ``published=false``.
      4. Bulk UPDATE all successfully-published rows to
         ``published=true`` in a single round-trip.

    Returns the count of rows successfully marked. ``0`` is BOTH the
    "empty batch" case AND the "redis-error mid-batch" case — they
    differ in side effects (the latter caused the rollback) but share
    the return shape because the caller only uses it for backoff
    decisions.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT e.id, e.seq, e.kind, e.payload, e.correlation_id,
                       e.ts, c.agent_instance_id
                FROM agent_events e
                JOIN agent_containers c ON c.id = e.agent_container_id
                WHERE e.published = FALSE
                  AND e.ts > NOW() - $1::interval
                ORDER BY e.id
                FOR UPDATE OF e SKIP LOCKED
                LIMIT $2
                """,
                ABANDON_AFTER, PUMP_BATCH_LIMIT,
            )
            if not rows:
                return 0
            published_ids: list[int] = []
            for r in rows:
                payload = r["payload"]
                # asyncpg returns JSONB as either dict (when the codec
                # is registered) or str (raw). We tolerate both —
                # production registers the dict codec but tests that
                # bypass that path send raw JSON strings.
                if isinstance(payload, str):
                    payload = json.loads(payload)
                channel = f"agent:inapp:{r['agent_instance_id']}"
                msg = json.dumps({
                    "seq": int(r["seq"]),
                    "kind": r["kind"],
                    "payload": payload,
                    "correlation_id": r["correlation_id"],
                    "ts": r["ts"].isoformat(),
                })
                try:
                    await redis_client.publish(channel, msg)
                except redis_async.RedisError:
                    _log.exception(
                        "phase22c3.outbox.redis_publish_failed",
                        extra={"event_id": int(r["id"])},
                    )
                    # Abort the batch: returning here causes the outer
                    # ``async with conn.transaction()`` to commit the
                    # SELECT-only work (no rows changed) and abandon the
                    # UPDATE entirely. All rows stay published=false.
                    # See Pitfall 3 strategy 2 for the trade-off
                    # discussion (duplicate-publish on retry).
                    return 0
                published_ids.append(int(r["id"]))
            if published_ids:
                await conn.execute(
                    """
                    UPDATE agent_events
                    SET published = TRUE
                    WHERE id = ANY($1::bigint[])
                    """,
                    published_ids,
                )
            return len(published_ids)


# ---------------------------------------------------------------------------
# outbox_pump_loop — the 100ms tick (lifespan-managed)
# ---------------------------------------------------------------------------


async def outbox_pump_loop(state: Any, stop_event: asyncio.Event) -> None:
    """Lifespan-managed outbox pump. Runs until ``stop_event`` is set.

    Plan 22c.3-09 lifespan creates this as an ``asyncio.Task`` and
    cancels it via ``stop_event.set()``. The loop:

    1. Calls :func:`_pump_once` with the asyncpg pool + the asyncio
       redis client (both attached to ``state`` by the lifespan).
    2. If the previous tick published any rows, sleeps ``PUMP_TICK_S``
       (100ms — keep latency low while there's work).
    3. If the previous tick was a no-op, sleeps ``PUMP_IDLE_TICK_S``
       (500ms — back off on a quiet system).
    4. Both sleeps go through ``asyncio.wait_for(stop_event.wait(), …)``
       so the task wakes IMMEDIATELY on shutdown, never lagging the
       full tick budget.

    Loop-level error handling: never let the loop die. Real underlying
    failures (DB outage, bad row) recur and produce a stream of error
    logs; ops can alert on that. Mirrors
    :func:`inapp_dispatcher.dispatcher_loop` and
    :func:`inapp_reaper.reaper_loop` discipline.
    """
    pool = state.db
    redis_client = state.redis
    while not stop_event.is_set():
        try:
            published_n = await _pump_once(pool, redis_client)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("phase22c3.outbox.pump_unexpected")
            published_n = 0
        sleep_s = PUMP_TICK_S if published_n > 0 else PUMP_IDLE_TICK_S
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_s)
            return  # stop_event set during the wait — exit cleanly.
        except asyncio.TimeoutError:
            # Normal sleep completion — loop continues.
            pass


__all__ = [
    "ABANDON_AFTER",
    "PUMP_BATCH_LIMIT",
    "PUMP_IDLE_TICK_S",
    "PUMP_TICK_S",
    "_pump_once",
    "outbox_pump_loop",
]
