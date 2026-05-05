"""Phase 28 Wave 0 — Spike B helper (activity module).

Imports the heavy infrastructure libraries (asyncpg, httpx, docker) that
the real ``forward_to_agent`` activity will pull in. The spike's purpose
is to prove the workflow file's

    with workflow.unsafe.imports_passed_through():
        from . import _phase28_b_activities

guard prevents the Python SDK sandbox from inspecting THIS module's
imports — i.e. asyncpg/httpx/docker do NOT trip
``RAISE_ON_UNINTENTIONAL_PASSTHROUGH`` warnings during workflow
registration, even though they are not deterministic-safe.

Closes RESEARCH §10 Assumption A2 empirically.
"""
from __future__ import annotations

# Intentional non-deterministic imports — we WANT the sandbox to refuse to
# enter this module. The workflow file's `imports_passed_through` context
# manager is the load-bearing seam.
import asyncpg  # noqa: F401
import docker  # noqa: F401
import httpx  # noqa: F401
from temporalio import activity


@activity.defn(name="spike_b_activity")
async def spike_b_activity(payload: str) -> str:
    """Echo the payload — proves the activity executes once registered."""
    return f"echo:{payload}"
