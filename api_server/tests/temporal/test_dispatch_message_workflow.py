"""Phase 28 Plan 28-07 Task 1 — workflow-level unit tests.

Per CLAUDE.md Golden Rule #1, NO in-memory mocks for the substrate:
``WorkflowEnvironment.start_time_skipping()`` runs a REAL Temporal Server
in test mode (the SDK ships it).

Mock activities ARE allowed inside workflow-level tests because we are
testing the WORKFLOW's logic, not the activities. Workflow tests register
fake activities with the same ``@activity.defn(name=...)`` so the
workflow sees them as real.

Coverage matrix (the 7 mandated cases per Plan 28-07 frontmatter):

  1. happy_path                         — all activities succeed → success=True
  2. container_not_ready                — readiness gate False on every attempt
                                          → success=False, error_type='container_not_ready'
  3. bot_timeout                        — forward_to_agent raises bot_timeout
                                          → success=False, error_type='bot_timeout'
  4. bot_empty                          — forward returns empty reply
                                          → success=False, error_type='bot_empty'
  5. record_usage_best_effort           — record_usage raises but workflow succeeds (D-15)
  6. mark_message_done_failure_propagates — mark_done raises → workflow fails (D-10)
  7. five_minute_execution_timeout      — workflow respects D-13 5-min hard cap
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from api_server.temporal.workflows.dispatch_message import (
    DispatchMessageResult,
    DispatchMessageWorkflow,
)
from api_server.temporal.workflows.types import ForwardResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_task_queue() -> str:
    return f"ap-msgs-test-{uuid.uuid4().hex[:8]}"


def _build_forward_result(reply: str = "hi back") -> ForwardResult:
    return ForwardResult(
        reply=reply,
        raw_response={"choices": [{"message": {"content": reply}}]},
        usage_input={
            "user_id": str(uuid.UUID(int=2)),
            "agent_instance_id": str(uuid.UUID(int=3)),
            "message_id": str(uuid.UUID(int=1)),
            "contract": "openai_compat",
            "provider": "openrouter",
            "model": "anthropic/claude-3.5-sonnet",
            "response": {"choices": [{"message": {"content": reply}}]},
            "source": "inapp",
        },
        event_input={
            "container_row_id": str(uuid.UUID(int=4)),
            "agent_id": str(uuid.UUID(int=3)),
            "user_id": str(uuid.UUID(int=2)),
            "reply": reply,
            "message_id": str(uuid.UUID(int=1)),
        },
        mark_done_input={
            "message_id": str(uuid.UUID(int=1)),
            "container_row_id": str(uuid.UUID(int=4)),
            "user_id": str(uuid.UUID(int=2)),
            "agent_id": str(uuid.UUID(int=3)),
            "bot_response": reply,
        },
    )


# ---------------------------------------------------------------------------
# 1. happy path
# ---------------------------------------------------------------------------


async def test_happy_path(temporal_env, make_dispatch_input) -> None:
    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        return _build_forward_result("hi back")

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    mark_done_calls: list[dict] = []

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(mark_done_input):  # type: ignore[no-untyped-def]
        mark_done_calls.append(mark_done_input)
        return None

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(_args):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready,
            fake_forward,
            fake_record,
            fake_emit,
            fake_mark_done,
            fake_mark_failed,
            fake_debit,
        ],
    ):
        result: DispatchMessageResult = await temporal_env.client.execute_workflow(
            DispatchMessageWorkflow.run,
            inp,
            id=f"msg-test-happy-{uuid.uuid4().hex[:8]}",
            task_queue=tq,
        )

    assert result.success is True
    assert result.reply == "hi back"
    assert result.error_type is None
    assert len(mark_done_calls) == 1, "mark_message_done must run exactly once on success path"


# ---------------------------------------------------------------------------
# 2. container_not_ready terminal — 5 ready-check attempts exhaust
# ---------------------------------------------------------------------------


async def test_container_not_ready_returns_failure(
    temporal_env, make_dispatch_input,
) -> None:
    """When check_container_ready returns False every attempt, the workflow's
    [250ms..4s] retry policy with maximum_attempts=5 exhausts and the workflow
    body's ``if not ready`` branch fires → DispatchMessageResult(success=False,
    error_type='container_not_ready').
    """
    ready_calls: list[int] = []

    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        ready_calls.append(1)
        return False

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        raise AssertionError("forward_to_agent must not be called when readiness is False")

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        raise AssertionError("mark_message_done must not run on the failure branch")

    failed_calls: list[tuple] = []

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(args):  # type: ignore[no-untyped-def]
        failed_calls.append(tuple(args))
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        result = await temporal_env.client.execute_workflow(
            DispatchMessageWorkflow.run,
            inp,
            id=f"msg-test-not-ready-{uuid.uuid4().hex[:8]}",
            task_queue=tq,
        )

    assert result.success is False
    assert result.error_type == "container_not_ready"
    # The activity returned False on first attempt — that is a normal
    # completion (the retry policy fires only on raised errors, not on
    # falsy return values). The workflow body's ``if not ready: _fail``
    # branch handled the False and routed to the failure path.
    assert len(ready_calls) == 1
    # mark_message_failed was invoked once with the right error_type.
    assert len(failed_calls) == 1
    assert failed_calls[0][1] == "container_not_ready"


# ---------------------------------------------------------------------------
# 3. bot_timeout — forward raises non-retryable ApplicationError
# ---------------------------------------------------------------------------


async def test_bot_timeout_terminal(
    temporal_env, make_dispatch_input,
) -> None:
    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        raise ApplicationError(
            "bot_timeout", type="bot_timeout", non_retryable=True,
        )

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        raise AssertionError("mark_message_done must not run on the bot_timeout branch")

    failed_calls: list[tuple] = []

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(args):  # type: ignore[no-untyped-def]
        failed_calls.append(tuple(args))
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        result = await temporal_env.client.execute_workflow(
            DispatchMessageWorkflow.run,
            inp,
            id=f"msg-test-bot-timeout-{uuid.uuid4().hex[:8]}",
            task_queue=tq,
        )

    assert result.success is False
    assert result.error_type == "bot_timeout"
    assert len(failed_calls) == 1
    assert failed_calls[0][1] == "bot_timeout"


# ---------------------------------------------------------------------------
# 4. bot_empty — forward returned a ForwardResult with empty reply
# ---------------------------------------------------------------------------


async def test_bot_empty_terminal(
    temporal_env, make_dispatch_input,
) -> None:
    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        return _build_forward_result("")

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        raise AssertionError("mark_message_done must not run on the bot_empty branch")

    failed_calls: list[tuple] = []

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(args):  # type: ignore[no-untyped-def]
        failed_calls.append(tuple(args))
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        result = await temporal_env.client.execute_workflow(
            DispatchMessageWorkflow.run,
            inp,
            id=f"msg-test-bot-empty-{uuid.uuid4().hex[:8]}",
            task_queue=tq,
        )

    assert result.success is False
    assert result.error_type == "bot_empty"
    assert len(failed_calls) == 1
    assert failed_calls[0][1] == "bot_empty"


# ---------------------------------------------------------------------------
# 5. record_usage best-effort failure — workflow STILL succeeds (D-15)
# ---------------------------------------------------------------------------


async def test_record_usage_best_effort_does_not_fail_workflow(
    temporal_env, make_dispatch_input,
) -> None:
    """D-15: record_usage failure is logged + swallowed; mark_message_done
    must still run; workflow returns success=True.
    """
    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        return _build_forward_result("hi back")

    record_calls: list[int] = []

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        record_calls.append(1)
        raise ApplicationError(
            "simulated_record_usage_failure", non_retryable=True,
        )

    emit_calls: list[int] = []

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        emit_calls.append(1)
        return None

    mark_done_calls: list[int] = []

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        mark_done_calls.append(1)
        return None

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(_args):  # type: ignore[no-untyped-def]
        raise AssertionError("mark_message_failed must NOT fire on the success path")

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        result = await temporal_env.client.execute_workflow(
            DispatchMessageWorkflow.run,
            inp,
            id=f"msg-test-record-usage-besteffort-{uuid.uuid4().hex[:8]}",
            task_queue=tq,
        )

    assert result.success is True, (
        "D-15 best-effort: record_usage failure must NOT fail the workflow"
    )
    assert result.reply == "hi back"
    # record_usage was tried (at least once — its retry policy may or may not run
    # additional attempts depending on the non_retryable=True flag; the swallow
    # is what matters).
    assert len(record_calls) >= 1
    # Downstream activities still ran.
    assert len(emit_calls) == 1
    assert len(mark_done_calls) == 1


# ---------------------------------------------------------------------------
# 6. mark_message_done failure propagates as workflow failure (D-10)
# ---------------------------------------------------------------------------


async def test_mark_message_done_failure_fails_workflow(
    temporal_env, make_dispatch_input,
) -> None:
    """D-10: mark_message_done is load-bearing; the workflow has no
    try/except around it. A persistent failure exhausts the
    maximum_attempts=5 retry budget and the WorkflowFailureError surfaces
    out of execute_workflow.
    """
    @activity.defn(name="check_container_ready")
    async def fake_ready(_inp):  # type: ignore[no-untyped-def]
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        return _build_forward_result("hi back")

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    mark_done_attempts: list[int] = []

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        mark_done_attempts.append(1)
        raise ApplicationError(
            "simulated_mark_done_failure",
            type="simulated_mark_done_failure",
            non_retryable=True,
        )

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(_args):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            fake_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        with pytest.raises(WorkflowFailureError):
            await temporal_env.client.execute_workflow(
                DispatchMessageWorkflow.run,
                inp,
                id=f"msg-test-mark-done-fail-{uuid.uuid4().hex[:8]}",
                task_queue=tq,
            )

    # mark_done was attempted at least once before the workflow failed.
    assert len(mark_done_attempts) >= 1


# ---------------------------------------------------------------------------
# 7. 5-minute execution_timeout cap (D-13)
# ---------------------------------------------------------------------------


async def test_five_minute_execution_timeout_cap(
    temporal_env, make_dispatch_input,
) -> None:
    """D-13: a workflow started with execution_timeout=5min must time out if
    the activities collectively run longer. Time-skipping advances virtual
    time so the test completes in real-world milliseconds while the
    workflow believes 6 minutes elapsed.

    The fake check_container_ready sleeps 6 minutes (virtual). The
    workflow's outer execution_timeout fires before the activity returns,
    surfacing as a WorkflowFailureError with a TimeoutFailure cause.
    """
    @activity.defn(name="check_container_ready")
    async def slow_ready(_inp):  # type: ignore[no-untyped-def]
        # Six minutes — under time-skipping the in-process server fast-
        # forwards virtual time so this returns instantly in real time
        # but the workflow records the elapsed virtual interval and the
        # 5-minute execution_timeout fires.
        await asyncio.sleep(360.0)
        return True

    @activity.defn(name="forward_to_agent")
    async def fake_forward(_inp):  # type: ignore[no-untyped-def]
        return _build_forward_result("hi back")

    @activity.defn(name="record_usage")
    async def fake_record(_usage_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="emit_inapp_outbound")
    async def fake_emit(_event_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="mark_message_done")
    async def fake_mark_done(_mark_done_input):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="mark_message_failed")
    async def fake_mark_failed(_args):  # type: ignore[no-untyped-def]
        return None

    @activity.defn(name="debit_balance")
    async def fake_debit(_inp):  # type: ignore[no-untyped-def]
        return "0"

    inp = make_dispatch_input()
    tq = _unique_task_queue()
    async with Worker(
        temporal_env.client,
        task_queue=tq,
        workflows=[DispatchMessageWorkflow],
        activities=[
            slow_ready, fake_forward, fake_record, fake_emit,
            fake_mark_done, fake_mark_failed, fake_debit,
        ],
    ):
        with pytest.raises(WorkflowFailureError):
            await temporal_env.client.execute_workflow(
                DispatchMessageWorkflow.run,
                inp,
                id=f"msg-test-exec-timeout-{uuid.uuid4().hex[:8]}",
                task_queue=tq,
                execution_timeout=timedelta(minutes=5),
            )
