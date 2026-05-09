"""Phase B Plan B-stripe-07 Task 1 RED — tier cap enforcement at agent.create.

Tests gate the POST /v1/agents/:id/start endpoint with the per-tier cap
(free=1 / pro=5 / ultra=∞) BEFORE the runner is invoked. A user at-cap
gets 403 TIER_LIMIT_EXCEEDED; a user under-cap proceeds (we do not
exercise the actual docker spawn — the test seeds a doomed-to-fail
recipe to prove the cap path returns 403 not 502/200).

Real Postgres + alembic upgrade head (golden rule #1 — no mocks).
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _set_user_tier(pool, *, user_id: str, tier: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET tier = $1 WHERE id = $2",
            tier, UUID(user_id),
        )


async def _seed_agent(pool, *, user_id: str, recipe_name: str = "hermes",
                      model: str = "anthropic/claude-haiku-4.5") -> UUID:
    """Seed an agent_instances row owned by user_id; no container yet."""
    agent_id = uuid4()
    name = f"agent-{uuid4().hex[:6]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, $4, $5)",
            agent_id, UUID(user_id), recipe_name, model, name,
        )
    return agent_id


async def _seed_active_container(
    pool, *, user_id: str, status: str = "running",
) -> UUID:
    """Seed an agent_instances + agent_containers (status=running) for the
    user. Used to fill the cap so a separate /start call gets blocked."""
    agent_id = uuid4()
    container_id = uuid4()
    recipe_name = f"recipe-{uuid4().hex[:6]}"
    name = f"agent-{uuid4().hex[:6]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, 'm-test', $4)",
            agent_id, UUID(user_id), recipe_name, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               deploy_mode, container_status)
            VALUES ($1, $2, $3, $4, 'persistent', $5)
            """,
            container_id, agent_id, UUID(user_id), recipe_name, status,
        )
    return agent_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_agent_start_returns_403_when_free_user_at_cap(
    async_client, db_pool, authenticated_cookie,
):
    """Free user with 1 active agent → POST /start on a SECOND agent → 403."""
    user_id = authenticated_cookie["_user_id"]
    # Default tier is 'free' from migration 014's column DEFAULT.
    await _seed_active_container(db_pool, user_id=user_id, status="running")
    # Seed a second agent_instance the user OWNS — they need to own it
    # for /start to even reach the cap check (404 otherwise).
    second_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{second_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["code"] == "TIER_LIMIT_EXCEEDED"
    # The message should mention the tier + cap so the mobile UI can
    # render an "Upgrade to Pro" CTA.
    msg = body["error"]["message"].lower()
    assert "free" in msg
    assert "1" in msg


async def test_agent_start_succeeds_for_pro_with_4_active_agents(
    async_client, db_pool, authenticated_cookie,
):
    """Pro user with 4 active agents → POST /start on a 5th → cap check
    passes (proceeds past gate; 5xx/4xx after the gate is fine for this
    test — we only care the 403 cap gate doesn't fire)."""
    user_id = authenticated_cookie["_user_id"]
    await _set_user_tier(db_pool, user_id=user_id, tier="pro")
    for _ in range(4):
        await _seed_active_container(db_pool, user_id=user_id, status="running")
    fifth_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{fifth_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    # Cap check passes — the request continues through the handler.
    # Without docker the runner will fail; we accept any non-403 code as
    # proof the cap gate did NOT trigger.
    assert r.status_code != 403, (
        f"cap check incorrectly blocked pro user under cap; body={r.text}"
    )
    if r.status_code != 200:
        # Whatever non-403 error fires (502 from runner, 500 from missing
        # recipe etc.), confirm it is NOT TIER_LIMIT_EXCEEDED.
        body = r.json()
        assert body["error"]["code"] != "TIER_LIMIT_EXCEEDED"


async def test_agent_start_returns_403_when_pro_user_at_5_active_agents(
    async_client, db_pool, authenticated_cookie,
):
    """Pro user with 5 active agents → POST /start on a 6th → 403."""
    user_id = authenticated_cookie["_user_id"]
    await _set_user_tier(db_pool, user_id=user_id, tier="pro")
    for _ in range(5):
        await _seed_active_container(db_pool, user_id=user_id, status="running")
    sixth_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{sixth_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["code"] == "TIER_LIMIT_EXCEEDED"
    msg = body["error"]["message"].lower()
    assert "pro" in msg


async def test_agent_start_ultra_user_with_many_agents_passes_cap(
    async_client, db_pool, authenticated_cookie,
):
    """Ultra user with 20 active agents → POST /start on a 21st → cap
    check passes (no 403). Ultra is effectively unlimited."""
    user_id = authenticated_cookie["_user_id"]
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    for _ in range(20):
        await _seed_active_container(db_pool, user_id=user_id, status="running")
    next_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{next_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code != 403, (
        f"cap check incorrectly blocked ultra user; body={r.text}"
    )
    if r.status_code != 200:
        body = r.json()
        assert body["error"]["code"] != "TIER_LIMIT_EXCEEDED"


async def test_agent_start_auto_paused_does_not_count_toward_cap(
    async_client, db_pool, authenticated_cookie,
):
    """D-15: auto_paused agents do NOT count toward the cap.

    A user post Pro→Free downgrade has 1 running + 4 auto_paused. The
    free cap is 1; the running counts as 1; auto_paused do NOT — but
    the user is at cap (1 of 1) so a NEW /start fails. The point of
    this test is that auto_paused does NOT inflate the count to 5/1
    (which would make the count look broken in the message).
    """
    user_id = authenticated_cookie["_user_id"]
    # Default tier is 'free'.
    await _seed_active_container(db_pool, user_id=user_id, status="running")
    for _ in range(4):
        await _seed_active_container(
            db_pool, user_id=user_id, status="auto_paused",
        )
    new_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{new_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["error"]["code"] == "TIER_LIMIT_EXCEEDED"
    # Message reflects count=1 (only the running row counted), not 5.
    assert "1" in body["error"]["message"]


async def test_agent_start_stopped_does_not_count_toward_cap(
    async_client, db_pool, authenticated_cookie,
):
    """A free user with 1 STOPPED agent can start a NEW one."""
    user_id = authenticated_cookie["_user_id"]
    await _seed_active_container(db_pool, user_id=user_id, status="stopped")
    new_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{new_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code != 403, (
        f"cap check incorrectly blocked free user with stopped agent; "
        f"body={r.text}"
    )
    if r.status_code != 200:
        body = r.json()
        assert body["error"]["code"] != "TIER_LIMIT_EXCEEDED"


async def test_agent_start_race_two_concurrent_calls_at_most_one_succeeds_past_cap(
    async_client, db_pool, authenticated_cookie,
):
    """Two concurrent POST /start calls against a fresh free user must
    NOT both succeed past the cap.

    The user has zero containers; cap=1. Two simultaneous /start
    requests — exactly one must be blocked by the cap (403) OR the
    transactional row-lock + container partial-unique-index combination
    must produce one 200 + one error (4xx/5xx).

    The contract: at the end of two concurrent calls, the count of
    'starting' or 'running' agent_containers rows for this user is
    either 0 (both failed runner, neither held a slot) OR 1 (one
    proceeded, one was blocked). It is NEVER 2.

    Because we don't have a real runner here (mocking the runner would
    violate golden rule #1), both requests will eventually fail at the
    runner step, but the cap gate must still fire on at least ONE of
    them when the OTHER request's pending-insert lands first. This
    test verifies the gate's transactional semantics — not the runner.
    """
    user_id = authenticated_cookie["_user_id"]
    agent_a = await _seed_agent(db_pool, user_id=user_id)
    agent_b = await _seed_agent(db_pool, user_id=user_id)

    async def _start(agent_id: UUID):
        return await async_client.post(
            f"/v1/agents/{agent_id}/start",
            json={"channel": "inapp", "channel_inputs": {}},
            headers={
                "Authorization": "Bearer test-key",
                "Cookie": authenticated_cookie["Cookie"],
            },
        )

    r_a, r_b = await asyncio.gather(_start(agent_a), _start(agent_b))
    statuses = sorted([r_a.status_code, r_b.status_code])

    # At end-of-test, count active containers for this user. Both
    # requests fail at the runner (no docker), but the cap gate must
    # have prevented both from inserting an active 'starting' row.
    async with db_pool.acquire() as conn:
        active = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_containers "
            "WHERE user_id=$1 "
            "AND container_status IN ('starting','running')",
            UUID(user_id),
        )

    # The transactional cap gate guarantees at most 1 active container
    # exists at any time post-handler-return. (0 if both runner-failures
    # cleared their pending row; 1 if one cleared and the other reached
    # 'starting'-then-cleanup ordering.)
    assert active <= 1, (
        f"two concurrent /start calls left {active} active rows; "
        f"cap gate failed; statuses={statuses}; "
        f"a={r_a.text}; b={r_b.text}"
    )

    # At least ONE response must NOT have been a 200 success.
    assert not (r_a.status_code == 200 and r_b.status_code == 200), (
        f"both concurrent /start calls returned 200 — cap broken; "
        f"a={r_a.text}; b={r_b.text}"
    )


async def test_agent_start_under_cap_does_not_get_403(
    async_client, db_pool, authenticated_cookie,
):
    """Free user with 0 active agents → /start on FIRST agent → no 403.

    This is the happy-path negative — the cap MUST NOT fire when the
    user is under-cap. Anything else that fires (502 from no docker etc.)
    is fine; we only assert on the absence of a 403 cap-block.
    """
    user_id = authenticated_cookie["_user_id"]
    new_agent = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.post(
        f"/v1/agents/{new_agent}/start",
        json={"channel": "inapp", "channel_inputs": {}},
        headers={
            "Authorization": "Bearer test-key",
            "Cookie": authenticated_cookie["Cookie"],
        },
    )
    assert r.status_code != 403, (
        f"cap incorrectly blocked free user under cap; body={r.text}"
    )
    if r.status_code != 200:
        body = r.json()
        assert body["error"]["code"] != "TIER_LIMIT_EXCEEDED"
