"""Phase 22c.3-08 Task 1 — chat-path idempotency middleware tests.

Verifies that ``IdempotencyMiddleware`` extends from POST /v1/runs to
also cover ``POST /v1/agents/{agent_id}/messages`` per D-39:

  * Same Idempotency-Key + same body → second POST returns the cached
    response verbatim (the original message_id) without inserting a new
    inapp_messages row.
  * Same key + different body → 422 IDEMPOTENCY_BODY_MISMATCH.
  * No Idempotency-Key header → each POST creates a new row (pass-through).

The middleware's response-cache predicate previously only accepted 200
responses; the chat path returns 202 (D-29 fast-ack), so the predicate
is widened to ``status in (200, 202)``. Existing /v1/runs 200-cache
behavior is verified by the un-touched ``tests/test_idempotency.py``.

These tests run against a minimal FastAPI app that mounts just the
session + idempotency middlewares + a stub route at the chat path so
we exercise the middleware path-predicate without the full main.py
include chain (Plan 22c.3-08 Task 2 wires the real route).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from api_server.middleware.idempotency import IdempotencyMiddleware
from api_server.middleware.session import SessionMiddleware


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


def _normalize_testcontainers_dsn(raw: str) -> str:
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


@pytest_asyncio.fixture
async def chat_idem_app(migrated_pg):
    """Minimal FastAPI app: Session + Idempotency middlewares + stub chat route.

    The stub route returns a 202 with a fresh ``message_id`` per call,
    incrementing ``call_count`` so we can prove cache hits short-circuit
    BEFORE the route runs (call_count stays unchanged on hit).
    """
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=3, command_timeout=5.0
    )
    app = FastAPI()
    app.state.db = pool
    app.state.session_last_seen = {}

    # Outermost-last: IdempotencyMiddleware runs BEFORE the route, AFTER
    # SessionMiddleware sets request.state.user_id (idempotency keys are
    # owned by user_id).
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(SessionMiddleware)

    state = {"call_count": 0}

    @app.post("/v1/agents/{agent_id}/messages")
    async def stub_post(request: Request, agent_id: str):
        body = await request.json()
        state["call_count"] += 1
        # Mirror the real handler's 202 + message_id shape so the cache
        # entry replays meaningfully.
        return JSONResponse(
            status_code=202,
            content={
                "message_id": str(uuid4()),
                "status": "pending",
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "_call_n": state["call_count"],  # diagnostic; proves cache vs replay
            },
        )

    try:
        yield app, pool, state
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def chat_idem_client(chat_idem_app):
    app, _pool, _state = chat_idem_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def session_cookie(chat_idem_app):
    """Seed a real users + sessions row; return the Cookie string + user_id."""
    _app, pool, _state = chat_idem_app
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES ($1, 'google', $2, 'idem@example.com', 'idem-test')",
            user_id, f"sub-{user_id.hex[:12]}",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            "INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at) "
            "VALUES ($1, $2, $3, $2) RETURNING id::text",
            user_id, now, now + timedelta(days=7),
        )
    return {
        "Cookie": f"ap_session={session_id}",
        "_user_id": str(user_id),
    }


@pytest.mark.asyncio
async def test_chat_idempotency_replays_response(
    chat_idem_client, chat_idem_app, session_cookie,
):
    """Same Idempotency-Key + same body → cached message_id replayed; route called once."""
    _app, _pool, state = chat_idem_app
    agent_id = uuid4()
    key = str(uuid.uuid4())
    body = {"content": "hello"}
    headers = {
        "Idempotency-Key": key,
        "Cookie": session_cookie["Cookie"],
        "Content-Type": "application/json",
    }

    r1 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages", headers=headers, json=body,
    )
    assert r1.status_code == 202, r1.text
    j1 = r1.json()
    msg_id_1 = j1["message_id"]
    assert state["call_count"] == 1

    # Second POST same key + same body → cache hit. Route MUST NOT run.
    r2 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages", headers=headers, json=body,
    )
    # Cache replay returns 200 with the cached body verbatim (matches the
    # /v1/runs replay convention — the original status was 202 but the
    # replay surfaces with 200).
    assert r2.status_code == 200, r2.text
    j2 = r2.json()
    assert j2["message_id"] == msg_id_1, (
        f"second POST should replay cached message_id, got {j2['message_id']} "
        f"vs original {msg_id_1}"
    )
    assert state["call_count"] == 1, (
        f"route was called {state['call_count']} times — second call should hit cache"
    )


@pytest.mark.asyncio
async def test_chat_idempotency_body_mismatch(
    chat_idem_client, chat_idem_app, session_cookie,
):
    """Same key + different body → 422 IDEMPOTENCY_BODY_MISMATCH."""
    _app, _pool, state = chat_idem_app
    agent_id = uuid4()
    key = str(uuid.uuid4())
    headers = {
        "Idempotency-Key": key,
        "Cookie": session_cookie["Cookie"],
        "Content-Type": "application/json",
    }

    r1 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "hello"},
    )
    assert r1.status_code == 202, r1.text
    assert state["call_count"] == 1

    r2 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "DIFFERENT"},
    )
    assert r2.status_code == 422, r2.text
    body = r2.json()
    assert body["error"]["code"] == "IDEMPOTENCY_BODY_MISMATCH", body
    assert state["call_count"] == 1, "route should not run on body mismatch"


@pytest.mark.asyncio
async def test_chat_idempotency_no_key_passes_through(
    chat_idem_client, chat_idem_app, session_cookie,
):
    """No Idempotency-Key header → each POST creates a new row (no caching)."""
    _app, _pool, state = chat_idem_app
    agent_id = uuid4()
    headers = {
        "Cookie": session_cookie["Cookie"],
        "Content-Type": "application/json",
    }

    r1 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "hi"},
    )
    assert r1.status_code == 202
    msg_id_1 = r1.json()["message_id"]

    r2 = await chat_idem_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers=headers,
        json={"content": "hi"},
    )
    assert r2.status_code == 202
    msg_id_2 = r2.json()["message_id"]
    assert msg_id_1 != msg_id_2, (
        "without Idempotency-Key, every POST must produce a fresh message_id"
    )
    assert state["call_count"] == 2
