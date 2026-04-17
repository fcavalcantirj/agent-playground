"""Tests for ``/healthz`` + ``/readyz`` per 19-CONTEXT.md D-04 (SC-02).

Two tiers:

1. ``test_healthz_is_trivial`` — runs without Postgres or any fixture,
   builds a minimal FastAPI app with just the health router, and asserts
   ``/healthz`` returns 200 + ``{"ok": True}``. Proves the D-04 invariant
   that ``/healthz`` does not touch Postgres.
2. ``test_readyz_live`` — marked ``api_integration``; uses the full
   ``async_client`` fixture (testcontainers Postgres + migrated schema +
   httpx) and asserts the rich ``/readyz`` envelope shape.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_healthz_is_trivial():
    """``GET /healthz`` returns ``{"ok": True}`` without any Postgres fixture.

    The test intentionally builds a bare FastAPI app (no lifespan, no
    middleware, no Postgres pool) and only mounts the health router.
    A passing assertion proves ``/healthz`` does not depend on anything
    the rest of the app wires up — the D-04 LB-probe invariant.
    """
    from fastapi import FastAPI

    from api_server.routes.health import router

    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_readyz_live(async_client):
    """``GET /readyz`` returns the full envelope against a real Postgres.

    Asserts every key CONTEXT.md D-04 mandates. ``recipes_count`` is 0
    because Plan 19-03 (which loads ``recipes/*.yaml`` into
    ``app.state.recipes`` at startup) has not yet landed — Plan 03's own
    tests will raise this expectation.
    """
    response = await async_client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    for key in (
        "ok",
        "docker_daemon",
        "postgres",
        "schema_version",
        "recipes_count",
        "concurrency_in_use",
    ):
        assert key in body, f"missing key {key}"
    assert body["schema_version"] == "ap.recipe/v0.1"
    assert body["postgres"] is True
    assert body["recipes_count"] == 0
    assert body["concurrency_in_use"] == 0
