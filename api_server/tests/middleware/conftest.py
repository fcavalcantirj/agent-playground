"""Shared fixtures for Phase 22c-04 SessionMiddleware integration tests.

Builds a minimal FastAPI app mounting ONLY ``SessionMiddleware`` plus a
``/_test/whoami`` echo route that surfaces ``request.state.user_id`` as
JSON. This lets the tests exercise middleware behavior end-to-end against
real PG + real asyncpg pool without pulling in ``main.create_app()`` and
its full middleware/route stack (which 22c-05 wires later).

All tests in ``tests/middleware/`` share these fixtures.
"""
from __future__ import annotations

import asyncpg
import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from api_server.middleware.session import SessionMiddleware


def _normalize_testcontainers_dsn(raw: str) -> str:
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


@pytest_asyncio.fixture
async def session_test_app(migrated_pg):
    """Minimal FastAPI app: SessionMiddleware + /_test/whoami echo route.

    Pool is created fresh per-test. App carries the pool on ``app.state.db``
    so SessionMiddleware's ``scope['app'].state.db.acquire()`` path works.
    ``app.state.session_last_seen`` is left unset so the middleware lazy-
    initializes it per the production code path.
    """
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=3, command_timeout=5.0
    )
    app = FastAPI()
    app.state.db = pool
    app.add_middleware(SessionMiddleware)

    @app.get("/_test/whoami")
    async def whoami(request: Request):
        uid = getattr(request.state, "user_id", None)
        return {"user_id": str(uid) if uid else None}

    try:
        yield app, pool
    finally:
        await pool.close()


@pytest_asyncio.fixture
async def session_client(session_test_app):
    """Bare httpx AsyncClient against the session-test FastAPI app."""
    app, _pool = session_test_app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
