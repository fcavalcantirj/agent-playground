"""Phase B Plan B-stripe-09 — reconcile_ledger activity body (D-17 sentinel).

Nightly drift detection between ``credit_balances`` (cache) and
``credit_transactions`` (ledger truth). For every row in
``credit_balances`` we recompute ``SUM(amount_cents)`` from
``credit_transactions`` for the same user; if cache disagrees with
ledger truth by more than 1 cent we:

  1. Log the drift at WARNING via stdlib logging (caught by structlog +
     scraped to Loki/Promtail same as the rest of the worker).
  2. Emit a Sentry ``capture_message`` at level=error so Phase 31 H6
     wiring routes the drift to ops alerting.
  3. UPDATE the cache row to match ledger truth — D-17 says ledger is
     the only source of truth; the cache is a best-effort denormalization
     that any drift means the cache is wrong, not the ledger.

D-17 invariant: a debit_balance / topup / refund handler that BUILT the
drift would have already lost the race that introduced it (the helpers
in ``services.ledger`` use ``SELECT ... FOR UPDATE`` to serialize on
``credit_balances`` rows; spike-c proved this concurrent-safe at 8-way
parallelism). So in normal operation, drift_count == 0 and the only
side-effect is the metric/log line. A non-zero drift_count fires a
Sentry alert so we can investigate the regression that introduced it.

Mirrors the class-bound shape used elsewhere in the Phase 28 activity
substrate so the worker can inject the process-wide asyncpg pool.
"""
from __future__ import annotations

import logging
from typing import Any

import sentry_sdk
from temporalio import activity


_log = logging.getLogger("api_server.temporal.reconcile_ledger")


class ReconcileLedgerActivities:
    """Class-bound holder for the reconcile-ledger activity."""

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="reconcile_ledger")
    async def reconcile(self) -> int:
        """Recompute every credit_balances row from ledger SUM.

        Returns the count of rows where drift was detected (and repaired).
        Zero on the steady state — the spike-c row-lock discipline prevents
        drift in normal operation.

        For each drifting row we emit:

          * structlog WARNING with full triple (cache_cents, truth_cents,
            drift) so the worker logs surface the issue immediately
          * Sentry ``capture_message`` at error level (Phase 31 H6) for
            ops paging
          * UPDATE the cache row to ledger truth — repair-on-detect, NOT
            "alert + leave broken". The ledger is canonical; the cache
            being wrong is the bug.
        """
        async with self.db_pool.acquire() as conn:
            # One CTE-style SELECT to compare cache + truth in a single
            # round-trip per user. COALESCE handles users with cache=0
            # but no ledger rows yet (e.g. fresh free-tier signups).
            rows = await conn.fetch(
                """
                SELECT
                    b.user_id,
                    b.balance_cents AS cache_cents,
                    COALESCE((
                        SELECT SUM(amount_cents)::BIGINT
                          FROM credit_transactions
                         WHERE user_id = b.user_id
                    ), 0)::BIGINT AS truth_cents
                  FROM credit_balances b
                """,
            )
            drift_count = 0
            for r in rows:
                cache_cents = int(r["cache_cents"])
                truth_cents = int(r["truth_cents"])
                drift = cache_cents - truth_cents
                if abs(drift) >= 1:
                    drift_count += 1
                    _log.warning(
                        "reconcile_ledger.drift user_id=%s "
                        "cache_cents=%s truth_cents=%s drift=%s",
                        r["user_id"], cache_cents, truth_cents, drift,
                    )
                    # Phase 31 H6: capture_message at error level so the
                    # Sentry quota path picks it up; before_send filter
                    # in instrumentation/sentry.py drops 4xx-shaped
                    # client errors but keeps server-side captures like
                    # this one through.
                    sentry_sdk.capture_message(
                        f"credit_balances cache drift detected "
                        f"user_id={r['user_id']} "
                        f"cache_cents={cache_cents} "
                        f"truth_cents={truth_cents} "
                        f"drift_cents={drift}",
                        level="error",
                    )
                    # Repair-on-detect: ledger is canonical (D-17), so
                    # the cache moves to truth. Single statement; runs
                    # without an outer transaction because we are
                    # repairing each row independently.
                    await conn.execute(
                        "UPDATE credit_balances "
                        "   SET balance_cents = $1, "
                        "       updated_at = NOW() "
                        " WHERE user_id = $2",
                        truth_cents, r["user_id"],
                    )
            _log.info(
                "reconcile_ledger.run_done rows_checked=%s drift_count=%s",
                len(rows), drift_count,
            )
            return drift_count


@activity.defn(name="reconcile_ledger")
async def reconcile_ledger() -> int:
    """Module-level placeholder — fail-loud import path.

    Workers register :meth:`ReconcileLedgerActivities.reconcile` (the
    bound method); this top-level function fails loudly so a
    misconfigured worker is detected immediately rather than silently
    passing.
    """
    raise NotImplementedError(
        "Workers register ReconcileLedgerActivities.reconcile "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )


__all__ = ["ReconcileLedgerActivities", "reconcile_ledger"]
