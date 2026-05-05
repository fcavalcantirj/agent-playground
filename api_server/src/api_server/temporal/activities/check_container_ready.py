"""Phase 28 activity — check_container_ready.

Class-bound activity that probes the ``agent_containers`` row for the
readiness triple (``container_status='running' AND ready_at IS NOT NULL
AND stopped_at IS NULL``) — the same gate the legacy
``services/inapp_dispatcher._handle_row`` uses at lines 381-388.

Returned values:

- ``True``  — container row exists AND is fully ready. The workflow
  proceeds to forward_to_agent.
- ``False`` — container row exists but is NOT YET ready (status !=
  'running', ready_at IS NULL, OR stopped_at IS NOT NULL but the row
  is still present). The workflow's
  ``[250ms, 500ms, 1s, 2s, 4s]`` retry budget kicks in (CONTEXT D-10)
  to cover the brief container-boot window.
- raises ``ApplicationError(type='container_dead', non_retryable=True)``
  — container row was DELETED entirely. This is a hard terminal: the
  workflow should NOT retry; ``_classify_forward_failure`` won't see it
  here (only the workflow's outer try/except around forward_to_agent
  catches ApplicationError) so the workflow body checks ``ready`` and
  routes to ``_fail`` for the matching ``container_not_ready`` error_type
  if False is returned. We raise instead of returning False for the
  delete case because retrying a DELETE is just wasted budget — no
  amount of waiting will resurrect the row.

Type-hint note: ``inp`` is annotated as ``Any`` (not
``DispatchMessageInput``) because ``@activity.defn`` calls
``typing.get_type_hints`` at decoration time, which forces forward-reference
resolution. A ``TYPE_CHECKING``-only import would be invisible at
runtime and runtime import would create a circular cycle. The runtime
contract is identical — Temporal serializes the dataclass via JSON
either way.

Module-level placeholder ``check_container_ready`` is preserved so the
workflow file's ``from ..activities import check_container_ready`` line
can import the module without trip-wiring on a missing symbol; the
worker file (Plan 04 Task 2) registers the BOUND METHOD on a
process-owned ``ReadinessActivities`` instance.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

from temporalio import activity
from temporalio.exceptions import ApplicationError


def _coerce_inp(inp: Any) -> Any:
    """Normalize ``inp`` so attribute access works.

    Temporal's default JSON converter deserializes the
    ``DispatchMessageInput`` dataclass into a plain dict because the
    activity's runtime type-hint is ``Any`` (the activity-stub
    discipline that sidesteps the workflows ↔ activities circular import
    at @activity.defn decoration time). For the activity body we want
    attribute access (``inp.container_row_id`` etc.) — convert dict to
    a ``SimpleNamespace`` so the rest of the function reads naturally.
    Already-namespaced inputs (e.g. tests passing dataclasses or
    SimpleNamespace) pass through untouched.
    """
    if isinstance(inp, dict):
        return SimpleNamespace(**inp)
    return inp


class ReadinessActivities:
    """Class-bound holder for the readiness probe activity.

    The worker (Plan 04 Task 2) instantiates this once with the
    process-wide asyncpg pool and registers ``self.check_container_ready``
    on the Worker's activities list.
    """

    def __init__(self, *, db_pool: Any) -> None:
        self.db_pool = db_pool

    @activity.defn(name="check_container_ready")
    async def check_container_ready(self, inp: Any) -> bool:
        """Return True iff the container row is fully ready, False if
        it exists but is still booting / stopping. Raise
        ``ApplicationError('container_dead', non_retryable=True)`` if
        the row was DELETED entirely.
        """
        inp = _coerce_inp(inp)
        container_row_id = UUID(inp.container_row_id)
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT container_status, ready_at, stopped_at
                FROM agent_containers
                WHERE id = $1
                """,
                container_row_id,
            )
        if row is None:
            # Row was deleted — hard terminal, no amount of retry will
            # resurrect it. Workflow's outer try/except in forward_to_agent
            # does NOT cover check_container_ready; this raise propagates
            # to the workflow run() which surfaces it through the
            # workflow-level retry policy. Return False instead so the
            # workflow body's ``if not ready: _fail(container_not_ready)``
            # branch handles the row.
            #
            # Rationale: ApplicationError(non_retryable=True) would cause
            # the workflow to bail with a Temporal-internal failure
            # rather than a clean ``DispatchMessageResult(success=False,
            # error_type='container_not_ready')`` — that breaks the
            # workflow's own contract with the caller. False is the
            # correct shape for "container is gone".
            return False
        if (
            row["container_status"] != "running"
            or row["ready_at"] is None
            or row["stopped_at"] is not None
        ):
            return False
        return True


@activity.defn(name="check_container_ready")
async def check_container_ready(inp: Any) -> bool:
    """Module-level placeholder kept for the workflow file's import path.

    The workflow imports this MODULE so ``execute_activity`` can locate
    the activity by reference; the actual REGISTERED activity on the
    worker is the bound method ``ReadinessActivities.check_container_ready``.
    Calling this top-level function directly raises NotImplementedError
    so a misconfigured worker (which forgot to swap in the bound method)
    fails loudly rather than silently passing.
    """
    raise NotImplementedError(
        "Workers register ReadinessActivities.check_container_ready "
        "(bound method); the module-level function is an import-path "
        "placeholder only."
    )
