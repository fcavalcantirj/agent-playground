"""Tests for the /v1/recipes endpoint family (SC-04).

Exercises:

- ``GET /v1/recipes`` returns the committed recipes (Phase 22c.3-13
  expanded the original 5-recipe set with zeroclaw, so the test
  asserts the original 5 are present and the API surfaces the
  recipe-format ``apiVersion`` field consistently).
- ``GET /v1/recipes/{name}`` returns the full recipe dict for a valid
  name.
- Unknown names return 404 with the ``RECIPE_NOT_FOUND`` envelope.

All tests are marked ``api_integration`` because they spin up the full
FastAPI app which loads recipes at lifespan startup.
"""
from __future__ import annotations

import pytest

# The original 5 (Phase 19-03) — every release MUST keep these loadable.
# zeroclaw (Phase 22c.3-13) and any future additions are validated
# implicitly by the ``apiVersion`` per-item check below; the literal-set
# equality used to pin to exactly 5 caused a stale-assertion regression
# when zeroclaw landed.
ORIGINAL_RECIPES = {"hermes", "nanobot", "nullclaw", "openclaw", "picoclaw"}

# Phase 22c.3-10..14 bumped every recipe's ``apiVersion`` to ``v0.2`` to
# admit the ``channels.inapp`` block. The original v0.1 tag was never
# deleted from the supported-schemas registry, so the loader still
# accepts both. This whitelist is the recipe-format version (the YAML
# field), distinct from the wire-schema version reported by ``/readyz``.
ACCEPTED_RECIPE_VERSIONS = {"ap.recipe/v0.1", "ap.recipe/v0.2"}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_list_recipes_includes_original_five(async_client):
    r = await async_client.get("/v1/recipes")
    assert r.status_code == 200
    body = r.json()
    names = {item["name"] for item in body["recipes"]}
    # Original 5 are a hard floor — the catalog only ever grows.
    missing = ORIGINAL_RECIPES - names
    assert not missing, f"original recipes missing from /v1/recipes: {missing}"
    # FastAPI serializes response models with ``by_alias=True`` by default,
    # so the wire key is the alias ``apiVersion`` (matching the recipe YAML
    # field name) rather than the snake_case Python attribute. Every
    # recipe in the response — original or newly added — must declare a
    # supported recipe-format version.
    for item in body["recipes"]:
        assert item["apiVersion"] in ACCEPTED_RECIPE_VERSIONS, (
            f"recipe {item.get('name')!r} declares apiVersion="
            f"{item.get('apiVersion')!r}, not in {ACCEPTED_RECIPE_VERSIONS}"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_get_recipe_detail(async_client):
    r = await async_client.get("/v1/recipes/hermes")
    assert r.status_code == 200
    body = r.json()
    assert body["recipe"]["name"] == "hermes"
    # Full dict passthrough means sub-objects like ``runtime`` are present.
    assert "runtime" in body["recipe"]
    assert "smoke" in body["recipe"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_unknown_recipe_404(async_client):
    r = await async_client.get("/v1/recipes/bogus")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "RECIPE_NOT_FOUND"
    assert body["error"]["type"] == "not_found"
    assert body["error"]["param"] == "name"
    assert body["error"]["request_id"]
