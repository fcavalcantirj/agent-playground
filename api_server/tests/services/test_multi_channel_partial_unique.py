"""2026-05-17 — Migration 018: per-channel partial-unique index.

Tests the schema-level invariant that a single agent_instance CAN have
multiple `running` agent_containers as long as each is on a distinct
channel_type. Before migration 018 the invariant was "at most one
running container per agent" — that broke hermes's multi-channel
gateway-daemon mode (inapp + telegram simultaneously).

Real Postgres testcontainer (golden rule #1 — no mocks).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg
import pytest


pytestmark = pytest.mark.api_integration


async def _seed_user(pool, *, tier: str = "free") -> UUID:
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, provider, sub, email, display_name, tier) "
            "VALUES ($1, 'google', $2, $3, $4, $5)",
            user_id, f"sub-{user_id.hex[:12]}",
            f"u-{user_id.hex[:6]}@example.com",
            f"User {user_id.hex[:6]}", tier,
        )
    return user_id


async def _seed_agent(pool, *, user_id: UUID) -> UUID:
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, 'hermes', 'm-test', $3)",
            agent_id, user_id, f"agent-{agent_id.hex[:6]}",
        )
    return agent_id


async def _insert_running_container(
    pool, *, agent_id: UUID, user_id: UUID, channel_type: str,
) -> UUID:
    """Insert an agent_containers row directly at status='running'.

    Mimics the runtime sequence (pending → starting → running) but in
    one INSERT for test simplicity. The partial-unique index fires on
    status='running' regardless of how the row got there.
    """
    container_row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               deploy_mode, container_status, channel_type)
            VALUES ($1, $2, $3, 'hermes', 'persistent', 'running', $4)
            """,
            container_row_id, agent_id, user_id, channel_type,
        )
    return container_row_id


async def test_two_running_containers_on_DIFFERENT_channels_for_same_agent(db_pool):
    """The point of migration 018: inapp + telegram simultaneously OK.

    Before 018: this 2nd INSERT would raise UniqueViolationError.
    After 018: both rows coexist, distinct on (agent_instance_id,
    channel_type).
    """
    user_id = await _seed_user(db_pool, tier="ultra")  # cap doesn't matter; this is the schema test
    agent_id = await _seed_agent(db_pool, user_id=user_id)

    await _insert_running_container(
        db_pool, agent_id=agent_id, user_id=user_id, channel_type="inapp",
    )
    # Second container — telegram channel on the same agent. Must succeed.
    await _insert_running_container(
        db_pool, agent_id=agent_id, user_id=user_id, channel_type="telegram",
    )

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT channel_type FROM agent_containers "
            "WHERE agent_instance_id = $1 AND container_status = 'running' "
            "ORDER BY channel_type",
            agent_id,
        )
    assert [r["channel_type"] for r in rows] == ["inapp", "telegram"], (
        f"expected one inapp + one telegram running for agent {agent_id}; "
        f"got {[r['channel_type'] for r in rows]}"
    )


async def test_two_running_containers_on_SAME_channel_for_same_agent_still_blocked(
    db_pool,
):
    """The partial-unique still binds per (agent_instance_id, channel_type).

    Migration 018 is NOT a license to spawn arbitrary duplicate containers
    on the same channel. It only allows ONE container per (agent, channel)
    in running status. A second 'running' inapp container for the same
    agent must still raise UniqueViolationError.
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)

    await _insert_running_container(
        db_pool, agent_id=agent_id, user_id=user_id, channel_type="inapp",
    )
    # Second container on the SAME channel — must violate partial-unique.
    with pytest.raises(asyncpg.UniqueViolationError):
        await _insert_running_container(
            db_pool, agent_id=agent_id, user_id=user_id, channel_type="inapp",
        )


async def test_two_running_containers_on_same_channel_DIFFERENT_agents_ok(db_pool):
    """Cross-agent isolation: two different agents (each owned by the
    same user) CAN both have a running inapp container. The partial-
    unique scopes by agent_instance_id.
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_a = await _seed_agent(db_pool, user_id=user_id)
    agent_b = await _seed_agent(db_pool, user_id=user_id)

    await _insert_running_container(
        db_pool, agent_id=agent_a, user_id=user_id, channel_type="inapp",
    )
    # Different agent, same channel — must succeed.
    await _insert_running_container(
        db_pool, agent_id=agent_b, user_id=user_id, channel_type="inapp",
    )

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_containers "
            "WHERE user_id = $1 AND container_status = 'running'",
            user_id,
        )
    assert count == 2


async def test_fetch_running_container_for_agent_filters_by_channel(db_pool):
    """The helper's channel_type=None still returns ONE (the most-recent);
    channel_type='telegram' picks specifically the telegram one.

    Regression for the bug Audit Review 1 flagged: under migration 018
    a multi-channel agent would have arbitrary container returned from
    the unfiltered helper; the optional channel_type param disambiguates.
    """
    from api_server.services.run_store import fetch_running_container_for_agent

    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)

    inapp_id = await _insert_running_container(
        db_pool, agent_id=agent_id, user_id=user_id, channel_type="inapp",
    )
    tg_id = await _insert_running_container(
        db_pool, agent_id=agent_id, user_id=user_id, channel_type="telegram",
    )

    async with db_pool.acquire() as conn:
        # channel_type=None → most-recent running (the telegram one, since
        # it was inserted after the inapp).
        any_running = await fetch_running_container_for_agent(conn, agent_id)
        # channel_type='inapp' → the specific inapp container.
        inapp_running = await fetch_running_container_for_agent(
            conn, agent_id, channel_type="inapp",
        )
        # channel_type='telegram' → the telegram container.
        tg_running = await fetch_running_container_for_agent(
            conn, agent_id, channel_type="telegram",
        )

    assert any_running is not None
    assert any_running["id"] == str(tg_id), (
        "channel_type=None should return the most-recent-created running row"
    )
    assert inapp_running is not None and inapp_running["id"] == str(inapp_id)
    assert tg_running is not None and tg_running["id"] == str(tg_id)
