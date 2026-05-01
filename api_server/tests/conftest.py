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
from testcontainers.redis import RedisContainer

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
def redis_container():
    """One Redis 7 container per test session — amortizes container boot cost.

    Phase 22c.3-07 fixture: consumed by ``redis_client`` (per-test) and the
    outbox-pump integration tests in ``tests/test_inapp_outbox.py``. Loop-back
    image keeps boot to a few seconds; same session-scope amortization model
    as ``postgres_container``.
    """
    with RedisContainer("redis:7-alpine") as r:
        yield r


@pytest_asyncio.fixture
async def redis_client(redis_container):
    """Per-test ``redis.asyncio`` client connected to the session container.

    Phase 22c.3-07 fixture: tests use this to PUBLISH/SUBSCRIBE against the
    real Redis. ``decode_responses=False`` so messages arrive as ``bytes`` —
    the outbox pump publishes JSON-encoded ``str`` (which redis-py upcasts to
    bytes); the test helper decodes on read.

    Per-test cleanup ``flushdb()`` + ``aclose()`` keeps test isolation —
    one test's stale keys / channel state cannot leak into the next.
    """
    import redis.asyncio as redis_async

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = redis_async.from_url(
        f"redis://{host}:{port}/0", decode_responses=False
    )
    try:
        yield client
    finally:
        try:
            await client.flushdb()
        except Exception:
            pass
        await client.aclose()


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

    Post-22c (migration 006): the anonymous seed row is gone. Every
    integration test is responsible for creating its own user(s) — either
    via the ``authenticated_cookie`` fixture (HTTP-layer tests, plan
    22c-05) or a direct asyncpg INSERT with a literal ``TEST_USER_ID``
    (DB-layer tests). The TRUNCATE list below covers every data-bearing
    table from migration 006 so test isolation survives a clean post-006
    DB.
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
            # Phase 22c-06: TRUNCATE list extended to match migration 006's
            # 8-table purge set. ``agent_events`` + ``agent_containers`` +
            # ``users`` were previously omitted because the ANONYMOUS seed
            # row had to survive. Post-006 that row no longer exists, so
            # TRUNCATE can now include ``users`` directly — integration
            # tests seed their own users via ``authenticated_cookie`` or
            # an inline ``TEST_USER_ID`` literal.
            await conn.execute(
                "TRUNCATE TABLE agent_events, runs, agent_containers, "
                "agent_instances, idempotency_keys, rate_limit_counters, "
                "sessions, users "
                "RESTART IDENTITY CASCADE"
            )
    finally:
        await cleanup_pool.close()


# ---------------------------------------------------------------------------
# Phase 22c.3.1 — promoted fixtures (B-7 fix)
#
# `started_api_server` and `e2e_docker_network` were previously local to
# `tests/e2e/conftest.py`. Phase 22c.3.1 Plan 01 Task 2 needs both visible to
# `tests/routes/test_agent_lifecycle_inapp.py` (a sibling of `tests/e2e/`,
# NOT a child) so we promote them to the top-level `tests/conftest.py`.
# pytest's directory-scoping rule then makes them visible to ALL test files
# under `tests/`, including both `tests/routes/` and `tests/e2e/`.
#
# `recipe_index`, `_e2e_host_port_map`, and `recipe_container_factory` STAY
# in `tests/e2e/conftest.py` — those are e2e-matrix-specific (macOS host-port
# publish workaround); Task 2's route tests do not need them.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def e2e_docker_network() -> str:
    """Create a dedicated bridge network for the test session. Tear down on exit.

    Promoted from `tests/e2e/conftest.py` per Phase 22c.3.1 Plan 01 B-7 fix
    so that route-handler tests in `tests/routes/` (which boot real recipe
    containers via runner_bridge → run_cell_persistent → docker run on this
    network) can inherit it.

    Mirrors the production lifespan pattern where `app.state.docker_network_name`
    is set; the dispatcher's InappRecipeIndex uses that name to read the
    container's IPv4 address from `NetworkSettings.Networks[<name>].IPAddress`.

    Phase 22c.3.1-01-AC01 dockerized-harness extension: when env var
    ``AP_E2E_NETWORK_PRESET`` is set, REUSE that pre-existing network — the
    outer dockerized harness (``make e2e-inapp-docker``) creates the network
    once (so the pytest container can ``--network <name>`` join it BEFORE
    pytest starts) and tears it down after pytest exits. In that mode the
    fixture must NOT create or destroy the network — outer harness owns the
    lifecycle. When the env var is unset, the legacy behavior runs (create +
    teardown inline) so host-pytest invocation is byte-identical to before.
    """
    import os as _os
    import uuid as _uuid
    import subprocess as _sp

    preset = _os.environ.get("AP_E2E_NETWORK_PRESET")
    if preset:
        # Outer dockerized harness manages lifecycle — do NOT create/destroy.
        yield preset
        return

    name = f"ap-e2e-{_uuid.uuid4().hex[:10]}"
    _sp.run(
        ["docker", "network", "create", "--driver", "bridge", name],
        check=True, capture_output=True, text=True,
    )
    try:
        yield name
    finally:
        _sp.run(
            ["docker", "network", "rm", name],
            capture_output=True, text=True, check=False,
        )


@pytest_asyncio.fixture
async def started_api_server(
    db_pool, migrated_pg, redis_container, e2e_docker_network, monkeypatch,
):
    """Function-scoped FastAPI app + httpx ASGI client + e2e docker network.

    Phase 22c.3.1 Plan 01 Wave 0 fixture. Mirrors `async_client` (lines
    207-263 above) verbatim with these B-7 extensions:

    - Sets ``AP_DOCKER_NETWORK_NAME=<e2e_docker_network>`` BEFORE
      ``create_app()`` so ``app.state.docker_network_name`` matches the
      e2e bridge — runner_bridge spawns containers on this network.
    - Wires ``app.state.recipe_index`` to a real ``InappRecipeIndex`` (NOT
      the ``_E2EWrappedIndex`` shim from ``tests/e2e/conftest.py``).
      Task 2's route tests don't need the macOS port-publish workaround;
      only the 5-cell matrix in Task 3 does. The matrix overrides
      ``app.state.recipe_index`` per-test inside ``_factory`` after
      acquiring this client.
    - Function-scoped (D-30): ~15s spawn overhead per test is acceptable;
      session-scoping would couple test isolation across cells.

    Yields an ``httpx.AsyncClient`` over ``ASGITransport``.
    """
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv(
        "AP_RECIPES_DIR", str((API_SERVER_DIR.parent / "recipes").resolve())
    )
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("DATABASE_URL", dsn)
    _redis_host = redis_container.get_container_host_ip()
    _redis_port = redis_container.get_exposed_port(6379)
    monkeypatch.setenv(
        "AP_REDIS_URL", f"redis://{_redis_host}:{_redis_port}/0"
    )
    # B-7 extension: set the docker network name BEFORE create_app() so
    # Settings.docker_network_name (env alias `AP_DOCKER_NETWORK`, see
    # config.py:69-71) lines up with the bridge our recipe containers
    # attach to.
    monkeypatch.setenv("AP_DOCKER_NETWORK", e2e_docker_network)

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
            # Expose the app on the client for tests that need to override
            # app.state.recipe_index per-test (the 5-cell matrix does so).
            client._app = app  # type: ignore[attr-defined]
            yield client


@pytest.fixture
def inapp_redis_env(redis_container, monkeypatch):
    """Inject ``AP_REDIS_URL`` pointing at the session-scoped testcontainer.

    Phase 22c.3-09 fixture: any test that boots the FastAPI app via
    ``create_app() + lifespan_context`` triggers the lifespan's hard PING
    of Redis at boot (D-15/D-16 invariant — fail-loud-not-silent in prod).
    File-local fixtures predating Plan 09 only set ``AP_ENV``, ``AP_RECIPES_DIR``,
    and ``DATABASE_URL`` — they would fail with ``redis.ConnectionError``
    against the prod-default ``redis://redis:6379/0`` hostname unresolvable
    outside docker compose.

    Compose this fixture into every file-local ``app_env_*`` fixture that
    boots a new app for the test. The ``async_client`` shared fixture
    above wires the same env directly without using this helper (kept for
    backward compatibility with Plan 09's original wire-up).
    """
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    monkeypatch.setenv("AP_REDIS_URL", f"redis://{host}:{port}/0")


@pytest_asyncio.fixture
async def async_client(db_pool, migrated_pg, redis_container, monkeypatch):
    """httpx ASGI client wired to a freshly-built FastAPI app.

    Overrides the lifespan-created pool with the test's ``db_pool`` so we
    don't double-connect to the container. The lifespan is entered
    manually via ``app.router.lifespan_context`` so startup hooks
    (including the pool init the tests are about to override) actually run.

    Phase 22c.3-09: depends on the session-scoped ``redis_container``
    fixture and wires ``AP_REDIS_URL`` to the testcontainer because the
    lifespan now PINGs Redis at boot and FAILS LOUD if it can't connect
    (D-15/D-16 invariant). Without this dependency, every test that
    consumes ``async_client`` would fail with a Redis ConnectionError
    against the prod-default ``redis://redis:6379/0`` hostname.
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
    # Phase 22c.3-09 lifespan PINGs Redis at boot — point at the
    # session-scoped testcontainer.
    _redis_host = redis_container.get_container_host_ip()
    _redis_port = redis_container.get_exposed_port(6379)
    monkeypatch.setenv(
        "AP_REDIS_URL", f"redis://{_redis_host}:{_redis_port}/0"
    )

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


# ------ Phase 22b Wave 0 shared fixtures ------


@pytest.fixture(scope="session")
def docker_client():
    """docker-py APIClient from-env. Skips test if daemon unavailable.

    Source: RESEARCH.md Standard Stack — docker>=7.0,<8; from_env auto-negotiates.
    """
    import docker  # local import: keep startup cost off Docker-free unit runs

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:  # pragma: no cover — environmental skip
        pytest.skip(f"Docker daemon unavailable: {exc}")
    yield client
    client.close()


@pytest.fixture
def running_alpine_container(docker_client):
    """Factory: spawn an alpine:3.19 container with a user-provided command.

    Auto-removes on teardown. Returns the docker Container object.

    Example::

        container = running_alpine_container(
            command=["sh", "-c", "echo hello; sleep 30"]
        )
    """
    created = []

    def _factory(command, **kwargs):
        container = docker_client.containers.run(
            "alpine:3.19",
            command=command,
            detach=True,
            auto_remove=True,
            **kwargs,
        )
        created.append(container)
        return container

    yield _factory
    for c in created:
        try:
            c.remove(force=True)
        except Exception:
            pass


@pytest.fixture(scope="session")
def event_log_samples_dir():
    """Path to the 5 spike-derived event-log fixture files."""
    return Path(__file__).parent / "fixtures" / "event_log_samples"


# ---------------------------------------------------------------------------
# Phase 22c-05 — OAuth integration test fixtures
# ---------------------------------------------------------------------------
#
# Used by tests under ``tests/auth/``, ``tests/routes/test_users_me.py``, and
# (future) ``tests/config/test_oauth_state_secret_fail_loud.py``. The two
# cookie fixtures seed real rows in ``users`` + ``sessions`` against the
# migrated testcontainer; ``respx_oauth_providers`` gives a context-manager
# factory that stubs every authlib outbound call to Google + GitHub so the
# callback integration tests never touch the public internet.


@pytest_asyncio.fixture
async def authenticated_cookie(db_pool):
    """Seed a google-provider user + a live session; yield cookie + ids.

    Consumed by ``tests/auth/test_logout.py``, ``tests/routes/test_users_me.py``,
    and (plan 22c-09) the cross-user isolation test. Uses asyncpg directly
    rather than ``upsert_user`` / ``mint_session`` so a regression in those
    helpers doesn't silently invalidate the fixture.

    The yielded dict carries three keys:

      * ``Cookie`` — ready to pass to httpx as ``headers={"Cookie": ...}``.
      * ``_user_id`` — the inserted user's UUID (string) for equality checks.
      * ``_session_id`` — the inserted session's UUID (string) for DELETE
        assertions in the logout flow.

    Sessions live 30 days; user_agent + ip_address intentionally NULL.
    """
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google",
            f"test-sub-{uuid4().hex[:12]}",
            "alice@example.com",
            "Alice",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2)
            RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )
    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": user_id,
        "_session_id": session_id,
    }


@pytest_asyncio.fixture
async def second_authenticated_cookie(db_pool):
    """A SECOND distinct user+session — used by the cross-user isolation
    test in plan 22c-09 (``test_user_cannot_access_others_agent``). Seeded
    here so plan 22c-09 doesn't duplicate the fixture.
    """
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google",
            f"test-sub-{uuid4().hex[:12]}",
            "bob@example.com",
            "Bob",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2)
            RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )
    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": user_id,
        "_session_id": session_id,
    }


@pytest.fixture
def respx_oauth_providers():
    """Context-manager factory that stubs Google + GitHub OAuth HTTP calls.

    Returns a ``@contextmanager`` — callers do::

        with respx_oauth_providers() as stubs:
            stubs["google_token"].mock(return_value=httpx.Response(200, json=...))
            stubs["github_user"].mock(return_value=httpx.Response(200, json=...))
            # ... drive the callback route ...

    ``assert_all_called=False`` because a given test usually exercises only
    one provider's endpoints; unexercised stubs are NOT a failure. The
    Google OIDC discovery endpoint is pre-stubbed with a canned metadata
    document so authlib's ``load_server_metadata()`` never hits the public
    ``accounts.google.com`` in tests. The JWKS endpoint gets an empty
    key-set so attempts to parse an id_token fail gracefully (routes
    already fall back to the explicit ``userinfo()`` call in that case).
    """
    import httpx
    import respx
    from contextlib import contextmanager

    _GOOGLE_DISCOVERY = {
        "issuer": "https://accounts.google.com",
        "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
        "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "email", "profile"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
    }

    @contextmanager
    def _ctx():
        with respx.mock(assert_all_called=False) as m:
            # Pre-stub discovery + JWKS with canned payloads. Tests may
            # override these if they need to test a specific discovery
            # failure; the default lets authlib bootstrap cleanly.
            m.get(
                "https://accounts.google.com/.well-known/openid-configuration"
            ).mock(return_value=httpx.Response(200, json=_GOOGLE_DISCOVERY))
            m.get(
                "https://www.googleapis.com/oauth2/v3/certs"
            ).mock(return_value=httpx.Response(200, json={"keys": []}))
            stubs = {
                "google_token": m.post(
                    "https://oauth2.googleapis.com/token"
                ),
                "google_userinfo": m.get(
                    "https://openidconnect.googleapis.com/v1/userinfo"
                ),
                "github_token": m.post(
                    "https://github.com/login/oauth/access_token"
                ),
                "github_user": m.get("https://api.github.com/user"),
                "github_user_emails": m.get(
                    "https://api.github.com/user/emails"
                ),
            }
            yield stubs

    return _ctx
