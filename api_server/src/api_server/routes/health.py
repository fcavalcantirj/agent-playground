"""Health + readiness endpoints per 19-CONTEXT.md D-04.

Two endpoints with DIFFERENT contracts by design:

- ``GET /healthz`` (LB probe) — returns ``{"ok": true}`` unconditionally.
  Never touches Postgres, never touches Docker. A load balancer hitting
  this 60/s must not cascade into dep probes. ``include_in_schema=False``
  keeps it out of the public OpenAPI surface.

- ``GET /readyz`` (operator probe) — the rich envelope with
  ``docker_daemon``, ``postgres``, ``schema_version``, ``recipes_count``,
  ``concurrency_in_use``. Declared in the OpenAPI schema so deploy gates
  and operator tooling can parse it.

The docker probe shells out to ``docker version --format '{{.Server.Version}}'``
with a 5-second timeout (matches ``tools/run_recipe.py``'s
``DOCKER_DAEMON_PROBE_TIMEOUT_S``). The subprocess is sync so the call is
wrapped in ``asyncio.to_thread`` to avoid blocking the event loop.

This module replaces the minimal stub from Plan 19-06 (which shipped a
thin ``/healthz`` only so the log-redaction middleware tests had a
downstream endpoint). 19-06's SUMMARY §"Downstream Plan Integration"
explicitly flags that Plan 19-02 overwrites this file with the full shape.
"""
from __future__ import annotations

import asyncio
import subprocess

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

# Mirrors ``tools/run_recipe.py``'s constant so the two probes stay in
# lockstep. 5 seconds is the ceiling for a healthy docker daemon to
# respond to ``docker version``; anything slower is operationally sick.
DOCKER_DAEMON_PROBE_TIMEOUT_S = 5


class ReadyzResponse(BaseModel):
    """Rich readiness envelope consumed by operators + deploy gates."""

    ok: bool
    docker_daemon: bool
    postgres: bool
    schema_version: str
    recipes_count: int
    concurrency_in_use: int


def _probe_docker_sync() -> bool:
    """Return True iff ``docker version`` exits 0 within the timeout.

    Swallows every exception (including ``FileNotFoundError`` when the
    docker CLI is absent and ``subprocess.TimeoutExpired`` when the daemon
    hangs) so ``/readyz`` reports ``docker_daemon: false`` instead of
    throwing 500.
    """
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            timeout=DOCKER_DAEMON_PROBE_TIMEOUT_S,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


async def _probe_docker() -> bool:
    """Async wrapper — runs ``_probe_docker_sync`` off the event loop."""
    return await asyncio.to_thread(_probe_docker_sync)


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, bool]:
    """Load-balancer liveness probe. Always 200. Never touches deps.

    D-04 invariant: this endpoint MUST NOT depend on Postgres or Docker.
    An LB polling this 60/s must not cascade into dep probes.
    """
    return {"ok": True}


@router.get("/readyz", tags=["operational"], response_model=ReadyzResponse)
async def readyz(request: Request) -> ReadyzResponse:
    """Operator readiness probe with full dependency + concurrency state.

    ``ok`` is True iff BOTH docker and postgres are healthy. ``recipes_count``
    reflects ``app.state.recipes`` (Plan 19-03 populates at startup).
    ``concurrency_in_use`` is ``max_concurrent_runs - semaphore._value`` —
    i.e. runs currently in flight, not capacity remaining.
    """
    # Deferred import avoids a module-load cycle if db.py ever grows a
    # back-reference into routes. ``probe_postgres`` is a simple helper.
    from ..db import probe_postgres

    docker_ok = await _probe_docker()
    pg_ok = await probe_postgres(request.app.state.db)
    settings = request.app.state.settings
    sem = request.app.state.run_semaphore
    # ``Semaphore._value`` exposes remaining capacity. Subtracting from the
    # cap gives the *in-use* count, which is the operator-meaningful metric.
    concurrency_in_use = settings.max_concurrent_runs - sem._value
    return ReadyzResponse(
        ok=bool(docker_ok and pg_ok),
        docker_daemon=bool(docker_ok),
        postgres=bool(pg_ok),
        schema_version="ap.recipe/v0.1",
        recipes_count=len(request.app.state.recipes),
        concurrency_in_use=max(0, concurrency_in_use),
    )
