"""SC-09 + threat tests for ``RateLimitMiddleware``.

Covers:

- **SC-09**: 11th ``POST /v1/runs`` within 1 min → 429 + ``Retry-After``.
- ``POST /v1/lint`` allows 120/min (no 429 under 100 requests).
- ``GET /v1/*`` allows 300/min (no 429 under 50 requests).
- T-19-05-01: ``X-Forwarded-For`` spoofing CANNOT bypass the limit
  when ``AP_TRUSTED_PROXY`` is unset (the default).

All tests use real Postgres via testcontainers (``async_client`` fixture
sets up the ASGI app against the migrated pool). ``mock_run_cell`` is
used for the POST /v1/runs paths so we don't spawn docker containers.
The lint path exercises the real lint service (no mock) — it's cheap
enough to run 100 times.
"""
from __future__ import annotations

import pytest

# Bearer token — never used upstream by these tests but required by
# POST /v1/runs for the 401 check. Any non-empty string works.
AUTH = {"Authorization": "Bearer sk-test"}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_429_after_limit(
    async_client, authenticated_cookie, mock_run_cell,
):
    """SC-09: the 11th POST /v1/runs in a 60s window returns 429.

    Phase 22c-06: all 11 POSTs carry the same authenticated_cookie so
    the rate-limit subject becomes ``user:<uuid>`` per the new
    user-scoped precedence in ``_subject_from_scope``.

    Regression gate for a subtle SQL bug in the original Pattern 4
    formula (``date_trunc('second', NOW()) - (epoch::bigint % W)*1s``)
    where ``::bigint`` rounds-to-nearest, not floor. The rounding split
    a single 117ms burst across two window-start rows (one at
    ``:59``, one at ``:00``) so the 11th request would silently land
    on a fresh counter with count=1. The fixed formula
    (``to_timestamp(floor(epoch / W) * W)``) produces one deterministic
    window_start per second.
    """
    mock_run_cell(verdict_category="PASS")
    headers = {**AUTH, "Cookie": authenticated_cookie["Cookie"]}
    # First 10 should all succeed (limit=10/min for the runs bucket).
    for i in range(10):
        r = await async_client.post(
            "/v1/runs",
            headers=headers,
            json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
        )
        assert r.status_code == 200, (
            f"request {i + 1} unexpectedly rate-limited: {r.text[:200]}"
        )
    # 11th must be blocked.
    r = await async_client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert r.status_code == 429, r.text
    ra = r.headers.get("retry-after")
    assert ra is not None and int(ra) >= 1
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["type"] == "rate_limit_error"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_lint_bucket_allows_higher_rate(async_client):
    """``POST /v1/lint`` has a 120/min cap — 100 requests must all pass."""
    # Minimal-but-valid-ish body; the lint verdict doesn't matter for
    # this test, only that the middleware lets the request reach the
    # handler. The handler always returns 200 (valid or not).
    body = b"name: x\napiVersion: ap.recipe/v0.1\n"
    for i in range(100):
        r = await async_client.post(
            "/v1/lint",
            content=body,
            headers={"Content-Type": "application/yaml"},
        )
        assert r.status_code == 200, (
            f"lint request {i + 1} rate-limited under 120/min cap: "
            f"{r.status_code} / {r.text[:200]}"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_get_bucket_300_per_min(async_client):
    """GET /v1/recipes 50 times — well under the 300/min GET cap."""
    for i in range(50):
        r = await async_client.get("/v1/recipes")
        assert r.status_code == 200, (
            f"GET request {i + 1} rate-limited under 300/min cap: "
            f"{r.status_code}"
        )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_spoofed_xff_ignored_when_no_trusted_proxy(
    async_client, authenticated_cookie, mock_run_cell,
):
    """T-19-05-01: ``X-Forwarded-For`` does NOT bypass the per-user limit.

    Phase 22c-06: the rate-limit subject is now ``user:<uuid>`` when a
    session cookie is present (superior to IP for authenticated traffic).
    XFF has no effect either way: when authenticated, user_id wins; when
    anonymous, the peer IP from ``scope["client"]`` wins (XFF ignored
    because ``AP_TRUSTED_PROXY`` is unset). This test exercises the
    authenticated path — varying XFF across 10 requests counts against
    the same user_id subject, and the 11th hits 429.
    """
    mock_run_cell(verdict_category="PASS")
    cookie = authenticated_cookie["Cookie"]
    for i in range(10):
        r = await async_client.post(
            "/v1/runs",
            headers={**AUTH, "Cookie": cookie, "X-Forwarded-For": f"10.0.0.{i}"},
            json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
        )
        assert r.status_code == 200, (
            f"request {i + 1} blocked; XFF should be ignored: {r.text[:200]}"
        )
    # All 10 slots consumed despite distinct XFF values — the 11th
    # with yet another XFF must still 429 because the user_id is the
    # same.
    r = await async_client.post(
        "/v1/runs",
        headers={**AUTH, "Cookie": cookie, "X-Forwarded-For": "99.99.99.99"},
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert r.status_code == 429, (
        "XFF spoofing bypassed the rate limit — T-19-05-01 failed"
    )
    assert r.headers.get("retry-after")
