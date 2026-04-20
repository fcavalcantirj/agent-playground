"""R3 acceptance tests for ``SessionMiddleware`` (Phase 22c-04).

Exercises the middleware end-to-end against real Postgres (testcontainers +
alembic 005 schema). Each test seeds a sessions row, drives an ASGI request
through the minimal session-test app, and asserts ``request.state.user_id``
observed by the echo route matches the behavior matrix:

  * No cookie                   → None
  * Valid cookie                → UUID (user_id)
  * Expired cookie              → None
  * Revoked cookie              → None
  * Malformed cookie (non-UUID) → None  (no PG query, no crash)
  * PG outage                   → None  (fail-closed, logs)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest


async def _seed_user(conn) -> str:
    """Insert a fresh users row and return its id::text."""
    return await conn.fetchval(
        "INSERT INTO users (id, display_name, provider, sub, email) "
        "VALUES (gen_random_uuid(), $1, 'google', $2, $3) RETURNING id::text",
        "Test User",
        f"sub-{uuid.uuid4()}",
        f"user-{uuid.uuid4()}@example.com",
    )


async def _seed_session(
    conn,
    user_id: str,
    *,
    expires_in: timedelta = timedelta(days=30),
    revoked: bool = False,
) -> str:
    """Insert a sessions row; return the id::text (used as cookie value)."""
    now = datetime.now(timezone.utc)
    expires_at = now + expires_in
    revoked_at = now if revoked else None
    return await conn.fetchval(
        """
        INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at, revoked_at)
        VALUES ($1, $2, $3, $2, $4)
        RETURNING id::text
        """,
        user_id, now, expires_at, revoked_at,
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_no_cookie_sets_user_id_none(session_client):
    """No ``ap_session`` cookie → echo route sees user_id=None."""
    r = await session_client.get("/_test/whoami")
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": None}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_valid_cookie_resolves_user_id(session_test_app, session_client):
    """Valid session cookie → echo route sees the user's UUID."""
    _app, pool = session_test_app
    async with pool.acquire() as conn:
        user_id = await _seed_user(conn)
        session_id = await _seed_session(conn, user_id)

    r = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": user_id}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_expired_session_returns_none(session_test_app, session_client):
    """Session with ``expires_at`` in the past → user_id=None."""
    _app, pool = session_test_app
    async with pool.acquire() as conn:
        user_id = await _seed_user(conn)
        session_id = await _seed_session(
            conn, user_id, expires_in=timedelta(hours=-1),
        )

    r = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": None}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_revoked_session_returns_none(session_test_app, session_client):
    """Session with ``revoked_at IS NOT NULL`` → user_id=None."""
    _app, pool = session_test_app
    async with pool.acquire() as conn:
        user_id = await _seed_user(conn)
        session_id = await _seed_session(conn, user_id, revoked=True)

    r = await session_client.get(
        "/_test/whoami",
        headers={"Cookie": f"ap_session={session_id}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": None}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_malformed_cookie_returns_none(session_test_app, session_client):
    """Non-UUID cookie value → user_id=None without issuing a PG query.

    Threat model T-22c-09: ``_coerce_uuid`` returns None on ValueError;
    middleware treats as anonymous and must not crash or issue a SELECT.

    To prove "no PG query", we swap ``app.state.db`` for a counting proxy
    that wraps the real pool and records every ``acquire()`` call. If the
    middleware short-circuits correctly on the non-UUID cookie, the count
    stays at 0.
    """
    app, pool = session_test_app

    acquire_count = {"n": 0}

    class _CountingPoolProxy:
        def __init__(self, inner):
            self._inner = inner

        def acquire(self, *args, **kwargs):
            acquire_count["n"] += 1
            return self._inner.acquire(*args, **kwargs)

    # Swap the pool proxy on app.state.db; restore in the finally block.
    app.state.db = _CountingPoolProxy(pool)
    try:
        r = await session_client.get(
            "/_test/whoami",
            headers={"Cookie": "ap_session=not-a-uuid"},
        )
    finally:
        app.state.db = pool

    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": None}
    assert acquire_count["n"] == 0, (
        f"malformed cookie triggered a PG SELECT (acquire called "
        f"{acquire_count['n']} times); middleware should short-circuit "
        "before touching PG — T-22c-09 regression"
    )


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_pg_outage_fails_closed(
    session_test_app, session_client, caplog,
):
    """PG outage during SELECT → user_id=None + log.exception emitted."""
    app, pool = session_test_app

    class _BrokenPool:
        """Stand-in pool whose ``acquire()`` raises inside the async-ctx."""

        def acquire(self):
            return _BrokenAcquirer()

    class _BrokenAcquirer:
        async def __aenter__(self):
            raise RuntimeError("simulated PG outage")

        async def __aexit__(self, *a, **kw):
            return False

    # Swap the pool for the broken one for this test. A valid-looking UUID
    # cookie is required so the middleware attempts the SELECT and hits
    # the simulated outage on acquire().
    app.state.db = _BrokenPool()
    caplog.set_level(logging.ERROR, logger="api_server.session")
    try:
        cookie_val = str(uuid.uuid4())
        r = await session_client.get(
            "/_test/whoami",
            headers={"Cookie": f"ap_session={cookie_val}"},
        )
    finally:
        # Restore the real pool for subsequent tests (the fixture's
        # finalizer closes it, but other tests in this function-scoped
        # fixture's lifespan don't apply — safety net nonetheless).
        app.state.db = pool

    assert r.status_code == 200, r.text
    assert r.json() == {"user_id": None}, (
        f"PG outage must fail-closed to anonymous; got {r.json()}"
    )
    # Middleware must log the exception (observable via caplog).
    messages = [rec.getMessage() for rec in caplog.records]
    assert any("session resolution failed" in m for m in messages), (
        f"expected 'session resolution failed' log; got: {messages}"
    )
