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
"""
from __future__ import annotations

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
