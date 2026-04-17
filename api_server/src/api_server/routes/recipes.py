"""Recipe catalog + lint endpoints.

- ``GET /recipes`` — list all loaded recipes as ``RecipeSummary`` projections
  (name + apiVersion + source + provider + pass_if + license + maintainer).
- ``GET /recipes/{name}`` — return the full recipe dict. 404 with a
  Stripe-shape envelope for unknown names.
- ``POST /lint`` — lint a YAML body (up to 256 KiB) against the recipe
  schema. Always 200 with ``{"valid": bool, "errors": [...]}`` except for
  413 (oversize body, V5 mitigation) and 500 (unexpected internal error).

The recipe registry is populated at app startup by the lifespan in
``api_server.main`` (Plan 19-03 extension) — this module only reads
``request.app.state.recipes``.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope
from ..models.recipes import RecipeDetailResponse, RecipeListResponse
from ..services.lint_service import (
    LINT_BODY_MAX_BYTES,
    LintBodyTooLargeError,
    lint_yaml_bytes,
)
from ..services.recipes_loader import to_summary

router = APIRouter()


@router.get("/recipes", response_model=RecipeListResponse)
async def list_recipes(request: Request) -> RecipeListResponse:
    """Return all loaded recipes as public summaries."""
    recipes = request.app.state.recipes
    return RecipeListResponse(
        recipes=[to_summary(r) for r in recipes.values()]
    )


@router.get("/recipes/{name}")
async def get_recipe(request: Request, name: str):
    """Return the full recipe dict for ``name`` or 404."""
    recipes = request.app.state.recipes
    if name not in recipes:
        return JSONResponse(
            status_code=404,
            content=make_error_envelope(
                ErrorCode.RECIPE_NOT_FOUND,
                f"recipe {name!r} not found",
                param="name",
            ),
        )
    return RecipeDetailResponse(recipe=recipes[name]).model_dump()


@router.post("/lint")
async def lint_recipe(request: Request):
    """Lint a YAML body. 200 + ``{valid, errors}`` or 413 on oversize.

    Cheap pre-check on declared ``Content-Length`` rejects oversize
    payloads without even reading the body. Post-read size check catches
    chunked / content-length-lies. Internal errors (not expected) fall
    through to 500 so the global exception handler can shape them.
    """
    # Cheap pre-check: refuse before reading the body.
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > LINT_BODY_MAX_BYTES:
                return JSONResponse(
                    status_code=413,
                    content=make_error_envelope(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        f"request body exceeds {LINT_BODY_MAX_BYTES} bytes",
                    ),
                )
        except ValueError:
            # Malformed Content-Length — fall through to post-read check.
            pass
    body = await request.body()
    try:
        result = lint_yaml_bytes(body)
    except LintBodyTooLargeError as e:
        return JSONResponse(
            status_code=413,
            content=make_error_envelope(
                ErrorCode.PAYLOAD_TOO_LARGE,
                str(e),
            ),
        )
    return result.model_dump()
