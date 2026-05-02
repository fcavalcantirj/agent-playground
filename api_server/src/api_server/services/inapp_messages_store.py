"""Phase 22c.3-04 — repository module for the ``inapp_messages`` table (D-27).

Every function takes ``conn: asyncpg.Connection`` (or ``pool``) and binds
parameters via ``$1, $2, ...`` placeholders — never f-string interpolation.
Cross-tenant isolation is enforced AT THE SQL LAYER: every query that
takes ``user_id`` includes ``WHERE user_id=$N`` even when the route layer
already validated ownership (defense-in-depth — mirrors
``run_store.fetch_agent_instance`` discipline at run_store.py:430-464).

The dispatcher (Plan 22c.3-05) consumes :func:`fetch_pending_for_dispatch`
+ :func:`mark_forwarded` + :func:`mark_done` + :func:`mark_failed`. The
reaper (Plan 22c.3-06) consumes :func:`fetch_stuck_forwarded` + the same
mark functions. Lifespan startup (Plan 22c.3-09) consumes
:func:`restart_sweep`. The HTTP routes (Plan 22c.3-08) consume
:func:`insert_pending` + :func:`fetch_history_for_agent` +
:func:`delete_history_for_agent_user`.

Status state machine (per D-27 CHECK constraint):

  pending --mark_forwarded--> forwarded --mark_done----> done
                                         --mark_failed--> failed
                                         --reaper-------> pending (re-queue)
                                                          OR failed (final)
  pending --restart_sweep---> pending      (no-op for pending; sweep targets forwarded only)
  forwarded --restart_sweep--> pending     (sweep on api-server restart, D-31)

The 9 functions below are the SOLE seam for state transitions — no
inlined SQL elsewhere in the codebase touches ``inapp_messages``. This
discipline is what enables multi-replica safety (Plan 22c.3-06 reaper +
Plan 22c.3-08 dispatcher both rely on ``FOR UPDATE SKIP LOCKED`` to avoid
double-processing) and what makes route handlers a thin wrapper around
this module.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


# ---------------------------------------------------------------------------
# Insert / fetch by id
# ---------------------------------------------------------------------------


async def insert_pending(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    user_id: UUID,
    content: str,
) -> UUID:
    """INSERT a new row with ``status='pending'`` and ``attempts=0``.

    Returns the row's UUID. ``status`` and ``attempts`` are populated by
    the column-level DEFAULTs in alembic 007 — we don't pass them
    explicitly so a future migration that changes the default can be
    rolled out without touching this function.

    The caller (Plan 22c.3-08 ``POST /v1/agents/:id/messages``) is
    responsible for asserting ``content != ""`` per D-41 BEFORE calling
    here; the store does NOT re-validate (single seam discipline + no
    duplicated invariants).
    """
    row = await conn.fetchrow(
        """
        INSERT INTO inapp_messages (agent_id, user_id, content)
        VALUES ($1, $2, $3)
        RETURNING id
        """,
        agent_id, user_id, content,
    )
    return row["id"]


async def fetch_by_id(
    conn: asyncpg.Connection,
    message_id: UUID,
    user_id: UUID,
) -> dict[str, Any] | None:
    """Return one row by id, filtered by ``user_id``.

    The ``user_id`` filter at the SQL layer is the project's
    defense-in-depth pattern (mirrors
    ``run_store.fetch_agent_instance``): even if a route forgets to
    pass the authenticated user, the query CANNOT leak a cross-user
    row. Returns a plain dict (not an asyncpg Record) so callers can
    unpack freely.
    """
    row = await conn.fetchrow(
        """
        SELECT id, agent_id, user_id, content, status, attempts,
               last_error, last_attempt_at, bot_response,
               created_at, completed_at
        FROM inapp_messages
        WHERE id=$1 AND user_id=$2
        """,
        message_id, user_id,
    )
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Dispatcher pump — FOR UPDATE OF m SKIP LOCKED + JOIN agent_containers
# ---------------------------------------------------------------------------


async def fetch_pending_for_dispatch(
    conn: asyncpg.Connection,
    limit: int,
) -> list[asyncpg.Record]:
    """SELECT FOR UPDATE OF m SKIP LOCKED — dispatcher's atomic pick.

    JOINs ``agent_containers`` so the dispatcher receives container_id +
    container_status + ready_at + stopped_at + recipe_name + channel_type
    + inapp_auth_token in ONE round-trip. The dispatcher (Plan 22c.3-05)
    is a pure consumer; the SQL contract lives here.

    The CALLER MUST be inside a transaction so the row-level lock taken
    by ``FOR UPDATE OF m`` survives until the subsequent
    ``mark_forwarded`` UPDATE commits — that pair-of-statements is what
    keeps two replicas from forwarding the same row twice.

    Note: this function returns rows REGARDLESS of container readiness —
    the readiness gate (``container_status='running' AND ready_at IS NOT NULL
    AND stopped_at IS NULL``) lives in the dispatcher per D-37 so a
    not-yet-ready container can be observed (and the dispatcher can
    decide whether to wait, mark failed with ``container_not_ready``, or
    leave pending for the next tick).
    """
    rows = await conn.fetch(
        """
        SELECT m.id, m.agent_id, m.user_id, m.content, m.attempts,
               c.id AS container_row_id, c.container_id, c.container_status,
               c.ready_at, c.stopped_at, c.recipe_name, c.channel_type,
               c.inapp_auth_token
        FROM inapp_messages m
        JOIN agent_containers c ON c.agent_instance_id = m.agent_id
        WHERE m.status = 'pending'
        ORDER BY m.created_at ASC
        FOR UPDATE OF m SKIP LOCKED
        LIMIT $1
        """,
        limit,
    )
    return list(rows)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def mark_forwarded(
    conn: asyncpg.Connection,
    message_ids: list[UUID],
) -> None:
    """Bulk transition ``pending → forwarded``; bumps ``attempts``.

    Empty input is a no-op (defensive guard: the dispatcher's
    ``fetch_pending_for_dispatch`` may legitimately return an empty
    list when the queue is drained, and we don't want a NULL-array
    UPDATE to round-trip in that case).
    """
    if not message_ids:
        return
    await conn.execute(
        """
        UPDATE inapp_messages
        SET status='forwarded',
            attempts=attempts+1,
            last_attempt_at=NOW()
        WHERE id = ANY($1::uuid[])
        """,
        message_ids,
    )


async def mark_done(
    conn: asyncpg.Connection,
    message_id: UUID,
    bot_response: str,
) -> None:
    """Transition ``forwarded → done``. Records the bot's reply.

    Per D-22 dumb-pipe: the api stores the bot's reply VERBATIM. No
    truncation, no length cap (matches D-41 inbound treatment).
    """
    await conn.execute(
        """
        UPDATE inapp_messages
        SET status='done',
            bot_response=$2,
            completed_at=NOW()
        WHERE id=$1
        """,
        message_id, bot_response,
    )


async def mark_failed(
    conn: asyncpg.Connection,
    message_id: UUID,
    reason: str,
) -> None:
    """Transition to ``failed``. Records the error reason in ``last_error``.

    The caller (dispatcher / reaper) is responsible for INSERTing the
    matching ``agent_events`` row (kind=inapp_outbound_failed) within
    the same transaction so the SSE outbox sees the failure event.
    """
    await conn.execute(
        """
        UPDATE inapp_messages
        SET status='failed',
            last_error=$2,
            completed_at=NOW()
        WHERE id=$1
        """,
        message_id, reason,
    )


# ---------------------------------------------------------------------------
# Reaper / restart sweeps
# ---------------------------------------------------------------------------


async def fetch_stuck_forwarded(
    conn: asyncpg.Connection,
    threshold_minutes: int,
    limit: int = 50,
) -> list[asyncpg.Record]:
    """Return rows with ``status='forwarded'`` AND ``last_attempt_at`` older
    than ``threshold_minutes`` (D-30).

    The reaper (Plan 22c.3-06) calls this every 15s. Default threshold
    is 11 minutes per D-40 (10min D-40 bot timeout + 1min slack so the
    reaper doesn't race a slow-but-still-running inference).

    Uses ``FOR UPDATE SKIP LOCKED`` so multiple api_server replicas can
    run reapers concurrently without re-processing the same row.
    """
    return list(await conn.fetch(
        """
        SELECT id, agent_id, user_id, attempts, last_attempt_at
        FROM inapp_messages
        WHERE status='forwarded'
          AND last_attempt_at < NOW() - make_interval(mins => $1)
        FOR UPDATE SKIP LOCKED
        LIMIT $2
        """,
        threshold_minutes, limit,
    ))


async def restart_sweep(
    conn: asyncpg.Connection,
    threshold_minutes: int = 15,
) -> int:
    """Lifespan startup sweep — D-31. Reset stale ``forwarded`` to ``pending``.

    Called once at api_server boot (Plan 22c.3-09 lifespan), BEFORE the
    dispatcher pump starts. Targets rows that were mid-forward when
    api_server crashed: they're stuck in ``forwarded`` but no live
    dispatcher will progress them. Setting them back to ``pending``
    lets the freshly-booted dispatcher resume.

    Returns the number of rows reset. Default threshold 15 minutes (per
    D-40 revision — looser than the reaper's 11min so a normal-flight
    inference that happened to be running across the restart isn't
    caught).

    asyncpg's ``conn.execute`` returns the command tag string
    ("UPDATE N"); the trailing integer is parsed off. Defensive
    fallback: if the tag is unexpectedly malformed, return 0 rather
    than raising — sweep is opportunistic.
    """
    res = await conn.execute(
        """
        UPDATE inapp_messages
        SET status='pending'
        WHERE status='forwarded'
          AND last_attempt_at < NOW() - make_interval(mins => $1)
        """,
        threshold_minutes,
    )
    try:
        return int(res.split()[-1])
    except (IndexError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# History (REST endpoints — Plan 22c.3-08)
# ---------------------------------------------------------------------------


async def fetch_history_for_agent(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    user_id: UUID,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """List a user's messages for an agent, most-recent first.

    The ``ORDER BY created_at DESC`` is intentional — this powers the
    future REST history endpoint (Plan 22c.3-08) which renders newest
    messages at the top. SSE replay queries from ``agent_events`` (not
    from this table) so the directionality choice here doesn't conflict
    with the SSE stream's ascending-seq order.
    """
    return list(await conn.fetch(
        """
        SELECT id, content, status, bot_response, created_at, completed_at,
               last_error, attempts
        FROM inapp_messages
        WHERE agent_id=$1 AND user_id=$2
        ORDER BY created_at DESC
        LIMIT $3
        """,
        agent_id, user_id, limit,
    ))


async def list_history_for_agent(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    limit: int,
) -> list[dict]:
    """Phase 23-03 (D-03 + D-04) — terminal-state chat history, oldest first.

    Returns rows with ``status IN ('done', 'failed')`` for the given agent
    ordered by ``created_at`` ASC, capped at ``limit``. In-flight rows
    (``pending``/``forwarded``) are EXCLUDED at the SQL layer per D-03 —
    in-flight chat is observed via the SSE stream, not the history snapshot.

    The caller (the GET /v1/agents/:id/messages handler) is responsible for:
      * clamping ``limit`` to ``[1, 1000]`` per D-04 (handler-level
        validation produces a 400 INVALID_REQUEST envelope when the
        client supplies < 1; values > 1000 are silently clamped);
      * filtering ownership via :func:`run_store.fetch_agent_instance`
        BEFORE calling here — defense-in-depth ownership lives at the
        agent_instances row level, not on inapp_messages.user_id (the
        handler proves the caller owns the agent_id, then trusts that
        every inapp_messages row pinned to that agent_id is fair game
        to surface; the inapp_messages.user_id column is preserved as
        a multi-tenant defense-in-depth tag for the WRITE path but is
        intentionally NOT filtered on here so future shared-agent
        designs need not refactor this seam).

    Returns rows shaped::

        [{id, content, status, bot_response, last_error, created_at}, ...]

    Returned as ``list[dict]`` (not asyncpg.Record) so the handler can
    iterate without coupling to driver-record semantics.
    """
    rows = await conn.fetch(
        """
        SELECT id, content, status, bot_response, last_error, created_at
        FROM inapp_messages
        WHERE agent_id = $1
          AND status IN ('done', 'failed')
        ORDER BY created_at ASC
        LIMIT $2
        """,
        agent_id, limit,
    )
    return [dict(r) for r in rows]


async def delete_history_for_agent_user(
    conn: asyncpg.Connection,
    *,
    agent_id: UUID,
    user_id: UUID,
) -> int:
    """Transactional delete for D-43.

    Returns the count. The caller (Plan 22c.3-08
    ``DELETE /v1/agents/:id/messages``) is expected to ALSO delete the
    matching ``agent_events`` rows (kind IN ``inapp_inbound`` /
    ``inapp_outbound`` / ``inapp_outbound_failed``) within the SAME
    transaction — this function does NOT cascade to events because
    ``agent_events`` is keyed by ``agent_container_id``, not
    ``agent_id``, so the join lives in the route handler.

    The ``agent_instances`` row stays put (D-44: deleting messages is
    a separate action from deleting the agent).
    """
    res = await conn.execute(
        """
        DELETE FROM inapp_messages
        WHERE agent_id=$1 AND user_id=$2
        """,
        agent_id, user_id,
    )
    try:
        return int(res.split()[-1])
    except (IndexError, ValueError):
        return 0
