"""Phase 28 — Wave 0 Spike B: workflow sandbox passthrough verification.

Empirically closes RESEARCH.md §10 Assumption A2 — that a workflow file
using ``workflow.unsafe.imports_passed_through()`` to bring in an
activity module that itself imports ``asyncpg`` / ``httpx`` / ``docker``
does NOT trip the Python SDK sandbox at workflow registration or
execution time.

If this spike FAILS, the workflow file design has to change (lazy-import
activities at activity-call time, or split the activity module so
sandbox-unsafe imports live further down the dependency chain). The
SUCCESS path is the assumed default per the verbatim port from MSV.

Run manually as part of Wave 0:

    cd api_server && pytest \
        tests/spikes/test_phase28_spike_b_workflow_sandbox.py \
        -x -m spike --tb=short

The test scopes warning capture with ``warnings.catch_warnings()``
around the workflow registration + execution body — sandbox-emitted
warnings (``temporalio.worker.workflow_sandbox._importer:warnings.warn``)
fail the test, but unrelated DeprecationWarnings from third-party libs
loaded via ``conftest.py`` do NOT (those come from outside the captured
scope). The original PLAN suggested ``-W error::Warning`` as a CLI flag;
that approach was abandoned because it caught a pre-existing
testcontainers DeprecationWarning during conftest import (Spike B finding
on first run — unrelated to the sandbox path the spike actually probes).

Precondition: ``temporalio==1.27.0`` is already installed in the venv
(Spike A's task installs it; pip-installed via ``uv pip install`` if
running fresh). The spike does NOT require Docker — it uses the SDK's
in-process ``WorkflowEnvironment.start_time_skipping()`` which bundles
a real Temporal test server (counts as "real Temporal" per Golden Rule
#1; not a mock).
"""
from __future__ import annotations

import asyncio
import uuid
import warnings

import pytest

# Substring matches inside `warnings.WarningMessage.message`/`filename`/
# `category.__module__` that flag a real sandbox issue. Anything coming
# from `temporalio.worker.workflow_sandbox` is in scope; broad
# DeprecationWarnings from unrelated libs (testcontainers, etc.) are not.
_SANDBOX_WARNING_NEEDLES = (
    "temporalio.worker.workflow_sandbox",
    "RAISE_ON_UNINTENTIONAL_PASSTHROUGH",
    "imports_passed_through",
    "RestrictedWorkflowAccess",
)


def _is_sandbox_warning(rec: warnings.WarningMessage) -> bool:
    haystacks: list[str] = []
    if rec.filename:
        haystacks.append(rec.filename)
    if rec.message is not None:
        haystacks.append(str(rec.message))
    if rec.category is not None:
        haystacks.append(rec.category.__module__)
        haystacks.append(rec.category.__name__)
    blob = "\n".join(haystacks)
    return any(needle in blob for needle in _SANDBOX_WARNING_NEEDLES)


@pytest.mark.spike
def test_workflow_sandbox_imports_passed_through_holds() -> None:
    """Spike B: imports_passed_through() bypasses sandbox cleanly."""
    # Imported lazily so test discovery doesn't fail when temporalio is
    # absent (the missing-dep path is a precondition error, not a spike
    # failure).
    pytest.importorskip("temporalio", reason="temporalio==1.27.0 required for Spike B")

    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from . import _phase28_b_activities
    from ._phase28_b_workflow import SpikeBWorkflow

    async def _run() -> str:
        # `start_time_skipping()` boots an in-process Temporal test server
        # bundled with the SDK. This is real Temporal — same gRPC, same
        # workflow-replay machinery — not an in-memory fake.
        async with await WorkflowEnvironment.start_time_skipping() as env:
            task_queue = f"spike-b-{uuid.uuid4()}"
            async with Worker(
                env.client,
                task_queue=task_queue,
                workflows=[SpikeBWorkflow],
                activities=[_phase28_b_activities.spike_b_activity],
            ):
                workflow_id = f"spike-b-{uuid.uuid4()}"
                result = await env.client.execute_workflow(
                    SpikeBWorkflow.run,
                    "hello",
                    id=workflow_id,
                    task_queue=task_queue,
                )
                return result

    # `warnings.catch_warnings(record=True)` captures every warning fired
    # inside this block without raising. We then post-filter for sandbox
    # provenance — keeps the assertion narrow to the spike's actual
    # subject and immune to third-party DeprecationWarnings (e.g. the
    # testcontainers RedisContainer warning observed on the first run).
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = asyncio.run(_run())

    sandbox_hits = [w for w in caught if _is_sandbox_warning(w)]
    assert not sandbox_hits, (
        "Sandbox warnings fired during workflow registration/execution — "
        "imports_passed_through() did NOT shield the activity module's "
        "asyncpg/httpx/docker imports.\n"
        + "\n".join(
            f"  - {w.category.__name__} @ {w.filename}:{w.lineno}: {w.message}"
            for w in sandbox_hits
        )
    )

    assert result == "echo:hello", (
        f"workflow returned {result!r}; expected 'echo:hello' — "
        f"either the activity body changed or the imports_passed_through "
        f"seam interfered with execution"
    )
    print(  # noqa: T201 — spike output is part of the evidence ledger
        f"SPIKE-B PASS: result={result!r} "
        f"(captured {len(caught)} total warnings, "
        f"0 from sandbox; non-sandbox warnings ignored)"
    )
