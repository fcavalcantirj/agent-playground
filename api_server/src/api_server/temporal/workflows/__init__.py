"""Temporal workflow definitions.

DETERMINISM RULES — read before adding any workflow file:

Workflow code runs inside Temporal's Python sandbox. The history
must be deterministic across replay; non-deterministic side effects
in workflow bodies break replay and corrupt history.

Allowed imports inside a workflow file (top-level):

- ``temporalio.workflow``
- ``temporalio.common`` (RetryPolicy, etc.)
- ``temporalio.exceptions`` (ApplicationError, etc.)
- ``datetime`` — but ONLY ``timedelta``. Never ``datetime.now`` /
  ``datetime.utcnow`` / ``datetime.today`` in workflow bodies. Use
  ``workflow.now()`` / ``workflow.time()`` if a timestamp is needed.
- ``dataclasses`` — frozen dataclasses for inputs/outputs are fine.
- ``typing`` — type hints only.
- ``uuid`` — type hints only. Never ``uuid.uuid4()`` in workflow
  bodies (use ``workflow.uuid4()``).

FORBIDDEN at workflow-file scope:

- ``httpx``, ``asyncpg``, ``redis``, ``docker``, ``subprocess`` —
  these are activity-only. The sandbox warns on unintentional
  passthrough; Wave 0 spike B confirmed
  ``workflow.unsafe.imports_passed_through()`` is the canonical
  escape hatch for importing the activity *function references*
  (the workflow needs the symbols to call ``execute_activity``;
  it never executes the activity bodies).
- ``os``, ``time``, ``random`` — non-deterministic in workflow context.
  Use ``workflow.now()`` / ``workflow.random()`` / etc.

ENFORCEMENT:

- Workflow file imports of activities MUST use the
  ``with workflow.unsafe.imports_passed_through():`` block.
- All workflow inputs/outputs MUST be primitive-typed dataclasses
  (frozen=True). UUID/datetime/Decimal are stringified before
  crossing the wire.
- Sandbox-passthrough warnings during ``Worker(...)`` registration
  are a hard error — the smoke test in Plan 28-03 Task 3 fails the
  build if any sandbox warning fires.
"""
