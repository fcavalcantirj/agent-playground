"""Health / readiness routes.

Plan 19-06 creates a MINIMAL `/healthz` route so the log-redaction middleware
tests have a real downstream endpoint to exercise. Plan 19-02 (FastAPI skeleton
Wave) expands this file per 19-CONTEXT.md D-04:

    - `GET /healthz`: LB probe, always `{"ok": True}`, include_in_schema=False
    - `GET /readyz`:  operator probe, reports docker_daemon + postgres + recipe
                     count + concurrency — expanded by 19-02

Until Plan 19-02 lands, only the thin `/healthz` is available.

Rule 3 deviation (Plan 19-06): the Plan 19-06 `test_log_redact.py` tests
`from api_server.routes.health import router` — the minimal router below
satisfies that dependency. 19-02 will OVERWRITE this file with the full
CONTEXT.md D-04 implementation.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, bool]:
    """Load-balancer liveness probe. Always 200. Never touches deps."""
    return {"ok": True}
