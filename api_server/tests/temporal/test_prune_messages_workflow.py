"""Phase B Plan B-stripe-09 Task 2 — prune_messages workflow tests.

Real Postgres (testcontainers, alembic-migrated) + ``ActivityEnvironment``
(real Temporal SDK activity runner) per CLAUDE.md golden rule #1.

Coverage matrix per PLAN.md ``<behavior>``:

  * test_prune_messages_deletes_messages_older_than_tier_retention
    — free user's 8d/31d/100d/365d msgs deleted; pro user's 31d/100d/365d
    deleted; ultra user keeps all msgs.
  * test_prune_messages_keeps_ultra_user_messages_at_one_year
    — explicit acceptance: ultra is unlimited retention; even 365d-old
    rows stay.
  * test_prune_messages_keeps_messages_under_retention_window
    — recent (1d, 5d) msgs untouched for both free + pro.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.prune_messages import (
    PruneMessagesActivities,
)


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(
    pool: asyncpg.Pool, *, tier: str,
) -> UUID:
    user_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, tier, display_name) "
            "VALUES ($1, $2, $3)",
            user_id, tier, f"prune-test-{tier}-{uuid4().hex[:8]}",
        )
    return user_id


async def _seed_agent(pool: asyncpg.Pool, *, user_id: UUID) -> UUID:
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'recipe-x', 'm-test', $3)
            """,
            agent_id, user_id, f"agent-{uuid4().hex[:8]}",
        )
    return agent_id


async def _seed_message(
    pool: asyncpg.Pool, *, user_id: UUID, agent_id: UUID, age_days: int,
) -> UUID:
    """INSERT one inapp_messages row backdated by ``age_days``."""
    msg_id = uuid4()
    created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
              (id, agent_id, user_id, content, status, created_at)
            VALUES ($1, $2, $3, $4, 'done', $5)
            """,
            msg_id, agent_id, user_id, f"msg-{age_days}d", created_at,
        )
    return msg_id


async def _count_messages(
    pool: asyncpg.Pool, *, user_id: UUID,
) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*)::int FROM inapp_messages WHERE user_id = $1",
            user_id,
        )


# ---------------------------------------------------------------------------
# 1. Per-tier retention windows applied
# ---------------------------------------------------------------------------


async def test_prune_messages_deletes_messages_older_than_tier_retention(
    db_pool: asyncpg.Pool,
) -> None:
    """free→7d, pro→30d, ultra→unlimited.

    Seed messages aged {1, 5, 8, 31, 100, 365}d for one user per tier.
    After prune:
      * free  keeps {1, 5}; deletes {8, 31, 100, 365}     → 2 left
      * pro   keeps {1, 5, 8}; deletes {31, 100, 365}     → 3 left
      * ultra keeps all {1, 5, 8, 31, 100, 365}            → 6 left
    """
    free_user = await _seed_user(db_pool, tier="free")
    free_agent = await _seed_agent(db_pool, user_id=free_user)
    pro_user = await _seed_user(db_pool, tier="pro")
    pro_agent = await _seed_agent(db_pool, user_id=pro_user)
    ultra_user = await _seed_user(db_pool, tier="ultra")
    ultra_agent = await _seed_agent(db_pool, user_id=ultra_user)

    ages = [1, 5, 8, 31, 100, 365]
    for d in ages:
        await _seed_message(
            db_pool, user_id=free_user, agent_id=free_agent, age_days=d,
        )
        await _seed_message(
            db_pool, user_id=pro_user, agent_id=pro_agent, age_days=d,
        )
        await _seed_message(
            db_pool, user_id=ultra_user, agent_id=ultra_agent, age_days=d,
        )

    acts = PruneMessagesActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    deleted = await env.run(acts.prune_messages)

    # free deletes 4 (8/31/100/365); pro deletes 3 (31/100/365); ultra 0.
    assert deleted == 4 + 3, (
        f"expected 7 total deletions (4 free + 3 pro), got {deleted}"
    )

    free_left = await _count_messages(db_pool, user_id=free_user)
    pro_left = await _count_messages(db_pool, user_id=pro_user)
    ultra_left = await _count_messages(db_pool, user_id=ultra_user)
    assert free_left == 2, f"free MUST keep 2 (1d, 5d); got {free_left}"
    assert pro_left == 3, f"pro MUST keep 3 (1d, 5d, 8d); got {pro_left}"
    assert ultra_left == 6, f"ultra MUST keep all 6; got {ultra_left}"


# ---------------------------------------------------------------------------
# 2. Ultra one-year explicit (separate guard)
# ---------------------------------------------------------------------------


async def test_prune_messages_keeps_ultra_user_messages_at_one_year(
    db_pool: asyncpg.Pool,
) -> None:
    """D-05: ultra retention is None (unlimited). Even a 365d msg stays."""
    user_id = await _seed_user(db_pool, tier="ultra")
    agent_id = await _seed_agent(db_pool, user_id=user_id)
    await _seed_message(
        db_pool, user_id=user_id, agent_id=agent_id, age_days=365,
    )

    acts = PruneMessagesActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    deleted = await env.run(acts.prune_messages)

    assert deleted == 0, "ultra user MUST never have messages deleted"
    assert await _count_messages(db_pool, user_id=user_id) == 1


# ---------------------------------------------------------------------------
# 3. Recent messages untouched (boundary check just inside window)
# ---------------------------------------------------------------------------


async def test_prune_messages_keeps_messages_under_retention_window(
    db_pool: asyncpg.Pool,
) -> None:
    """Free at age=6d (under 7d window) and Pro at age=29d (under 30d).

    Both must survive the prune; deleted count == 0.
    """
    free_user = await _seed_user(db_pool, tier="free")
    free_agent = await _seed_agent(db_pool, user_id=free_user)
    pro_user = await _seed_user(db_pool, tier="pro")
    pro_agent = await _seed_agent(db_pool, user_id=pro_user)

    await _seed_message(
        db_pool, user_id=free_user, agent_id=free_agent, age_days=6,
    )
    await _seed_message(
        db_pool, user_id=pro_user, agent_id=pro_agent, age_days=29,
    )

    acts = PruneMessagesActivities(db_pool=db_pool)
    env = ActivityEnvironment()
    deleted = await env.run(acts.prune_messages)

    assert deleted == 0, (
        f"in-window msgs MUST survive; got {deleted} deletions"
    )
    assert await _count_messages(db_pool, user_id=free_user) == 1
    assert await _count_messages(db_pool, user_id=pro_user) == 1
