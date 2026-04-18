"""Pydantic models for recipe endpoints.

Three shapes:

- ``RecipeSummary`` — public projection used in list responses. Keeps
  field names snake_case on the API boundary while aliasing the original
  recipe paths (e.g. ``apiVersion`` stays camelCase on the schema side).
- ``RecipeListResponse`` — wraps ``list[RecipeSummary]``.
- ``RecipeDetailResponse`` — the full dict passthrough for
  ``GET /v1/recipes/{name}``. v0.1 has no private fields so the entire
  recipe dict is emitted verbatim.

Field mapping (recipe path → model field):

===============================  =================
Recipe path                       Model field
===============================  =================
``apiVersion``                    ``api_version``
``source.repo``                   ``source_repo``
``source.ref``                    ``source_ref``
``runtime.provider``              ``provider``
``smoke.pass_if``                 ``pass_if``
``metadata.license``              ``license``
``metadata.maintainer``           ``maintainer``
===============================  =================

The plan's prose used ``source.url`` + ``runtime.family`` but those paths
don't exist in ``ap.recipe/v0.1``; the actual schema uses ``source.repo``
+ ``runtime.provider``. The service layer maps from the canonical schema
paths into these summary fields (documented as a Rule-1 bug fix in the
plan SUMMARY).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RecipeSummary(BaseModel):
    """Public projection of a recipe suitable for list responses."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    api_version: str = Field(..., alias="apiVersion")
    display_name: str | None = None
    description: str | None = None
    upstream_version: str | None = None
    image_size_gb: float | None = None
    expected_runtime_seconds: float | None = None
    source_repo: str | None = None
    source_ref: str | None = None
    provider: str | None = None
    pass_if: str | None = None
    license: str | None = None
    maintainer: str | None = None
    # v0.2 channels fields (Phase 22 plan 22-01). Surface the recipe's
    # ``persistent:`` + ``channels:`` blocks so the frontend can gate
    # deploy-form Step 2.5 without a second request. None-safe: recipes
    # that don't declare channels return empty/absent values.
    persistent_mode_available: bool = False
    # ``recipe["channels"]`` keys in iteration order (e.g. ["telegram"]).
    channels_supported: list[str] = Field(default_factory=list)
    # ``{channel_id: {supported: [...], deferred: [...]}}`` — only populated
    # when at least one channel declares ``provider_compat`` (openclaw-only
    # today). Lets the frontend swap BYOK key copy (OpenRouter → Anthropic)
    # for recipes with known-broken provider paths.
    channel_provider_compat: dict[str, dict[str, list[str]]] | None = None
    verified_models: list[str] = Field(default_factory=list)


class RecipeListResponse(BaseModel):
    recipes: list[RecipeSummary]


class RecipeDetailResponse(BaseModel):
    """Full dict passthrough for ``GET /v1/recipes/{name}``.

    Phase 19 has no private fields to strip; the entire recipe dict is
    emitted. Future phases that introduce secret fields (e.g. maintainer
    email, private-registry credentials) MUST replace this passthrough
    with an explicit projection.
    """

    recipe: dict
