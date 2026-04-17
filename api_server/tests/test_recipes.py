"""Tests for the /v1/recipes endpoint family (SC-04).

Exercises:

- ``GET /v1/recipes`` returns exactly the 5 committed recipes
  (hermes, nanobot, nullclaw, openclaw, picoclaw).
- ``GET /v1/recipes/{name}`` returns the full recipe dict for a valid
  name.
- Unknown names return 404 with the ``RECIPE_NOT_FOUND`` envelope.

All tests are marked ``api_integration`` because they spin up the full
FastAPI app which loads the 5 recipes at lifespan startup.
"""
from __future__ import annotations

import pytest

EXPECTED_RECIPES = {"hermes", "nanobot", "nullclaw", "openclaw", "picoclaw"}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_list_recipes_returns_five(async_client):
    r = await async_client.get("/v1/recipes")
    assert r.status_code == 200
    body = r.json()
    names = {item["name"] for item in body["recipes"]}
    assert names == EXPECTED_RECIPES
    # FastAPI serializes response models with ``by_alias=True`` by default,
    # so the wire key is the alias ``apiVersion`` (matching the recipe YAML
    # field name) rather than the snake_case Python attribute.
    for item in body["recipes"]:
        assert item["apiVersion"] == "ap.recipe/v0.1"


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
