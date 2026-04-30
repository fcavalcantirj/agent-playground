"""Phase 22c.3-08 Task 2 — DELETE /v1/agents/:id/messages integration tests.

Real PG via testcontainers. Coverage:

  * ``test_delete_history_clears_messages_and_events``
  * ``test_delete_history_other_user_returns_404``
  * ``test_delete_history_no_session_returns_401``
  * ``test_delete_history_empty_agent_returns_204``
  * ``test_delete_history_preserves_non_inapp_events``
  * ``test_delete_history_preserves_agent_instance_and_container`` (D-44)
"""
from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


async def _seed_agent_with_events(
    pool, user_id_str: str,
    n_messages: int = 3,
    n_inapp_events: int = 3,
    n_other_events: int = 2,
):
    """Seed agent_instance + agent_container + messages + events.

    Returns ``(agent_id, container_row_id)``.
    """
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    user_id = UUID(user_id_str)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, 'm-test', $4)
            """,
            agent_id, user_id, recipe_name, name,
        )
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
        # inapp_messages
        for i in range(n_messages):
            await conn.execute(
                """
                INSERT INTO inapp_messages (agent_id, user_id, content)
                VALUES ($1, $2, $3)
                """,
                agent_id, user_id, f"msg-{i}",
            )
        # agent_events: 3 inapp_outbound + 2 reply_sent (V13 7-kind set)
        seq = 0
        for i in range(n_inapp_events):
            seq += 1
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload, published)
                VALUES ($1, $2, 'inapp_outbound', $3::jsonb, true)
                """,
                container_row_id, seq,
                json.dumps({
                    "content": f"reply-{i}",
                    "source": "agent",
                    "captured_at": "2026-04-30T20:00:00Z",
                }),
            )
        for i in range(n_other_events):
            seq += 1
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload, published)
                VALUES ($1, $2, 'reply_sent', $3::jsonb, true)
                """,
                container_row_id, seq,
                json.dumps({
                    "chat_id": "12345",
                    "length_chars": 10,
                    "captured_at": "2026-04-30T20:00:00Z",
                }),
            )
    return agent_id, container_row_id


async def test_delete_history_clears_messages_and_events(
    async_client, db_pool, authenticated_cookie,
):
    """DELETE clears 3 inapp_messages + 3 agent_events (inapp_outbound).

    The 2 reply_sent events stay (defense-in-depth: kind filter scopes
    delete to inapp_* only).
    """
    agent_id, container_row_id = await _seed_agent_with_events(
        db_pool, authenticated_cookie["_user_id"],
        n_messages=3, n_inapp_events=3, n_other_events=2,
    )

    r = await async_client.delete(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text

    async with db_pool.acquire() as conn:
        msgs = await conn.fetchval(
            "SELECT COUNT(*) FROM inapp_messages WHERE agent_id=$1", agent_id,
        )
        inapp_evs = await conn.fetchval(
            """
            SELECT COUNT(*) FROM agent_events
            WHERE agent_container_id=$1 AND kind='inapp_outbound'
            """,
            container_row_id,
        )
        other_evs = await conn.fetchval(
            """
            SELECT COUNT(*) FROM agent_events
            WHERE agent_container_id=$1 AND kind='reply_sent'
            """,
            container_row_id,
        )
    assert msgs == 0, f"inapp_messages count {msgs}, expected 0"
    assert inapp_evs == 0, f"inapp_outbound count {inapp_evs}, expected 0"
    assert other_evs == 2, (
        f"reply_sent count {other_evs}, expected 2 — kind filter leaked"
    )


async def test_delete_history_other_user_returns_404(
    async_client, db_pool, authenticated_cookie, second_authenticated_cookie,
):
    """User A's agent; user B calls DELETE → 404 AGENT_NOT_FOUND."""
    agent_id, _ = await _seed_agent_with_events(
        db_pool, authenticated_cookie["_user_id"],
        n_messages=2, n_inapp_events=0, n_other_events=0,
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": second_authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"

    # Defense in depth: rows still present (cross-tenant DELETE blocked).
    async with db_pool.acquire() as conn:
        msgs = await conn.fetchval(
            "SELECT COUNT(*) FROM inapp_messages WHERE agent_id=$1", agent_id,
        )
    assert msgs == 2, f"cross-tenant DELETE leaked: messages count {msgs}"


async def test_delete_history_no_session_returns_401(
    async_client, db_pool,
):
    """No cookie → 401 (require_user gate)."""
    r = await async_client.delete(f"/v1/agents/{uuid4()}/messages")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_delete_history_empty_agent_returns_204(
    async_client, db_pool, authenticated_cookie,
):
    """Agent exists but no messages/events → 204 + 0 rows deleted."""
    agent_id, _ = await _seed_agent_with_events(
        db_pool, authenticated_cookie["_user_id"],
        n_messages=0, n_inapp_events=0, n_other_events=0,
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text


async def test_delete_history_preserves_agent_instance_and_container(
    async_client, db_pool, authenticated_cookie,
):
    """D-44: DELETE /messages MUST NOT touch agent_instances or agent_containers.

    Deleting messages is a separate action from deleting the agent.
    """
    agent_id, container_row_id = await _seed_agent_with_events(
        db_pool, authenticated_cookie["_user_id"],
        n_messages=1, n_inapp_events=1, n_other_events=0,
    )
    r = await async_client.delete(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204

    async with db_pool.acquire() as conn:
        ai = await conn.fetchval(
            "SELECT 1 FROM agent_instances WHERE id=$1", agent_id,
        )
        ac = await conn.fetchval(
            "SELECT 1 FROM agent_containers WHERE id=$1", container_row_id,
        )
    assert ai == 1, "agent_instances row was deleted (D-44 violated)"
    assert ac == 1, "agent_containers row was deleted (D-44 violated)"


async def test_delete_history_kind_filter_includes_failed_events(
    async_client, db_pool, authenticated_cookie,
):
    """The 3 inapp_* kinds (inapp_inbound + inapp_outbound + inapp_outbound_failed)
    are all swept; reply_sent / reply_failed / agent_ready / agent_error stay.
    """
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = uuid4()
    container_row_id = uuid4()
    recipe_name = f"recipe-{uuid4().hex[:8]}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, 'm', 'a')",
            agent_id, user_id, recipe_name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id, ready_at)
            VALUES ($1, $2, $3, $4, 'persistent', 'running',
                    $5, NOW())
            """,
            container_row_id, agent_id, user_id, recipe_name,
            f"x{uuid4().hex[:24]}",
        )
        # 1 of each inapp_* kind + 1 reply_sent.
        seq = 0
        for kind, payload in (
            ("inapp_inbound", {"content": "in", "source": "user",
                               "from_user_id": str(user_id),
                               "captured_at": "2026-04-30T20:00:00Z"}),
            ("inapp_outbound", {"content": "out", "source": "agent",
                                "captured_at": "2026-04-30T20:00:00Z"}),
            ("inapp_outbound_failed", {"error_type": "bot_5xx",
                                       "message": "boom",
                                       "retry_count": 1,
                                       "captured_at": "2026-04-30T20:00:00Z"}),
            ("reply_sent", {"chat_id": "1", "length_chars": 1,
                            "captured_at": "2026-04-30T20:00:00Z"}),
        ):
            seq += 1
            await conn.execute(
                """
                INSERT INTO agent_events
                    (agent_container_id, seq, kind, payload, published)
                VALUES ($1, $2, $3, $4::jsonb, true)
                """,
                container_row_id, seq, kind, json.dumps(payload),
            )

    r = await async_client.delete(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 204, r.text

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT kind FROM agent_events WHERE agent_container_id=$1 ORDER BY seq",
            container_row_id,
        )
    kinds_left = [r["kind"] for r in rows]
    assert kinds_left == ["reply_sent"], (
        f"only reply_sent should survive; got {kinds_left}"
    )
