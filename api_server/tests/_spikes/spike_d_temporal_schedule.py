"""Phase B Wave 0 spike D — Temporal schedule registration idempotency.

Proves the ``register_schedules`` helper template from RESEARCH §Pattern 4
survives a second-boot create attempt by catching ``RPCError`` with
``"already exists"`` and falling back to ``get_schedule_handle().update()``.

Without this guard the worker crash-loops on the second boot (Pitfall 8).
The exact ``RPCError`` message string is not contractually stable across
Temporal SDK versions; this spike documents what 1.27.x raises today so
Wave 1 can pin against the same SDK version.

Connects to the deploy stack's Temporal cluster (``localhost:7233``).
Cleans up the spike schedule on exit (try/finally with ``delete()``).

Run via::

    cd api_server && uv run --extra dev python tests/_spikes/spike_d_temporal_schedule.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta

from temporalio import workflow
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
    ScheduleUpdate,
)
from temporalio.service import RPCError


SCHEDULE_ID = "spike-d-test"
TASK_QUEUE = os.environ.get("AP_TEMPORAL_TASK_QUEUE", "ap-messages")
TEMPORAL_HOST = os.environ.get("AP_TEMPORAL_HOST", "localhost:7233")
NAMESPACE = os.environ.get("AP_TEMPORAL_NAMESPACE", "default")


@workflow.defn(name="SpikeDWorkflow")
class SpikeDWorkflow:
    """Trivial workflow used as the schedule's start_workflow target.

    This spike does NOT actually run the workflow — it only registers the
    schedule. The schedule's first scheduled execution is far in the
    future (1 hour interval, no immediate trigger), and we delete it
    before any execution fires. The workflow definition exists only so
    Temporal can validate the start_workflow target shape.
    """

    @workflow.run
    async def run(self) -> int:
        return 1


def _build_schedule() -> Schedule:
    """Return a Schedule with a 1-hour interval (effectively never fires
    during the spike's lifetime).
    """
    return Schedule(
        action=ScheduleActionStartWorkflow(
            SpikeDWorkflow.run,
            id=f"{SCHEDULE_ID}-wf",
            task_queue=TASK_QUEUE,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(hours=1))],
        ),
    )


async def _create_or_update(client: Client, *, schedule_id: str, schedule: Schedule) -> str:
    """The Wave 1 ``register_schedules`` template.

    Returns the action taken: ``"created"`` or ``"updated"``.

    DISCOVERY (Wave 0 spike-d): Temporal SDK 1.27.x raises a typed
    ``temporalio.client.ScheduleAlreadyRunningError`` (NOT a generic
    ``RPCError`` with ``"already exists"`` substring). The PATTERNS.md /
    RESEARCH §Pattern 4 string-match guidance is wrong; Wave 1 must
    catch the typed exception. Keep the RPCError fallback as
    defense-in-depth in case the SDK changes the typed surface.
    """
    try:
        await client.create_schedule(schedule_id, schedule)
        return "created"
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle(schedule_id)
        await handle.update(lambda _: ScheduleUpdate(schedule=schedule))
        return "updated"
    except RPCError as e:
        # Defense-in-depth fallback for SDK versions that surface the
        # condition as RPCError with a known substring instead of the
        # typed exception above.
        if "already exists" in str(e).lower() or "already running" in str(e).lower():
            handle = client.get_schedule_handle(schedule_id)
            await handle.update(lambda _: ScheduleUpdate(schedule=schedule))
            return "updated"
        raise


async def _run() -> int:
    print(f"Connecting to Temporal at {TEMPORAL_HOST} (ns={NAMESPACE}) ...")
    client = await Client.connect(TEMPORAL_HOST, namespace=NAMESPACE)

    # Pre-flight cleanup: if a previous spike crashed mid-test the schedule
    # may already exist. Delete it so the "first call creates" assertion
    # below is meaningful. Several "absent" shapes are tolerated:
    #   * "not found" — clean Temporal, no schedule has ever existed
    #   * "workflow execution already completed" — the scheduler-shadow
    #     workflow already terminated from a previous delete; the schedule
    #     is effectively gone.
    try:
        handle = client.get_schedule_handle(SCHEDULE_ID)
        await handle.delete()
        print(f"  pre-flight: deleted lingering schedule {SCHEDULE_ID!r}")
    except RPCError as e:
        msg = str(e).lower()
        if (
            "not found" in msg
            or "already completed" in msg
            or "does not exist" in msg
        ):
            pass  # expected on a clean run or after a prior delete
        else:
            raise

    try:
        schedule = _build_schedule()

        # ---- (a) first call — creates ------------------------------
        action_1 = await _create_or_update(
            client, schedule_id=SCHEDULE_ID, schedule=schedule,
        )
        assert action_1 == "created", (
            f"first call expected 'created', got {action_1!r}"
        )
        print(f"  (a) first call:  {action_1}")

        # ---- (b) second call — updates -----------------------------
        action_2 = await _create_or_update(
            client, schedule_id=SCHEDULE_ID, schedule=schedule,
        )
        assert action_2 == "updated", (
            f"second call expected 'updated', got {action_2!r} — "
            "register_schedules helper is NOT idempotent across boots"
        )
        print(f"  (b) second call: {action_2} (idempotent re-create OK)")

        # ---- (c) third call — also updates (consistency check) -----
        action_3 = await _create_or_update(
            client, schedule_id=SCHEDULE_ID, schedule=schedule,
        )
        assert action_3 == "updated"
        print(f"  (c) third call:  {action_3} (helper stays idempotent)")

    finally:
        # Cleanup — best-effort delete.
        try:
            handle = client.get_schedule_handle(SCHEDULE_ID)
            await handle.delete()
            print(f"  cleanup:        deleted {SCHEDULE_ID!r}")
        except Exception as e:  # noqa: BLE001
            print(f"  cleanup WARN: {e!r}")

    print("PASS spike-d")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
