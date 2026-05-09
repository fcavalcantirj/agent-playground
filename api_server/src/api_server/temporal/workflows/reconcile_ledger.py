"""Phase B Plan B-stripe-09 — ReconcileLedgerWorkflow shim.

Nightly-cron workflow wrapper around the
:func:`reconcile_ledger` activity. Cron-scheduled at 04:30 UTC (after
the daily prune at 03:00 UTC) by ``temporal/schedules.py::register_schedules``
under schedule id ``phase-b-reconcile-ledger-nightly``.

The activity body recomputes ``credit_balances.balance_cents`` from
``credit_transactions`` SUM for every user and emits a Sentry alert
+ repair-on-detect for any drift > 1 cent. D-17 ledger-as-truth: the
ledger is canonical; the cache being wrong is the bug.

Determinism rules per ``workflows/__init__.py``:

  * Body imports ONLY ``temporalio.workflow`` + ``temporalio.common`` +
    ``datetime.timedelta`` at workflow scope.
  * Activity reference imported under
    ``workflow.unsafe.imports_passed_through()`` so the sandbox does
    NOT walk the activity's asyncpg + sentry_sdk dependency tree.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import reconcile_ledger


@workflow.defn(name="ReconcileLedgerWorkflow")
class ReconcileLedgerWorkflow:
    """Nightly-cron workflow that recomputes credit_balances from ledger.

    Returns the count of drifting rows detected (and repaired) this run.
    Zero on the steady state — the spike-c row-lock discipline prevents
    drift in normal operation. Non-zero indicates a regression that
    introduced racey balance updates, surfaced via Sentry alert.
    """

    @workflow.run
    async def run(self) -> int:
        return await workflow.execute_activity(
            reconcile_ledger.ReconcileLedgerActivities.reconcile,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )


__all__ = ["ReconcileLedgerWorkflow"]
