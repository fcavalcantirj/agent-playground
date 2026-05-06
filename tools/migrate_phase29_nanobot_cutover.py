#!/usr/bin/env python3
"""Phase 29 cutover — wipe live nanobot containers + transition rows to stopped.

Purpose
-------

Phase 29 (Plans 29-04 / 29-05 / 29-08) flipped the nanobot recipe to
``runtime.via_proxy: true``. After the api_server image rolls with the
new code, any *pre-cutover* nanobot containers are still running with
the **old** env shape (``OPENAI_BASE_URL`` pointing directly at
``openrouter.ai`` + the user's BYOK key baked into the bot's env). Those
rows ALSO have ``agent_containers.provider_key_enc IS NULL`` because
they were deployed before the proxy custody column existed.

Leaving them running is harmless to billing (their LLM calls still hit
OpenRouter directly with the user's own key) but they will NOT route
through the proxy — meaning their next chat round-trip will NOT be
captured in ``usage_logs`` via the new path. They are also incompatible
with the proxy-cache rehydrate at lifespan startup (no encrypted blob
to decrypt).

This script:

    1. Selects ``agent_containers WHERE recipe_name = 'nanobot' AND
       container_status IN ('running', 'starting')`` — per AMD-01 the
       canonical recipe name is **nanobot** (a historical CONTEXT-D-04
       misnomer used a different label; AMD-01 fixed the naming).
    2. For each row:
       a) Calls ``docker stop`` against the row's ``container_id`` with a
          10s timeout. ``docker.errors.NotFound`` is logged and tolerated
          (orphan reconciliation — the container is already gone).
       b) Updates the row to ``container_status = 'stopped'``,
          ``stopped_at = NOW()``, ``last_error = 'phase29_cutover_swept'``.
    3. Prints a summary line for the audit trail.

The mobile + web "deploy" UX is unchanged — users redeploy with one tap
and the new nanobot agent goes through the proxy from boot.

Idempotency
-----------

Re-running a successful cutover is a no-op (the WHERE clause matches
zero rows once the rows are transitioned to ``stopped``). Safe to re-run.

Usage
-----

::

    DATABASE_URL=postgresql://... python tools/migrate_phase29_nanobot_cutover.py
    DATABASE_URL=postgresql://... python tools/migrate_phase29_nanobot_cutover.py --dry-run
    DATABASE_URL=postgresql://... python tools/migrate_phase29_nanobot_cutover.py --limit 5

Canonical post-Phase-29-deploy invocation::

    docker exec deploy-api_server-1 \\
        python /app/tools/migrate_phase29_nanobot_cutover.py --dry-run
    docker exec deploy-api_server-1 \\
        python /app/tools/migrate_phase29_nanobot_cutover.py

Safety cap (--limit, default 10000)
-----------------------------------

Phase 29 cutover is not expected to find more than single-digit live
nanobot containers on a dev box. If the count blows past the cap that's
a signal to stop and inspect the DB before mutating en masse.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

import asyncpg


log = logging.getLogger("phase29.cutover")


# Per AMD-01: the recipe name in agent_containers is `nanobot`
# (historical CONTEXT-D-04 used a different label; AMD-01 corrected
# the naming). The grep gate in 29-09-PLAN.md acceptance_criteria
# enforces that the historical-misnomer string never appears here.
DRY_RUN_SQL = """
SELECT id, user_id, agent_instance_id, container_id, container_status, recipe_name
FROM agent_containers
WHERE recipe_name = 'nanobot'
  AND container_status IN ('running', 'starting')
ORDER BY created_at ASC
"""


COUNT_SQL = """
SELECT COUNT(*) FROM agent_containers
WHERE recipe_name = 'nanobot'
  AND container_status IN ('running', 'starting')
"""


# Per-row UPDATE: transactional, returns nothing — we already have the
# id from the SELECT pass and orchestrate per-row via a Python loop so
# the docker-stop side-effect can sit between SELECT and UPDATE.
UPDATE_SQL = """
UPDATE agent_containers
SET container_status = 'stopped',
    stopped_at = NOW(),
    last_error = 'phase29_cutover_swept'
WHERE id = $1
"""


def _build_docker_client() -> Any:
    """Return a docker SDK client. Imported lazily so unit tests that
    monkeypatch this module can swap a fake before main() runs."""
    import docker  # noqa: WPS433  — lazy by design (test mockability)

    return docker.from_env()


def _docker_not_found_class() -> type[BaseException]:
    """Return the ``docker.errors.NotFound`` class for try/except."""
    import docker  # noqa: WPS433

    return docker.errors.NotFound


async def _stop_container(
    docker_client: Any,
    container_id: str,
    *,
    timeout_s: int = 10,
) -> tuple[bool, str | None]:
    """Stop one Docker container.

    Returns ``(stopped, not_found_reason)``:
      * ``(True, None)``  — docker accepted the stop (or it was already
        stopped); row should be UPDATEd.
      * ``(False, "not_found")`` — container is already gone (404);
        row should still be UPDATEd (orphan reconciliation).
      * Other exceptions propagate — the caller skips the UPDATE for
        that row and the operator can retry.
    """
    try:
        # docker SDK is synchronous; offload to thread to keep the loop
        # responsive when sweeping multiple rows.
        await asyncio.to_thread(_sync_stop, docker_client, container_id, timeout_s)
        return (True, None)
    except _docker_not_found_class():
        log.info(
            "phase29.cutover.container_not_found container_id=%s",
            container_id[:12] if container_id else None,
        )
        return (False, "not_found")


def _sync_stop(docker_client: Any, container_id: str, timeout_s: int) -> None:
    container = docker_client.containers.get(container_id)
    container.stop(timeout=timeout_s)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 29 cutover — stop live nanobot containers + transition "
            "their agent_containers rows to status='stopped'. Per AMD-01 "
            "the canonical recipe name is 'nanobot'."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change, do not stop containers, do not UPDATE",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help=(
            "safety cap on per-run sweep size (default 10000). The script "
            "processes the OLDEST N matching rows and leaves the remainder "
            "for a follow-up run — supports incremental cutover on a host "
            "with many live nanobot containers without single-shotting them."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = args.dsn or os.environ.get("DATABASE_URL")
    if not dsn:
        log.error(
            "phase29.cutover.dsn_missing — pass --dsn or set DATABASE_URL"
        )
        return 2

    # asyncpg DSN does not accept the SQLAlchemy ``+asyncpg`` driver hint.
    # The api_server's deploy DSN uses ``postgresql+asyncpg://`` — strip
    # it so the script is drop-in compatible with the same env var the
    # api_server reads.
    dsn_clean = dsn.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn_clean)
    try:
        # Always SELECT first so dry-run + live both share the same
        # row-discovery path (only the side effects differ).
        rows = await conn.fetch(DRY_RUN_SQL)
        match_count = len(rows)

        # --limit caps the per-run sweep size; rows beyond the cap stay
        # in 'running' for a follow-up invocation (incremental cutover).
        if match_count > args.limit:
            log.warning(
                "phase29.cutover.limit_capping_sweep total=%d limit=%d "
                "remaining_after_run=%d",
                match_count,
                args.limit,
                match_count - args.limit,
            )
        rows = list(rows)[: args.limit]

        log.info(
            "phase29.cutover.candidates row_count=%d dry_run=%s",
            len(rows),
            args.dry_run,
        )
        for r in rows:
            log.info(
                "phase29.cutover.row id=%s user_id=%s agent_instance_id=%s "
                "container_id=%s container_status=%s",
                r["id"],
                r["user_id"],
                r["agent_instance_id"],
                (r["container_id"] or "")[:12],
                r["container_status"],
            )

        if args.dry_run or len(rows) == 0:
            log.info(
                "phase29.cutover.summary stopped=0 not_found=0 updated=0 "
                "dry_run=%s",
                args.dry_run,
            )
            return 0

        docker_client = _build_docker_client()

        stopped_count = 0
        not_found_count = 0
        updated_count = 0

        for r in rows:
            row_id = r["id"]
            container_id = r["container_id"]
            if not container_id:
                # Defensive — a row without a container_id (e.g. failed
                # very early in start_agent) needs no docker call but
                # MUST still be transitioned to stopped so the proxy
                # rehydrate skip-clause sees a clean state.
                await conn.execute(UPDATE_SQL, row_id)
                updated_count += 1
                continue

            stopped, not_found_reason = await _stop_container(
                docker_client, container_id,
            )
            if stopped:
                stopped_count += 1
            elif not_found_reason == "not_found":
                not_found_count += 1
            else:
                # Other failure — skip the UPDATE so the operator can
                # diagnose. The row stays in 'running' for retry.
                continue

            await conn.execute(UPDATE_SQL, row_id)
            updated_count += 1

        log.info(
            "phase29.cutover.summary stopped=%d not_found=%d updated=%d",
            stopped_count,
            not_found_count,
            updated_count,
        )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
