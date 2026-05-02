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

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

__all__ = [
    "upsert_agent_instance",
    "list_agents",
    "insert_pending_run",
    "write_verdict",
    "fetch_run",
    # Phase 22-02: persistent-container audit CRUD.
    "insert_pending_agent_container",
    "write_agent_container_running",
    "mark_agent_container_stopped",
    "fetch_agent_container",
    "fetch_running_container_for_agent",
    # Phase 22-05: agent_instance lookup by (agent_id, user_id).
    "fetch_agent_instance",
]


async def upsert_agent_instance(
    conn: asyncpg.Connection,
    user_id: UUID,
    recipe_name: str,
    model: str,
    name: str,
    personality: str | None,
) -> UUID:
    """Atomic upsert on ``(user_id, name)`` + bump ``total_runs``.

    The unique key is the user-given agent name (migration 002). A user can
    own many agents that share the same recipe + model with different names
    and personas. Re-deploying with the same name is treated as "use my
    existing agent" — recipe / model / personality are preserved (the
    upsert leaves them untouched on conflict so a name collision can't
    silently mutate a deployed agent's config).
    """
    row = await conn.fetchrow(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model, name,
                                     personality, last_run_at, total_runs)
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, NOW(), 1)
        ON CONFLICT (user_id, name)
        DO UPDATE SET last_run_at = NOW(),
                      total_runs = agent_instances.total_runs + 1
        RETURNING id
        """,
        user_id,
        recipe_name,
        model,
        name,
        personality,
    )
    return row["id"]


async def list_agents(
    conn: asyncpg.Connection,
    user_id: UUID,
) -> list[dict[str, Any]]:
    """Return all agents owned by ``user_id``, newest first.

    Includes a derived ``last_verdict`` from the most recent linked run via
    ``LATERAL`` join — single round-trip even for users with many agents.

    Phase 23 plan 04 (D-10/D-11/D-27): two extra LATERAL joins surface the
    Mobile Dashboard's status dot + "last active …" subtitle in the same
    round-trip:

    - ``ac.container_status AS status`` — most recently spawned LIVE
      ``agent_containers`` row (``WHERE stopped_at IS NULL ORDER BY
      created_at DESC LIMIT 1``). NULL when the agent never started or
      every container is stopped (D-11). The partial unique index
      ``ix_agent_containers_agent_instance_running`` already guarantees
      at most one such row, but the extra ORDER BY + LIMIT 1 belt-and-
      braces against any historical state-machine drift.
    - ``last_activity = GREATEST(ai.last_run_at, MAX(im.created_at))`` —
      D-27's "last active" timestamp. PostgreSQL ``GREATEST`` ignores
      NULLs since 8.4, so the cold-account case (no runs + no messages)
      naturally falls out as NULL. The MAX() sub-select is wrapped in a
      LATERAL so ``inapp_messages`` is read at most once per outer row;
      no index on ``(agent_id, created_at)`` exists today
      (``ix_inapp_messages_agent_status`` is on ``(agent_id, status)``)
      but the per-agent scan is cheap at MVP volumes (RESEARCH §A3).
    """
    rows = await conn.fetch(
        """
        SELECT
            ai.id,
            ai.name,
            ai.recipe_name,
            ai.model,
            ai.personality,
            ai.created_at,
            ai.last_run_at,
            ai.total_runs,
            lr.verdict AS last_verdict,
            lr.category AS last_category,
            lr.run_id AS last_run_id,
            ac.container_status AS status,
            GREATEST(ai.last_run_at, im.last_msg_at) AS last_activity
        FROM agent_instances ai
        LEFT JOIN LATERAL (
            SELECT id AS run_id, verdict, category
            FROM runs
            WHERE agent_instance_id = ai.id
            ORDER BY created_at DESC
            LIMIT 1
        ) lr ON TRUE
        LEFT JOIN LATERAL (
            SELECT container_status
            FROM agent_containers
            WHERE agent_instance_id = ai.id
              AND stopped_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
        ) ac ON TRUE
        LEFT JOIN LATERAL (
            SELECT MAX(created_at) AS last_msg_at
            FROM inapp_messages
            WHERE agent_id = ai.id
        ) im ON TRUE
        WHERE ai.user_id = $1
        ORDER BY ai.created_at DESC
        """,
        user_id,
    )
    return [dict(r) for r in rows]


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


# ---------------------------------------------------------------------------
# Phase 22-02: agent_containers CRUD
# ---------------------------------------------------------------------------
#
# Schema reference: ``api_server/alembic/versions/003_agent_containers.py``.
#
# These helpers back Plan 22-05's ``POST /v1/agents/:id/start`` +
# ``/stop`` + ``GET /status`` flow. Two-phase insert mirrors the
# ``insert_pending_run`` + ``write_verdict`` shape so routes can release
# their DB connection across the long ``execute_persistent_start`` await
# (Pitfall 4 — DB pool exhaustion if conn held across a blocking run).
#
# The partial unique index
# ``ix_agent_containers_agent_instance_running`` (WHERE
# ``container_status='running'``) enforces at-most-one running
# container per agent. Concurrent /start calls race on the UPDATE-to-
# running step in ``write_agent_container_running``; the losing side
# raises ``asyncpg.UniqueViolationError`` which the route maps to
# 409 AGENT_ALREADY_RUNNING.


async def insert_pending_agent_container(
    conn: asyncpg.Connection,
    agent_instance_id: UUID,
    user_id: UUID,
    recipe_name: str,
    channel_type: str,
    channel_config_enc: bytes,
) -> UUID:
    """Insert a pending agent_containers row with status='starting'.

    Returns the newly-minted container row id. Encrypted channel config
    (see ``crypto/age_cipher.py``) is written straight into the BYTEA
    column; decrypt only happens at container-spawn time in the route
    layer, and the plaintext is discarded immediately after the
    ``--env-file`` has been written.

    Partial unique index enforcement happens AT THE WRITE-TO-RUNNING
    step, not here — a row in 'starting' state is fine alongside
    another agent's running row. The route serializes by attempting
    the UPDATE-to-'running' and treating UniqueViolation as 409.
    """
    row = await conn.fetchrow(
        """
        INSERT INTO agent_containers
            (id, agent_instance_id, user_id, recipe_name, deploy_mode,
             container_status, channel_type, channel_config_enc)
        VALUES (gen_random_uuid(), $1, $2, $3, 'persistent',
                'starting', $4, $5)
        RETURNING id
        """,
        agent_instance_id,
        user_id,
        recipe_name,
        channel_type,
        channel_config_enc,
    )
    return row["id"]


async def write_agent_container_running(
    conn: asyncpg.Connection,
    container_row_id: UUID,
    *,
    container_id: str,
    boot_wall_s: float,
    ready_at: datetime,
    inapp_auth_token: str | None = None,
) -> None:
    """Flip a pending container row 'starting' -> 'running'.

    Called from the route handler AFTER ``execute_persistent_start``
    returns the docker container id + ready_at. The WHERE clause
    constrains to rows currently in 'starting' so a concurrent /stop
    cannot mark a row running out from under itself.

    The partial unique index on (agent_instance_id) WHERE status='running'
    fires here when another container for the SAME agent_instance is
    already running — asyncpg raises ``UniqueViolationError`` which the
    route maps to 409 AGENT_ALREADY_RUNNING. The caller is expected to
    rollback via ``mark_agent_container_stopped(..., last_error=...)``.

    Phase 22c.3.1 (D-33, AC-13): ``inapp_auth_token`` is folded into the
    SAME UPDATE — closes the microsecond race window where a chat POST
    arriving between the running-UPDATE and a separate token-UPDATE
    would dispatch unauthenticated. Backwards-compat: telegram callers
    omit the kwarg (or pass None) — the column default is NULL.
    """
    await conn.execute(
        """
        UPDATE agent_containers
           SET container_id = $2,
               container_status = 'running',
               boot_wall_s = $3,
               ready_at = $4,
               inapp_auth_token = $5
         WHERE id = $1
           AND container_status = 'starting'
        """,
        container_row_id,
        container_id,
        boot_wall_s,
        ready_at,
        inapp_auth_token,
    )


async def mark_agent_container_stopped(
    conn: asyncpg.Connection,
    container_row_id: UUID,
    *,
    last_error: str | None = None,
) -> None:
    """Terminal-state transition. Writes stopped_at=NOW() plus status.

    When ``last_error`` is None (happy-path /stop) the row flips to
    'stopped'. When ``last_error`` is a (redacted) string the row
    flips to 'start_failed' — callers use this from the /start error
    path to record a durable failure trace for /status and ops review.

    Caller is responsible for redacting secrets from ``last_error``
    BEFORE calling (the runner's ``_redact_api_key`` helper handles
    the two places — VAR= form and bare value). This function does
    NOT redact; it only persists.

    Phase 22c.3.1 (D-29): also clears ``inapp_auth_token`` to NULL on
    every stop — the token has no audit value beyond the running window
    and the dispatcher gates on container_status='running' anyway.
    Honors D-09's "cleared by mark_stopped" semantics.
    """
    new_status = "start_failed" if last_error else "stopped"
    await conn.execute(
        """
        UPDATE agent_containers
           SET container_status = $2,
               stopped_at = NOW(),
               last_error = $3,
               inapp_auth_token = NULL
         WHERE id = $1
        """,
        container_row_id,
        new_status,
        last_error,
    )


async def fetch_agent_container(
    conn: asyncpg.Connection,
    container_row_id: UUID,
) -> dict[str, Any] | None:
    """Read a single agent_containers row by PK. Returns dict or None.

    UUID columns cast to text for easy JSON serialization in the route
    layer; NUMERIC ``boot_wall_s`` cast to float (asyncpg returns
    ``decimal.Decimal`` otherwise). ``channel_config_enc`` stays as
    raw bytes — decrypt is a route-layer responsibility and the CRUD
    never touches the plaintext.
    """
    row = await conn.fetchrow(
        """
        SELECT id::text AS id,
               agent_instance_id::text AS agent_instance_id,
               user_id::text AS user_id,
               recipe_name,
               deploy_mode,
               container_id,
               container_status,
               channel_type,
               channel_config_enc,
               boot_wall_s,
               ready_at,
               created_at,
               stopped_at,
               last_error
          FROM agent_containers
         WHERE id = $1
        """,
        container_row_id,
    )
    if row is None:
        return None
    d = dict(row)
    if d.get("boot_wall_s") is not None:
        d["boot_wall_s"] = float(d["boot_wall_s"])
    return d


async def fetch_running_container_for_agent(
    conn: asyncpg.Connection,
    agent_instance_id: UUID,
) -> dict[str, Any] | None:
    """Find the currently-running container for an agent, or None.

    The partial unique index guarantees at most one such row exists;
    LIMIT 1 is belt-and-braces so a corrupted-state DB can't return
    multiple rows. Used by /stop and /status routes.
    """
    row = await conn.fetchrow(
        """
        SELECT id::text AS id,
               agent_instance_id::text AS agent_instance_id,
               user_id::text AS user_id,
               recipe_name,
               container_id,
               container_status,
               channel_type,
               channel_config_enc,
               boot_wall_s,
               ready_at,
               created_at
          FROM agent_containers
         WHERE agent_instance_id = $1
           AND container_status = 'running'
         LIMIT 1
        """,
        agent_instance_id,
    )
    if row is None:
        return None
    d = dict(row)
    if d.get("boot_wall_s") is not None:
        d["boot_wall_s"] = float(d["boot_wall_s"])
    return d


async def fetch_agent_instance(
    conn: asyncpg.Connection,
    agent_id: UUID,
    user_id: UUID,
) -> dict[str, Any] | None:
    """Return the ``agent_instances`` row for ``(agent_id, user_id)`` or None.

    The ``user_id`` parameter is the multi-tenancy seam: the route layer
    resolves it via ``require_user`` (plan 22c-05) from the authenticated
    session cookie. Defense in depth: even if the route forgets to pass
    the correct user_id, the query can't leak cross-user rows because
    ``user_id`` is always in the WHERE clause.

    Returns a plain dict (not an asyncpg Record) so route handlers can
    unpack it freely. UUID ``id`` is cast to text for easy JSON
    serialization in any downstream response model.
    """
    row = await conn.fetchrow(
        """
        SELECT id::text AS id,
               name,
               recipe_name,
               model,
               personality,
               created_at,
               last_run_at,
               total_runs
          FROM agent_instances
         WHERE id = $1
           AND user_id = $2
        """,
        agent_id,
        user_id,
    )
    return dict(row) if row else None
