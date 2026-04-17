"""Response models for the ``/v1/schemas`` endpoint family.

Two shapes:

- ``SchemasListResponse`` — the version string list from ``GET /v1/schemas``.
- ``SchemaDocResponse`` — the (version, JSON Schema body) pair from
  ``GET /v1/schemas/{version}``. The ``schema`` field carries the raw
  JSON Schema dict loaded from ``tools/ap.recipe.schema.json``.

Pydantic's ``BaseModel`` shadows a legacy ``.schema`` classmethod; to keep
the public JSON key literally ``"schema"`` without tripping the
BaseModel-shadow warning, the field is declared with a safe Python name
(``schema_body``) and aliased to ``schema`` via ``Field(alias=..., serialization_alias=...)``. Routes dump with ``by_alias=True`` so
clients see ``{"version": ..., "schema": {...}}``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SchemasListResponse(BaseModel):
    schemas: list[str]


class SchemaDocResponse(BaseModel):
    # ``populate_by_name`` lets the constructor accept either ``schema``
    # (alias, for external callers) or ``schema_body`` (field name, for
    # internal code). ``protected_namespaces=()`` silences the ``model_*``
    # prefix warnings Pydantic v2 emits by default.
    model_config = ConfigDict(populate_by_name=True, protected_namespaces=())

    version: str
    schema_body: dict[str, Any] = Field(
        ..., alias="schema", serialization_alias="schema"
    )
