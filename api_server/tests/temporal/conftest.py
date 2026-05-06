"""Shared fixtures for Phase 28 Temporal workflow / activity / route tests.

Three fixtures live here:

* ``temporal_env`` — per-test ``WorkflowEnvironment.start_time_skipping``.
  NOT session-scoped: each test gets a fresh in-process Temporal Server
  so registered workflow / activity sets cannot leak between tests.
  (Plan 28-07 Task 1.)
* ``make_dispatch_input`` — factory yielding valid
  ``DispatchMessageInput`` dataclass instances with sane UUID defaults.
  (Plan 28-07 Task 1.)
* ``async_client_no_temporal`` — Plan 28-07 Task 3 helper. A drop-in
  replacement for the top-level ``async_client`` fixture that
  short-circuits the Temporal connect with an ``AsyncMock`` BEFORE the
  FastAPI lifespan runs. Route-level Phase 28 tests need the full app
  (DB pool + middleware + routes) but do NOT need a live Temporal
  cluster — the workflow body is already covered by Task 1 against a
  real ``WorkflowEnvironment``. Stubbing the lifespan-Temporal client
  keeps this test ring at the route layer where it belongs.

The Postgres-backed ``db_pool`` fixture used by activity-level tests is
inherited from ``tests/conftest.py`` (testcontainers Postgres 17,
session-scoped container + per-test TRUNCATE). The respx-mocked HTTP
boundary is per-test inside each activity test body.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio


_API_SERVER_DIR = Path(__file__).resolve().parent.parent.parent


@pytest_asyncio.fixture
async def temporal_env():
    """Per-test WorkflowEnvironment with time-skipping. Disposed after test.

    NOT session-scoped — each test gets a fresh in-process Temporal Server
    so registered workflow / activity sets don't leak between cases.

    The ``start_time_skipping()`` factory boots a real Temporal test
    server bundled with the SDK. This is real Temporal — same gRPC,
    same workflow-replay machinery — NOT a mock. CLAUDE.md Golden
    Rule #1 compliant.
    """
    from temporalio.testing import WorkflowEnvironment

    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


@pytest.fixture
def make_dispatch_input():
    """Factory for valid ``DispatchMessageInput`` dataclass instances.

    Returns a callable accepting per-test field overrides; defaults are
    syntactically valid UUIDs and reasonable scalar values so a typical
    test only overrides the field(s) under examination.
    """
    from api_server.temporal.workflows.dispatch_message import DispatchMessageInput

    def _make(**overrides: Any) -> DispatchMessageInput:
        defaults: dict[str, Any] = dict(
            message_id=str(UUID(int=1)),
            user_id=str(UUID(int=2)),
            agent_id=str(UUID(int=3)),
            container_row_id=str(UUID(int=4)),
            container_id="docker-cont-id-deadbeef",
            recipe_name="hermes-test",
            agent_model="anthropic/claude-3.5-sonnet",
            content="hi",
            inapp_auth_token=None,
            bot_timeout_seconds=60.0,
        )
        defaults.update(overrides)
        return DispatchMessageInput(**defaults)

    return _make


def _normalize_testcontainers_dsn(raw: str) -> str:
    """Mirror of ``tests/conftest.py``'s helper for the local fixture.

    Avoids cross-conftest import; the substitution is purely string-shape
    (asyncpg rejects the ``+psycopg2`` driver hint testcontainers emits).
    """
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


@pytest_asyncio.fixture
async def async_client_no_temporal(
    db_pool, migrated_pg, redis_container, monkeypatch,
):
    """httpx ASGI client wired to a freshly-built FastAPI app, **without**
    a live Temporal cluster.

    Mirrors ``async_client`` from ``tests/conftest.py`` byte-for-byte
    EXCEPT it monkey-patches ``api_server.main.make_client`` BEFORE the
    lifespan runs. The patched factory returns an ``AsyncMock`` so the
    lifespan's 5×5s connect retry loop never fires and the app boots
    cleanly without a Temporal cluster on localhost.

    The route handler reads ``request.app.state.temporal_client`` per-call;
    individual route-layer tests further override that attribute on the
    yielded client's ``_app`` reference (set on the client below) to
    customize ``start_workflow`` behavior (e.g. raise
    ``WorkflowAlreadyStartedError``).

    Why a stub here is OK (and not a Golden Rule #1 violation): the real
    Temporal end-to-end contract is covered by Task 1's
    WorkflowEnvironment-backed workflow tests (real Temporal Server). This
    fixture exists ONLY for the route-layer call-shape tests in
    ``tests/temporal/test_route_starts_workflow.py``. Postgres remains real.
    """
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv(
        "AP_RECIPES_DIR", str((_API_SERVER_DIR.parent / "recipes").resolve())
    )
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("DATABASE_URL", dsn)
    _redis_host = redis_container.get_container_host_ip()
    _redis_port = redis_container.get_exposed_port(6379)
    monkeypatch.setenv(
        "AP_REDIS_URL", f"redis://{_redis_host}:{_redis_port}/0"
    )

    # Patch the lifespan's Temporal client factory BEFORE create_app() and
    # lifespan_context. ``api_server.main`` imports ``make_client`` lazily
    # inside the lifespan body so the patch lands on the imported binding.
    fake_temporal_client = AsyncMock(name="fake_temporal_client")

    async def _fake_make_client(_settings):  # noqa: ARG001 — sig-compat
        return fake_temporal_client

    # Patch both the factory module's symbol AND the lifespan import site
    # (defensive — the lifespan body uses ``from .temporal.client import
    # make_client``, so the local binding inside ``main`` is the one
    # actually called; patching the module symbol covers any future inline
    # ``api_server.temporal.client.make_client`` reference too).
    monkeypatch.setattr(
        "api_server.temporal.client.make_client", _fake_make_client,
    )

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        try:
            await app.state.db.close()
        except Exception:
            pass
        app.state.db = db_pool
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Expose app on the client so per-test code can override
            # app.state.temporal_client (e.g. to raise WorkflowAlreadyStartedError).
            client._app = app  # type: ignore[attr-defined]
            yield client
