"""Phase 22b-08 — POST /v1/agents/:id/events/inject-test-event integration tests.

Full FastAPI app wired against real PG17 via testcontainers. NO mocks.

Test matrix (8 tests; all required to PASS for Task 1 done):
  1. ``test_inject_test_event_prod_returns_404`` — even with valid sysadmin
     Bearer, the route is invisible in prod (FastAPI 404 for any path not
     registered). Defense-in-depth gate #1: the conditional include in
     main.py.
  2. ``test_inject_test_event_sysadmin_happy_path`` — happy path: real DB
     INSERT, real seq allocation, response shape per contract.
  3. ``test_inject_test_event_missing_bearer_401`` — 401 for missing
     Authorization header (mirrors GET handler's parse step).
  4. ``test_inject_test_event_wrong_bearer_404_opaque`` — wrong Bearer
     returns 404 (not 403) so the surface area is opaque to non-sysadmin
     callers.
  5. ``test_inject_test_event_sysadmin_token_unset_404`` — defense-in-depth
     gate #2: when AP_SYSADMIN_TOKEN is unset, even matching Bearer fails.
  6. ``test_inject_test_event_no_running_container_404`` — agent_id with no
     row in agent_containers returns 404 AGENT_NOT_FOUND.
  7. ``test_inject_test_event_wakes_long_poll_within_1s`` — end-to-end:
     long-poll waits → inject runs → long-poll wakes within 3s window with
     the injected event. Spike B B2 — URL key MUST be container_row_id on
     BOTH sides for the wake to fire.
  8. ``test_inject_test_event_double_inject_advances_seq`` — two injects
     with the same correlation_id produce two distinct rows and seq
     advances per insert (no idempotency dedup).

Pattern source: ``test_events_long_poll.py`` (httpx ``AsyncClient`` +
``ASGITransport``; real PG via testcontainers fixture chain
``migrated_pg`` → ``db_pool``; pool injection through
``app.router.lifespan_context``).
"""
from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api_server.constants import ANONYMOUS_USER_ID

pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]

API_SERVER_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_recipes_dir(tmp_path) -> Path:
    """Tmp recipes dir containing only hermes.yaml.

    Bypasses pre-existing DI-01 (``recipes/openclaw.yaml`` duplicate-key
    YAML bug) which crashes ``load_all_recipes`` at lifespan startup.
    Mirrors the workaround used by every prior 22b test file.
    """
    src = API_SERVER_DIR.parent / "recipes" / "hermes.yaml"
    dst_dir = tmp_path / "recipes"
    dst_dir.mkdir()
    shutil.copy(src, dst_dir / "hermes.yaml")
    return dst_dir


@pytest.fixture
def sysadmin_env(monkeypatch):
    """Mint a per-test AP_SYSADMIN_TOKEN; export to env; return the value."""
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


def _normalize(raw: str) -> str:
    """Strip the testcontainers ``+psycopg2`` driver hint asyncpg can't open."""
    return raw.replace(
        "postgresql+psycopg2://", "postgresql://"
    ).replace("+psycopg2", "")


@pytest_asyncio.fixture
async def dev_app_and_client(
    monkeypatch, isolated_recipes_dir, migrated_pg, db_pool, sysadmin_env,
):
    """Build a fresh FastAPI app with AP_ENV=dev + sysadmin token set.

    Uses the same pattern as ``test_events_long_poll.py`` ``app_and_client``:
    enter the lifespan context manually so startup hooks run, then swap the
    lifespan-created pool for the test's ``db_pool`` so seeded rows are
    visible to the route handler.
    """
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))
    monkeypatch.setenv("DATABASE_URL", _normalize(migrated_pg.get_connection_url()))
    # get_settings() is NOT lru_cache-wrapped (config.py:53-55 returns a fresh
    # Settings() per call). The defensive cache_clear() is here so future
    # refactors that DO add @lru_cache don't silently break this fixture.
    try:
        from api_server.config import get_settings
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()
    except Exception:
        pass
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


@pytest_asyncio.fixture
async def prod_app_and_client(
    monkeypatch, isolated_recipes_dir, migrated_pg, db_pool, sysadmin_env,
):
    """Build a fresh FastAPI app with AP_ENV=prod (inject route NOT registered)."""
    monkeypatch.setenv("AP_ENV", "prod")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))
    monkeypatch.setenv("DATABASE_URL", _normalize(migrated_pg.get_connection_url()))
    # AP_CHANNEL_MASTER_KEY is required-at-use by crypto/age_cipher.py when
    # AP_ENV=prod. The lifespan startup does NOT touch the key; the prod
    # test only POSTs an inject request which never decrypts, so we can
    # safely run prod-mode tests without setting this. Leaving the env
    # untouched keeps the prod-realism assertion honest.
    try:
        from api_server.config import get_settings
        if hasattr(get_settings, "cache_clear"):
            get_settings.cache_clear()
    except Exception:
        pass
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


@pytest_asyncio.fixture
async def seed_agent_instance(db_pool) -> UUID:
    """Insert an agent_instances row owned by the anonymous user.

    Returns the new agent_instance_id (UUID). Used by the no-running-container
    test — the URL key (per Spike B B2) is agent_containers.id, NOT
    agent_instances.id, so passing an agent_instance_id where a container
    PK is expected will trigger the AGENT_NOT_FOUND branch.
    """
    instance_id = uuid4()
    instance_name = f"inject-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes',
                    'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            ANONYMOUS_USER_ID,
            instance_name,
        )
    return instance_id


@pytest_asyncio.fixture
async def seed_running_container(db_pool) -> tuple[UUID, UUID]:
    """Insert agent_instances + agent_containers rows in 'running' state.

    Returns ``(container_row_id, agent_instance_id)`` — container_row_id
    FIRST because it is the canonical URL key for ``/v1/agents/{?}/events*``
    routes per Spike B 2026-04-19. Tests destructure as
    ``container_row_id, _ = seed_running_container``.

    The fake container_id ``test-fake-<hex>`` mirrors the pattern in
    ``test_events_lifespan_reattach.py`` (which uses a fabricated 64-hex
    pretend ID). The inject endpoint validates that the container row
    EXISTS in the DB and is in 'running' status; it does NOT verify the
    docker container is alive (that's the watcher's job).
    """
    instance_id = uuid4()
    container_row_id = uuid4()
    instance_name = f"inject-run-{instance_id.hex[:8]}"
    fake_container_id = "test-fake-" + uuid4().hex[:12]
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes',
                    'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            ANONYMOUS_USER_ID,
            instance_name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               container_id, container_status, channel_type)
            VALUES ($1, $2, $3, 'hermes', $4, 'running', 'telegram')
            """,
            container_row_id,
            instance_id,
            ANONYMOUS_USER_ID,
            fake_container_id,
        )
    return container_row_id, instance_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_inject_test_event_prod_returns_404(
    prod_app_and_client, seed_running_container, sysadmin_env,
):
    """Even with valid sysadmin Bearer, the route is invisible in prod.

    Defense-in-depth gate #1: the conditional ``app.include_router`` in
    main.py only registers the inject router when ``settings.env != 'prod'``.
    """
    _app, client = prod_app_and_client
    container_row_id, _instance_id = seed_running_container
    resp = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 5},
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 404, (
        f"prod must return 404 (route not registered), got "
        f"{resp.status_code}: {resp.text[:300]}"
    )


async def test_inject_test_event_sysadmin_happy_path(
    dev_app_and_client, seed_running_container, sysadmin_env, db_pool,
):
    """Sysadmin Bearer + AP_ENV=dev + running container → 200 with seq + correlation_id prefix."""
    _app, client = dev_app_and_client
    container_row_id, _instance_id = seed_running_container
    resp = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "abc1", "chat_id": "152099202", "length_chars": 12},
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["test_event"] is True
    assert body["correlation_id"] == "test:abc1"
    assert body["kind"] == "reply_sent"
    assert int(body["seq"]) >= 1
    assert UUID(body["agent_container_id"]) == container_row_id
    assert UUID(body["agent_id"]) == container_row_id, (
        "agent_id in response echoes URL value (URL key contract per Spike B B2)"
    )

    # Verify the real DB row exists with the prefixed correlation id.
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT seq, kind, correlation_id, payload "
            "FROM agent_events WHERE agent_container_id=$1",
            container_row_id,
        )
    assert any(
        r["correlation_id"] == "test:abc1" and r["kind"] == "reply_sent"
        for r in rows
    ), f"row not in DB; got rows={[dict(r) for r in rows]}"


async def test_inject_test_event_missing_bearer_401(
    dev_app_and_client, seed_running_container, sysadmin_env,
):
    _app, client = dev_app_and_client
    container_row_id, _instance_id = seed_running_container
    resp = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
        timeout=5.0,
    )
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


async def test_inject_test_event_wrong_bearer_404_opaque(
    dev_app_and_client, seed_running_container, sysadmin_env,
):
    """Wrong Bearer returns 404 (not 403) — surface is opaque."""
    _app, client = dev_app_and_client
    container_row_id, _instance_id = seed_running_container
    resp = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
        headers={"Authorization": "Bearer some-random-not-sysadmin-token"},
        timeout=5.0,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_inject_test_event_sysadmin_token_unset_404(
    monkeypatch, isolated_recipes_dir, migrated_pg, db_pool, seed_running_container,
):
    """Defense-in-depth gate #2: AP_SYSADMIN_TOKEN unset → 404 even with matching Bearer.

    A misconfigured dev box must NOT expose admin actions to anyone who
    can craft a request. Builds the app inline (NOT via the dev_app_and_client
    fixture) so we control whether AP_SYSADMIN_TOKEN is present at all.
    """
    monkeypatch.delenv("AP_SYSADMIN_TOKEN", raising=False)
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))
    monkeypatch.setenv("DATABASE_URL", _normalize(migrated_pg.get_connection_url()))
    from api_server.main import create_app

    app = create_app()
    container_row_id, _instance_id = seed_running_container
    async with app.router.lifespan_context(app):
        try:
            await app.state.db.close()
        except Exception:
            pass
        app.state.db = db_pool
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/v1/agents/{container_row_id}/events/inject-test-event",
                json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
                headers={"Authorization": "Bearer anything"},
                timeout=5.0,
            )
    assert resp.status_code == 404, resp.text


async def test_inject_test_event_no_running_container_404(
    dev_app_and_client, seed_agent_instance, sysadmin_env,
):
    """A UUID with no matching agent_containers row → 404 AGENT_NOT_FOUND.

    Spike B B2: URL key is agent_containers.id (container_row_id). We pass
    an agent_instances UUID — by definition NOT present in agent_containers.
    Step 4 of the handler does ``SELECT FROM agent_containers WHERE id=$1``
    and returns 404 when the row is absent.
    """
    _app, client = dev_app_and_client
    resp = await client.post(
        f"/v1/agents/{seed_agent_instance}/events/inject-test-event",
        json={"correlation_id": "abc1", "chat_id": "1", "length_chars": 1},
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"
    assert "no running container" in resp.json()["error"]["message"]


async def test_inject_test_event_wakes_long_poll_within_1s(
    dev_app_and_client, seed_running_container, sysadmin_env,
):
    """End-to-end: long-poll waits → inject runs → long-poll wakes within 3s.

    Spike B B2 — BOTH the inject AND the long-poll MUST use container_row_id
    in the URL. Using instance_id on either side (or mismatched on the two
    calls) breaks the wake — long-poll times out with 0 events. Empirically
    verified 2026-04-19.
    """
    _app, client = dev_app_and_client
    container_row_id, _instance_id = seed_running_container

    async def injector():
        await asyncio.sleep(0.4)
        return await client.post(
            f"/v1/agents/{container_row_id}/events/inject-test-event",
            json={"correlation_id": "wake1", "chat_id": "152099202", "length_chars": 8},
            headers={"Authorization": f"Bearer {sysadmin_env}"},
            timeout=5.0,
        )

    injector_task = asyncio.create_task(injector())
    long_poll_resp = await client.get(
        f"/v1/agents/{container_row_id}/events?since_seq=0&kinds=reply_sent&timeout_s=3",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=6.0,
    )
    inject_resp = await injector_task

    assert inject_resp.status_code == 200, inject_resp.text
    assert long_poll_resp.status_code == 200, long_poll_resp.text
    body = long_poll_resp.json()
    assert body["timed_out"] is False, (
        f"long-poll TIMED OUT — signal-wake failed; body={body}"
    )
    assert any(
        e.get("correlation_id") == "test:wake1" for e in body["events"]
    ), f"injected event not in long-poll response: {body['events']}"


async def test_inject_test_event_double_inject_advances_seq(
    dev_app_and_client, seed_running_container, sysadmin_env,
):
    """Two POSTs with same correlation_id produce 2 rows; seq advances per insert."""
    _app, client = dev_app_and_client
    container_row_id, _instance_id = seed_running_container
    first = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "dup1", "chat_id": "1", "length_chars": 1},
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    second = await client.post(
        f"/v1/agents/{container_row_id}/events/inject-test-event",
        json={"correlation_id": "dup1", "chat_id": "1", "length_chars": 1},
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert int(second.json()["seq"]) > int(first.json()["seq"])
