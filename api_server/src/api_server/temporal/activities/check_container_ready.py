"""Phase 28 activity stub — check_container_ready.

Plan 04 fills the body. The signature here is the contract.

Type-hint note: ``inp`` is annotated as ``Any`` (not ``DispatchMessageInput``)
because ``@activity.defn`` calls ``typing.get_type_hints`` at decoration
time, which forces forward-reference resolution. A ``TYPE_CHECKING``-only
import of ``DispatchMessageInput`` is invisible at runtime and breaks
the decorator. The runtime contract is identical — Temporal serializes
the dataclass via JSON either way; the workflow-side annotation in
``DispatchMessageWorkflow.run`` is the canonical type record.
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="check_container_ready")
async def check_container_ready(inp: Any) -> bool:
    """Return True iff the user's agent container is responsive on its
    inapp HTTP endpoint. Plan 28-04 implements the body.

    Workflow retry policy (configured in dispatch_message.py):
    [250ms, 500ms, 1s, 2s, 4s] with maximum_attempts=5 — covers the
    transient container_not_ready window (CONTEXT D-10).
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
