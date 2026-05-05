"""Phase 28 — DispatchMessageWorkflow.

Mirrors MSV's ``messaging/workflows/send_message.go`` (lines 16-198) verbatim
in shape so backlog 999.2 (Go API rewrite) has a clean migration template
(CONTEXT D-09: Go-portable Python).

Workflow ID convention (D-08, revised 2026-05-05): ``msg-{user_id}-{message_uuid}``.
User-scoped — Temporal UI search by ``msg-{user_id}-*`` lists every workflow
for that user; defense-in-depth against cross-user mis-dispatch.

Determinism:

- The body imports ONLY: temporalio.workflow, temporalio.common,
  temporalio.exceptions, datetime (timedelta only), dataclasses.
- Activity function references are imported under
  ``workflow.unsafe.imports_passed_through()`` so the sandbox doesn't
  walk into the activities' httpx/asyncpg/docker dependency tree.
- No wall-clock readers, no ``time`` module calls, no ``random``
  module calls, no UUID4 generators — those are non-deterministic
  in workflow context. Use ``workflow.now()`` / ``workflow.random()``
  / ``workflow.uuid4()`` if any of those are ever needed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from .types import ForwardResult  # noqa: F401  (re-exported for downstream)

# Workflow imports must NOT touch activity bodies (they pull in
# asyncpg / httpx / docker — sandbox-passthrough warnings). The
# ``imports_passed_through`` context manager lets us import the
# function symbols (so we can call ``execute_activity`` with them)
# without invoking the sandbox import machinery on their dependency
# trees. Wave 0 spike B confirmed this works on Python 3.13 against
# temporalio==1.27.x with zero sandbox warnings.
with workflow.unsafe.imports_passed_through():
    from ..activities import (
        check_container_ready,
        debit_balance,
        emit_inapp_outbound,
        forward_to_agent,
        mark_message_done,
        mark_message_failed,
        record_usage,
    )


@dataclass(frozen=True)
class DispatchMessageInput:
    """Inputs the API route hands to ``client.start_workflow`` (Plan 28-06).

    All fields are primitive-typed so Temporal JSON serialization is safe.
    UUIDs are stringified at the API boundary; activities re-parse them
    via ``UUID(s)`` if/when DB calls need them.

    Field order mirrors MSV's ``messaging.SendMessageInput`` (Go struct).
    """

    message_id: str           # UUID stringified — workflow ID = f"msg-{user_id}-{message_id}" (D-08, user-scoped)
    user_id: str
    agent_id: str
    container_row_id: str
    container_id: str
    recipe_name: str
    agent_model: str
    content: str
    inapp_auth_token: str | None
    bot_timeout_seconds: float


@dataclass(frozen=True)
class DispatchMessageResult:
    """Workflow output. ``error_type`` follows the existing AP taxonomy
    (``services/inapp_dispatcher.py:325-335`` ``_KNOWN_ERROR_TYPES``)."""

    success: bool
    error_type: str | None = None
    reply: str | None = None


@workflow.defn(name="DispatchMessageWorkflow")
class DispatchMessageWorkflow:
    """Orchestrates a single user message dispatch end-to-end.

    Defense-in-depth (D-13 + RESEARCH §8 Q5):

    The 5-minute hard cap on workflow execution requires defense-in-depth
    so a future caller cannot accidentally omit it. RESEARCH §8 Q5
    recommends combining a defn/worker-level default with a
    per-start ``execution_timeout`` override.

    Empirical finding (verified against the pinned ``temporalio==1.27.0``
    SDK during Plan 28-03 execution — see Plan 03 SUMMARY):

    - ``@workflow.defn`` accepts ONLY ``name``, ``sandboxed``, ``dynamic``,
      ``failure_exception_types``, ``versioning_behavior``. It does NOT
      accept ``default_execution_timeout``.
    - ``Worker.__init__`` does NOT accept
      ``default_workflow_execution_timeout`` either.
    - Therefore the ONLY enforcement path in 1.27.x is the per-start
      ``execution_timeout`` kwarg on ``Client.start_workflow``.

    Plan 28-06 (the route handler that calls ``start_workflow``) MUST
    therefore pass ``execution_timeout=timedelta(minutes=5)``. The
    Plan 28-03 SUMMARY records this requirement explicitly so the Plan
    06 implementer cannot miss it. If a future SDK version adds a
    defn/worker-level default, this docstring should be updated and a
    second defense line layered in.
    """

    @workflow.run
    async def run(self, inp: DispatchMessageInput) -> DispatchMessageResult:
        # ---- Step 1: readiness gate ----
        # Activity-internal retry [250ms, 500ms, 1s, 2s, 4s] — covers
        # the transient container_not_ready window that surfaced in the
        # 2026-05-04 → 2026-05-05 chat-stability investigation.
        ready = await workflow.execute_activity(
            check_container_ready.check_container_ready,
            inp,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(milliseconds=250),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(seconds=4),
                maximum_attempts=5,
            ),
        )
        if not ready:
            await self._fail(inp, "container_not_ready")
            return DispatchMessageResult(
                success=False, error_type="container_not_ready"
            )

        # ---- Step 2: forward to agent (the bot HTTP call) ----
        # Activity-internal retry on transport errors [1s, 2s, 4s] per
        # D-11. Workflow-level MaxAttempts=1 because the activity owns
        # its own retry budget for transport faults; HTTP 4xx/5xx fail
        # terminal via ApplicationError(non_retryable=True).
        try:
            forward_result = await workflow.execute_activity(
                forward_to_agent.forward_to_agent,
                inp,
                start_to_close_timeout=timedelta(
                    seconds=inp.bot_timeout_seconds + 30.0,  # D-12 buffer
                ),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ApplicationError as e:
            err = _classify_forward_failure(e)
            await self._fail(inp, err)
            return DispatchMessageResult(success=False, error_type=err)

        if not forward_result.reply or not forward_result.reply.strip():
            await self._fail(inp, "bot_empty")
            return DispatchMessageResult(
                success=False, error_type="bot_empty"
            )

        # ---- Step 3a: record_usage (best-effort per D-15) ----
        # Failure is logged + swallowed; does NOT fail the workflow.
        try:
            await workflow.execute_activity(
                record_usage.record_usage,
                forward_result.usage_input,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(
                    maximum_attempts=3,
                    initial_interval=timedelta(seconds=1),
                ),
            )
        except ApplicationError as e:
            workflow.logger.warning(
                "phase28.record_usage.swallowed",
                extra={"error": str(e), "message_id": inp.message_id},
            )

        # ---- Step 3b: debit_balance (D-22 no-op stub; best-effort) ----
        # Phase B replaces the activity body with real Stripe debit logic.
        # Activity contract is locked here so Phase B doesn't reshape
        # the workflow.
        try:
            await workflow.execute_activity(
                debit_balance.debit_balance,
                inp,
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ApplicationError as e:
            workflow.logger.warning(
                "phase28.debit_balance.swallowed",
                extra={"error": str(e), "message_id": inp.message_id},
            )

        # ---- Step 3c: emit_inapp_outbound (best-effort per D-15) ----
        try:
            await workflow.execute_activity(
                emit_inapp_outbound.emit_inapp_outbound,
                forward_result.event_input,
                start_to_close_timeout=timedelta(seconds=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ApplicationError as e:
            workflow.logger.warning(
                "phase28.emit_inapp_outbound.swallowed",
                extra={"error": str(e), "message_id": inp.message_id},
            )

        # ---- Step 3d: mark_message_done (load-bearing per D-10) ----
        # No try/except — failure here propagates as workflow failure
        # so the message row never gets stuck in 'forwarded' state with
        # no terminal status. The retry policy below gives 5 attempts
        # at 250ms + exponential backoff before finally failing.
        await workflow.execute_activity(
            mark_message_done.mark_message_done,
            forward_result.mark_done_input,
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(
                maximum_attempts=5,
                initial_interval=timedelta(milliseconds=250),
            ),
        )

        return DispatchMessageResult(
            success=True, reply=forward_result.reply
        )

    async def _fail(
        self, inp: DispatchMessageInput, error_type: str
    ) -> None:
        """Best-effort terminal failure marker.

        Calls ``mark_message_failed`` with ``(message_id, error_type)``
        tuple. Best-effort — if the failure-marker activity itself fails
        after 5 retries, the workflow returns its own
        ``DispatchMessageResult(success=False, error_type=...)`` anyway,
        so Temporal's history captures the original cause.
        """
        await workflow.execute_activity(
            mark_message_failed.mark_message_failed,
            (inp.message_id, error_type),
            start_to_close_timeout=timedelta(seconds=5),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )


def _classify_forward_failure(e: ApplicationError) -> str:
    """Map ``ApplicationError`` back to the AP error_type taxonomy.

    The forward_to_agent activity raises:
        ``ApplicationError(message=<error_type>, type=<error_type>,
        non_retryable=True)``
    where ``<error_type>`` is one of ``_KNOWN_ERROR_TYPES`` from
    ``services/inapp_dispatcher.py:325-335``. The workflow recovers
    the type string and forwards it to ``_fail`` + the workflow result.

    Resolution order (most specific to least):
    1. ``e.type`` attribute (set by the activity).
    2. ``e.args[0]`` (set by the ``ApplicationError(message=...)`` ctor).
    3. ``"internal_error"`` fallback for unclassified bugs.
    """
    t = getattr(e, "type", None)
    if t:
        return str(t)
    if e.args:
        return str(e.args[0])
    return "internal_error"
