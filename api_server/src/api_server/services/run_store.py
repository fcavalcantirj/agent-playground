"""asyncpg repository for ``runs`` + ``agent_instances`` tables.

Four functions, all parameterized. CRITICAL: every query uses ``$1, $2, ...``
placeholders. No string interpolation, no f-strings with user input. The
Pydantic validators in ``models/runs.RunRequest`` (``recipe_name`` pattern,
``model`` length cap) provide schema-level input hardening; the
parameterized queries here are the defense-in-depth layer (V13).

Schema reference: ``api_server/alembic/versions/001_baseline.py``.

- ``runs.id`` is ``TEXT`` (26-char ULID); ``runs.agent_instance_id`` is UUID FK.
- ``agent_instances`` has ``UNIQUE(user_id, recipe_name, model)`` — the upsert
  below relies on that exact constraint name for ``ON CONFLICT`` resolution.
- ``runs.created_at`` defaults to ``NOW()`` via the server; verdict columns
  stay NULL until ``write_verdict`` fires at the end of a run.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from ..constants import ANONYMOUS_USER_ID  # re-export so routes can use a single import site

__all__ = [
    "ANONYMOUS_USER_ID",
    "upsert_agent_instance",
    "insert_pending_run",
    "write_verdict",
    "fetch_run",
]


async def upsert_agent_instance(
    conn: asyncpg.Connection,
    user_id: UUID,
    recipe_name: str,
    model: str,
) -> UUID:
    """Atomic upsert on ``(user_id, recipe_name, model)`` + bump ``total_runs``.

    Returns the ``id`` of the row (newly inserted or updated). The same
    transaction increments ``total_runs`` so the happy path is a single
    round-trip (no SELECT-then-INSERT race).

    The ``ON CONFLICT`` target matches the unique constraint
    ``uq_agent_instances_user_recipe_model`` from the baseline migration.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model,
                                     last_run_at, total_runs)
        VALUES (gen_random_uuid(), $1, $2, $3, NOW(), 1)
        ON CONFLICT (user_id, recipe_name, model)
        DO UPDATE SET last_run_at = NOW(),
                      total_runs = agent_instances.total_runs + 1
        RETURNING id
        """,
        user_id,
        recipe_name,
        model,
    )
    return row["id"]


async def insert_pending_run(
    conn: asyncpg.Connection,
    run_id: str,
    agent_instance_id: UUID,
    prompt: str,
) -> None:
    """Insert a ``runs`` row with NULL verdict/category/etc.

    ``created_at`` is filled by the server default (``NOW()``); verdict
    columns stay NULL until ``write_verdict`` completes the row at the end
    of the run. This two-phase write is what lets ``/v1/runs`` release the
    DB connection across the long ``to_thread(run_cell)`` call (Pitfall 4)
    without losing the audit trail if the runner crashes.
    """
    await conn.execute(
        "INSERT INTO runs (id, agent_instance_id, prompt) VALUES ($1, $2, $3)",
        run_id,
        agent_instance_id,
        prompt,
    )


async def write_verdict(
    conn: asyncpg.Connection,
    run_id: str,
    details: dict[str, Any],
) -> None:
    """Complete a pending ``runs`` row with the runner's ``details`` dict.

    ``details`` is the dict half of ``run_cell``'s return tuple (same keys
    the route handler passes to ``RunResponse``). All fields are bound as
    parameters — no dict value ever reaches the query string.

    ``wall_time_s`` is bound as whatever numeric type ``details`` has
    (runner emits ``round(wall, 2)`` as a float); asyncpg coerces it into
    the ``NUMERIC`` column.
    """
    await conn.execute(
        """
        UPDATE runs
           SET verdict = $2,
               category = $3,
               detail = $4,
               exit_code = $5,
               wall_time_s = $6,
               filtered_payload = $7,
               stderr_tail = $8,
               completed_at = NOW()
         WHERE id = $1
        """,
        run_id,
        details.get("verdict"),
        details.get("category"),
        details.get("detail"),
        details.get("exit_code"),
        details.get("wall_time_s"),
        details.get("filtered_payload"),
        details.get("stderr_tail"),
    )


async def fetch_run(conn: asyncpg.Connection, run_id: str) -> dict[str, Any] | None:
    """Return a fully-joined ``runs`` + ``agent_instances`` row or ``None``.

    Joins so the GET response can expose ``recipe`` + ``model`` without a
    second round-trip. Returns a plain dict (not an asyncpg Record) so the
    route handler can unpack it straight into ``RunGetResponse(**row)``.

    ``wall_time_s`` is cast to ``float`` here because asyncpg returns
    ``decimal.Decimal`` for ``NUMERIC`` columns by default; Pydantic's
    ``float`` coercion would accept the Decimal but ``RunGetResponse``
    serializes cleaner with a native float.
    """
    row = await conn.fetchrow(
        """
        SELECT r.id AS run_id,
               r.agent_instance_id::text AS agent_instance_id,
               r.prompt,
               a.recipe_name AS recipe,
               a.model,
               r.verdict,
               r.category,
               r.detail,
               r.exit_code,
               r.wall_time_s,
               r.filtered_payload,
               r.stderr_tail,
               r.created_at,
               r.completed_at
          FROM runs r
          JOIN agent_instances a ON a.id = r.agent_instance_id
         WHERE r.id = $1
        """,
        run_id,
    )
    if row is None:
        return None
    d = dict(row)
    if d.get("wall_time_s") is not None:
        d["wall_time_s"] = float(d["wall_time_s"])
    return d
