"""Phase 22b-05 Task 1 — errors.py extension + Task 3 — full auth matrix.

This file is populated across two tasks:
- Task 1: Unit tests for the two new ErrorCode constants.
- Task 3: Integration tests that hit GET /v1/agents/:id/events with
  various Authorization shapes — Bearer required, AP_SYSADMIN_TOKEN
  bypass, ownership 404, ANONYMOUS_USER_ID 200.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api_server.constants import ANONYMOUS_USER_ID
from api_server.models.errors import ErrorCode, make_error_envelope


# ---------------------------------------------------------------------------
# Task 1 — pure unit tests (no DB / no app)
# ---------------------------------------------------------------------------


def test_concurrent_poll_limit_constant():
    assert ErrorCode.CONCURRENT_POLL_LIMIT == "CONCURRENT_POLL_LIMIT"


def test_event_stream_unavailable_constant():
    assert ErrorCode.EVENT_STREAM_UNAVAILABLE == "EVENT_STREAM_UNAVAILABLE"


def test_concurrent_poll_limit_maps_to_rate_limit_type():
    envelope = make_error_envelope(
        ErrorCode.CONCURRENT_POLL_LIMIT,
        "another long-poll is already active for this agent",
        param="agent_id",
        category=None,
    )
    assert envelope["error"]["code"] == "CONCURRENT_POLL_LIMIT"
    assert envelope["error"]["type"] == "rate_limit_error"
    assert envelope["error"]["param"] == "agent_id"


def test_event_stream_unavailable_maps_to_infra_type():
    envelope = make_error_envelope(
        ErrorCode.EVENT_STREAM_UNAVAILABLE,
        "watcher dead",
        param=None,
        category=None,
    )
    assert envelope["error"]["code"] == "EVENT_STREAM_UNAVAILABLE"
    assert envelope["error"]["type"] == "infra_error"


# ---------------------------------------------------------------------------
# Task 3 — integration auth matrix (real PG + real FastAPI app + real route)
# ---------------------------------------------------------------------------

API_SERVER_DIR = Path(__file__).resolve().parent.parent
ANON_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def isolated_recipes_dir(tmp_path) -> Path:
    """Tmp recipes dir with only hermes.yaml — bypasses DI-01 openclaw bug."""
    src = API_SERVER_DIR.parent / "recipes" / "hermes.yaml"
    dst_dir = tmp_path / "recipes"
    dst_dir.mkdir()
    shutil.copy(src, dst_dir / "hermes.yaml")
    return dst_dir


@pytest.fixture
def sysadmin_env(monkeypatch):
    token = "sysadmin-test-token-" + uuid4().hex
    monkeypatch.setenv("AP_SYSADMIN_TOKEN", token)
    return token


@pytest.fixture
def app_env_no_sysadmin(monkeypatch, isolated_recipes_dir, migrated_pg):
    """Set env for create_app() WITHOUT AP_SYSADMIN_TOKEN."""
    monkeypatch.delenv("AP_SYSADMIN_TOKEN", raising=False)
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))

    def _normalize(raw: str) -> str:
        return raw.replace(
            "postgresql+psycopg2://", "postgresql://"
        ).replace("+psycopg2", "")

    monkeypatch.setenv(
        "DATABASE_URL", _normalize(migrated_pg.get_connection_url())
    )
    return True


@pytest.fixture
def app_env_with_sysadmin(
    monkeypatch, isolated_recipes_dir, migrated_pg, sysadmin_env
):
    """Set env for create_app() WITH AP_SYSADMIN_TOKEN active."""
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_RECIPES_DIR", str(isolated_recipes_dir))

    def _normalize(raw: str) -> str:
        return raw.replace(
            "postgresql+psycopg2://", "postgresql://"
        ).replace("+psycopg2", "")

    monkeypatch.setenv(
        "DATABASE_URL", _normalize(migrated_pg.get_connection_url())
    )
    return sysadmin_env


@pytest_asyncio.fixture
async def app_and_client_no_sysadmin(app_env_no_sysadmin, db_pool):
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
async def app_and_client_sysadmin(app_env_with_sysadmin, db_pool):
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
    """Insert an agent_instances row owned by ANONYMOUS_USER_ID; return id.

    The plan's `<read_first>` notes this fixture may not yet exist in the
    Phase 22 conftest — defining inline here per Plan 22b-02 SUMMARY's
    decision-4 pattern (per-test inline fixtures, no conftest pollution).
    """
    name = f"auth-test-agent-{uuid4().hex[:8]}"
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1,
                    'hermes', 'openrouter/anthropic/claude-haiku-4.5', $2)
            RETURNING id
            """,
            ANON_USER_ID,
            name,
        )
    return row["id"]


# ---- The 6 integration tests (auth matrix) ----


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_missing_authorization_returns_401(app_and_client_sysadmin):
    _app, client = app_and_client_sysadmin
    resp = await client.get(
        f"/v1/agents/{uuid4()}/events?timeout_s=1", timeout=5.0
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"
    assert resp.json()["error"].get("param") == "Authorization"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_non_bearer_scheme_returns_401(app_and_client_sysadmin):
    _app, client = app_and_client_sysadmin
    resp = await client.get(
        f"/v1/agents/{uuid4()}/events?timeout_s=1",
        headers={"Authorization": "Token abc123"},
        timeout=5.0,
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_empty_bearer_returns_401(app_and_client_sysadmin):
    _app, client = app_and_client_sysadmin
    resp = await client.get(
        f"/v1/agents/{uuid4()}/events?timeout_s=1",
        headers={"Authorization": "Bearer "},
        timeout=5.0,
    )
    assert resp.status_code == 401
    assert "empty" in resp.json()["error"]["message"].lower()


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_sysadmin_bypass_on_nonexistent_agent(
    app_and_client_sysadmin, sysadmin_env,
):
    """AP_SYSADMIN_TOKEN bypass: even a made-up agent_id returns 200 empty."""
    _app, client = app_and_client_sysadmin
    random_agent = uuid4()
    resp = await client.get(
        f"/v1/agents/{random_agent}/events?timeout_s=1",
        headers={"Authorization": f"Bearer {sysadmin_env}"},
        timeout=5.0,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["events"] == []
    assert body["timed_out"] is True


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_non_sysadmin_nonexistent_agent_404(app_and_client_no_sysadmin):
    """Without sysadmin bypass and no matching agent_instance -> 404."""
    _app, client = app_and_client_no_sysadmin
    random_agent = uuid4()
    resp = await client.get(
        f"/v1/agents/{random_agent}/events?timeout_s=1",
        headers={"Authorization": "Bearer anyvalue"},
        timeout=5.0,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "AGENT_NOT_FOUND"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_anonymous_user_existing_agent_200(
    app_and_client_no_sysadmin, seed_agent_instance,
):
    """Regular bearer (non-sysadmin) + ANONYMOUS_USER_ID-owned agent -> 200."""
    _app, client = app_and_client_no_sysadmin
    resp = await client.get(
        f"/v1/agents/{seed_agent_instance}/events?since_seq=9999&timeout_s=1",
        headers={"Authorization": "Bearer some-regular-bearer"},
        timeout=5.0,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["timed_out"] is True
