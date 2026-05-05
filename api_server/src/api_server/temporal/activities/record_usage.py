"""Phase 28 activity stub — record_usage.

Plan 04 fills the body by wrapping
``services/usage_recorder.py::record_usage`` (CONTEXT D-07).
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="record_usage")
async def record_usage(usage_input: dict[str, Any]) -> None:
    """Record a usage_logs row for the just-completed bot call.

    Workflow retry policy: maximum_attempts=3 with 1s initial interval;
    best-effort per CONTEXT D-15 (failure is logged + swallowed by the
    workflow, does NOT fail the dispatch).
    Plan 28-04 implements the body.
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
