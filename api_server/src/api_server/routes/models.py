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

Bug fix 2026-05-04 (4-agent root-cause confirmation + empirical
OpenRouter catalog probe): added optional ``?provider=`` query param so
the wizard's model picker can show ONLY the candidates a recipe can
actually deploy with. openclaw's recipe routes Anthropic-direct (not via
OpenRouter); without filtering, the user picked an OpenAI model that
the recipe rejected. Filter accepts BOTH ``provider/`` AND ``~provider/``
prefixes — OpenRouter publishes routing aliases like
``~anthropic/claude-haiku-latest`` that point to the same underlying
model and are load-bearing in production (nanobot uses them).
"""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from ..models.errors import ErrorCode, make_error_envelope
from ..services.openrouter_models import get_models_payload

router = APIRouter()


@router.get("/models")
async def list_models(
    request: Request,
    provider: Literal["openrouter", "anthropic", "openai"] | None = Query(
        default=None,
        description=(
            "When set, return only models whose id starts with the "
            "provider prefix (e.g. anthropic/, openai/) — including "
            "routing aliases (~anthropic/...). Default (omitted) returns "
            "the full OpenRouter catalog."
        ),
    ),
):
    """RESEARCH §Q2: Cache-Control: private, max-age=300 — 5min mobile-side
    cache complements 15min in-process server cache. The HTTP cache key
    includes the query string, so ``?provider=anthropic`` and the
    no-param variant cache independently on the client.
    """
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
    # Hot path: no filter → byte-for-byte passthrough (D-20 preserved).
    if provider is None or provider == "openrouter":
        return Response(
            content=payload,
            media_type="application/json",
            headers={"Cache-Control": "private, max-age=300"},
        )
    # Filter path: parse, filter, re-serialize. The 371-row OpenRouter
    # catalog parses in <1ms; cost is negligible vs the cached upstream
    # round-trip the filter avoids. Both `provider/` and `~provider/`
    # routing-alias prefixes are accepted (Agent 4 nit — OpenRouter's
    # `~anthropic/claude-haiku-latest` etc. are load-bearing aliases).
    canonical = f"{provider}/"
    routing_alias = f"~{provider}/"
    data = json.loads(payload)
    rows = data.get("data") if isinstance(data, dict) else None
    if isinstance(rows, list):
        data["data"] = [
            row for row in rows
            if isinstance(row, dict)
            and isinstance(row.get("id"), str)
            and (
                row["id"].startswith(canonical)
                or row["id"].startswith(routing_alias)
            )
        ]
    return JSONResponse(
        content=data,
        headers={"Cache-Control": "private, max-age=300"},
    )
