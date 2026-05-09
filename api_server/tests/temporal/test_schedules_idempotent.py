"""Phase B Plan B-stripe-09 Task 2 — register_schedules idempotency tests.

Real Temporal cluster (deploy stack must be up at ``localhost:7233``)
per CLAUDE.md golden rule #1 — Wave 0 spike D proved the typed
``ScheduleAlreadyRunningError`` against this exact infrastructure path,
and we replay the spike's contract here at the production helper layer.

If the deploy stack is not running the test SKIPS rather than fails —
local dev iterations should not gate on the stack. The dockerized e2e
matrix (tests/e2e/) brings the stack up unconditionally and runs this
file as part of the gate.

Coverage matrix per PLAN.md ``<behavior>``:

  * test_register_schedules_first_call_creates_all_three
  * test_register_schedules_second_call_updates_without_error  (Pitfall 8 fix proof)
"""
from __future__ import annotations

import os

import pytest

from api_server.temporal.schedules import (
    PRUNE_MESSAGES_SCHEDULE_ID,
    RECONCILE_LEDGER_SCHEDULE_ID,
    RECONCILE_STRIPE_SCHEDULE_ID,
    register_schedules,
)


pytestmark = pytest.mark.api_integration


_TEMPORAL_HOST = os.environ.get("AP_TEMPORAL_HOST", "localhost:7233")
_TEMPORAL_NAMESPACE = os.environ.get("AP_TEMPORAL_NAMESPACE", "default")
_TASK_QUEUE = os.environ.get(
    "AP_TEMPORAL_TASK_QUEUE_TEST",
    "ap-msgs-schedule-test",
)


async def _connect_or_skip():
    """Return a connected Temporal Client or skip the test."""
    try:
        from temporalio.client import Client

        client = await Client.connect(
            _TEMPORAL_HOST, namespace=_TEMPORAL_NAMESPACE,
        )
        return client
    except Exception as e:  # noqa: BLE001 — broad on purpose
        pytest.skip(
            f"Temporal cluster not reachable at {_TEMPORAL_HOST!r}: {e}"
        )


async def _delete_all_phase_b_schedules(client) -> None:
    """Best-effort delete of every Phase B schedule id (test isolation)."""
    from temporalio.service import RPCError

    for sid in (
        PRUNE_MESSAGES_SCHEDULE_ID,
        RECONCILE_STRIPE_SCHEDULE_ID,
        RECONCILE_LEDGER_SCHEDULE_ID,
    ):
        try:
            handle = client.get_schedule_handle(sid)
            await handle.delete()
        except RPCError:
            # Not found / already completed are fine.
            pass
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 1. First call creates all three schedules
# ---------------------------------------------------------------------------


async def test_register_schedules_first_call_creates_all_three() -> None:
    """All 3 Phase B schedules exist after the first registration."""
    client = await _connect_or_skip()

    # Pre-clean any residue from a prior crashed test run.
    await _delete_all_phase_b_schedules(client)

    try:
        await register_schedules(client, _TASK_QUEUE)
        # Each schedule resolves via get_schedule_handle().describe();
        # absence raises RPCError("not found").
        for sid in (
            PRUNE_MESSAGES_SCHEDULE_ID,
            RECONCILE_STRIPE_SCHEDULE_ID,
            RECONCILE_LEDGER_SCHEDULE_ID,
        ):
            handle = client.get_schedule_handle(sid)
            desc = await handle.describe()
            assert desc.id == sid
    finally:
        await _delete_all_phase_b_schedules(client)


# ---------------------------------------------------------------------------
# 2. Second call updates without error (Pitfall 8 — typed exception path)
# ---------------------------------------------------------------------------


async def test_register_schedules_second_call_updates_without_error() -> None:
    """Pitfall 8 mitigated. Second call falls into the update branch via
    typed ``ScheduleAlreadyRunningError``; no exception escapes.
    """
    client = await _connect_or_skip()

    await _delete_all_phase_b_schedules(client)

    try:
        # First call — creates.
        await register_schedules(client, _TASK_QUEUE)
        # Second call — must NOT raise; the helper's typed-exception
        # path takes the update branch.
        await register_schedules(client, _TASK_QUEUE)
        # Third call for extra safety — same outcome.
        await register_schedules(client, _TASK_QUEUE)

        # All 3 schedules still exist (update did not delete them).
        for sid in (
            PRUNE_MESSAGES_SCHEDULE_ID,
            RECONCILE_STRIPE_SCHEDULE_ID,
            RECONCILE_LEDGER_SCHEDULE_ID,
        ):
            handle = client.get_schedule_handle(sid)
            desc = await handle.describe()
            assert desc.id == sid
    finally:
        await _delete_all_phase_b_schedules(client)
