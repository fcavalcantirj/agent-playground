"""Tests for the /v1/schemas endpoint family (SC-03).

Exercises:

- ``GET /v1/schemas`` returns exactly ``["ap.recipe/v0.1"]``.
- ``GET /v1/schemas/ap.recipe/v0.1`` returns a ``{version, schema}``
  envelope whose ``schema`` field has a ``$schema`` key (i.e. a real
  JSON Schema document, not an error envelope).
- Unknown versions return 404 with the Stripe-shape error envelope and a
  non-empty ``request_id`` (proves ``CorrelationIdMiddleware`` wired it).

All tests are marked ``api_integration`` because they spin up the full
FastAPI app (which in turn loads the 5 committed recipes at lifespan
startup via ``load_all_recipes``).
"""
from __future__ import annotations

import pytest


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_list_schemas(async_client):
    r = await async_client.get("/v1/schemas")
    assert r.status_code == 200
    assert r.json() == {"schemas": ["ap.recipe/v0.1"]}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_get_schema_doc(async_client):
    r = await async_client.get("/v1/schemas/ap.recipe/v0.1")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "ap.recipe/v0.1"
    # Real JSON Schema documents declare a $schema URI.
    assert "$schema" in body["schema"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_unknown_schema_404(async_client):
    r = await async_client.get("/v1/schemas/ap.recipe/v9.9")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "SCHEMA_NOT_FOUND"
    assert body["error"]["type"] == "not_found"
    # Plan 19-06 wires CorrelationIdMiddleware as outermost; the
    # request_id field must be populated (not "unknown").
    assert body["error"]["request_id"]
    assert body["error"]["request_id"] != "unknown"
