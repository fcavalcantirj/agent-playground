"""Phase B Plan B-stripe-09 — ReconcileStripeWorkflow shim.

Five-minute-cron workflow wrapper around the
:func:`reconcile_stripe` activity. Cron-scheduled by
``temporal/schedules.py::register_schedules`` under schedule id
``phase-b-reconcile-stripe-5min``.

The activity body queries Stripe for ``checkout.session.completed``
events in the last 15 min that are NOT in our ``stripe_webhook_events``
table and applies them via the same handler used by the live webhook
route (Pitfall 2: same-tx dedupe-row INSERT + side-effect).

Determinism rules per ``workflows/__init__.py``:

  * Body imports ONLY ``temporalio.workflow`` + ``temporalio.common`` +
    ``datetime.timedelta`` at workflow scope.
  * Activity reference imported under
    ``workflow.unsafe.imports_passed_through()`` so the sandbox does
    NOT walk the activity's stripe + asyncpg dependency tree.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import reconcile_stripe


@workflow.defn(name="ReconcileStripeWorkflow")
class ReconcileStripeWorkflow:
    """5-minute-cron workflow that backstops missed Stripe webhooks.

    Returns the count of events newly applied this run. Zero on the
    common path where every event arrived via webhook. The return value
    is surfaced in Temporal history for ops visibility.

    Activity-level timeout is 300s — covers Stripe's network latency
    (events.list + side-effect over 100 events worst-case) with headroom.
    """

    @workflow.run
    async def run(self) -> int:
        return await workflow.execute_activity(
            reconcile_stripe.ReconcileStripeActivities.reconcile,
            start_to_close_timeout=timedelta(seconds=300),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )


__all__ = ["ReconcileStripeWorkflow"]
