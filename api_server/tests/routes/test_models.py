"""Phase 23-05 (REQ API-04 + D-18..D-20 + D-25) — GET /v1/models tests.

Plan 23-05 implements an OpenRouter `/api/v1/models` passthrough proxy
with:
  * 15-min in-process TTL cache (D-18)
  * asyncio.Lock dedupe of concurrent first-fetches (RESEARCH §6)
  * Stale-while-revalidate on upstream failure (D-18)
  * 503 INFRA_UNAVAILABLE envelope on cold-start failure
  * Cache-Control: private, max-age=300 (RESEARCH §Q2 RESOLVED)
  * GZipMiddleware compression for >=1024-byte responses (D-25)
  * Byte-for-byte passthrough — no JSON parse/re-serialize (D-20)

Real Postgres + Redis via testcontainers (golden rule #1 — no mocks).
The upstream OpenRouter HTTP call is the ONLY thing stubbed (via respx);
state mutations are made directly against the real
``app.state.models_cache`` dict the lifespan provisioned.

Coverage matrix (6 tests):
  * cache miss → upstream fetched once, body byte-equal, content-type JSON
  * cache hit within TTL → upstream NOT called, body byte-equal cached
  * stale-while-revalidate → upstream returns 5xx, prior payload survived
  * cold-start failure → no cache + upstream 5xx → 503 + envelope
  * gzip header set when client advertises Accept-Encoding: gzip
  * Cache-Control header overrides upstream no-store with private, max-age=300
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


def _state(async_client):
    """Return the FastAPI ``app.state`` for the running ASGI app.

    The conftest ``async_client`` wires the FastAPI app via httpx's
    ``ASGITransport``; the canonical access path used elsewhere in the
    suite (e.g. tests/auth/test_google_authorize.py) is
    ``async_client._transport.app.state``.
    """
    return async_client._transport.app.state


@respx.mock
async def test_get_models_cache_miss_fetches_and_caches(async_client):
    """Cache miss → upstream is called once; body is byte-equal passthrough."""
    fake_payload = b'{"data":[{"id":"a","name":"alpha"}]}'
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, content=fake_payload),
    )
    state = _state(async_client)
    state.models_cache.clear()

    r = await async_client.get("/v1/models")

    assert r.status_code == 200, r.text
    assert r.content == fake_payload  # byte-equal passthrough (D-20)
    assert r.headers["content-type"].startswith("application/json")
    assert route.call_count == 1, f"expected 1 upstream call, got {route.call_count}"


@respx.mock
async def test_get_models_cache_hit_within_ttl_skips_upstream(async_client):
    """Pre-warmed cache + within-TTL request: upstream MUST NOT be called."""
    fake_payload = b'{"data":[{"id":"a"}]}'
    route = respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, content=fake_payload),
    )
    state = _state(async_client)
    state.models_cache.clear()
    state.models_cache["payload"] = fake_payload
    state.models_cache["fetched_at"] = datetime.now(timezone.utc)

    r = await async_client.get("/v1/models")

    assert r.status_code == 200, r.text
    assert r.content == fake_payload
    assert route.call_count == 0, "upstream MUST NOT be called when cache is fresh"


@respx.mock
async def test_get_models_swr_on_upstream_failure(async_client):
    """Cache stale (>TTL) + upstream 5xx → serve stale (D-18 SWR)."""
    stale_payload = b'{"data":[{"id":"stale"}]}'
    state = _state(async_client)
    state.models_cache.clear()
    state.models_cache["payload"] = stale_payload
    # fetched_at older than _CACHE_TTL (15min) → forces refresh attempt
    state.models_cache["fetched_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=20)
    )
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(503, content=b"upstream gone"),
    )

    r = await async_client.get("/v1/models")

    assert r.status_code == 200, r.text  # SWR — served stale, NOT 503
    assert r.content == stale_payload


@respx.mock
async def test_get_models_cold_start_failure_returns_503(async_client):
    """No cache + upstream failure → 503 envelope with INFRA_UNAVAILABLE."""
    state = _state(async_client)
    state.models_cache.clear()  # no prior payload
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(500),
    )

    r = await async_client.get("/v1/models")

    assert r.status_code == 503, r.text
    body = r.json()
    assert "error" in body, body
    assert body["error"]["code"] in (
        "INFRA_UNAVAILABLE",
        "SERVICE_UNAVAILABLE",
    ), body


@respx.mock
async def test_get_models_gzip_header_when_requested(async_client):
    """Accept-Encoding: gzip + payload >1024B → response gzipped (D-25)."""
    # Build a >1024-byte JSON payload so GZipMiddleware engages.
    large_payload = (
        b'{"data":['
        + b','.join(b'{"id":"x"}' for _ in range(200))
        + b']}'
    )
    assert len(large_payload) > 1024
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(200, content=large_payload),
    )
    state = _state(async_client)
    state.models_cache.clear()

    r = await async_client.get(
        "/v1/models",
        headers={"Accept-Encoding": "gzip"},
    )

    assert r.status_code == 200, r.text
    # httpx auto-decodes gzip; assert the wire was compressed.
    assert r.headers.get("content-encoding") == "gzip", dict(r.headers)


@respx.mock
async def test_get_models_cache_control_header(async_client):
    """Q2 RESOLVED: response sets Cache-Control: private, max-age=300 so
    a mobile reload within 5min skips the round-trip. Complements the
    15min in-process server cache.
    """
    fake_payload = b'{"data":[{"id":"a"}]}'
    respx.get("https://openrouter.ai/api/v1/models").mock(
        return_value=httpx.Response(
            200,
            content=fake_payload,
            # Simulate OpenRouter's upstream Cache-Control to prove we OVERRIDE it.
            headers={"Cache-Control": "private, no-store"},
        ),
    )
    state = _state(async_client)
    state.models_cache.clear()

    r = await async_client.get("/v1/models")

    assert r.status_code == 200, r.text
    cc = r.headers.get("cache-control", "")
    assert "private" in cc.lower(), f"missing private directive: {cc!r}"
    assert "max-age=300" in cc.lower(), f"missing max-age=300: {cc!r}"
    # Critically, the upstream no-store hint MUST NOT leak through.
    assert "no-store" not in cc.lower(), f"upstream no-store leaked: {cc!r}"
