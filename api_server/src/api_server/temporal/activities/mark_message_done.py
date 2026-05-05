"""Phase 28 activity — mark_message_done (atomic mark + emit dual-write).

Per RESEARCH §7 R2: mark_done + insert_agent_event run inside a
SINGLE asyncpg transaction so the outbox pump
(services/inapp_outbox.py) never sees torn state — i.e. an
``inapp_messages.status='done'`` without its matching
``agent_events`` row, or vice versa.

This is the same atomic-pair pattern the legacy
``services/inapp_dispatcher._handle_row`` uses at lines 469-477. The
workflow's ``emit_inapp_outbound`` activity is reduced to a no-op here
(see emit_inapp_outbound.py) because the actual write happens here.

The mark_done_input dict shape produced by ``forward_to_agent`` is::

    {
        "message_id": "<uuid-str>",
        "container_row_id": "<uuid-str>",
        "user_id": "<uuid-str>",
        "agent_id": "<uuid-str>",
        "bot_response": "<reply text>",
    }

``captured_at`` is computed in activity context — the activity is
unsandboxed, so ``datetime.now(timezone.utc)`` is fine. Workflows are
sandboxed and would have to use ``workflow.now()``; activities don't.

Failure here PROPAGATES (no try/except) per the workflow's
maximum_attempts=5 retry policy on this activity. If the workflow's
retry budget is exhausted the entire workflow fails — that is the
correct behavior because a message stuck in 'forwarded' with no
terminal status would block the user's chat thread forever; better to
surface the failure all the way up so the operator can investigate
than to silently drop the row.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from temporalio import activity


class MarkActivities:
    """Class-bound holder for the atomic mark-done + emit-event activity."""

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="mark_message_done")
    async def mark_message_done(self, mark_done_input: dict[str, Any]) -> None:
        """Atomic dual-write per RESEARCH §7 R2.

        mark_done + insert_agent_event(kind='inapp_outbound') run in
        ONE transaction. The outbox pump reads agent_events with
        published=false and fans out to Redis Pub/Sub.
        """
        # Late imports to keep module-level surface narrow + match the
        # legacy dispatcher's late-import discipline at lines 65-73.
        from ...services.event_store import insert_agent_event
        from ...services.inapp_messages_store import mark_done

        message_id = UUID(mark_done_input["message_id"])
        container_row_id = UUID(mark_done_input["container_row_id"])
        bot_response = mark_done_input["bot_response"]
        captured_at = datetime.now(timezone.utc).isoformat()

        # InappOutboundPayload schema (models/events.py:140-158):
        #   content: str (min_length=1)
        #   source: str (literal "agent")
        #   captured_at: datetime  -- pydantic accepts ISO-8601 string
        payload = {
            "content": bot_response,
            "source": "agent",
            "captured_at": captured_at,
        }

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await mark_done(conn, message_id, bot_response)
                await insert_agent_event(
                    conn,
                    container_row_id,
                    "inapp_outbound",
                    payload,
                )

@activity.defn(name="mark_message_done")
async def mark_message_done(mark_done_input: dict[str, Any]) -> None:
    """Module-level placeholder kept for the workflow file's import path.

    Workers register ``MarkActivities.mark_message_done`` (bound
    method); this top-level function fails loudly to surface a
    misconfigured worker.
    """
    raise NotImplementedError(
        "Workers register MarkActivities.mark_message_done "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )
