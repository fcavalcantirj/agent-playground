"""Phase B Plan B-stripe-09 — idempotent Temporal schedule registration.

Helper that registers Phase B's three scheduled workflows
(prune_messages daily, reconcile_stripe every 5 min, reconcile_ledger
nightly) and survives a second-boot create attempt without crashing.

Idempotency discipline (Wave 0 spike D — see
``tests/_spikes/spike_d_temporal_schedule.py``):

  * Catch typed :class:`temporalio.client.ScheduleAlreadyRunningError`
    FIRST. Wave 0 spike D proved this is what Temporal SDK 1.27.x raises
    on a colliding ``create_schedule``. RESEARCH §Pattern 4 / PATTERNS.md
    were wrong on this point — they recommended catching ``RPCError``
    and string-matching ``"already exists"``.
  * Keep the ``RPCError`` substring fallback as defense-in-depth in case
    a future SDK version changes the typed surface.

Without this guard the worker (and the api_server's redundant lifespan
call) crash-loop on the second boot — Pitfall 8 in
``B-stripe-RESEARCH.md``. Spike D documents the exact behavior of the
1.27.x SDK.

Schedule cadences match the plan frontmatter:

  * ``phase-b-prune-messages-daily``      — cron ``0 3 * * *`` (03:00 UTC)
  * ``phase-b-reconcile-stripe-5min``     — interval ``timedelta(minutes=5)``
  * ``phase-b-reconcile-ledger-nightly``  — cron ``30 4 * * *`` (04:30 UTC,
                                            after daily prune)

Caller pattern: ``register_schedules`` is called from BOTH the worker
process and the api_server lifespan after the Temporal client connects.
The redundant call ensures the schedules exist even if the worker boots
later (or vice versa); the helper's idempotency makes the redundancy
free of side effects.
"""
from __future__ import annotations

import logging
from datetime import timedelta

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

from .workflows.prune_messages import PruneMessagesWorkflow
from .workflows.reconcile_ledger import ReconcileLedgerWorkflow
from .workflows.reconcile_stripe import ReconcileStripeWorkflow


_log = logging.getLogger("api_server.temporal.schedules")


# Schedule IDs (canonical — used by the helper AND by ops tooling like
# ``tctl schedule describe``). Exposed for tests + ops scripts.
PRUNE_MESSAGES_SCHEDULE_ID = "phase-b-prune-messages-daily"
RECONCILE_STRIPE_SCHEDULE_ID = "phase-b-reconcile-stripe-5min"
RECONCILE_LEDGER_SCHEDULE_ID = "phase-b-reconcile-ledger-nightly"


async def _create_or_update(
    client: Client, *, schedule_id: str, schedule: Schedule,
) -> str:
    """Create the schedule, or update if it already exists.

    Returns ``"created"`` or ``"updated"`` so callers / tests can assert
    on the action taken. Wave 0 spike D proved this idempotency shape
    against a real Temporal cluster.

    The typed ``ScheduleAlreadyRunningError`` is the canonical signal in
    Temporal SDK 1.27.x; the ``RPCError`` substring fallback is purely
    defensive — covers future SDK versions that might change the typed
    surface back to a generic gRPC error.
    """
    try:
        await client.create_schedule(schedule_id, schedule)
        _log.info("temporal.schedule.created id=%s", schedule_id)
        return "created"
    except ScheduleAlreadyRunningError:
        handle = client.get_schedule_handle(schedule_id)
        await handle.update(lambda _input: ScheduleUpdate(schedule=schedule))
        _log.info("temporal.schedule.updated id=%s", schedule_id)
        return "updated"
    except RPCError as e:
        # Defense-in-depth — should never fire against 1.27.x but covers
        # SDK versions that surface the condition as RPCError instead of
        # the typed exception above.
        msg = str(e).lower()
        if "already exists" in msg or "already running" in msg:
            handle = client.get_schedule_handle(schedule_id)
            await handle.update(
                lambda _input: ScheduleUpdate(schedule=schedule)
            )
            _log.info(
                "temporal.schedule.updated_via_rpc_fallback id=%s",
                schedule_id,
            )
            return "updated"
        raise


def _build_prune_messages_schedule(task_queue: str) -> Schedule:
    """Daily 03:00 UTC schedule for PruneMessagesWorkflow."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            PruneMessagesWorkflow.run,
            id="prune-messages",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(cron_expressions=["0 3 * * *"]),
    )


def _build_reconcile_stripe_schedule(task_queue: str) -> Schedule:
    """Every-5-minute interval schedule for ReconcileStripeWorkflow."""
    return Schedule(
        action=ScheduleActionStartWorkflow(
            ReconcileStripeWorkflow.run,
            id="reconcile-stripe",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(
            intervals=[ScheduleIntervalSpec(every=timedelta(minutes=5))],
        ),
    )


def _build_reconcile_ledger_schedule(task_queue: str) -> Schedule:
    """Nightly 04:30 UTC schedule for ReconcileLedgerWorkflow.

    Scheduled after the daily prune (03:00 UTC) so the ledger reconcile
    sees the post-prune state. The retention prune doesn't touch
    credit_transactions / credit_balances directly, but ordering keeps
    the diagnostic narrative simple in Temporal Web UI.
    """
    return Schedule(
        action=ScheduleActionStartWorkflow(
            ReconcileLedgerWorkflow.run,
            id="reconcile-ledger",
            task_queue=task_queue,
        ),
        spec=ScheduleSpec(cron_expressions=["30 4 * * *"]),
    )


async def register_schedules(client: Client, task_queue: str) -> None:
    """Idempotent registration of Phase B's 3 scheduled workflows.

    Run once at ``api_server`` boot AND once at temporal-worker boot —
    second invocation falls into the update branch instead of crashing
    (Pitfall 8). The redundancy is intentional: it ensures schedules
    exist even if the worker boots later (or vice versa).
    """
    await _create_or_update(
        client,
        schedule_id=PRUNE_MESSAGES_SCHEDULE_ID,
        schedule=_build_prune_messages_schedule(task_queue),
    )
    await _create_or_update(
        client,
        schedule_id=RECONCILE_STRIPE_SCHEDULE_ID,
        schedule=_build_reconcile_stripe_schedule(task_queue),
    )
    await _create_or_update(
        client,
        schedule_id=RECONCILE_LEDGER_SCHEDULE_ID,
        schedule=_build_reconcile_ledger_schedule(task_queue),
    )
    _log.info(
        "temporal.schedules.registered task_queue=%s ids=%s",
        task_queue,
        (
            PRUNE_MESSAGES_SCHEDULE_ID,
            RECONCILE_STRIPE_SCHEDULE_ID,
            RECONCILE_LEDGER_SCHEDULE_ID,
        ),
    )


__all__ = [
    "register_schedules",
    "PRUNE_MESSAGES_SCHEDULE_ID",
    "RECONCILE_STRIPE_SCHEDULE_ID",
    "RECONCILE_LEDGER_SCHEDULE_ID",
]
