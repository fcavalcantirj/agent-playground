"""GET /v1/models — OpenRouter catalog passthrough (Phase 23 Plan 05).

Single public route. Mirrors ``routes/recipes.py::list_recipes`` shape:
unauthenticated (D-19 — public catalog), thin handler, all caching
intelligence lives in ``services/openrouter_models.py``.

On success: returns the upstream payload bytes byte-for-byte (D-20
passthrough — no JSON parse / re-serialize) wrapped in a Starlette
``Response`` with ``media_type="application/json"`` and an explicit
``Cache-Control: private, max-age=300`` header (RESEARCH §Q2 RESOLVED —
overrides upstream OpenRouter's ``private, no-store`` so a Flutter app
reload within 5min skips the round-trip; complements the 15min in-process
server cache).

On upstream fetch failure with no cache available: returns 503 with the
shared Stripe-shape error envelope (``ErrorCode.INFRA_UNAVAILABLE``).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..models.errors import ErrorCode, make_error_envelope
from ..services.openrouter_models import get_models_payload

router = APIRouter()


@router.get("/models")
async def list_models(request: Request):
    """RESEARCH §Q2: Cache-Control: private, max-age=300 — 5min mobile-side
    cache complements 15min in-process server cache."""
    try:
        payload = await get_models_payload(request.app.state)
    except Exception:
        return JSONResponse(
            status_code=503,
            content=make_error_envelope(
                ErrorCode.INFRA_UNAVAILABLE,
                "OpenRouter catalog temporarily unavailable",
            ),
        )
    return Response(content=payload, media_type="application/json", headers={"Cache-Control": "private, max-age=300"})
