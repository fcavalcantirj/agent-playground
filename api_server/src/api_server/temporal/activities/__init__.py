"""Phase 28 activity stubs.

Plan 03 places ``NotImplementedError``-raising stubs so the
:mod:`api_server.temporal.workflows.dispatch_message` workflow file can
import the activity function references at registration time without
running into circular-import or ``NameError`` failures.

Plan 04 replaces each stub body with the real implementation.

**Exception:** ``debit_balance`` keeps its ``Decimal('0')`` no-op body
per CONTEXT D-22 — the activity exists so the workflow shape is locked,
but the body stays a no-op until Phase B / Phase 29 swaps in real Stripe
credit-balance debit logic. Plan 04 does NOT replace ``debit_balance``.

The seven activities (names locked here, signatures in
:mod:`...workflows.dispatch_message` and :mod:`...workflows.types`):

- ``check_container_ready.check_container_ready``
- ``forward_to_agent.forward_to_agent``
- ``record_usage.record_usage``
- ``debit_balance.debit_balance``  (D-22 no-op stub)
- ``emit_inapp_outbound.emit_inapp_outbound``
- ``mark_message_done.mark_message_done``
- ``mark_message_failed.mark_message_failed``
"""
