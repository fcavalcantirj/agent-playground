"""Phase 28 activity — debit_balance (D-22 no-op stub).

UNIQUE among the Plan 28-03 activity stubs: the body here is the FINAL
shape, not a placeholder. Plan 04 does NOT replace this body.

Per CONTEXT D-22, the activity exists so the workflow shape is locked
in Phase 28 — Phase B / Phase 29 swaps in real Stripe credit-balance
debit logic by editing this file's body, but the workflow's
``execute_activity(debit_balance.debit_balance, inp, ...)`` call site
in :mod:`...workflows.dispatch_message` is untouched.

The function returns the string ``"0"`` so the workflow logs a
deterministic "0 currency units debited" trace through the run, which
is useful for the Phase B integration tests that will assert non-zero
debits once Stripe is wired. Plan 28-06 deviation Rule 1: the original
``Decimal('0')`` return was rejected by Temporal's default JSON
payload converter (``TypeError: Object of type Decimal is not JSON
serializable``). Returning a stringified decimal is the smallest fix
that preserves the future-proof "currency-units-as-string" precedent
(Phase B can decode via ``Decimal(<str>)`` without precision loss).
"""
from __future__ import annotations

from typing import Any

from temporalio import activity


@activity.defn(name="debit_balance")
async def debit_balance(inp: Any) -> str:
    """No-op debit (CONTEXT D-22). Returns ``"0"`` (string).

    Workflow retry policy: maximum_attempts=1, best-effort per D-22
    (the workflow swallows exceptions from this activity in Phase 28
    so it cannot break dispatch even after Phase B reshapes the body).
    Phase B replaces the body; the activity name + signature stay
    (string-encoded decimal: ``Decimal(returned_value)`` recovers the
    typed value losslessly).
    """
    return "0"
