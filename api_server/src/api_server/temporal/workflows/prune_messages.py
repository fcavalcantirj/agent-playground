"""Phase B Plan B-stripe-09 — PruneMessagesWorkflow shim.

Daily-cron workflow wrapper around the
:func:`prune_messages` activity. Cron-scheduled at 03:00 UTC by
``temporal/schedules.py::register_schedules`` under schedule id
``phase-b-prune-messages-daily``.

The activity body owns the actual DELETE-by-tier work; this workflow
just schedules it with a defensive retry policy so a transient Temporal
fault (worker SIGTERM mid-run, gRPC blip) doesn't drop the day's
retention enforcement.

Determinism rules per ``workflows/__init__.py``:

  * Body imports ONLY ``temporalio.workflow`` + ``temporalio.common`` +
    ``datetime.timedelta`` at workflow scope.
  * Activity reference imported under
    ``workflow.unsafe.imports_passed_through()`` so the sandbox does
    NOT walk the activity's asyncpg dependency tree.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities import prune_messages


@workflow.defn(name="PruneMessagesWorkflow")
class PruneMessagesWorkflow:
    """Daily-cron workflow that deletes inapp_messages past tier retention.

    Returns the count of rows deleted across all (free, pro) tiers; ultra
    is unlimited and never contributes deletions. The return value is
    captured in Temporal history and surfaces in the Web UI for ops
    visibility but is not consumed by any caller.
    """

    @workflow.run
    async def run(self) -> int:
        return await workflow.execute_activity(
            prune_messages.PruneMessagesActivities.prune_messages,
            start_to_close_timeout=timedelta(seconds=120),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )


__all__ = ["PruneMessagesWorkflow"]
