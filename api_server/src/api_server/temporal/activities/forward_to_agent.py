"""Phase 28 activity stub — forward_to_agent.

Plan 04 fills the body verbatim from MSV
``messaging/activities/forward_to_agent.go:64-196`` — connection-retry
pattern [1s, 2s, 4s] for transport errors only; HTTP 4xx/5xx fail
terminal via ``ApplicationError(non_retryable=True)``.

Type-hint note: ``inp`` is annotated as ``Any`` (not
``DispatchMessageInput``) because ``@activity.defn`` calls
``typing.get_type_hints`` at decoration time, which forces
forward-reference resolution. A ``TYPE_CHECKING``-only import would
be invisible at runtime; a runtime import would create a circular
import (workflow → activities → workflow). The workflow-side
annotation in ``DispatchMessageWorkflow.run`` is the canonical type
record. ``ForwardResult`` is safe to import at runtime because
``types.py`` is dependency-free.
"""
from __future__ import annotations

from typing import Any

from temporalio import activity

# ForwardResult import is fine here — types.py has zero circular-import
# risk because it imports nothing from this package.
from ..workflows.types import ForwardResult


@activity.defn(name="forward_to_agent")
async def forward_to_agent(inp: Any) -> ForwardResult:
    """Forward the user message to the agent container's inapp HTTP
    endpoint and capture the bot reply + downstream payloads.

    Workflow retry policy: ``maximum_attempts=1`` because the activity
    body OWNS the transport-retry budget (CONTEXT D-11).
    Plan 28-04 implements the body.
    """
    raise NotImplementedError("Plan 28-04 implements this activity body")
