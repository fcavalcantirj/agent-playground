"""Phase 28 activity — mark_message_failed (atomic mark_failed + emit dual-write).

Per RESEARCH §7 R2 (failure path): mark_failed +
insert_agent_event(kind='inapp_outbound_failed') run in ONE asyncpg
transaction so the outbox pump never sees a failure marker without
its corresponding event row.

Invocation contract (locked in Plan 03's workflow file): the workflow's
``_fail`` helper passes a ``(message_id, error_type)`` tuple positional
argument. A 2-tuple keeps the JSON payload compact and mirrors MSV's
pattern of grouping the failure-marker inputs into a single positional
arg.

The error_type is mapped through ``_truncate_error_type`` (verbatim from
inapp_dispatcher.py:338-358) to project the free-form taxonomy onto the
``InappOutboundFailedPayload``'s narrow 9-value enum. The full unmapped
value is preserved on ``inapp_messages.last_error`` so operators can
read which recipe / contract triggered the failure.

The container_row_id needed by ``insert_agent_event`` is resolved from
the ``inapp_messages`` row via a JOIN (the workflow's _fail args don't
carry it — only the success-path ForwardResult does). One read is
cheap; alternative would reshape Plan 03's _fail call site (sealed)
or add a new store helper. Inline JOIN is the lightest-footprint
option.

A separate file from mark_message_done.py because the workflow imports
each module independently (``from ..activities import mark_message_failed``)
and Plan 04's acceptance criteria require the per-file structure
(``grep -c conn.transaction()`` in this exact file path).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from temporalio import activity


class MarkFailedActivities:
    """Class-bound holder for the atomic mark_failed + emit-failure activity.

    Same ``db_pool`` dependency shape as ``MarkActivities`` in
    mark_message_done.py — kept separate so the workflow's per-module
    import (one module per activity name) resolves cleanly.
    """

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="mark_message_failed")
    async def mark_message_failed(self, args: tuple[str, str]) -> None:
        """Atomic dual-write per RESEARCH §7 R2 (failure path).

        ``args`` is ``(message_id_str, error_type)``. mark_failed +
        insert_agent_event(kind='inapp_outbound_failed') run in ONE
        transaction.
        """
        # Late imports to keep module-level surface narrow + match the
        # legacy dispatcher's late-import discipline.
        from ...services.event_store import insert_agent_event
        from ...services.inapp_dispatcher import _truncate_error_type
        from ...services.inapp_messages_store import mark_failed

        message_id_str, error_type = args
        message_id = UUID(message_id_str)
        captured_at = datetime.now(timezone.utc).isoformat()

        # InappOutboundFailedPayload schema (models/events.py:161-194):
        #   error_type: enum (9 values, see _KNOWN_ERROR_TYPES)
        #   message: str (min_length=1, max_length=512)
        #   retry_count: int (>= 0)
        #   captured_at: datetime
        message_text = (error_type[:512] or "unspecified")
        payload = {
            "error_type": _truncate_error_type(error_type),
            "message": message_text,
            "retry_count": 1,
            "captured_at": captured_at,
        }

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                await mark_failed(conn, message_id, error_type)
                # Resolve container_row_id from the message row.
                row = await conn.fetchrow(
                    """
                    SELECT c.id AS container_row_id
                    FROM inapp_messages m
                    JOIN agent_containers c
                      ON c.agent_instance_id = m.agent_id
                    WHERE m.id = $1
                    ORDER BY c.created_at DESC
                    LIMIT 1
                    """,
                    message_id,
                )
                if row is None:
                    activity.logger.warning(
                        "phase28.mark_message_failed.row_missing",
                        extra={"message_id": message_id_str},
                    )
                    return
                await insert_agent_event(
                    conn,
                    row["container_row_id"],
                    "inapp_outbound_failed",
                    payload,
                )


@activity.defn(name="mark_message_failed")
async def mark_message_failed(args: tuple[str, str]) -> None:
    """Module-level placeholder kept for the workflow file's import path.

    Workers register ``MarkFailedActivities.mark_message_failed`` (the
    bound method); this top-level function fails loudly so a
    misconfigured worker (which forgot to swap in the bound method) is
    detected immediately rather than silently passing.

    Args:
        args: ``(message_id, error_type)`` tuple. The two-element shape
            mirrors MSV's pattern of grouping the failure-marker
            inputs into a single positional argument.
    """
    raise NotImplementedError(
        "Workers register MarkFailedActivities.mark_message_failed "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )
