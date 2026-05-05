"""Phase 28 activity stub — mark_message_done.

Plan 04 fills the body by updating ``inapp_messages.status = 'done'``
for the just-completed message_id. Idempotent at the DB layer
(``UPDATE ... WHERE status != 'done'`` per CONTEXT D-15).
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="mark_message_done")
async def mark_message_done(mark_done_input: dict[str, Any]) -> None:
    """Mark the inapp_messages row as ``status='done'``.

    Workflow retry policy: maximum_attempts=5 with 250ms initial
    interval — load-bearing per CONTEXT D-10. Failure here propagates
    as workflow failure so the message row never gets stuck in
    'forwarded' state with no terminal status.
    Plan 28-04 implements the body.
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
