"""Postgres-backed rate limiter — fixed window via advisory lock + upsert counter.

Implements RESEARCH.md Pattern 4: ``pg_advisory_xact_lock`` serializes the
increment per ``(subject, bucket)`` pair so concurrent requests cannot
over-count under the limit, and the counter row itself is an upsert keyed
on ``(subject, bucket, window_start)``. The window boundary is floored to
``window_s``-second boundaries in SQL so every request in the same window
lands on the same row deterministically (``EXTRACT(EPOCH) % window_s``).

Known tradeoff: fixed-window allows a 2x burst at the window boundary
(documented in CONTEXT.md §D-05 and RESEARCH.md §Pattern 4). True sliding
window would require per-request timestamps — write amplification not
worth the added fairness under the D-05 "not aggressive, fair-use"
posture. Revisit in Phase 22+ if needed.

``window_start`` GC is Plan 19-07's responsibility via a cron against
``idx_rate_limit_gc`` (``DELETE FROM rate_limit_counters WHERE
window_start < NOW() - INTERVAL '1 hour'``).
"""
from __future__ import annotations

import asyncpg


def _lock_key(subject: str, bucket: str) -> int:
    """Hash ``(subject, bucket)`` to a positive int64 for ``pg_advisory_xact_lock``.

    ``hash()`` returns a platform-dependent ``int`` that can be negative;
    ``& ((1 << 63) - 1)`` masks to a positive 63-bit int which fits in
    PostgreSQL's ``bigint`` signed range. Two distinct subject-bucket pairs
    can collide on the same lock key (low probability, 1-in-2^63), but
    the upsert itself is still correct under the worst case — collisions
    only serialize unrelated increments, they never over- or under-count.
    """
    combined = f"{subject}|{bucket}"
    return hash(combined) & ((1 << 63) - 1)


async def check_and_increment(
    conn: asyncpg.Connection,
    subject: str,
    bucket: str,
    limit: int,
    window_s: int,
) -> tuple[bool, int]:
    """Increment the fixed-window counter for ``(subject, bucket)``.

    Returns ``(allowed, retry_after_s)``. ``retry_after_s`` is 0 when
    ``allowed=True``; otherwise it is the number of whole seconds until
    the current window expires (minimum 1 so clients always see a
    non-zero ``Retry-After`` header).

    Callers MUST pass a pre-acquired connection — the function opens its
    own transaction on that connection so ``pg_advisory_xact_lock`` is
    released automatically on commit.
    """
    lock_key = _lock_key(subject, bucket)
    async with conn.transaction():
        # Advisory lock serializes concurrent increments for the same
        # (subject, bucket) pair — without it two concurrent requests
        # could both read count=9 and both write count=10, accepting 11
        # requests under a 10/min limit. Transaction-scoped lock auto-
        # releases on COMMIT.
        await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
        # Window-start formula: ``to_timestamp(floor(epoch / W) * W)`` floors
        # the current epoch to the nearest ``window_s``-second boundary. The
        # RESEARCH.md sketch used ``date_trunc('second', NOW()) - (epoch::bigint
        # % W) * 1s`` which MIS-COMPUTES when the fractional part of the epoch
        # is ≥ 0.5 — ``::bigint`` rounds-to-nearest (not floor), so it can
        # produce a window_start off by one second. Two consecutive requests
        # landing either side of the round-point land on DIFFERENT counter
        # rows and the 11th request gets count=1 instead of count=11 → SC-09
        # silently breaks. ``floor()`` plus ``to_timestamp()`` gives a single
        # deterministic boundary.
        row = await conn.fetchrow(
            """
            INSERT INTO rate_limit_counters (subject, bucket, window_start, count)
            VALUES (
                $1, $2,
                to_timestamp(floor(EXTRACT(EPOCH FROM NOW()) / $3) * $3),
                1
            )
            ON CONFLICT (subject, bucket, window_start)
            DO UPDATE SET count = rate_limit_counters.count + 1
            RETURNING count,
                      window_start,
                      GREATEST(
                          0,
                          EXTRACT(EPOCH FROM (NOW() - window_start))::int
                      ) AS age_s
            """,
            subject, bucket, window_s,
        )
        count: int = row["count"]
        age_s: int = row["age_s"]
        if count > limit:
            retry_after = max(1, window_s - age_s)
            return (False, retry_after)
        return (True, 0)
