#!/usr/bin/env python3
"""Phase 28 cutover — one-shot sweep of legacy stuck inapp_messages rows.

Run BEFORE rolling api_server to the Phase 28 build (Plan 28-06 cutover).
Rows that the legacy ``inapp_dispatcher`` left in ``status='forwarded'``
past the 11-minute reaper threshold are orphaned by the cutover (no
in-flight Temporal workflow exists to claim them, and the reaper loop
itself is being deleted as part of Plan 28-06's big-bang swap per D-06).

This script transitions them to ``status='failed'`` with
``last_error='phase28_cutover_swept'`` so the audit log is preserved
and the user surface shows a terminal failure instead of a perpetual
"typing" indicator.

Usage::

    DATABASE_URL=postgresql://... python tools/migrate_phase28_stuck_rows.py
    DATABASE_URL=postgresql://... python tools/migrate_phase28_stuck_rows.py --dry-run

Canonical post-cutover invocation (api_server container + bind-mounted
``/app/tools`` from the build per ``deploy/docker-compose.prod.yml``)::

    docker exec deploy-api_server-1 \\
        python /app/tools/migrate_phase28_stuck_rows.py

If ``tools/`` is NOT bind-mounted (the prod compose builds it in via
``COPY tools /src/tools`` in ``tools/Dockerfile.api`` rather than
mounting), the script ships in the container at build time and the
above invocation works unchanged. For a one-shot run on a container
that pre-dates this script, ``docker cp`` it in first::

    docker cp tools/migrate_phase28_stuck_rows.py \\
        deploy-api_server-1:/app/tools/

Idempotency: re-running the non-dry-run path after the sweep is a no-op
(the WHERE clause matches zero rows once they're all transitioned to
``failed``). Safe to re-run for confidence.

Safety cap: ``--limit`` (default 10000) aborts the run if more rows
match than the cap. Phase 28 cutover is not expected to find more than
single-digit stuck rows; if the count blows past the cap that's a
signal to stop and inspect the DB before mutating en masse.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import asyncpg


log = logging.getLogger("phase28.cutover")


# UPDATE: targets exactly the same WHERE clause shape used by
# services/inapp_reaper.py (status='forwarded' AND last_attempt_at older
# than 11 minutes — D-30 reaper threshold). RETURNING surfaces the
# affected rows for audit logging.
SWEEP_SQL = """
UPDATE inapp_messages
SET status = 'failed',
    last_error = 'phase28_cutover_swept',
    completed_at = NOW()
WHERE status = 'forwarded'
  AND last_attempt_at < NOW() - INTERVAL '11 minutes'
RETURNING id, user_id, agent_id, last_attempt_at
"""


# Dry-run preview: same WHERE clause as SWEEP_SQL, read-only SELECT.
DRY_RUN_SQL = """
SELECT id, user_id, agent_id, last_attempt_at
FROM inapp_messages
WHERE status = 'forwarded'
  AND last_attempt_at < NOW() - INTERVAL '11 minutes'
"""


# Pre-count guard: counts the rows the SWEEP_SQL will touch so the
# safety cap can fire BEFORE any mutation runs. Same WHERE clause.
COUNT_SQL = """
SELECT COUNT(*) FROM inapp_messages
WHERE status = 'forwarded'
  AND last_attempt_at < NOW() - INTERVAL '11 minutes'
"""


async def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 28 cutover sweep")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change, do not write",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help="safety cap; abort if more rows match",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        log.error("DATABASE_URL env var is required")
        return 2

    # asyncpg DSN does not accept the SQLAlchemy ``+asyncpg`` driver hint.
    # The api_server's deploy DSN uses ``postgresql+asyncpg://`` so strip
    # it here to keep the script drop-in compatible with the same env var
    # the api_server reads.
    dsn_clean = dsn.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(dsn_clean)
    try:
        if args.dry_run:
            rows = await conn.fetch(DRY_RUN_SQL)
            log.info(
                "phase28.cutover.dry_run row_count=%d",
                len(rows),
            )
            for r in rows[:50]:
                log.info(
                    "phase28.cutover.row id=%s user_id=%s agent_id=%s "
                    "last_attempt_at=%s",
                    r["id"],
                    r["user_id"],
                    r["agent_id"],
                    r["last_attempt_at"].isoformat(),
                )
            if len(rows) > 50:
                log.info(
                    "phase28.cutover.dry_run.truncated shown=50 total=%d",
                    len(rows),
                )
            return 0

        # Live path: pre-count guard + transactional UPDATE.
        async with conn.transaction():
            count = await conn.fetchval(COUNT_SQL)
            if count > args.limit:
                log.error(
                    "phase28.cutover.safety_cap_exceeded count=%d limit=%d",
                    count,
                    args.limit,
                )
                return 3
            rows = await conn.fetch(SWEEP_SQL)
            log.info(
                "phase28.cutover.swept row_count=%d",
                len(rows),
            )
            for r in rows:
                log.info(
                    "phase28.cutover.swept.row id=%s user_id=%s agent_id=%s "
                    "last_attempt_at=%s",
                    r["id"],
                    r["user_id"],
                    r["agent_id"],
                    r["last_attempt_at"].isoformat(),
                )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
