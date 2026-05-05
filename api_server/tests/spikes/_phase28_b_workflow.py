"""Phase 28 Wave 0 — Spike B helper (workflow module).

Mirrors the planned ``api_server/temporal/workflows/dispatch_message.py``
import shape verbatim: workflow file imports ONLY temporalio +
deterministic stdlib, and uses ``workflow.unsafe.imports_passed_through()``
to bring in the activity module without entering the sandbox.

Spike asserts:
  1. Module imports without raising during `Worker(...)` registration.
  2. Workflow executes against
     ``temporalio.testing.WorkflowEnvironment.start_time_skipping()``.
  3. NO sandbox passthrough warnings fire under ``-W error::Warning``.
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from . import _phase28_b_activities


@workflow.defn(name="SpikeBWorkflow")
class SpikeBWorkflow:
    """Single-step workflow that exercises the activity helper."""

    @workflow.run
    async def run(self, payload: str) -> str:
        return await workflow.execute_activity(
            _phase28_b_activities.spike_b_activity,
            payload,
            start_to_close_timeout=timedelta(seconds=5),
        )
