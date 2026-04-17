"""Shared pytest fixtures for api_server tests.

Heavy infra (Postgres via testcontainers) is session-scoped and shared.
``TRUNCATE`` between tests keeps isolation without paying container boot
cost on every case. Default pytest invocation excludes ``api_integration``
(see ``pyproject.toml``) so unit-only runs remain fast and Docker-free.

Fixture map:

- ``postgres_container`` (session) — ``PostgresContainer("postgres:17-alpine")``
- ``migrated_pg`` (session) — runs ``alembic upgrade head`` against the container
- ``db_pool`` (function) — asyncpg pool against ``migrated_pg``
- ``_truncate_tables`` (autouse, function) — ``TRUNCATE`` per-test for isolation
- ``async_client`` (function) — httpx ``AsyncClient`` + ``ASGITransport`` →
  the FastAPI app from ``create_app()`` with the test pool injected
- ``mock_run_cell`` (function) — factory that monkeypatches ``asyncio.to_thread``
  so runner calls short-circuit with a canned verdict (Plan 04 consumes)
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer

API_SERVER_DIR = Path(__file__).resolve().parent.parent


def _normalize_testcontainers_dsn(raw: str) -> str:
    """Return a driverless Postgres DSN asyncpg can open.

    testcontainers emits ``postgresql+psycopg2://...`` by default; asyncpg
    rejects the driver hint. Both ``postgresql+psycopg2`` → ``postgresql``
    and the bare ``+psycopg2`` remnant are stripped.
    """
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


@pytest.fixture(scope="session")
def postgres_container():
    """One Postgres 17 container per test session — amortizes ~3-5s boot cost."""
    with PostgresContainer("postgres:17-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def migrated_pg(postgres_container):
    """Apply ``alembic upgrade head`` once per session, reuse the schema.

    Invokes alembic via ``python -m alembic`` so the tests work whether or
    not the ``alembic`` console script is on ``PATH`` (it isn't by default
    when the dev dependencies are installed to a user-site layout).
    """
    import sys

    dsn = _normalize_testcontainers_dsn(postgres_container.get_connection_url())
    env = {**os.environ, "DATABASE_URL": dsn}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_SERVER_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return postgres_container


@pytest_asyncio.fixture
async def db_pool(migrated_pg):
    """Per-test asyncpg pool against the migrated session-scoped container."""
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=3, command_timeout=5.0
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables(request):
    """``TRUNCATE`` every mutable table between tests that touch the DB.

    Only runs for tests that request ``db_pool`` or ``async_client``
    (either directly or transitively). The ``migrated_pg`` fixture is
    resolved LAZILY via ``request.getfixturevalue`` — if it is resolved
    eagerly as a parameter on an autouse fixture, pytest spins up the
    session-scoped Postgres container and runs alembic for every test,
    including pure-unit ``test_docs_gating.py`` that has no DB needs.

    ``users`` is intentionally NOT truncated — the anonymous seed row
    (``00000000-0000-0000-0000-000000000001``) must survive, and FKs
    cascade appropriately via ``RESTART IDENTITY CASCADE``.
    """
    needs_db = (
        "db_pool" in request.fixturenames
        or "async_client" in request.fixturenames
    )
    if not needs_db:
        yield
        return
    # Lazy resolution: only triggers container + migration when we have a
    # test that actually touches the DB.
    migrated_pg = request.getfixturevalue("migrated_pg")
    yield
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    cleanup_pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=1, command_timeout=5.0
    )
    try:
        async with cleanup_pool.acquire() as conn:
            await conn.execute(
                "TRUNCATE TABLE rate_limit_counters, idempotency_keys, runs, "
                "agent_instances RESTART IDENTITY CASCADE"
            )
    finally:
        await cleanup_pool.close()


@pytest_asyncio.fixture
async def async_client(db_pool, migrated_pg, monkeypatch):
    """httpx ASGI client wired to a freshly-built FastAPI app.

    Overrides the lifespan-created pool with the test's ``db_pool`` so we
    don't double-connect to the container. The lifespan is entered
    manually via ``app.router.lifespan_context`` so startup hooks
    (including the pool init the tests are about to override) actually run.
    """
    # AP_ENV=dev keeps /docs on so tests can assert its presence without
    # re-instantiating the app. Tests that need prod semantics construct
    # their own app via create_app() inside the test body.
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    # Plan 19-03 populates ``app.state.recipes`` from this directory at
    # lifespan-startup. Tests run from ``api_server/`` (pytest testpaths)
    # so the committed recipes live one level up.
    monkeypatch.setenv(
        "AP_RECIPES_DIR", str((API_SERVER_DIR.parent / "recipes").resolve())
    )
    # DATABASE_URL must be set for Settings() to resolve. The lifespan
    # creates its own pool that we then immediately close + replace with
    # ``db_pool`` below, so this DSN only has to be reachable at startup
    # time — the migrated container's URL is perfect for that.
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("DATABASE_URL", dsn)

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Swap the lifespan-created pool for the test's pool so any DB
        # state the test inspects via ``db_pool`` is the same pool the app
        # read/wrote against. Closing the prior pool prevents a leak.
        try:
            await app.state.db.close()
        except Exception:
            pass
        app.state.db = db_pool
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client


@pytest.fixture
def mock_run_cell(monkeypatch):
    """Factory fixture replacing ``asyncio.to_thread`` with a canned verdict.

    Mirrors the ``tools/tests/conftest.py`` ``mock_subprocess`` style.
    Plans 04/05 consume this to drive route-level behavior without
    spawning real docker containers.

    Usage::

        def test_x(mock_run_cell):
            mock_run_cell(verdict_category="PASS", wall_s=1.2)

    ``verdict_category`` matches the runner's ``Category`` enum; ``verdict``
    is derived (PASS when category is PASS, else FAIL).
    """
    def _configure(
        verdict_category: str = "PASS",
        wall_s: float = 1.0,
        exit_code: int = 0,
        stderr_tail: str | None = None,
        filtered_payload: str = "",
    ):
        async def fake_to_thread(fn, *args, **kwargs):
            details = {
                "recipe": (
                    kwargs.get("recipe", {}).get("name")
                    or (args[0].get("name") if args and isinstance(args[0], dict) else "test")
                ),
                "model": kwargs.get("model") or "test-model",
                "prompt": kwargs.get("prompt") or "test",
                "pass_if": "exit_zero",
                "verdict": "PASS" if verdict_category == "PASS" else "FAIL",
                "category": verdict_category,
                "detail": "",
                "exit_code": exit_code,
                "wall_time_s": wall_s,
                "filtered_payload": filtered_payload,
                "stderr_tail": stderr_tail,
            }
            # Return shape matches run_cell's ``details`` half. The
            # ``Verdict`` tuple half isn't consumed by current plans — if
            # Plan 04's bridge needs it, extend here.
            return details

        monkeypatch.setattr("asyncio.to_thread", fake_to_thread)

    return _configure
