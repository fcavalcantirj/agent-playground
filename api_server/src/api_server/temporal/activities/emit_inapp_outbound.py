"""Phase 28 activity — emit_inapp_outbound (success-path no-op).

Per RESEARCH §7 R2 + R7 the success-path ``agent_events`` row is written
by ``mark_message_done`` in the SAME asyncpg transaction as the
``inapp_messages`` status flip — atomic dual-write. This activity is
preserved as a NO-OP for shape parity with MSV's ``send_message.go``
workflow which keeps ``emit_inapp_outbound`` as a separate step.

Why preserve the activity instead of deleting it:

1. **Workflow-file stability** — the workflow file (Plan 03) imports
   the module and calls ``execute_activity(emit_inapp_outbound.emit_inapp_outbound, ...)``.
   Deleting the activity here would force a workflow change, which Plan 04
   is explicitly not allowed to do (workflow is sealed by Plan 03; only
   activity bodies + worker.py are in scope).
2. **Test-contract stability** — Plan 05 tests register all 7 activities
   on the WorkflowEnvironment; an absent activity would cause
   ``Worker.__init__`` to error.
3. **Future-extension hook** — if the atomic dual-write needs to split
   for a future scale point (e.g. a separate event-store DB), the
   activity body can be replaced without reshaping the workflow.

Plan 06 implementer note: when wiring ``start_workflow`` from the route
handler, this activity's no-op nature is invisible — the bot reply
still surfaces to SSE clients via the agent_events row written by
``mark_message_done``. The outbox pump (services/inapp_outbox.py) reads
that row with ``published=false`` and fans out to Redis.
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="emit_inapp_outbound")
async def emit_inapp_outbound(event_input: dict[str, Any]) -> None:
    """No-op — agent_events row is written atomically by
    ``mark_message_done`` (RESEARCH §7 R2 + R7). This activity is
    preserved for shape parity with MSV's send_message.go.
    """
    activity.logger.info(
        "phase28.emit_inapp_outbound.noop",
        extra={
            "message_id": event_input.get("message_id"),
            "rationale": "agent_events written atomically by mark_message_done",
        },
    )
    return None
