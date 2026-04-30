"""Phase 22c.3-08 Task 1 — chat-path rate-limit middleware tests.

Verifies that ``RateLimitMiddleware`` extends from runs/lint/get to also
cover the chat path with per-(user, agent) bucketing per D-42:

  * 4/min cap on ``POST /v1/agents/{agent_id}/messages``; 5th in 60s → 429
    with ``Retry-After`` header.
  * The bucket key is ``chat:{user_id}:{agent_id}`` (Pitfall 7) — so a user
    posting 4 to agent A and 4 to agent B in the same minute does NOT
    trigger 429 on either (they are independent buckets).
  * Chat bucket exhaustion does NOT bleed into the runs bucket.

These tests use a minimal FastAPI app that mounts just the session +
rate-limit middlewares + stubs at /v1/agents/{id}/messages and /v1/runs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
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

    The middleware reads ``trusted_proxy`` from ``app.state.settings`` —
    everything else (recipes_dir, etc) is irrelevant here.
    """

    trusted_proxy = False


@pytest_asyncio.fixture
async def chat_rl_app(migrated_pg):
    """Minimal FastAPI app: Session + RateLimit middlewares + stub routes."""
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

    @app.post("/v1/agents/{agent_id}/messages")
    async def stub_chat(agent_id: str):
        return JSONResponse(
            status_code=202,
            content={"message_id": str(uuid4()), "status": "pending"},
        )

    @app.post("/v1/runs")
    async def stub_runs():
        return JSONResponse(status_code=200, content={"run_id": str(uuid4())})

    try:
        yield app, pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def chat_rl_client(chat_rl_app):
    app, _pool = chat_rl_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def session_cookie(chat_rl_app):
    """Seed a real users + sessions row; return Cookie string."""
    _app, pool = chat_rl_app
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


@pytest.mark.asyncio
async def test_chat_rate_limit_5th_in_60s_returns_429(
    chat_rl_client, session_cookie,
):
    """4 POSTs allowed, 5th returns 429 with Retry-After (D-42)."""
    agent_id = uuid4()
    headers = {"Cookie": session_cookie["Cookie"], "Content-Type": "application/json"}

    for i in range(4):
        r = await chat_rl_client.post(
            f"/v1/agents/{agent_id}/messages",
            headers=headers,
            json={"content": f"msg-{i}"},
        )
        assert r.status_code == 202, (
            f"chat POST {i + 1}/4 unexpectedly rejected: {r.status_code} {r.text[:200]}"
        )

    r5 = await chat_rl_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "msg-5"},
    )
    assert r5.status_code == 429, r5.text
    ra = r5.headers.get("retry-after")
    assert ra is not None and int(ra) >= 1, ra
    body = r5.json()
    assert body["error"]["code"] == "RATE_LIMITED", body


@pytest.mark.asyncio
async def test_chat_rate_limit_per_agent(chat_rl_client, session_cookie):
    """User posts 4 to agent A then 4 to agent B in same minute — both succeed.

    Pitfall 7: the rate-limit bucket key is composite
    ``chat:{user_id}:{agent_id}`` so per-agent quotas don't share a bucket.
    """
    agent_a = uuid4()
    agent_b = uuid4()
    headers = {"Cookie": session_cookie["Cookie"], "Content-Type": "application/json"}

    for i in range(4):
        r = await chat_rl_client.post(
            f"/v1/agents/{agent_a}/messages",
            headers=headers,
            json={"content": f"a-{i}"},
        )
        assert r.status_code == 202, f"agent A POST {i + 1} rejected: {r.text[:200]}"

    # Agent B should have a fresh 4/min bucket — these 4 also succeed.
    for i in range(4):
        r = await chat_rl_client.post(
            f"/v1/agents/{agent_b}/messages",
            headers=headers,
            json={"content": f"b-{i}"},
        )
        assert r.status_code == 202, (
            f"agent B POST {i + 1} unexpectedly rejected — Pitfall 7 mitigation "
            f"failed: chat bucket is keyed without agent_id"
        )

    # Agent A's 5th still 429 — proves the cap is enforced per-agent.
    r5a = await chat_rl_client.post(
        f"/v1/agents/{agent_a}/messages",
        headers=headers,
        json={"content": "a-5"},
    )
    assert r5a.status_code == 429, r5a.text


@pytest.mark.asyncio
async def test_chat_rate_limit_does_not_affect_runs(
    chat_rl_client, session_cookie,
):
    """Exhausting the chat bucket leaves the runs bucket fresh.

    User posts 4 chat messages to /v1/agents/X/messages (chat bucket
    exhausted), then POSTs to /v1/runs — runs bucket is at 0/10 so the
    request succeeds. Proves the buckets are independent.
    """
    agent_id = uuid4()
    headers = {"Cookie": session_cookie["Cookie"], "Content-Type": "application/json"}

    for i in range(4):
        r = await chat_rl_client.post(
            f"/v1/agents/{agent_id}/messages",
            headers=headers,
            json={"content": f"msg-{i}"},
        )
        assert r.status_code == 202

    # The 5th chat message is over cap.
    r5 = await chat_rl_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "msg-5"},
    )
    assert r5.status_code == 429

    # But /v1/runs is still at 0/10 — this MUST succeed.
    rr = await chat_rl_client.post(
        "/v1/runs",
        headers=headers,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert rr.status_code == 200, (
        f"chat bucket exhaustion bled into runs bucket: {rr.status_code} "
        f"{rr.text[:200]}"
    )
