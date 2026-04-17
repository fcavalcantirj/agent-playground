"""Schema registry endpoints.

- ``GET /schemas`` — list supported recipe schema versions. Today only
  ``ap.recipe/v0.1`` is live. Future versions (v0.2 per Phase 13) append
  to ``SUPPORTED_SCHEMAS`` and register an additional loader here.

- ``GET /schemas/{version:path}`` — return the raw JSON Schema dict for a
  given version. ``{version:path}`` lets the URL carry a slash
  (``ap.recipe/v0.1``). Unknown versions respond 404 with a Stripe-shape
  ``ErrorEnvelope`` (``code = SCHEMA_NOT_FOUND``).

The schema dict is loaded via ``services.lint_service.get_runner_schema``
which ultimately calls ``tools/run_recipe.py::_load_schema`` — keeps a
single source of truth for schema bytes.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..models.errors import ErrorCode, make_error_envelope
from ..models.schemas import SchemaDocResponse, SchemasListResponse
from ..services.lint_service import get_runner_schema

router = APIRouter()

# Append here when a new schema version ships. Keep the list ordered
# oldest-first; clients that only understand v0.1 read element 0 and
# proceed without breaking.
SUPPORTED_SCHEMAS = ["ap.recipe/v0.1"]


@router.get("/schemas", response_model=SchemasListResponse)
async def list_schemas() -> SchemasListResponse:
    """Return the list of supported recipe schema versions."""
    return SchemasListResponse(schemas=list(SUPPORTED_SCHEMAS))


@router.get("/schemas/{version:path}")
async def get_schema(version: str):
    """Return the JSON Schema dict for ``version``.

    ``version`` is slash-containing by design — clients hit
    ``/v1/schemas/ap.recipe/v0.1``. 404 with a Stripe-shape error
    envelope when the version is not in ``SUPPORTED_SCHEMAS``.
    """
    if version not in SUPPORTED_SCHEMAS:
        return JSONResponse(
            status_code=404,
            content=make_error_envelope(
                ErrorCode.SCHEMA_NOT_FOUND,
                f"schema version {version!r} not supported",
                param="version",
            ),
        )
    # ``by_alias=True`` serializes ``schema_body`` as ``"schema"`` on the
    # wire, matching the external contract (``{"version": ..., "schema": ...}``).
    return SchemaDocResponse(
        version=version, schema_body=get_runner_schema()
    ).model_dump(by_alias=True)
