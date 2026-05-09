"""Phase B Plan B-stripe-08 — debit_balance activity body (real ledger debit).

Contract preserved from Phase 28 D-22 (sealed call site in
``workflows/dispatch_message.py:194-205``):

  * ``@activity.defn(name="debit_balance")`` — wire name byte-identical.
  * Signature ``async def debit_balance(self, inp) -> str`` — accepts the
    workflow's ``DispatchMessageInput`` dataclass; returns Decimal-as-string.
    The Temporal JSON serializer cannot round-trip ``Decimal`` directly;
    callers recover losslessly via ``Decimal(<returned-str>)``.

Behavior (D-12 + D-13 + D-17 + D-22):

  * Read ``users.tier``; if not ``'ultra'``, return ``"0"`` — BYOK Free / Pro
    tiers pay the upstream provider directly (D-02), so we never debit them.
  * Read the latest ``usage_logs`` row for ``inp.message_id + inp.user_id``.
    If no row, or status != 'success', or cost_usd is null/zero → return
    ``"0"`` (D-13 — debit only on success).
  * Compute ``cost_cents = round(cost_usd * 100)``; ``cost_usd`` already has
    the ap_multiplier baked in at proxy time (``llm_proxy.py`` Phase 29 path).
  * Atomic INSERT debit row + UPDATE balance cache rebuild from SUM, both
    inside one ``conn.transaction()`` (D-17 ledger-as-truth via the
    Wave 1 ``services.ledger.debit_user`` helper).
  * Idempotent on UNIQUE(reference_id=usage_log.id, reference_type='usage_log')
    — Temporal retry produces no double-debit; ``debit_user`` catches the
    UniqueViolationError and returns the originally-debited Decimal.

Wave 0 spike-b (``tests/_spikes/spike_b_debit_activity_contract.py``)
proved the round-trip on a stripped-down body before this Wave 1 land.

Worker registration: ``temporal/worker.py`` instantiates
``DebitBalanceActivities(db_pool=db_pool)`` and registers
``debit_acts.debit_balance`` (the bound method) in the ``activities=`` list.
The ``workflows/dispatch_message.py`` workflow imports this module and
references ``debit_balance.debit_balance`` — that path resolves to the
module-level alias defined at the bottom of this file. Temporal's SDK
dispatches by the registered activity *name* (``"debit_balance"``), so
the unbound function reference and the registered bound method line up
on the wire.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from temporalio import activity

_log = logging.getLogger("api_server.temporal.debit_balance")


class DebitBalanceActivities:
    """Class-bound holder for the debit-balance activity (mirrors
    ``record_usage.RecordUsageActivities``).
    """

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="debit_balance")
    async def debit_balance(self, inp: Any) -> str:
        """Phase B body. Returns Decimal-as-string per Phase 28 D-22 contract.

        ``inp`` is the workflow's ``DispatchMessageInput`` dataclass (or a
        duck-typed object exposing ``user_id`` + ``message_id`` strings).
        """
        # Late import — keeps module import surface narrow at worker boot
        # (mirrors ``record_usage.py`` rationale).
        from ...services.ledger import debit_user
        from uuid import UUID

        user_uuid = UUID(inp.user_id)
        message_uuid = UUID(inp.message_id)

        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                # Bail when user is not platform-billed.
                tier = await conn.fetchval(
                    "SELECT tier FROM users WHERE id = $1", user_uuid,
                )
                if tier != "ultra":
                    return "0"

                # Read the usage_logs row written by ``llm_proxy.py``'s
                # ``_record_usage_from_parsed`` after the upstream stream
                # completed. ``ORDER BY created_at DESC LIMIT 1`` covers
                # the unlikely retry-shape where two rows exist for one
                # message_id (newest wins).
                row = await conn.fetchrow(
                    """
                    SELECT id, cost_usd, status FROM usage_logs
                    WHERE message_id = $1 AND user_id = $2
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    message_uuid, user_uuid,
                )
                if (
                    row is None
                    or row["status"] != "success"
                    or row["cost_usd"] is None
                ):
                    return "0"

                # Compute cents. ``cost_usd`` is a Decimal column; quantize
                # to whole cents so a row that recorded 0.00499 doesn't
                # cast to 0 via int() truncation. Round-half-even is the
                # Decimal default (banker's rounding) which is fine here —
                # the proxy's cost path quantizes to micro-USD already so
                # cents-rounding only affects sub-cent fragments.
                cost_cents = int(
                    (Decimal(str(row["cost_usd"])) * Decimal(100))
                    .quantize(Decimal("1"))
                )
                if cost_cents <= 0:
                    return "0"

                charged = await debit_user(
                    conn,
                    user_id=user_uuid,
                    cost_cents=cost_cents,
                    reference_id=str(row["id"]),
                    reference_type="usage_log",
                )
                _log.info(
                    "debit_balance.applied user_id=%s message_id=%s cents=%s",
                    user_uuid, message_uuid, cost_cents,
                )
                return str(charged)


# ---------------------------------------------------------------------------
# Backward-compatibility module-level alias (Phase 28 D-22 import path)
# ---------------------------------------------------------------------------
# The workflow file imports this module and references ``debit_balance.
# debit_balance`` as the activity callable handed to ``execute_activity``.
# That path now resolves to the unbound class method below; Temporal's
# SDK introspects ``@activity.defn(name="debit_balance")`` from the
# decorator and dispatches to whichever bound method the worker registered
# (``DebitBalanceActivities.debit_balance`` via ``debit_acts.debit_balance``).
#
# Mirrors the pattern in ``record_usage.py`` — except where ``record_usage``
# uses a NotImplementedError-raising standalone function as the alias,
# we expose the unbound method directly. The type-hint ignore is because
# ``debit_balance`` is overloaded between the class attribute and the
# module-level binding.

debit_balance = DebitBalanceActivities.debit_balance  # type: ignore[assignment]
