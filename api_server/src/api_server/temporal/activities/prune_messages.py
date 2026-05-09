"""Phase B Plan B-stripe-09 — prune_messages activity body (D-09 retention).

Class-bound activity that hard-deletes ``inapp_messages`` rows older than
each tier's retention window (D-05 single source of truth via
``services.tier_enforcement.retention_window_days``):

  * free  → 7 days
  * pro   → 30 days
  * ultra → ``None`` — unlimited retention; tier is skipped entirely

Triggered daily by ``temporal/schedules.py::register_schedules`` via the
``phase-b-prune-messages-daily`` cron schedule (03:00 UTC). Idempotent on
re-run — a second invocation in the same day no-ops on rows already
deleted because the cutoff window only widens forward.

Mirrors the class-bound shape of ``record_usage.RecordUsageActivities`` /
``debit_balance.DebitBalanceActivities`` so the worker can inject the
process-wide asyncpg pool and register ``self.prune_messages`` as a bound
method (Phase 28 D-22 contract for activity registration).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from temporalio import activity


_log = logging.getLogger("api_server.temporal.prune_messages")


class PruneMessagesActivities:
    """Class-bound holder for the prune-messages activity."""

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="prune_messages")
    async def prune_messages(self) -> int:
        """Delete inapp_messages older than each tier's retention window.

        Returns the total number of rows deleted across all tiers. The
        ``ultra`` tier is skipped (``retention_window_days`` returns
        ``None``) — those messages live forever per D-05.

        The DELETE is scoped per-tier via a JOIN against ``users.tier``
        so a row's retention is governed by the OWNER's current tier.
        A user who downgrades from Pro→Free at the next cron tick will
        have their 8-30d old messages collected on the next pass — that
        is the intended D-15 grace shape.
        """
        from ...services.tier_enforcement import retention_window_days

        now = datetime.now(timezone.utc)
        total_deleted = 0
        async with self.db_pool.acquire() as conn:
            for tier in ("free", "pro", "ultra"):
                days = retention_window_days(tier)
                if days is None:
                    # ultra → unlimited retention; skip the DELETE entirely.
                    continue
                cutoff = now - timedelta(days=days)
                deleted = await conn.fetchval(
                    """
                    WITH del AS (
                        DELETE FROM inapp_messages m
                         USING users u
                         WHERE m.user_id = u.id
                           AND u.tier = $1
                           AND m.created_at < $2
                        RETURNING m.id
                    )
                    SELECT COUNT(*)::BIGINT FROM del
                    """,
                    tier, cutoff,
                )
                total_deleted += int(deleted or 0)
                _log.info(
                    "prune_messages.tier_done tier=%s cutoff=%s deleted=%s",
                    tier, cutoff.isoformat(), deleted,
                )
        _log.info("prune_messages.total deleted=%s", total_deleted)
        return total_deleted


@activity.defn(name="prune_messages")
async def prune_messages() -> int:
    """Module-level placeholder — fail-loud import path.

    Workers register :meth:`PruneMessagesActivities.prune_messages`
    (the bound method); this top-level function fails loudly so a
    misconfigured worker is detected immediately rather than silently
    passing. Mirror of ``record_usage.py``.
    """
    raise NotImplementedError(
        "Workers register PruneMessagesActivities.prune_messages "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )


__all__ = ["PruneMessagesActivities", "prune_messages"]
