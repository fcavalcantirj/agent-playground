"""Phase 22b-05 Task 2 — long-poll contract tests.

Hits ``GET /v1/agents/:id/events`` with various since_seq / kinds /
timeout_s combinations + concurrent-poll 429. Uses httpx ``AsyncClient``
+ ``ASGITransport`` per the test_runs.py pattern; real PG via
testcontainers; NO docker required for these tests (watcher is simulated
by directly inserting rows via :func:`insert_agent_event` and setting
the wake signal manually).

Marked ``api_integration`` because:
  1. Requires real Postgres + ``agent_events`` table (Plan 22b-02 schema)
  2. Boots a fresh FastAPI app via ``create_app()`` + lifespan_context
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Phase 22c-06: ANONYMOUS_USER_ID constant deleted. Use a deterministic
# local seed UUID for DB-layer fixtures that don't exercise the HTTP auth
# surface; the fixtures in this file use ``ANON_USER_ID`` (string form of
# TEST_USER_ID) for FK satisfaction in direct INSERTs.
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")

pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]

API_SERVER_DIR = Path(__file__).resolve().parent.parent
ANON_USER_ID = str(TEST_USER_ID)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def real_db_pool(db_pool):
    """Alias the conftest ``db_pool`` fixture under the plan-specified name."""
    yield db_pool


@pytest_asyncio.fixture
async def seed_agent_container(real_db_pool) -> UUID:
    """Insert agent_instance + agent_container; return the agent_containers UUID.

    Mirrors the ``_seed_container_via_pool`` helper used by
    ``test_events_store.py`` so this plan's tests build against the
    same row shape Plan 22b-02 verified.
    """
    recipe_name = f"events-long-poll-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with real_db_pool.acquire() as conn:
        # Phase 22c-06: seed the FK target (migration 006 purged ANONYMOUS).
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1, 'events-long-poll-test-owner')
            ON CONFLICT (id) DO NOTHING
            """,
            TEST_USER_ID,
        )
        instance = await conn.fetchrow(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
            RETURNING id
            """,
            ANON_USER_ID,
            recipe_name,
            name,
        )
        container = await conn.fetchrow(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status)
            VALUES (gen_random_uuid(), $1, $2, $3,
                    'persistent', 'starting')
            RETURNING id
            """,
            instance["id"],
            ANON_USER_ID,
            recipe_name,
        )
    return container["id"]


@pytest.fixture
def isolated_recipes_dir(tmp_path) -> Path:
    """Tmp recipes dir containing only hermes.yaml.

    Bypasses pre-existing DI-01 (recipes/openclaw.yaml duplicate-key
    YAML bug) which crashes load_all_recipes at lifespan startup.
    Mirrors the workaround from Plan 22b-04 SUMMARY.
    """
    src = API_SERVER_DIR.parent / "recipes" / "hermes.yaml"
    dst_dir = tmp_path / "recipes"
    dst_dir.mkdir()
    shutil.copy(src, dst_dir / "hermes.yaml")
    return dst_dir


@pytest.fixture
def app_env(monkeypatch, isolated_recipes_dir, migrated_pg, sysadmin_env):
    """Set env vars create_app() needs at lifespan-startup."""
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))
    # AP_SYSADMIN_TOKEN is set by sysadmin_env fixture (chained dependency).

    def _normalize(raw: str) -> str:
        return raw.replace(
            "postgresql+psycopg2://", "postgresql://"
        ).replace("+psycopg2", "")

    monkeypatch.setenv(
        "DATABASE_URL", _normalize(migrated_pg.get_connection_url())
    )
    return True


@pytest.fixture
def sysadmin_env(monkeypatch):
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


@pytest_asyncio.fixture
async def app_and_client(app_env, db_pool):
    """Build a fresh app and an httpx client wired into it.

    The lifespan-created pool is swapped out for the test's ``db_pool``
    so seeded rows are visible to the route handler.
    """
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
            yield app, client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_long_poll_returns_existing_rows_immediately(
    seed_agent_container, real_db_pool, app_and_client, sysadmin_env,
):
    """Fast-path: rows already in DB return immediately, no wait."""
    from api_server.services.event_store import insert_agent_event

    async with real_db_pool.acquire() as conn:
        await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 3,
                "captured_at": "2026-04-18T00:00:00Z",
            },
            correlation_id="abc1",
        )
    _app, client = app_and_client
    resp = await client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=2",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["timed_out"] is False
    assert len(body["events"]) == 1
    assert body["events"][0]["kind"] == "reply_sent"
    assert body["next_since_seq"] == 1


async def test_long_poll_timeout_empty(
    seed_agent_container, real_db_pool, app_and_client, sysadmin_env,
):
    """No rows + 1s timeout returns 200 timed_out=true with events=[]."""
    _app, client = app_and_client
    import time
    t0 = time.monotonic()
    resp = await client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=9999&timeout_s=1",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    elapsed = time.monotonic() - t0
    assert resp.status_code == 200
    body = resp.json()
    assert body["timed_out"] is True
    assert body["events"] == []
    assert body["next_since_seq"] == 9999
    # Wall time should be approximately the requested timeout (~1s),
    # not 0 (would mean we never waited) and not >> 1s (would mean we
    # held the DB pool across the wait — Pitfall 4).
    assert 0.8 <= elapsed <= 2.5, f"elapsed={elapsed}s outside [0.8, 2.5]"


async def test_long_poll_signal_wake(
    seed_agent_container, real_db_pool, app_and_client, sysadmin_env,
):
    """INSERT a row mid-wait + signal.set() wakes the handler immediately."""
    from api_server.services.event_store import insert_agent_event
    from api_server.services.watcher_service import _get_poll_signal

    app, client = app_and_client

    async def waker():
        await asyncio.sleep(0.5)
        async with real_db_pool.acquire() as conn:
            await insert_agent_event(
                conn,
                seed_agent_container,
                "reply_sent",
                {
                    "chat_id": "1",
                    "length_chars": 1,
                    "captured_at": "2026-04-18T00:00:00Z",
                },
                correlation_id="wake1",
            )
        _get_poll_signal(app.state, seed_agent_container).set()

    waker_task = asyncio.create_task(waker())
    import time
    t0 = time.monotonic()
    resp = await client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=3",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    elapsed = time.monotonic() - t0
    await waker_task
    assert resp.status_code == 200
    body = resp.json()
    assert body["timed_out"] is False
    assert len(body["events"]) >= 1
    # Signal-wake should respond well before the 3s timeout (~0.5s wake +
    # epsilon for scope-2 fetch). 1.5s is a generous ceiling.
    assert elapsed < 1.5, f"signal wake elapsed={elapsed}s — slow"


async def test_long_poll_kinds_filter(
    seed_agent_container, real_db_pool, app_and_client, sysadmin_env,
):
    """kinds=reply_sent filters out agent_error rows."""
    from api_server.services.event_store import insert_agent_event

    async with real_db_pool.acquire() as conn:
        await insert_agent_event(
            conn,
            seed_agent_container,
            "reply_sent",
            {
                "chat_id": "1",
                "length_chars": 1,
                "captured_at": "2026-04-18T00:00:00Z",
            },
        )
        await insert_agent_event(
            conn,
            seed_agent_container,
            "agent_error",
            {
                "severity": "ERROR",
                "detail": "x",
                "captured_at": "2026-04-18T00:00:01Z",
            },
        )
    _app, client = app_and_client
    resp = await client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=0"
        f"&kinds=reply_sent&timeout_s=1",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    kinds_returned = {e["kind"] for e in body["events"]}
    assert kinds_returned == {"reply_sent"}


async def test_long_poll_unknown_kind_400(
    seed_agent_container, app_and_client, sysadmin_env,
):
    """kinds=bogus returns 400 INVALID_REQUEST (V13 whitelist guard)."""
    _app, client = app_and_client
    resp = await client.get(
        f"/v1/agents/{seed_agent_container}/events?kinds=bogus&timeout_s=1",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
    assert resp.json()["error"].get("param") == "kinds"


async def test_long_poll_concurrent_poll_429(
    seed_agent_container, real_db_pool, app_and_client, sysadmin_env,
):
    """Second concurrent poll on the SAME agent returns 429."""
    _app, client = app_and_client

    # First poll waits 2s with no rows
    first = asyncio.create_task(client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=9998&timeout_s=2",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    ))
    # Let first grab the lock before the second hits the route
    await asyncio.sleep(0.3)
    second = await client.get(
        f"/v1/agents/{seed_agent_container}/events?since_seq=0&timeout_s=1",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=3.0,
    )
    await first
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "CONCURRENT_POLL_LIMIT"
    assert second.json()["error"].get("param") == "agent_id"
