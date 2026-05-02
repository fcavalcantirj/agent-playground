"""Phase 23 plan 04 — GET /v1/agents `status` + `last_activity` integration tests.

Real PG via testcontainers (golden rule #1 — no mocks). Each test marked
``api_integration``; the ``async_client`` fixture from conftest builds the
full FastAPI app via ``create_app()`` so middleware + route + DB stack
exercised end-to-end.

Coverage matrix (8 tests — D-10/D-11/D-27 + cross-user + backward-compat):

  * ``test_get_agents_status_running_for_live_container``  (D-10)
  * ``test_get_agents_status_none_when_no_container``      (D-11 — never started)
  * ``test_get_agents_status_none_when_container_stopped`` (D-11 — only LIVE counts)
  * ``test_get_agents_last_activity_none_for_cold_account`` (D-27 — both NULL)
  * ``test_get_agents_last_activity_from_inapp_messages``  (D-27 — message-only)
  * ``test_get_agents_last_activity_max_of_runs_and_messages`` (D-27 — GREATEST)
  * ``test_get_agents_cross_user_isolation_preserved``     (V4 invariant regression)
  * ``test_get_agents_existing_fields_preserved``          (backward-compat)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def _seed_agent_for_user(pool, user_id: str) -> UUID:
    """INSERT an agent_instance + a 'running' agent_container for the user.

    Mirrors ``tests/routes/test_agent_messages_post.py::_seed_agent_for_user``
    verbatim so the helper signature/contract stays identical across plan-23
    test files. Returns the ``agent_instances.id`` UUID.
    """
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, 'm-test', $4)
            """,
            agent_id, UUID(user_id), recipe_name, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, NOW())
            """,
            container_row_id, agent_id, UUID(user_id), recipe_name,
            docker_container_id,
        )
    return agent_id


# ---------------------------------------------------------------------------
# Status field — D-10 / D-11
# ---------------------------------------------------------------------------


async def test_get_agents_status_running_for_live_container(
    async_client, db_pool, authenticated_cookie,
):
    """D-10: live agent_containers row → status reflects container_status."""
    # _seed_agent_for_user inserts agent_containers with container_status='running'.
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    agents = r.json()["agents"]
    matching = [a for a in agents if a["id"] == str(agent_id)]
    assert len(matching) == 1, f"expected 1 agent matching {agent_id}, got {matching}"
    assert matching[0]["status"] == "running"


async def test_get_agents_status_none_when_no_container(
    async_client, db_pool, authenticated_cookie,
):
    """D-11: agent without an agent_containers row → status=None."""
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = uuid4()
    async with db_pool.acquire() as conn:
        # Insert agent_instances ONLY — skip agent_containers.
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'rec', 'm', $3)
            """,
            agent_id, user_id, f"cold-agent-{uuid4().hex[:8]}",
        )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    assert matching[0]["status"] is None


async def test_get_agents_status_none_when_container_stopped(
    async_client, db_pool, authenticated_cookie,
):
    """D-11: stopped_at IS NOT NULL → not selected → status=None.

    Confirms the LATERAL JOIN's ``WHERE stopped_at IS NULL`` filter — only
    LIVE containers count. A historical 'stopped'/'crashed' row must NOT
    surface as the dashboard's status indicator.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = uuid4()
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'rec', 'm', $3)
            """,
            agent_id, user_id, f"stopped-agent-{uuid4().hex[:8]}",
        )
        # NOTE: even though container_status='running' here, ``stopped_at``
        # IS NOT NULL — the partial LATERAL filters this row out. The
        # production state-machine sets container_status='stopped' AND
        # stopped_at=NOW() together, but the SQL invariant under test is
        # the ``stopped_at IS NULL`` predicate, so we exercise the boundary
        # by writing a row that would only be returned if the predicate
        # were missing.
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id,
                 ready_at, stopped_at)
            VALUES ($1, $2, $3, 'rec', 'persistent', 'stopped',
                    'docker-id', NOW(), NOW())
            """,
            uuid4(), agent_id, user_id,
        )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    assert matching[0]["status"] is None


# ---------------------------------------------------------------------------
# Last activity — D-27 + GREATEST NULL semantics
# ---------------------------------------------------------------------------


async def test_get_agents_last_activity_none_for_cold_account(
    async_client, db_pool, authenticated_cookie,
):
    """D-27: no runs (last_run_at IS NULL) + no messages → last_activity=None.

    ``_seed_agent_for_user`` inserts agent_instances WITHOUT setting
    ``last_run_at``, so the agent is "deployed but never run/messaged".
    Both inputs to GREATEST are NULL → result is NULL (PG semantics).
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    assert matching[0]["last_activity"] is None


async def test_get_agents_last_activity_from_inapp_messages(
    async_client, db_pool, authenticated_cookie,
):
    """D-27: an inapp_messages row drives last_activity even when last_run_at IS NULL.

    GREATEST(NULL, msg_time) = msg_time in PostgreSQL ≥ 8.4. Confirms the
    cold-runs-but-warm-chat path renders correctly on the dashboard.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = await _seed_agent_for_user(db_pool, authenticated_cookie["_user_id"])
    msg_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, created_at)
            VALUES ($1, $2, $3, 'hi', 'done', $4)
            """,
            uuid4(), agent_id, user_id, msg_time,
        )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    assert matching[0]["last_activity"] is not None
    parsed = datetime.fromisoformat(
        matching[0]["last_activity"].replace("Z", "+00:00")
    )
    # Normalize to UTC for the abs-delta check (asyncpg returns tz-aware
    # timestamps so the parsed value already carries an offset).
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    assert abs((parsed - msg_time).total_seconds()) < 5


async def test_get_agents_last_activity_max_of_runs_and_messages(
    async_client, db_pool, authenticated_cookie,
):
    """D-27: last_activity = GREATEST(last_run_at, MAX(inapp_messages.created_at)).

    Seeds an agent with last_run_at=2h ago AND an inapp_message=5min ago;
    asserts the newer (message) timestamp wins.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = uuid4()
    older = datetime.now(timezone.utc) - timedelta(hours=2)
    newer = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances
                (id, user_id, recipe_name, model, name, last_run_at)
            VALUES ($1, $2, 'rec', 'm', $3, $4)
            """,
            agent_id, user_id, f"mixed-{uuid4().hex[:8]}", older,
        )
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, created_at)
            VALUES ($1, $2, $3, 'recent', 'done', $4)
            """,
            uuid4(), agent_id, user_id, newer,
        )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    parsed = datetime.fromisoformat(
        matching[0]["last_activity"].replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    # The newer (5-min-ago message) timestamp must win — never the older
    # (2h-ago last_run_at).
    assert abs((parsed - newer).total_seconds()) < 5, (
        f"expected last_activity≈{newer} (message), got {parsed}"
    )
    # Belt-and-braces: confirm last_run_at is preserved as the older value
    # (proves we didn't overwrite the existing field).
    last_run_parsed = datetime.fromisoformat(
        matching[0]["last_run_at"].replace("Z", "+00:00")
    )
    if last_run_parsed.tzinfo is None:
        last_run_parsed = last_run_parsed.replace(tzinfo=timezone.utc)
    assert abs((last_run_parsed - older).total_seconds()) < 5


# ---------------------------------------------------------------------------
# Regression — cross-user isolation + backward compat
# ---------------------------------------------------------------------------


async def test_get_agents_cross_user_isolation_preserved(
    async_client, db_pool, authenticated_cookie, second_authenticated_cookie,
):
    """V4 invariant: user A doesn't see user B's agents (regression check).

    The Phase 23-04 LATERAL extension MUST NOT widen the cross-user surface.
    The existing ``WHERE ai.user_id = $1`` filter is the only thing standing
    between caller A and caller B — re-verify here.
    """
    agent_id_b = await _seed_agent_for_user(
        db_pool, second_authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},  # user A
    )
    assert r.status_code == 200, r.text
    agent_ids = {a["id"] for a in r.json()["agents"]}
    assert str(agent_id_b) not in agent_ids, (
        f"CROSS-USER LEAK: bob's agent surfaced in alice's view: {agent_ids}"
    )


async def test_get_agents_existing_fields_preserved(
    async_client, db_pool, authenticated_cookie,
):
    """Backward compat: every Phase 22c-09 AgentSummary field is still present.

    A dashboard consumer (Phase 22c-09 callers, Phase 23 frontend) MUST be
    able to read every prior field even after the schema-extension. This
    test asserts presence (not values) for the entire prior contract.
    """
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.get(
        "/v1/agents",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    matching = [a for a in r.json()["agents"] if a["id"] == str(agent_id)]
    assert len(matching) == 1
    a = matching[0]
    for field in (
        "id", "name", "recipe_name", "model", "personality", "created_at",
        "last_run_at", "total_runs", "last_verdict", "last_category",
        "last_run_id",
    ):
        assert field in a, f"backward-compat field missing: {field}"
    # New fields exist.
    assert "status" in a
    assert "last_activity" in a
