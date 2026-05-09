"""Phase B Plan B-stripe-07 Task 1 RED — services/tier_enforcement.py unit tests.

Two surfaces exercised here:

1. Pure-Python lookup helpers (``agent_cap_for_tier`` /
   ``retention_window_days``) — no DB, no network. Locks the per-tier
   limits per D-05 so a future "raise pro cap to 10" change updates one
   place + this test.
2. ``check_can_create_agent`` against a real Postgres testcontainer — the
   helper fetches ``users.tier``, counts active ``agent_containers`` rows,
   returns ``(allowed, current_active_count, tier)``.

Real Postgres + alembic upgrade head (golden rule #1 — no mocks).
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Pure-function lookup helpers
# ---------------------------------------------------------------------------


def test_agent_cap_for_tier_free_is_one():
    from api_server.services.tier_enforcement import agent_cap_for_tier
    assert agent_cap_for_tier("free") == 1


def test_agent_cap_for_tier_pro_is_five():
    from api_server.services.tier_enforcement import agent_cap_for_tier
    assert agent_cap_for_tier("pro") == 5


def test_agent_cap_for_tier_ultra_is_effectively_infinite():
    """Ultra cap is a sentinel large number (D-05 'unlimited' as int).

    A literal `math.inf` won't work — count comparisons return int. The
    contract is: a normal user (even one with hundreds of agents) never
    trips the cap on ultra.
    """
    from api_server.services.tier_enforcement import agent_cap_for_tier
    cap = agent_cap_for_tier("ultra")
    assert cap >= 1_000_000


def test_agent_cap_for_tier_unknown_falls_back_to_free():
    """Unknown tier (typo, future migration drift) → safest cap (free)."""
    from api_server.services.tier_enforcement import agent_cap_for_tier
    assert agent_cap_for_tier("not-a-real-tier") == 1


def test_retention_window_days_free_is_seven():
    from api_server.services.tier_enforcement import retention_window_days
    assert retention_window_days("free") == 7


def test_retention_window_days_pro_is_thirty():
    from api_server.services.tier_enforcement import retention_window_days
    assert retention_window_days("pro") == 30


def test_retention_window_days_ultra_is_unlimited():
    """Ultra returns None — caller MUST treat as 'no retention filter'."""
    from api_server.services.tier_enforcement import retention_window_days
    assert retention_window_days("ultra") is None


def test_retention_window_days_unknown_falls_back_to_free():
    from api_server.services.tier_enforcement import retention_window_days
    assert retention_window_days("not-a-real-tier") == 7


# ---------------------------------------------------------------------------
# DB-backed check_can_create_agent
# ---------------------------------------------------------------------------


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


async def _seed_agent_container(
    pool, *, user_id: UUID, status: str = "running",
) -> UUID:
    """Seed an agent_instances + agent_containers row for the user with
    the given container_status."""
    agent_id = uuid4()
    container_id = uuid4()
    recipe_name = f"recipe-{uuid4().hex[:6]}"
    name = f"agent-{uuid4().hex[:6]}"
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, 'm-test', $4)",
            agent_id, user_id, recipe_name, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               deploy_mode, container_status)
            VALUES ($1, $2, $3, $4, 'persistent', $5)
            """,
            container_id, agent_id, user_id, recipe_name, status,
        )
    return container_id


async def test_check_can_create_agent_returns_true_for_free_with_zero_agents(
    db_pool,
):
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="free")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is True
    assert count == 0
    assert tier == "free"


async def test_check_can_create_agent_returns_false_for_free_with_one_agent(
    db_pool,
):
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="free")
    await _seed_agent_container(db_pool, user_id=user_id, status="running")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is False
    assert count == 1
    assert tier == "free"


async def test_check_can_create_agent_returns_true_for_pro_with_four_agents(
    db_pool,
):
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="pro")
    for _ in range(4):
        await _seed_agent_container(db_pool, user_id=user_id, status="running")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is True
    assert count == 4
    assert tier == "pro"


async def test_check_can_create_agent_returns_false_for_pro_with_five_agents(
    db_pool,
):
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="pro")
    for _ in range(5):
        await _seed_agent_container(db_pool, user_id=user_id, status="running")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is False
    assert count == 5
    assert tier == "pro"


async def test_check_can_create_agent_returns_true_for_ultra_with_thousand_agents(
    db_pool,
):
    """Ultra has effectively-infinite cap — even 1000 agents stay allowed."""
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="ultra")
    # Real-Postgres seeding 1000 rows is slow; seed enough to prove the
    # contract (much greater than pro's cap of 5).
    for _ in range(20):
        await _seed_agent_container(db_pool, user_id=user_id, status="running")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is True
    assert count == 20
    assert tier == "ultra"


async def test_check_can_create_agent_excludes_stopped_failed_auto_paused_from_count(
    db_pool,
):
    """Only 'starting' + 'running' count toward the cap.

    'stopped', 'start_failed', 'crashed', 'auto_paused', 'stopping' do
    NOT count — D-15 explicitly excludes auto_paused so a Pro→Free
    downgrade leaves the user at 1 active agent + 4 paused, NOT capped
    at the free=1 limit and unable to start anything.
    """
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="free")
    # Seed one 'running' and one of every non-active status — only the
    # 'running' row should count.
    await _seed_agent_container(db_pool, user_id=user_id, status="running")
    for s in ("stopped", "start_failed", "crashed",
              "auto_paused", "stopping"):
        await _seed_agent_container(db_pool, user_id=user_id, status=s)
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    # 1 running counts; cap is 1; allowed=False because we're AT the cap.
    assert allowed is False
    assert count == 1
    assert tier == "free"


async def test_check_can_create_agent_starting_status_counts(db_pool):
    """'starting' is an active status — counts toward the cap.

    Without this test, an in-flight POST /start could be bypassed by a
    second concurrent /start because the first hasn't reached 'running'
    yet — both would count zero and both would proceed. The 'starting'
    row from request 1 must block request 2.
    """
    from api_server.services.tier_enforcement import check_can_create_agent

    user_id = await _seed_user(db_pool, tier="free")
    await _seed_agent_container(db_pool, user_id=user_id, status="starting")
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_id,
            )
    assert allowed is False
    assert count == 1


async def test_check_can_create_agent_user_not_found_denies(db_pool):
    """Defense: a UUID with no users row returns (False, 0, 'free').

    Should never happen in practice (require_user gates the route), but
    making the helper safe-by-default avoids an assumption-driven crash
    if the row was concurrently deleted.
    """
    from api_server.services.tier_enforcement import check_can_create_agent

    bogus_user = uuid4()
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=bogus_user,
            )
    assert allowed is False
    assert count == 0
    assert tier == "free"


async def test_check_can_create_agent_cross_tenant_isolation(db_pool):
    """Agent rows for OTHER users are not counted.

    User A's 5 running agents must not block user B (free) from creating
    their first. Cross-tenant-ish isolation at the SQL layer.
    """
    from api_server.services.tier_enforcement import check_can_create_agent

    user_a = await _seed_user(db_pool, tier="pro")
    user_b = await _seed_user(db_pool, tier="free")
    for _ in range(5):
        await _seed_agent_container(db_pool, user_id=user_a, status="running")
    # User B has none.
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            allowed, count, tier = await check_can_create_agent(
                conn, user_id=user_b,
            )
    assert allowed is True
    assert count == 0
    assert tier == "free"
