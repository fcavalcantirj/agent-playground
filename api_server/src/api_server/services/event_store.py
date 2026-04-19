"""Phase 22b-02 — asyncpg repository for ``agent_events`` (D-16).

Three durable ops:

  - :func:`insert_agent_event` — single-row insert with per-agent
    advisory-lock seq allocation (D-16). Spike-05 proved 4-way concurrent
    writers on the SAME ``agent_container_id`` produce gap-free 1..N
    seqs with 0 ``UniqueViolationError`` and 0 ``DeadlockDetectedError``.
  - :func:`insert_agent_events_batch` — ``executemany`` under a SINGLE
    advisory lock per batch (D-12). Spike-04 measured a 12.4x speedup
    versus 100 sequential per-row inserts. The watcher pump consumes
    this for its 100-row / 100ms flush window.
  - :func:`fetch_events_after_seq` — read-side projection for the
    long-poll handler. The ``kinds`` filter is bound via
    ``kind = ANY($3::text[])`` — NEVER interpolated into the query
    string (V13 defense). The handler's V5 enum-validation in
    ``routes/agent_events.py`` is the app-layer gate; the parameter
    binding here is the defense-in-depth backstop.

Every query uses ``$1, $2, ...`` placeholders. No string interpolation,
no f-strings with user input. Per-kind payload validators in
``models/events.py`` (``ConfigDict(extra="forbid")``) are the
schema-level input hardening — D-06 leaks are rejected at parse time
BEFORE :func:`insert_agent_event` runs. The DB-layer CHECK constraint
on ``kind`` is the cheap last-resort guard.

Authorization (ownership / sysadmin bypass) is the CALLER's
responsibility — every function takes ``agent_container_id`` as a
parameter and assumes the route handler has already validated the
caller may read/write that container's events. See
``routes/agent_events.py`` (Plan 22b-05) for the auth seam.

Schema reference: ``api_server/alembic/versions/004_agent_events.py``.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


async def insert_agent_event(
    conn: asyncpg.Connection,
    agent_container_id: UUID,
    kind: str,
    payload: dict,
    correlation_id: str | None = None,
) -> int:
    """Allocate the next per-agent seq + INSERT one row. Returns the seq.

    Uses ``pg_advisory_xact_lock(hashtext($1::text))`` to serialize
    concurrent writers on the same ``agent_container_id`` (D-16). The
    lock + ``MAX(seq)+1`` + INSERT all happen inside a single
    transaction — the lock is released at COMMIT/ROLLBACK so a crashed
    writer never holds the lock past its connection lifetime.

    The composite UNIQUE on ``(agent_container_id, seq)`` is the DB-layer
    backstop: if a future API replica somehow bypasses the advisory lock
    (e.g. a different connection didn't pass through this function), the
    INSERT raises ``asyncpg.UniqueViolationError`` rather than producing
    a duplicate seq.

    Caller is responsible for validating ``kind`` against
    ``models.events.VALID_KINDS`` and ``payload`` against
    ``models.events.KIND_TO_PAYLOAD[kind]`` BEFORE calling — this
    function does not re-validate (cost minimization on the hot path).
    The CHECK constraint on ``kind`` is the cheap DB-layer last-resort.
    """
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))",
            str(agent_container_id),
        )
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq "
            "FROM agent_events WHERE agent_container_id = $1",
            agent_container_id,
        )
        next_seq = row["next_seq"]
        await conn.execute(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload, correlation_id) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            agent_container_id,
            next_seq,
            kind,
            json.dumps(payload),
            correlation_id,
        )
    return next_seq


async def insert_agent_events_batch(
    conn: asyncpg.Connection,
    agent_container_id: UUID,
    rows: list[tuple[str, dict, str | None]],
) -> list[int]:
    """Batched INSERT with ONE advisory lock per batch (D-12).

    ``rows`` is a list of ``(kind, payload_dict, correlation_id)``
    tuples. Returns the list of allocated seqs in the same order.

    Spike-04 measured 12.4x speedup vs 100 sequential per-row calls
    because:

      1. ONE advisory lock acquisition per batch (instead of N)
      2. ONE transaction commit per batch (instead of N)
      3. ``executemany`` reuses the prepared statement N times

    Empty batch is a no-op — returns ``[]`` without acquiring the lock
    (saves a wasted round-trip for the common "watcher woke up but the
    queue drained" case).

    The watcher pump caller (Plan 22b-03) bounds batch size to 100;
    larger batches risk OOM on payload JSON encoding (T-22b-02-04 —
    accepted: watcher is trusted, same process).
    """
    if not rows:
        return []
    async with conn.transaction():
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))",
            str(agent_container_id),
        )
        base = await conn.fetchval(
            "SELECT COALESCE(MAX(seq), 0) "
            "FROM agent_events WHERE agent_container_id = $1",
            agent_container_id,
        )
        values = [
            (
                agent_container_id,
                base + i + 1,
                kind,
                json.dumps(payload),
                cid,
            )
            for i, (kind, payload, cid) in enumerate(rows)
        ]
        await conn.executemany(
            "INSERT INTO agent_events "
            "(agent_container_id, seq, kind, payload, correlation_id) "
            "VALUES ($1, $2, $3, $4::jsonb, $5)",
            values,
        )
    return [base + i + 1 for i in range(len(rows))]


async def fetch_events_after_seq(
    conn: asyncpg.Connection,
    agent_container_id: UUID,
    since_seq: int,
    kinds: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return events with seq > since_seq, optionally filtered by kinds.

    V13 defense — ``kinds`` is bound via ``$3::text[]`` and matched with
    ``kind = ANY($3::text[])``. The query string NEVER contains the
    set's elements interpolated. asyncpg handles the array binding +
    unknown-kind values gracefully (returns ``[]`` rather than erroring).

    Returns a list of plain dicts (not asyncpg Records) so the route
    layer can build :class:`AgentEvent` instances directly via
    ``AgentEvent(**row)``. The JSONB ``payload`` column is automatically
    decoded by asyncpg into a Python dict.

    Ordering is ASC by seq — the long-poll handler streams events in
    write order so the client can advance ``since_seq`` to the last
    seq it saw.
    """
    if kinds:
        query = (
            "SELECT seq, kind, payload, correlation_id, ts "
            "FROM agent_events "
            "WHERE agent_container_id = $1 AND seq > $2 "
            "AND kind = ANY($3::text[]) "
            "ORDER BY seq ASC"
        )
        rows = await conn.fetch(
            query, agent_container_id, since_seq, list(kinds)
        )
    else:
        query = (
            "SELECT seq, kind, payload, correlation_id, ts "
            "FROM agent_events "
            "WHERE agent_container_id = $1 AND seq > $2 "
            "ORDER BY seq ASC"
        )
        rows = await conn.fetch(query, agent_container_id, since_seq)
    return [dict(r) for r in rows]


__all__ = [
    "insert_agent_event",
    "insert_agent_events_batch",
    "fetch_events_after_seq",
]
