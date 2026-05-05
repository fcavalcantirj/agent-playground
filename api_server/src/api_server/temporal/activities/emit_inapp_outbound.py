"""Phase 28 activity stub — emit_inapp_outbound.

Plan 04 fills the body by writing an ``inapp_outbound`` row into
``agent_events`` so the SSE pump fans out the bot reply to the user's
mobile + web clients. Idempotent via the existing
``agent_events.seq`` per-container monotonic counter (CONTEXT D-15).
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="emit_inapp_outbound")
async def emit_inapp_outbound(event_input: dict[str, Any]) -> None:
    """Emit the SSE outbound event for the just-completed bot reply.

    Workflow retry policy: maximum_attempts=3, best-effort per D-15.
    Plan 28-04 implements the body.
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
