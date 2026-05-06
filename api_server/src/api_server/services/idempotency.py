"""Postgres-backed Stripe-style idempotency.

Implements RESEARCH.md Pattern 3: ``pg_advisory_xact_lock`` serializes
concurrent first-use of the same ``(user_id, key)`` so the N-th concurrent
request with a cache miss doesn't fire N runs. The ``request_body_hash``
column (RESEARCH.md Pitfall 6) rejects re-use of the same key with a
different body — the canonical Stripe semantic for preventing silent
replay of a stale response for a payload the caller never actually sent.

Scope:

- ``check_or_reserve`` checks the cache under advisory lock and returns
  one of ``"hit"`` / ``"mismatch"`` / ``"miss"``. The middleware uses the
  tag to decide between replaying the cached verdict, returning 422, or
  running normally.
- ``write_idempotency`` inserts the cache row AFTER the run completes.
  ``ON CONFLICT (user_id, key) DO NOTHING`` makes this safe under the
  rare race where two concurrent misses both write — the first wins.
- ``hash_body`` is the canonical body-hash used by the middleware. Raw
  request bytes (NOT re-serialized JSON) — avoids semantically-equivalent
  but byte-different payloads accidentally triggering mismatch.

24h TTL default matches CONTEXT.md §D-01. GC is Plan 19-07's
responsibility via a cron against ``idx_idempotency_expires``.

AMD-03 reserved-row extension (Phase 29):

The Phase 29 LLM proxy needs idempotent retries against a multi-second
upstream call. The existing ``check_or_reserve`` primitive returns
``"miss"`` until the FIRST request finishes and writes its row — under
concurrent retries 50ms apart, BOTH callers see ``"miss"`` and BOTH
forward to upstream → double charge. PROBE-VAL-06 reproduced this gap
empirically.

The reserved-row pattern closes the gap: the FIRST caller inserts a
placeholder row with ``status='in_flight'`` and ``verdict_json=NULL``
(via ``insert_reserved_row``) BEFORE forwarding upstream. The SECOND
concurrent caller sees ``ON CONFLICT DO NOTHING`` and falls through
to ``poll_for_completion``, waiting for the first caller to flip the
row to ``status='success'`` (via ``finalize_reserved_row``) and then
replaying the cached verdict.

Migration 013 added the ``status`` text column + relaxed
``verdict_json`` to NULLABLE on ``idempotency_keys`` to support this
pattern. The legacy ``check_or_reserve`` / ``write_idempotency`` pair
is unchanged — chat-path callers continue to work.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Literal
from uuid import UUID

import asyncpg

# Tag returned by :func:`check_or_reserve` to indicate the caller's next
# step. ``hit`` → return cached verdict; ``mismatch`` → 422 IDEMPOTENCY_BODY_MISMATCH;
# ``miss`` → run the endpoint then call :func:`write_idempotency`.
CheckResult = tuple[Literal["hit", "miss", "mismatch"], dict | None]


def hash_body(raw_bytes: bytes) -> str:
    """SHA-256 hex digest of the raw request body bytes.

    Using the raw bytes (not JSON-normalized) matches Stripe's semantic —
    two byte-different payloads that happen to deserialize equivalently
    are still different requests from the client's perspective.
    """
    return hashlib.sha256(raw_bytes).hexdigest()


def _lock_key(user_id: UUID, key: str) -> int:
    """Derive a signed int64 advisory lock key from ``(user_id, key)``.

    Uses SHA-256 because Python's ``hash()`` is randomized per process
    by default (``PYTHONHASHSEED``) and would yield different lock keys
    across app workers — two workers must agree on the lock key so the
    advisory lock actually serializes across processes.
    """
    digest = hashlib.sha256(f"{user_id}:{key}".encode()).digest()[:8]
    return int.from_bytes(digest, "big", signed=True)


async def check_or_reserve(
    conn: asyncpg.Connection,
    user_id: UUID,
    key: str,
    body_hash: str,
) -> CheckResult:
    """Look up ``(user_id, key)`` under advisory lock.

    Three outcomes:

    - ``("hit", cached_verdict_dict)`` — a non-expired row exists and its
      ``request_body_hash`` matches. Caller must return the cached verdict
      verbatim with HTTP 200.
    - ``("mismatch", None)`` — a non-expired row exists but its hash does
      NOT match. Caller MUST return 422 IDEMPOTENCY_BODY_MISMATCH.
    - ``("miss", None)`` — no non-expired row. Caller runs normally and
      MUST call :func:`write_idempotency` after the run.

    ``user_id`` is always part of the lookup predicate (cross-user isolation
    per T-19-05-02) and part of the lock key (concurrent collision between
    two users is impossible by construction).
    """
    lock_key = _lock_key(user_id, key)
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
        row = await conn.fetchrow(
            """
            SELECT run_id, verdict_json, request_body_hash
              FROM idempotency_keys
             WHERE user_id = $1
               AND key = $2
               AND expires_at > NOW()
            """,
            user_id, key,
        )
        if row is None:
            return ("miss", None)
        if row["request_body_hash"] != body_hash:
            return ("mismatch", None)
        cached = row["verdict_json"]
        # asyncpg decodes JSONB to either a dict or a JSON string depending
        # on the codec registered for the pool. Normalize here so callers
        # can always expect a dict — middleware serializes it as JSON once.
        if isinstance(cached, (str, bytes, bytearray)):
            cached = json.loads(cached)
        return ("hit", cached)


async def write_idempotency(
    conn: asyncpg.Connection,
    user_id: UUID,
    key: str,
    body_hash: str,
    run_id: str,
    verdict_json: dict,
    ttl_hours: int = 24,
) -> None:
    """Insert the idempotency cache row after a successful run.

    ``ON CONFLICT (user_id, key) DO NOTHING`` handles the race where two
    concurrent misses both finish and both try to write — the first wins,
    the second is a no-op. 24-hour default TTL matches Stripe's behavior
    and CONTEXT.md §D-01.

    ``verdict_json`` is JSON-dumped here (rather than let asyncpg handle
    jsonb encoding) so the ``::jsonb`` cast in the SQL stays explicit —
    keeps the schema's ``verdict_json JSONB`` column type enforced at
    the call site rather than relying on codec configuration.
    """
    await conn.execute(
        """
        INSERT INTO idempotency_keys
            (id, user_id, key, run_id, verdict_json,
             request_body_hash, expires_at)
        VALUES
            (gen_random_uuid(), $1, $2, $3, $4::jsonb, $5,
             NOW() + ($6 || ' hours')::interval)
        ON CONFLICT (user_id, key) DO NOTHING
        """,
        user_id, key, run_id, json.dumps(verdict_json),
        body_hash, str(ttl_hours),
    )


# ---------------------------------------------------------------------------
# AMD-03 reserved-row primitive (Phase 29 — closes the in-flight gap)
# ---------------------------------------------------------------------------


async def insert_reserved_row(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    key: str,
    request_body_hash: str,
    ttl_seconds: int = 86400,
) -> bool:
    """Insert a placeholder ``status='in_flight'`` row.

    Returns ``True`` if WE inserted the row (we own the in-flight slot
    and must call :func:`finalize_reserved_row` after the upstream call
    completes), or ``False`` if a row already existed for
    ``(user_id, key)`` (another caller is in-flight; poll for completion
    via :func:`poll_for_completion`).

    The ``ON CONFLICT (user_id, key) DO NOTHING`` semantics make this
    the single race-resolution point: concurrent callers serialize on
    the unique constraint and exactly one wins the in-flight slot.

    AMD-03 — closes the in-flight gap PROBE-VAL-06 reproduced. Migration
    013 added the ``status`` column + relaxed ``verdict_json`` to
    NULLABLE so this row can be inserted BEFORE the upstream returns.
    """
    result = await conn.execute(
        """
        INSERT INTO idempotency_keys (
            id, user_id, key, request_body_hash,
            verdict_json, status, expires_at, run_id
        ) VALUES (
            gen_random_uuid(), $1, $2, $3,
            NULL, 'in_flight',
            NOW() + ($4 || ' seconds')::interval,
            NULL
        )
        ON CONFLICT (user_id, key) DO NOTHING
        """,
        user_id, key, request_body_hash, str(ttl_seconds),
    )
    # asyncpg returns 'INSERT 0 1' on insert, 'INSERT 0 0' on conflict-skip.
    return result.endswith(" 1")


async def poll_for_completion(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    key: str,
    max_wait_s: float = 5.0,
    poll_interval_s: float = 0.1,
) -> dict | None:
    """Wait for a reserved row to flip to ``status='success'``.

    Returns the cached ``verdict_json`` dict on success, or ``None`` on
    timeout / ``status='failed'`` / row missing. The caller treats
    ``None`` as "fall through to a fresh upstream attempt" — which is
    safe because the failed/timed-out row is already terminal in this
    iteration; the original caller has either crashed or surfaced the
    error to the user.

    Polls every ``poll_interval_s`` (default 100ms) up to ``max_wait_s``
    (default 5s) — the same window PROBE-VAL-06 demonstrated single-
    charges under a 3s simulated upstream.
    """
    deadline = asyncio.get_event_loop().time() + max_wait_s
    while True:
        row = await conn.fetchrow(
            """
            SELECT status, verdict_json
            FROM idempotency_keys
            WHERE user_id = $1 AND key = $2
            """,
            user_id, key,
        )
        if row is None:
            return None
        status = row["status"]
        if status == "success":
            cached = row["verdict_json"]
            # Mirror check_or_reserve's JSON normalization — asyncpg
            # decodes JSONB to either a dict or a JSON string depending
            # on the codec registered for the pool.
            if isinstance(cached, (str, bytes, bytearray)):
                cached = json.loads(cached)
            return cached
        if status == "failed":
            return None
        if asyncio.get_event_loop().time() >= deadline:
            return None
        await asyncio.sleep(poll_interval_s)


async def finalize_reserved_row(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    key: str,
    verdict_json: dict,
    status: str = "success",
) -> None:
    """Update an in-flight row to its terminal status + verdict.

    Called by the original caller AFTER the upstream call resolves.
    ``status`` must be ``'success'`` or ``'failed'`` — the check
    constraint added in migration 013 enforces this at the DB layer
    too, but failing fast in Python gives a clearer error than a
    constraint violation.

    ``verdict_json`` is JSON-dumped here so the ``::jsonb`` cast in the
    SQL stays explicit (mirrors :func:`write_idempotency`'s pattern —
    schema's JSONB column type is enforced at the call site, not via
    asyncpg codec configuration).
    """
    if status not in ("success", "failed"):
        raise ValueError(
            f"finalize status must be 'success' or 'failed', got {status!r}"
        )
    await conn.execute(
        """
        UPDATE idempotency_keys
        SET status = $3, verdict_json = $4::jsonb
        WHERE user_id = $1 AND key = $2
        """,
        user_id, key, status, json.dumps(verdict_json),
    )
