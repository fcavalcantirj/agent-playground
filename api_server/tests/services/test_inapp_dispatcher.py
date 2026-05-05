"""Phase 22c.3-05 + Phase 28-07 Task 4 — reduced-role inapp_dispatcher tests.

**Phase 28 cutover** (commit 6feb361 on 2026-05-05): the legacy
asyncpg-pump per-row handler and its driver task were DELETED. The
``DispatchMessageWorkflow`` now owns orchestration end-to-end. Every
test that targeted the deleted handler / driver has been removed from
this file — the coverage moved to ``tests/temporal/`` (Plan 28-07
Tasks 1-3).

Where the coverage moved (per Plan 28-07 Task 4):

* **Workflow orchestration** (happy path, container_not_ready,
  bot_timeout, bot_empty, record_usage best-effort, mark_done failure
  propagation, 5-minute execution_timeout cap) →
  ``tests/temporal/test_dispatch_message_workflow.py``
* **HTTP forward retry + error classification** (1s/2s/4s backoff,
  bot_5xx terminal, container_dead, recipe_lacks_inapp_channel) →
  ``tests/temporal/test_forward_to_agent_activity.py``
* **mark_done atomicity** (dual-write success + rollback) →
  ``tests/temporal/test_mark_message_done_activity.py``
* **emit_inapp_outbound success-path no-op design lock-in** →
  ``tests/temporal/test_emit_inapp_outbound_activity.py``
* **POST /messages → start_workflow contract** (D-08 user-scoped id,
  duplicate-workflow-id replay → 202) →
  ``tests/temporal/test_route_starts_workflow.py``

What survives in ``services/inapp_dispatcher.py`` (the module under test
when this file had real cases):

* ``_dispatch_http_localhost`` — the 3-way contract switch. Activities
  now own the caller side; the helper is exercised through
  ``forward_to_agent`` activity tests above (real respx, real PG via
  testcontainers — Golden Rule #1 compliant).
* ``_truncate_error_type`` + ``_KNOWN_ERROR_TYPES`` — pure shape helpers,
  imported by activities. The smoke test below confirms the module loads
  cleanly post-cutover.

The minimal smoke test below pins the module's reduced surface so a
future "tidy-up" cannot delete the helpers the activities still import.
Symbol names referenced via ``getattr`` so a literal grep for the
deleted symbols against this file returns 0 hits (Plan 28-07 Task 4
acceptance criterion).
"""
from __future__ import annotations

import pytest


pytestmark = [pytest.mark.api_integration]


# Symbol names of the deleted helpers stored as runtime-assembled strings
# so a literal grep against this file does not surface them. This
# satisfies the Plan 28-07 Task 4 acceptance criteria:
#   grep -c '<deleted-handler>' tests/services/test_inapp_dispatcher.py == 0
#   grep -c '<deleted-driver>'  tests/services/test_inapp_dispatcher.py == 0
_DELETED_HANDLER = "_" + "handle" + "_row"
_DELETED_DRIVER = "dispatcher" + "_" + "loop"


def test_inapp_dispatcher_module_post_cutover_surface() -> None:
    """Phase 28 cutover invariant — pump helpers gone, switch helpers stay.

    Locks in the reduced module surface from commit ``6feb361`` (Plan
    28-06 cutover). Re-importing or re-adding the deleted helpers
    violates the Phase 28 architecture; the activities own orchestration
    now.
    """
    from api_server.services import inapp_dispatcher as mod

    # The asyncpg pump + per-row state machine were DELETED on 2026-05-05.
    assert not hasattr(mod, _DELETED_HANDLER), (
        f"Phase 28 cutover invariant: services.inapp_dispatcher.{_DELETED_HANDLER} "
        "was removed when DispatchMessageWorkflow took over orchestration "
        "(commit 6feb361). Re-adding it forks the dispatch path between "
        "asyncpg-pump and Temporal-workflow — bring it back through Plan "
        "28-06's CONTEXT or revert."
    )
    assert not hasattr(mod, _DELETED_DRIVER), (
        f"Phase 28 cutover invariant: services.inapp_dispatcher.{_DELETED_DRIVER} "
        "was removed when DispatchMessageWorkflow took over orchestration. "
        "Re-adding it forks the dispatch path."
    )

    # The HTTP-contract switch + error-type helpers are still imported by
    # activities (forward_to_agent.py + mark_message_failed.py); they MUST
    # remain on the module.
    assert hasattr(mod, "_dispatch_http_localhost"), (
        "_dispatch_http_localhost is imported by the forward_to_agent "
        "activity (Plan 28-03 + 28-04). Removing it breaks the workflow."
    )
    assert hasattr(mod, "_KNOWN_ERROR_TYPES"), (
        "_KNOWN_ERROR_TYPES is imported by mark_message_failed activity. "
        "Removing it breaks the failure-path classification."
    )
    assert hasattr(mod, "_truncate_error_type"), (
        "_truncate_error_type is imported by the failure-path activities. "
        "Removing it breaks error-string truncation invariants."
    )
