"""Phase 27 — read-side queries over usage_logs (server-side aggregation).

Counterpart to ``usage_recorder.py`` (the write side). All aggregation
happens HERE in SQL, never in client code (CLAUDE.md golden rule #2 +
D-13). The route handlers in ``routes/usage.py`` are thin shims that
project these query results into Pydantic response models.

5 queries across 2 endpoints:

  GET /v1/usage/summary
    Q1a — user_total: SUM(cost_usd) + COUNT(*) for the user
    Q1b — by_agent:    per-agent breakdown (JOIN agent_instances) ordered DESC

  GET /v1/agents/:id/usage
    Q2a — agent_cumulative: SUM tokens + cost + count + max(created_at)
    Q2b — series_7d:        DATE-bucketed last 7 days
    Q2c — series_30d:       DATE-bucketed last 30 days

NUMERIC(14,8) / `Decimal` precision is preserved end-to-end. Routes
convert to JSON-string at the response-serialization boundary so float
coercion never enters the path.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg


# ---------------------------------------------------------------------------
# /v1/usage/summary
# ---------------------------------------------------------------------------


async def fetch_user_total(
    conn: asyncpg.Connection, user_id: UUID
) -> tuple[Decimal, int]:
    """Q1a — total USD + message count for a user. Index-only scan.

    Returns ``(total_usd, message_count)``. Empty state → ``(Decimal('0'), 0)``.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(cost_usd), 0::NUMERIC(14, 8)) AS total_usd,
               COUNT(*) AS message_count
        FROM usage_logs
        WHERE user_id = $1
        """,
        user_id,
    )
    # COALESCE guarantees row[0] is non-NULL; COUNT is always non-NULL.
    return row["total_usd"], row["message_count"]


async def fetch_user_by_agent(
    conn: asyncpg.Connection, user_id: UUID
) -> list[dict[str, Any]]:
    """Q1b — per-agent breakdown for a user. ORDER BY cost DESC.

    Joins ``agent_instances`` to surface display name + recipe + model.
    Empty state → ``[]``.
    """
    rows = await conn.fetch(
        """
        SELECT ul.agent_instance_id AS agent_id,
               ai.name AS agent_name,
               ai.recipe_name,
               ai.model,
               COALESCE(SUM(ul.cost_usd), 0::NUMERIC(14, 8)) AS cost_usd,
               COUNT(*) AS message_count,
               MAX(ul.created_at) AS last_activity
        FROM usage_logs ul
        JOIN agent_instances ai ON ai.id = ul.agent_instance_id
        WHERE ul.user_id = $1
        GROUP BY ul.agent_instance_id, ai.name, ai.recipe_name, ai.model
        ORDER BY SUM(ul.cost_usd) DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# /v1/agents/:id/usage
# ---------------------------------------------------------------------------


async def fetch_agent_cumulative(
    conn: asyncpg.Connection, agent_instance_id: UUID
) -> dict[str, Any]:
    """Q2a — cumulative aggregates for a single agent.

    Empty state → all token counts and message_count = 0,
    cost_usd = ``Decimal('0')``, last_activity = ``None``.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(input_tokens), 0)         AS input_tokens,
               COALESCE(SUM(output_tokens), 0)        AS output_tokens,
               COALESCE(SUM(cache_read_tokens), 0)    AS cache_read_tokens,
               COALESCE(SUM(cache_creation_tokens), 0) AS cache_creation_tokens,
               COALESCE(SUM(cost_usd), 0::NUMERIC(14, 8)) AS cost_usd,
               COUNT(*) AS message_count,
               MAX(created_at) AS last_activity
        FROM usage_logs
        WHERE agent_instance_id = $1
        """,
        agent_instance_id,
    )
    return dict(row)


async def fetch_agent_series(
    conn: asyncpg.Connection,
    agent_instance_id: UUID,
    *,
    days: int,
) -> list[dict[str, Any]]:
    """Q2b/Q2c — per-day series for the last N days.

    Days with zero rows are OMITTED (no server-side zero-fill — D-15).
    Each row: ``{day: date, cost_usd: Decimal, tokens: int, message_count: int}``.

    ``days`` is interpolated into the SQL as a literal because asyncpg's
    ``$N`` placeholders cannot parameterize an INTERVAL literal. The value
    is only ever called with internal integer constants (7 / 30) — no
    user-supplied input reaches this path.
    """
    if days not in (7, 30):
        # Defensive: callers are limited to 7/30 for v1; widen explicitly
        # if a future endpoint adds more windows.
        raise ValueError(f"days must be 7 or 30, got {days}")

    rows = await conn.fetch(
        f"""
        SELECT DATE(created_at AT TIME ZONE 'UTC') AS day,
               COALESCE(SUM(cost_usd), 0::NUMERIC(14, 8)) AS cost_usd,
               COALESCE(
                 SUM(input_tokens + output_tokens
                     + cache_read_tokens + cache_creation_tokens),
                 0
               ) AS tokens,
               COUNT(*) AS message_count
        FROM usage_logs
        WHERE agent_instance_id = $1
          AND created_at >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE(created_at AT TIME ZONE 'UTC')
        ORDER BY day DESC
        """,
        agent_instance_id,
    )
    return [dict(r) for r in rows]


__all__ = [
    "fetch_user_total",
    "fetch_user_by_agent",
    "fetch_agent_cumulative",
    "fetch_agent_series",
]
