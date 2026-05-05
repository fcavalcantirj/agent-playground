"""Phase 28 activity stub — mark_message_failed.

Plan 04 fills the body by updating
``inapp_messages.status = 'failed'`` + ``last_error = error_type`` for
the message_id, plus emitting an ``inapp_outbound_failed`` event so
the SSE channel surfaces the failure to the client.

Invocation contract: the workflow's ``_fail`` helper passes a
``(message_id, error_type)`` tuple positional argument so a single
JSON payload covers both fields.
"""
from __future__ import annotations

from temporalio import activity


@activity.defn(name="mark_message_failed")
async def mark_message_failed(args: tuple[str, str]) -> None:
    """Mark the inapp_messages row as ``status='failed'`` with the
    given error_type, and emit the failure event.

    Workflow retry policy: maximum_attempts=5, best-effort. Even if
    this activity fails after all 5 retries, the workflow returns its
    own ``DispatchMessageResult(success=False, ...)`` so Temporal's
    history captures the original cause regardless.
    Plan 28-04 implements the body.

    Args:
        args: ``(message_id, error_type)`` tuple. The two-element shape
            mirrors MSV's pattern of grouping the failure-marker
            inputs into a single positional argument.
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
