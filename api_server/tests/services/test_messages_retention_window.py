"""Phase B Plan B-stripe-07 Task 2 RED — per-tier retention filter tests.

Tests gate the GET /v1/agents/:id/messages handler with the per-tier
retention window (free=7d / pro=30d / ultra=∞). Two surfaces covered:

1. Service-layer ``list_history_for_agent(..., since=...)`` SQL filter
   semantics — when ``since is None`` no filter; when ``since`` is a
   datetime, the SQL adds ``created_at >= $N``.
2. Route-layer ``GET /v1/agents/:id/messages`` reads the user's tier
   and computes the cutoff via ``retention_window_days(tier)``, passes
   it to the store helper.

Real Postgres + alembic upgrade head (golden rule #1 — no mocks).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

# Re-use the seed helper from test_agent_messages_post — agent + container
# seeding shape stays in one place.
from ..routes.test_agent_messages_post import _seed_agent_for_user


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_done_message_at(
    pool, *, agent_id: UUID, user_id: UUID,
    days_ago: float, content: str = "msg",
) -> UUID:
    """Insert a 'done' inapp_messages row with created_at exactly N days
    ago. Returns the row id."""
    msg_id = uuid4()
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO inapp_messages
                (id, agent_id, user_id, content, status, bot_response,
                 created_at)
            VALUES ($1, $2, $3, $4, 'done', 'bot reply', $5)
            """,
            msg_id, agent_id, user_id, content, created,
        )
    return msg_id


async def _set_user_tier(pool, *, user_id: str, tier: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET tier = $1 WHERE id = $2",
            tier, UUID(user_id),
        )


# ---------------------------------------------------------------------------
# Service-layer SQL filter
# ---------------------------------------------------------------------------


async def test_list_history_for_agent_no_since_returns_all_rows(
    db_pool, authenticated_cookie,
):
    """``since=None`` (or omitted) returns every row regardless of age."""
    from api_server.services import inapp_messages_store as ims

    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=1, content="new",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=400,
        content="ancient",
    )

    async with db_pool.acquire() as conn:
        rows = await ims.list_history_for_agent(
            conn, agent_id=agent_id, limit=100,
        )
    contents = sorted(r["content"] for r in rows)
    assert contents == ["ancient", "new"]


async def test_list_history_for_agent_with_since_filters_old(
    db_pool, authenticated_cookie,
):
    """``since=now-7d`` filters out rows older than 7 days."""
    from api_server.services import inapp_messages_store as ims

    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=1, content="new",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=10,
        content="old",
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with db_pool.acquire() as conn:
        rows = await ims.list_history_for_agent(
            conn, agent_id=agent_id, limit=100, since=cutoff,
        )
    contents = [r["content"] for r in rows]
    assert contents == ["new"]


async def test_list_history_for_agent_since_boundary_excludes_just_outside(
    db_pool, authenticated_cookie,
):
    """A row just OUTSIDE the cutoff is excluded; a row just INSIDE is kept.

    The semantics are ``WHERE created_at >= $N`` — a row exactly at the
    cutoff is INCLUDED (>=), but a row 1ms OLDER is excluded.
    """
    from api_server.services import inapp_messages_store as ims

    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    user_id = UUID(authenticated_cookie["_user_id"])
    # 6.99d ago — well within a 7d window
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=6.99,
        content="kept",
    )
    # 7.01d ago — just outside
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_id, days_ago=7.01,
        content="dropped",
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    async with db_pool.acquire() as conn:
        rows = await ims.list_history_for_agent(
            conn, agent_id=agent_id, limit=100, since=cutoff,
        )
    contents = [r["content"] for r in rows]
    assert contents == ["kept"]


# ---------------------------------------------------------------------------
# Route-layer integration — handler reads user.tier and applies the filter
# ---------------------------------------------------------------------------


async def test_get_messages_no_retention_filter_for_ultra(
    async_client, db_pool, authenticated_cookie,
):
    """Ultra user → handler returns ALL rows including a year-old one."""
    user_id = authenticated_cookie["_user_id"]
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    agent_id = await _seed_agent_for_user(db_pool, user_id)
    user_uuid = UUID(user_id)
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=1,
        content="recent",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=365,
        content="ancient",
    )

    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    msgs = r.json()["messages"]
    user_contents = [m["content"] for m in msgs if m["role"] == "user"]
    assert sorted(user_contents) == ["ancient", "recent"]


async def test_get_messages_filters_by_30d_for_pro(
    async_client, db_pool, authenticated_cookie,
):
    """Pro user → 30d window: 5d row kept, 31d row dropped."""
    user_id = authenticated_cookie["_user_id"]
    await _set_user_tier(db_pool, user_id=user_id, tier="pro")
    agent_id = await _seed_agent_for_user(db_pool, user_id)
    user_uuid = UUID(user_id)
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=5,
        content="kept-pro",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=31,
        content="dropped-pro",
    )

    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    user_contents = [m["content"] for m in r.json()["messages"]
                     if m["role"] == "user"]
    assert user_contents == ["kept-pro"]


async def test_get_messages_filters_by_7d_for_free(
    async_client, db_pool, authenticated_cookie,
):
    """Free user → 7d window: 1d row kept, 8d row dropped."""
    user_id = authenticated_cookie["_user_id"]
    # Default tier is 'free' from migration 014's column DEFAULT.
    agent_id = await _seed_agent_for_user(db_pool, user_id)
    user_uuid = UUID(user_id)
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=1,
        content="kept-free",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=8,
        content="dropped-free",
    )

    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    user_contents = [m["content"] for m in r.json()["messages"]
                     if m["role"] == "user"]
    assert user_contents == ["kept-free"]


async def test_get_messages_with_messages_at_boundary_8d_for_free_excludes_oldest(
    async_client, db_pool, authenticated_cookie,
):
    """Boundary: free=7d, a row at 8d ago is OUTSIDE the window and dropped.

    This is the precise boundary semantics check — `>= now-7d` predicate
    means a row 7.5d old is excluded; this test seeds 7.5d to confirm.
    """
    user_id = authenticated_cookie["_user_id"]
    agent_id = await _seed_agent_for_user(db_pool, user_id)
    user_uuid = UUID(user_id)
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=6.5,
        content="just-inside",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=7.5,
        content="just-outside",
    )

    r = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    user_contents = [m["content"] for m in r.json()["messages"]
                     if m["role"] == "user"]
    assert user_contents == ["just-inside"]


async def test_get_messages_handler_reads_user_tier_then_applies_filter(
    async_client, db_pool, authenticated_cookie,
):
    """Same dataset, FLIP the user's tier mid-test, expect different sets.

    Proves the handler re-reads tier on every request (D-18 lazy re-read)
    rather than caching.
    """
    user_id = authenticated_cookie["_user_id"]
    agent_id = await _seed_agent_for_user(db_pool, user_id)
    user_uuid = UUID(user_id)
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=1,
        content="recent",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=15,
        content="mid",
    )
    await _seed_done_message_at(
        db_pool, agent_id=agent_id, user_id=user_uuid, days_ago=100,
        content="old",
    )

    # Free: only "recent"
    r1 = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    user_contents_1 = [m["content"] for m in r1.json()["messages"]
                       if m["role"] == "user"]
    assert user_contents_1 == ["recent"]

    # Flip to pro → 30d window: "recent" + "mid"
    await _set_user_tier(db_pool, user_id=user_id, tier="pro")
    r2 = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    user_contents_2 = [m["content"] for m in r2.json()["messages"]
                       if m["role"] == "user"]
    assert sorted(user_contents_2) == ["mid", "recent"]

    # Flip to ultra → all: "recent" + "mid" + "old"
    await _set_user_tier(db_pool, user_id=user_id, tier="ultra")
    r3 = await async_client.get(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    user_contents_3 = [m["content"] for m in r3.json()["messages"]
                       if m["role"] == "user"]
    assert sorted(user_contents_3) == ["mid", "old", "recent"]
