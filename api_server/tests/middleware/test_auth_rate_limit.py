"""Real-Postgres integration tests for the H3 auth rate-limit bucket.

Phase 31 D-01..D-04 + AC1..AC4. Mirrors ``test_chat_rate_limit.py``'s
testcontainers-Postgres + ASGITransport + httpx pattern; substitutes the
auth-route stubs for the chat-route stubs; asserts the 5/min/IP per-route
ceiling AND the per-route composite-subject isolation AND the cross-bucket
non-interference AND the inherited Postgres-outage fail-open semantic.

Test obligations to acceptance criteria (SPEC §H3):
  * AC1 (5/min cap + 429 + Retry-After) ↔ test_auth_rate_limit_6th_in_60s_returns_429
  * AC2 (per-route counters)            ↔ test_auth_rate_limit_per_route
  * AC3 (real-Postgres counter)         ↔ all four tests run against testcontainers
  * AC4 (fail-open on PG outage)        ↔ test_auth_rate_limit_pg_outage_fail_open
  * Cross-bucket isolation              ↔ test_auth_rate_limit_does_not_affect_chat
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


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


def _normalize_testcontainers_dsn(raw: str) -> str:
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


class _MiniSettings:
    """Minimal stand-in for app.state.settings used by RateLimitMiddleware.

    ``trusted_proxy = True`` so the per-test XFF headers (203.0.113.x)
    are honored — this isolates each test's counter rows by IP, given
    the autouse ``_truncate_tables`` fixture only fires for tests
    requesting ``db_pool`` / ``async_client`` (and these don't).
    """

    trusted_proxy = True


@pytest_asyncio.fixture
async def auth_rl_app(migrated_pg):
    """Minimal FastAPI app: Session + RateLimit + auth-route stubs + chat stub.

    Mirrors ``chat_rl_app`` in ``test_chat_rate_limit.py`` exactly, with
    the route surface swapped to the four auth POSTs covered by the new
    bucket plus a chat POST stub for the cross-bucket-isolation test.
    """
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

    @app.post("/v1/auth/google/mobile")
    async def stub_google_mobile():
        return JSONResponse(status_code=200, content={"ok": True})

    @app.post("/v1/auth/github/mobile")
    async def stub_github_mobile():
        return JSONResponse(status_code=200, content={"ok": True})

    @app.post("/v1/auth/logout")
    async def stub_logout():
        return JSONResponse(status_code=200, content={"ok": True})

    @app.post("/v1/agents/{agent_id}/messages")
    async def stub_chat(agent_id: str):
        return JSONResponse(
            status_code=202,
            content={"message_id": str(uuid4()), "status": "pending"},
        )

    try:
        yield app, pool
    finally:
        # Close only if not already closed (test_pg_outage closes the
        # pool deliberately to simulate a PG outage).
        if not pool._closed:  # pragma: no branch
            await pool.close()


@pytest_asyncio.fixture
async def session_cookie(auth_rl_app):
    """Seed a real users + sessions row; return Cookie string.

    Used by ``test_auth_rate_limit_does_not_affect_chat`` so the chat
    route's session resolution succeeds before rate-limiting runs.
    """
    _app, pool = auth_rl_app
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES ($1, 'google', $2, 'rl-auth@example.com', 'rl-auth-test')",
            user_id, f"sub-{user_id.hex[:12]}",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_id, now, now + timedelta(days=7),
        )
    return {"Cookie": f"ap_session={session_id}", "_user_id": str(user_id)}


@pytest.mark.asyncio
async def test_auth_rate_limit_6th_in_60s_returns_429(auth_rl_app):
    """AC1 + AC3 — 5 calls allowed, 6th returns 429 with Retry-After + Stripe envelope."""
    app, _pool = auth_rl_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for i in range(5):
            r = await c.post(
                "/v1/auth/google/mobile",
                headers={"x-forwarded-for": "203.0.113.5"},
            )
            assert r.status_code == 200, (
                f"call #{i + 1}/5 unexpectedly rejected: "
                f"{r.status_code} {r.text[:200]}"
            )
        r6 = await c.post(
            "/v1/auth/google/mobile",
            headers={"x-forwarded-for": "203.0.113.5"},
        )
        assert r6.status_code == 429, r6.text
        ra = r6.headers.get("retry-after")
        assert ra is not None and int(ra) >= 1, ra
        body = r6.json()
        assert body["error"]["code"] == "RATE_LIMITED", body
        assert body["error"]["param"] == "auth", body


@pytest.mark.asyncio
async def test_auth_rate_limit_per_route(auth_rl_app):
    """AC2 — 3 calls to google_mobile + 3 to github_mobile from same IP all succeed.

    The composite subject ``auth:<ip>:<route_key>`` keeps each route's
    counter row distinct, so a 3+3 split across two distinct routes
    never hits the per-route 5/min ceiling.
    """
    app, _pool = auth_rl_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for i in range(3):
            r = await c.post(
                "/v1/auth/google/mobile",
                headers={"x-forwarded-for": "203.0.113.6"},
            )
            assert r.status_code == 200, (
                f"google_mobile #{i + 1}/3 rejected: "
                f"{r.status_code} {r.text[:200]}"
            )
        for i in range(3):
            r = await c.post(
                "/v1/auth/github/mobile",
                headers={"x-forwarded-for": "203.0.113.6"},
            )
            assert r.status_code == 200, (
                f"github_mobile #{i + 1}/3 unexpectedly rejected — D-02 "
                f"per-route composite subject contract violated: "
                f"{r.status_code} {r.text[:200]}"
            )


@pytest.mark.asyncio
async def test_auth_rate_limit_does_not_affect_chat(auth_rl_app, session_cookie):
    """Cross-bucket isolation — auth bucket exhaustion leaves chat bucket fresh.

    Exhausts the auth bucket (6 POSTs to google_mobile from one IP), then
    POSTs to /v1/agents/{uuid}/messages from the SAME IP — chat bucket
    counter is keyed by ``chat:<user>:<agent>`` (never crosses to
    ``auth:<ip>:<route>``), so the chat call succeeds.
    """
    app, _pool = auth_rl_app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        for _ in range(6):
            await c.post(
                "/v1/auth/google/mobile",
                headers={"x-forwarded-for": "203.0.113.7"},
            )
        agent_id = uuid4()
        r = await c.post(
            f"/v1/agents/{agent_id}/messages",
            headers={
                "x-forwarded-for": "203.0.113.7",
                "Cookie": session_cookie["Cookie"],
                "Content-Type": "application/json",
            },
            json={"content": "hello"},
        )
        assert r.status_code == 202, (
            f"chat bucket got hit by auth bucket exhaustion — D-01 "
            f"isolation contract violated: {r.status_code} "
            f"{r.text[:200]}"
        )


@pytest.mark.asyncio
async def test_auth_rate_limit_pg_outage_fail_open(auth_rl_app):
    """AC4 + T-31-01 — Postgres outage during auth-bucket lookup → pass through.

    Closes the asyncpg pool BEFORE issuing the request; every
    ``check_and_increment`` call inside the middleware will raise. The
    fail-open branch at rate_limit.py:222-227 logs the exception and
    delegates to the wrapped app. The stub returns 200 — NOT 429, NOT 5xx.
    """
    app, pool = auth_rl_app
    await pool.close()  # simulate Postgres outage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post(
            "/v1/auth/google/mobile",
            headers={"x-forwarded-for": "203.0.113.8"},
        )
        assert r.status_code == 200, (
            f"expected fail-open pass-through (T-31-01 contract); "
            f"got {r.status_code} {r.text[:200]}"
        )
