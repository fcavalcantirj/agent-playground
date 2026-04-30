"""Phase 22c.3-06 — inapp_messages stuck-forwarded reaper.

Lifespan-managed asyncio task. Ticks every 15s; selects rows in
``status='forwarded'`` whose ``last_attempt_at`` is older than 11
minutes (D-30 + D-40 revision: 10min bot timeout + 1min slack). Per
D-40 (no auto-retry), every stuck row is transitioned DIRECTLY to
``status='failed'`` with ``last_error='reaper_timeout'``. The reaper
does NOT requeue; clients retry by sending a new message.

Why this exists: the api_server crashes between the dispatcher's
``mark_forwarded`` UPDATE and the bot HTTP call's resolution can
leave rows stuck in ``'forwarded'``. The lifespan-startup restart
sweep (D-31, 15-min threshold) catches MOST of these on boot, but
two cases still need a steady-state safety net:

  1. The api_server stayed up but a single dispatcher coroutine
     hung on a TCP-level non-timeout (e.g. a pathological keep-alive
     stall) and the per-bot 600s httpx timeout did not fire.
  2. The api_server restarted close to a crash: the restart sweep
     uses a 15-min threshold (per D-40 looser than the reaper's 11
     min so a normal-flight inference that happened to be running
     across the restart isn't caught) and may not have triggered
     for a very-recently-stuck row.

Multi-replica safety (D-32): ``fetch_stuck_forwarded`` issues
``FOR UPDATE SKIP LOCKED``, so two reaper ticks (or a reaper + a
dispatcher) can never pick the same row.

Outbox discipline (D-33): each failure transition writes an
``agent_events`` row kind=``inapp_outbound_failed``,
``error_type='reaper_timeout'`` with the column-default
``published=false`` IN THE SAME transaction as the
``mark_failed`` UPDATE — Plan 22c.3-07 outbox pump fans the row
out to Redis. The atomicity is what guarantees the outbox pump
never sees a ``status='failed'`` without its matching event, nor
the reverse.

The reaper consumes Plan 22c.3-04's ``inapp_messages_store`` API
verbatim — no inlined SQL on ``inapp_messages`` in this module.
This is the single-seam discipline that lets the reaper +
dispatcher + future replicas share the same state-machine
contract without drift.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from . import inapp_messages_store as ims
from .event_store import insert_agent_event


_log = logging.getLogger("api_server.inapp_reaper")


# ---------------------------------------------------------------------------
# Tunable constants — kept module-level so tests can monkey-patch them.
# ---------------------------------------------------------------------------

#: Tick interval for the reaper_loop. 15s is the D-30 specification —
#: a steady-state safety net does not need sub-second responsiveness.
REAPER_TICK_S = 15.0

#: Per-tick batch size. SKIP LOCKED ensures a second replica picks the
#: next 50 without overlap.
REAPER_BATCH_LIMIT = 50

#: Stuck threshold per D-40 revision: 10min dispatcher bot-timeout +
#: 1min slack. A row whose ``last_attempt_at`` is older than this
#: cannot still be a live in-flight inference.
STUCK_THRESHOLD_MINUTES = 11


# ---------------------------------------------------------------------------
# Per-tick sweep (the unit of work)
# ---------------------------------------------------------------------------


async def _sweep_once(state: Any) -> int:
    """Pick stuck rows + transition each to failed. Returns count.

    All work happens inside ONE acquired connection + ONE outer
    transaction so the ``FOR UPDATE SKIP LOCKED`` row-locks taken by
    ``fetch_stuck_forwarded`` survive across the per-row
    ``mark_failed`` + ``insert_agent_event`` writes — no parallel
    reaper / dispatcher can pick the same row mid-sweep.

    The agent_events INSERT requires the row's
    ``agent_container_id`` (FK to ``agent_containers.id``), but
    ``fetch_stuck_forwarded`` only returns ``inapp_messages`` columns.
    We re-query for the container by joining through ``agent_id`` and
    pick the most-recent (live, then most-recently created) container
    for that agent. If no container exists the row is still marked
    failed but no event is emitted — Plan 07 outbox + SSE consumers
    track agent_events and would otherwise see nothing.

    The 600s bot-call window is irrelevant inside the reaper — there
    is no httpx call. Holding the FOR UPDATE lock for the duration
    of N ``mark_failed`` + N agent_events INSERTs is fine because
    each is a fast PG round-trip.
    """
    pool = state.db
    async with pool.acquire() as conn:
        async with conn.transaction():
            stuck = await ims.fetch_stuck_forwarded(
                conn,
                threshold_minutes=STUCK_THRESHOLD_MINUTES,
                limit=REAPER_BATCH_LIMIT,
            )
            if not stuck:
                return 0
            captured_at = datetime.now(timezone.utc).isoformat()
            for row in stuck:
                container_row_id = await conn.fetchval(
                    """
                    SELECT id FROM agent_containers
                    WHERE agent_instance_id = $1
                    ORDER BY stopped_at DESC NULLS LAST,
                             created_at DESC
                    LIMIT 1
                    """,
                    row["agent_id"],
                )
                # Persist-before-action: mark_failed first so a crash
                # mid-sweep leaves the row in its terminal state. The
                # outbox event INSERT fires next so the SSE outbox sees
                # the failure (Plan 07 fan-out).
                await ims.mark_failed(conn, row["id"], "reaper_timeout")
                if container_row_id is None:
                    # No container row to attribute the event to — log +
                    # continue. This is a rare orphan case (an agent
                    # whose container row was deleted before its
                    # messages were swept); the user-facing inapp
                    # message is still terminal so a future POST will
                    # create a new pending row + a fresh container.
                    _log.warning(
                        "phase22c3.reaper.orphan_message_no_container",
                        extra={
                            "message_id": str(row["id"]),
                            "agent_id": str(row["agent_id"]),
                        },
                    )
                    continue
                payload = {
                    "error_type": "reaper_timeout",
                    "message": "reaper_timeout",
                    "retry_count": int(row["attempts"] or 0),
                    "captured_at": captured_at,
                }
                await insert_agent_event(
                    conn,
                    container_row_id,
                    "inapp_outbound_failed",
                    payload,
                    correlation_id=str(row["id"]),
                )
            return len(stuck)


# ---------------------------------------------------------------------------
# reaper_loop — the 15s tick (lifespan-managed)
# ---------------------------------------------------------------------------


async def reaper_loop(state: Any, stop_event: asyncio.Event) -> None:
    """Lifespan-managed reaper. Runs until ``stop_event`` is set.

    Plan 22c.3-09 lifespan creates this as an ``asyncio.Task`` and
    cancels it via ``stop_event.set()``. The loop:

    1. Calls :func:`_sweep_once` (one PG round-trip + per-stuck-row
       writes inside one tx; the entire pass is bounded).
    2. Sleeps for ``REAPER_TICK_S`` via ``asyncio.wait_for`` on the
       stop_event so the task wakes IMMEDIATELY when shutdown is
       signaled — never a full 15s lag at app teardown.

    Loop-level error handling: never let the loop die. Real
    underlying failures (DB outage) recur and produce a stream of
    error logs; ops can alert on that. Mirrors
    :func:`inapp_dispatcher.dispatcher_loop` discipline.
    """
    while not stop_event.is_set():
        try:
            await _sweep_once(state)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("phase22c3.reaper.sweep_failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=REAPER_TICK_S)
            return  # stop_event set during the wait — exit cleanly.
        except asyncio.TimeoutError:
            # Normal sleep completion — loop continues.
            pass


__all__ = [
    "REAPER_BATCH_LIMIT",
    "REAPER_TICK_S",
    "STUCK_THRESHOLD_MINUTES",
    "reaper_loop",
    "_sweep_once",
]
