"""Phase B Plan B-stripe-03 Task 2 — billing-bucket rate-limit middleware tests.

Verifies that ``RateLimitMiddleware`` extends from runs/lint/get/chat/auth
to also cover ``/v1/billing/*`` (excluding the webhook path) per the
new ``billing`` bucket — 30 calls / 60s per (user, billing).

Coverage matrix (6 behaviors per PLAN <behavior>):

  * ``/v1/billing/packs``        → routed to billing bucket
  * ``/v1/billing/balance``      → routed to billing bucket
  * ``/v1/billing/transactions`` → routed to billing bucket
  * ``/v1/billing/webhook``      → NOT routed to billing bucket
    (Stripe is the sole caller; rate-limiting Stripe escalates its
    retry storm. The webhook's abuse-prevention surface is the
    HMAC signature + stripe_event_id UNIQUE — Wave 3 owns)
  * 31st call to a billing path inside the 60s window → 429 with
    Retry-After
  * Exhausting the billing bucket does NOT bleed into the runs bucket

Mirrors ``tests/middleware/test_chat_rate_limit.py`` shape — minimal
FastAPI app with Session + RateLimit middlewares + stub routes; real
Postgres testcontainer for the rate_limit_counters table.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from api_server.middleware.rate_limit import RateLimitMiddleware
from api_server.middleware.session import SessionMiddleware


pytestmark = pytest.mark.api_integration


def _normalize_testcontainers_dsn(raw: str) -> str:
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


class _MiniSettings:
    """Minimal stand-in for app.state.settings used by RateLimitMiddleware."""

    trusted_proxy = False


@pytest_asyncio.fixture
async def billing_rl_app(migrated_pg):
    """Minimal FastAPI app: Session + RateLimit + stub billing/runs/usage routes."""
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=3, command_timeout=5.0
    )
    app = FastAPI()
    app.state.db = pool
    app.state.session_last_seen = {}
    app.state.settings = _MiniSettings()

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SessionMiddleware)

    @app.get("/v1/billing/packs")
    async def stub_packs():
        return JSONResponse(status_code=200, content={"packs": []})

    @app.get("/v1/billing/balance")
    async def stub_balance():
        return JSONResponse(
            status_code=200,
            content={
                "tier": "free",
                "balance_cents": 0,
                "display_balance_cents": 0,
                "is_negative": False,
            },
        )

    @app.get("/v1/billing/transactions")
    async def stub_transactions():
        return JSONResponse(
            status_code=200,
            content={"transactions": [], "next_before": None},
        )

    @app.post("/v1/billing/webhook")
    async def stub_webhook():
        return JSONResponse(status_code=200, content={"received": True})

    @app.get("/v1/usage/summary")
    async def stub_usage_summary():
        return JSONResponse(
            status_code=200,
            content={"total_usd": "0", "message_count": 0, "by_agent": []},
        )

    @app.post("/v1/runs")
    async def stub_runs():
        return JSONResponse(status_code=200, content={"run_id": str(uuid4())})

    try:
        yield app, pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def billing_rl_client(billing_rl_app):
    app, _pool = billing_rl_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def session_cookie(billing_rl_app):
    """Seed a real users + sessions row; return Cookie string."""
    _app, pool = billing_rl_app
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES ($1, 'google', $2, 'rl@example.com', 'rl-test')",
            user_id, f"sub-{user_id.hex[:12]}",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_id, now, now + timedelta(days=7),
        )
    return {"Cookie": f"ap_session={session_id}", "_user_id": str(user_id)}


# ---------------------------------------------------------------------------
# Path predicate — /v1/billing/{packs,balance,transactions} → billing bucket;
# /v1/billing/webhook → NOT billing bucket.
#
# Direct unit tests against ``_bucket_for`` keep the predicate honest even if
# the request-level integration tests below regress — the unit tests pin the
# branch so the integration tests can rely on the routing.
# ---------------------------------------------------------------------------


def _scope_for(method: str, path: str) -> dict:
    """Build a minimal ASGI scope dict for ``_bucket_for`` lookups."""
    return {"type": "http", "method": method, "path": path}


def test_billing_packs_path_routes_to_billing_bucket():
    from api_server.middleware.rate_limit import _bucket_for

    assert _bucket_for(_scope_for("GET", "/v1/billing/packs")) == "billing"


def test_billing_balance_path_routes_to_billing_bucket():
    from api_server.middleware.rate_limit import _bucket_for

    assert _bucket_for(_scope_for("GET", "/v1/billing/balance")) == "billing"


def test_billing_transactions_path_routes_to_billing_bucket():
    from api_server.middleware.rate_limit import _bucket_for

    assert (
        _bucket_for(_scope_for("GET", "/v1/billing/transactions"))
        == "billing"
    )


def test_billing_webhook_path_does_NOT_route_to_billing_bucket():
    """Stripe's webhook caller MUST NOT be rate-limited.

    The webhook abuse-prevention surface is the Stripe-Signature HMAC
    + the ``stripe_webhook_events.stripe_event_id`` UNIQUE constraint
    (Wave 3 owns). A ``billing`` bucket return here would let a single
    user's misbehavior throttle Stripe globally — escalating Stripe's
    retry storm into a real outage.
    """
    from api_server.middleware.rate_limit import _bucket_for

    bucket = _bucket_for(_scope_for("POST", "/v1/billing/webhook"))
    assert bucket != "billing", (
        f"webhook accidentally landed in billing bucket: {bucket!r}"
    )


# ---------------------------------------------------------------------------
# Integration — burst the bucket, confirm the 31st request gets 429.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_billing_bucket_30_in_60s_then_429(
    billing_rl_client, session_cookie,
):
    """30 GETs to /v1/billing/balance allowed; 31st in <60s returns 429."""
    headers = {"Cookie": session_cookie["Cookie"]}
    for i in range(30):
        r = await billing_rl_client.get(
            "/v1/billing/balance", headers=headers,
        )
        assert r.status_code == 200, (
            f"billing GET {i + 1}/30 unexpectedly rejected: "
            f"{r.status_code} {r.text[:200]}"
        )
    r31 = await billing_rl_client.get(
        "/v1/billing/balance", headers=headers,
    )
    assert r31.status_code == 429, r31.text
    ra = r31.headers.get("retry-after")
    assert ra is not None and int(ra) >= 1, ra
    body = r31.json()
    assert body["error"]["code"] == "RATE_LIMITED", body
    assert body["error"]["param"] == "billing"


@pytest.mark.asyncio
async def test_billing_webhook_path_unaffected_by_billing_bucket(
    billing_rl_client,
):
    """31 POSTs to /v1/billing/webhook all succeed — no rate limit applies.

    Webhook is auth-less (Stripe sends; signature verifies in Wave 3
    handler). 31 POSTs would 429 if the path predicate accidentally
    routed it to the billing bucket; getting 200 from all 31 proves
    the exclusion.
    """
    for i in range(31):
        r = await billing_rl_client.post("/v1/billing/webhook")
        assert r.status_code == 200, (
            f"webhook POST {i + 1}/31 returned {r.status_code} — "
            f"the billing bucket leaked into the webhook path: "
            f"{r.text[:200]}"
        )


@pytest.mark.asyncio
async def test_billing_bucket_does_not_affect_runs_bucket(
    billing_rl_client, session_cookie,
):
    """Exhausting the billing bucket leaves the runs bucket fresh.

    User burns 30 GETs to /v1/billing/balance (billing bucket
    exhausted), then POSTs to /v1/runs — runs bucket is at 0/10 so
    the request succeeds. Independent buckets per Phase 19-05 spec.
    """
    headers = {"Cookie": session_cookie["Cookie"]}
    for i in range(30):
        r = await billing_rl_client.get(
            "/v1/billing/balance", headers=headers,
        )
        assert r.status_code == 200

    # 31st billing GET is over cap.
    r31 = await billing_rl_client.get(
        "/v1/billing/balance", headers=headers,
    )
    assert r31.status_code == 429

    # But /v1/runs is still at 0/10 — this MUST succeed.
    rr = await billing_rl_client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert rr.status_code == 200, (
        f"billing bucket exhaustion bled into runs bucket: "
        f"{rr.status_code} {rr.text[:200]}"
    )
