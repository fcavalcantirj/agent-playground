"""POST /v1/runs + GET /v1/runs/{id} tests.

Covers:

- **SC-05** happy path: valid recipe + model + BYOK → 200 + PASS verdict.
- **SC-08** persistence: every run writes a ``runs`` row + bumps
  ``agent_instances.total_runs``.
- Negative paths: missing Authorization (401), unknown recipe (404),
  SQL-injection-shaped ``recipe_name`` (422), inline YAML field rejected
  (422), invalid ULID in GET (400), unknown ULID in GET (404).

Tests split into two tiers:

- No-DB-needed (``test_missing_authorization_returns_401``,
  ``test_recipe_name_injection_is_safe``, ``test_inline_yaml_rejected``,
  ``test_get_run_invalid_ulid_returns_400``) — run without Docker. These
  short-circuit at the validation layer before any DB call.
- ``api_integration`` marker — spin up Postgres via testcontainers.
"""
from __future__ import annotations

import pytest

VALID_AUTH = {"Authorization": "Bearer sk-test-fake"}


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_run_hermes_gpt4o_mini(async_client, mock_run_cell):
    """SC-05: POST /v1/runs with valid recipe + model + BYOK → 200 + PASS."""
    mock_run_cell(verdict_category="PASS", wall_s=1.5, exit_code=0)
    r = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={
            "recipe_name": "hermes",
            "model": "openai/gpt-4o-mini",
            "prompt": "who are you?",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "PASS"
    assert body["verdict"] == "PASS"
    assert len(body["run_id"]) == 26
    # agent_instance_id is the UUID-stringified upsert result
    assert body["agent_instance_id"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_persist_run_row(async_client, mock_run_cell, db_pool):
    """SC-08: a successful POST writes a runs row with verdict filled."""
    mock_run_cell(verdict_category="PASS")
    r = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT verdict, category, completed_at FROM runs WHERE id = $1",
            run_id,
        )
    assert row is not None
    assert row["verdict"] == "PASS"
    assert row["category"] == "PASS"
    assert row["completed_at"] is not None


@pytest.mark.asyncio
async def test_missing_authorization_returns_401(async_client):
    """POST without Authorization header → 401 UNAUTHORIZED."""
    r = await async_client.post(
        "/v1/runs",
        json={"recipe_name": "hermes", "model": "m"},
    )
    assert r.status_code == 401
    env = r.json()
    assert env["error"]["code"] == "UNAUTHORIZED"
    # Envelope must have request_id (pulled from CorrelationIdMiddleware)
    assert env["error"]["request_id"]


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_unknown_recipe_returns_404(async_client):
    """POST with recipe_name that's not in app.state.recipes → 404."""
    r = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={"recipe_name": "bogus", "model": "m"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RECIPE_NOT_FOUND"


@pytest.mark.asyncio
async def test_recipe_name_injection_is_safe(async_client):
    """Pydantic pattern validator rejects SQL-injection shapes at parse time."""
    r = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={"recipe_name": "'; DROP TABLE runs; --", "model": "m"},
    )
    # 422 — FastAPI's default for Pydantic validation errors
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_inline_yaml_rejected(async_client):
    """RunRequest has ``extra=forbid`` — inline recipe YAML field is rejected."""
    r = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={
            "recipe_name": "hermes",
            "model": "m",
            "recipe_yaml": "name: injected\n",
        },
    )
    assert r.status_code == 422


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_get_run_by_id_returns_persisted(async_client, mock_run_cell):
    """GET /v1/runs/{id} returns the full run shape after a POST."""
    mock_run_cell(verdict_category="PASS")
    post = await async_client.post(
        "/v1/runs",
        headers=VALID_AUTH,
        json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
    )
    assert post.status_code == 200, post.text
    run_id = post.json()["run_id"]
    got = await async_client.get(f"/v1/runs/{run_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["run_id"] == run_id
    assert body["recipe"] == "hermes"
    assert body["model"] == "m"
    assert body["verdict"] == "PASS"
    assert body["category"] == "PASS"


@pytest.mark.asyncio
async def test_get_run_invalid_ulid_returns_400(async_client):
    """GET /v1/runs/short → 400 INVALID_REQUEST (ULID pre-check)."""
    r = await async_client.get("/v1/runs/short")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_get_run_unknown_returns_404(async_client):
    """GET /v1/runs/{valid-but-missing-ulid} → 404."""
    # 26-char Crockford-valid ULID that will never exist in the DB.
    # ``01HQZX9MZVJ5KQXYZ123456789`` is exactly 26 chars + uses only
    # Crockford-legal letters (no I, L, O, U).
    r = await async_client.get("/v1/runs/01HQZX9MZVJ5KQXYZ123456789")
    assert r.status_code == 404


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_agent_instance_dedupes_across_runs(async_client, mock_run_cell, db_pool):
    """3 POSTs with same (recipe, model) share one agent_instances row.

    SC-08 subclause: ``agent_instances.total_runs`` bumps by 1 per run
    via the ``ON CONFLICT DO UPDATE`` upsert.
    """
    mock_run_cell(verdict_category="PASS")
    for _ in range(3):
        r = await async_client.post(
            "/v1/runs",
            headers=VALID_AUTH,
            json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
        )
        assert r.status_code == 200, r.text
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, total_runs FROM agent_instances "
            "WHERE recipe_name = $1 AND model = $2",
            "hermes", "m",
        )
    assert len(rows) == 1, f"expected 1 agent_instance row, got {len(rows)}"
    assert rows[0]["total_runs"] == 3
