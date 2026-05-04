"""DELETE /v1/agents/:id integration tests.

Real PG via testcontainers. Coverage:

  * test_delete_agent_happy_path_no_container
  * test_delete_agent_unowned_returns_404
  * test_delete_agent_no_session_returns_401
  * test_delete_agent_with_running_container_stops_and_deletes
  * test_delete_agent_double_delete_idempotent_404
  * test_delete_agent_runs_explicit_delete
  * test_delete_agent_tolerant_to_docker_stop_failure

Companion to ``DELETE /v1/agents/:id/messages``
(``test_agent_messages_delete.py``) — that one clears history but
preserves the agent + container (D-44). This route deletes everything.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def _seed_agent(
    pool, user_id_str: str, *, with_running_container: bool = False,
    with_runs: int = 0, with_messages: int = 0,
):
    """Seed agent_instances + optional agent_containers + runs + messages.

    Returns ``(agent_id, container_row_id_or_None)``.
    """
    agent_id = uuid4()
    user_id = UUID(user_id_str)
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    container_row_id = None

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, 'm-test', $4)
            """,
            agent_id, user_id, recipe_name, name,
        )
        if with_running_container:
            container_row_id = uuid4()
            docker_container_id = f"deadbeef{uuid4().hex[:24]}"
            await conn.execute(
                """
                INSERT INTO agent_containers
                    (id, agent_instance_id, user_id, recipe_name,
                     deploy_mode, container_status, container_id, ready_at)
                VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, NOW())
                """,
                container_row_id, agent_id, user_id, recipe_name,
                docker_container_id,
            )
        for i in range(with_runs):
            await conn.execute(
                """
                INSERT INTO runs (id, agent_instance_id, prompt, verdict)
                VALUES ($1, $2, $3, 'PASS')
                """,
                f"01HRUN{uuid4().hex[:20].upper()}",
                agent_id,
                f"prompt-{i}",
            )
        for i in range(with_messages):
            await conn.execute(
                """
                INSERT INTO inapp_messages (agent_id, user_id, content)
                VALUES ($1, $2, $3)
                """,
                agent_id, user_id, f"msg-{i}",
            )
    return agent_id, container_row_id


async def test_delete_agent_happy_path_no_container(
    async_client, db_pool, authenticated_cookie,
):
    """Agent with no container, no runs, no messages → 204 + row gone."""
    agent_id, _ = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text

    async with db_pool.acquire() as conn:
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
    assert ai is None, "agent_instances row not deleted"


async def test_delete_agent_unowned_returns_404(
    async_client, db_pool, authenticated_cookie, second_authenticated_cookie,
):
    """User A's agent; user B calls DELETE → 404 AGENT_NOT_FOUND.

    Defense-in-depth: row still present (cross-tenant DELETE blocked).
    """
    agent_id, _ = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": second_authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"

    async with db_pool.acquire() as conn:
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
    assert ai == 1, "cross-tenant DELETE leaked"


async def test_delete_agent_no_session_returns_401(async_client, db_pool):
    """No cookie → 401 (require_user gate)."""
    r = await async_client.delete(f"/v1/agents/{uuid4()}")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_delete_agent_with_running_container_stops_and_deletes(
    async_client, db_pool, authenticated_cookie, monkeypatch,
):
    """Running container → execute_persistent_stop is called, then
    cascade-deletes everything. We don't require a real docker daemon —
    monkeypatch the runner stop primitive to a no-op coroutine.
    """
    import api_server.routes.agent_lifecycle as al

    captured: dict = {}

    async def _fake_stop(container_id, **kwargs):
        captured["container_id"] = container_id
        captured["kwargs"] = dict(kwargs)
        return {
            "stopped_gracefully": True,
            "force_killed": False,
            "exit_code": 0,
            "stop_wall_s": 0.1,
        }

    monkeypatch.setattr(al, "execute_persistent_stop", _fake_stop)

    agent_id, container_row_id = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"],
        with_running_container=True, with_messages=2,
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text
    assert "container_id" in captured, "execute_persistent_stop was not called"

    async with db_pool.acquire() as conn:
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
        ac = await conn.fetchval(
            "SELECT 1 FROM agent_containers WHERE id=$1", container_row_id,
        )
        msgs = await conn.fetchval(
            "SELECT COUNT(*) FROM inapp_messages WHERE agent_id=$1", agent_id,
        )
    assert ai is None, "agent_instances not deleted"
    assert ac is None, "agent_containers not cascade-deleted"
    assert msgs == 0, "inapp_messages not cascade-deleted"


async def test_delete_agent_double_delete_idempotent_404(
    async_client, db_pool, authenticated_cookie,
):
    """First DELETE → 204. Second DELETE → 404 (idempotent end-state)."""
    agent_id, _ = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"],
    )
    r1 = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r1.status_code == 204, r1.text
    r2 = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r2.status_code == 404, r2.text
    assert r2.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_delete_agent_runs_explicit_delete(
    async_client, db_pool, authenticated_cookie,
):
    """3 runs rows for the agent are deleted explicitly (no FK cascade
    on runs.agent_instance_id per migration 001) so the agent_instances
    DELETE doesn't error on FK violation.
    """
    agent_id, _ = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"], with_runs=3,
    )
    async with db_pool.acquire() as conn:
        before = await conn.fetchval(
            "SELECT COUNT(*) FROM runs WHERE agent_instance_id=$1", agent_id,
        )
    assert before == 3, f"seeded 3 runs, got {before}"

    r = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text

    async with db_pool.acquire() as conn:
        after_runs = await conn.fetchval(
            "SELECT COUNT(*) FROM runs WHERE agent_instance_id=$1", agent_id,
        )
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
    assert after_runs == 0, f"runs not cleaned: {after_runs}"
    assert ai is None, "agent_instances not deleted"


async def test_delete_agent_tolerant_to_docker_stop_failure(
    async_client, db_pool, authenticated_cookie, monkeypatch,
):
    """If execute_persistent_stop raises, DB delete still completes.

    Tolerance is by design: orphan reaper sweeps the leaked docker
    container; never block deletion on docker flakiness.
    """
    import api_server.routes.agent_lifecycle as al

    async def _failing_stop(*args, **kwargs):
        raise RuntimeError("docker daemon down")

    monkeypatch.setattr(al, "execute_persistent_stop", _failing_stop)

    agent_id, container_row_id = await _seed_agent(
        db_pool, authenticated_cookie["_user_id"],
        with_running_container=True,
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text

    async with db_pool.acquire() as conn:
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
        ac = await conn.fetchval(
            "SELECT 1 FROM agent_containers WHERE id=$1", container_row_id,
        )
    assert ai is None, "DB delete did not complete despite docker failure"
    assert ac is None, "agent_containers not cascade-deleted"
