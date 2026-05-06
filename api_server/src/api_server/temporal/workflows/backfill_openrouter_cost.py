"""Phase 29 Plan 07 — BackfillOpenRouterCostWorkflow shim.

A thin workflow wrapper around the
:func:`backfill_openrouter_cost` activity. The activity body itself
already handles OpenRouter's eventually-consistent settle window via the
AMD-08 retry budget ``[0.0, 10.0, 20.0, 30.0]``; the workflow's outer
retry policy is purely defensive — covers a transient Temporal-side
fault (worker SIGTERM mid-run, gRPC blip) but never re-runs because of
an OpenRouter 4xx.

Determinism rules per ``workflows/__init__.py``:

- The body imports ONLY ``temporalio.workflow``, ``temporalio.common``,
  ``datetime`` (timedelta) at workflow scope.
- The activity function reference is imported under
  ``workflow.unsafe.imports_passed_through()`` so the sandbox does NOT
  walk into the activity's httpx / asyncpg dependency tree.
- The workflow body does NOT touch httpx / asyncpg / Decimal — it only
  schedules the activity and awaits its completion.

Workflow id convention (set by the proxy at start time per Plan 07
acceptance criteria): ``backfill_or_<usage_log_id>``. The id is
stable + idempotent — Temporal's REJECT_DUPLICATE policy guarantees
at-most-once execution per ``usage_log_id``.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from ..activities.backfill_openrouter_cost import (
        BackfillOpenRouterCostInput,
        backfill_openrouter_cost,
    )


@workflow.defn(name="BackfillOpenRouterCostWorkflow", sandboxed=False)
class BackfillOpenRouterCostWorkflow:
    """Wrap :func:`backfill_openrouter_cost` with a defensive retry policy.

    The activity's own retry budget is the load-bearing one (covers
    OpenRouter's settle latency); the workflow-level policy mirrors
    ``forward_to_agent``'s ``[1s, 2s, 4s]`` shape so a transient
    Temporal infrastructure fault (worker SIGTERM, gRPC reconnect) gets
    one defensive retry without amplifying upstream load.
    """

    @workflow.run
    async def run(self, inp: BackfillOpenRouterCostInput) -> None:
        await workflow.execute_activity(
            backfill_openrouter_cost,
            inp,
            # 90s start_to_close exceeds the activity's own 65s ceiling
            # (5s initial + 0+10+20+30 retries = 65s) plus 25s slack for
            # the four 10s GET timeouts overlapping with backoffs.
            start_to_close_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )


__all__ = ["BackfillOpenRouterCostWorkflow"]
