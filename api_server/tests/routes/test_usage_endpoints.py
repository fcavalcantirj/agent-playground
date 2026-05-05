"""Phase 27 Change 3a — TDD route tests for /v1/usage/summary + /v1/agents/:id/usage.

Tests-first per CLAUDE.md golden rule #2 (dumb client) + Phase 27 D-13/D-14/D-15:
the api_server returns ready-to-render JSON (server-side aggregation, USD as
strings, no client-side SUM). These tests pin the endpoint contract before any
route handler exists — running this file with no `routes/usage.py` should
produce 404s (route not registered), which proves the suite drives the
implementation rather than the implementation driving the suite.

Coverage matrix:

  GET /v1/usage/summary
   * 401 without cookie → Stripe-shape envelope, code=UNAUTHORIZED
   * 200 with no usage_logs → total_usd="0", message_count=0, by_agent=[]
   * 200 with seeded data spanning 2 agents → totals + by_agent ORDER BY cost DESC
   * isolation: User A's totals never include User B's usage_logs

  GET /v1/agents/:id/usage
   * 401 without cookie
   * 404 on non-existent agent UUID
   * 404 on agent owned by another user (Pattern A — hides existence vs ownership)
   * 200 happy path — cumulative aggregates + 7d series + 30d series with
     correct day grouping, omitting empty days
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_agent(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    name: str | None = None,
    recipe_name: str = "test-recipe",
    model: str = "anthropic/claude-haiku-4.5",
) -> UUID:
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO agent_instances (id, user_id, recipe_name, model, name) "
            "VALUES ($1, $2, $3, $4, $5)",
            agent_id, user_id, recipe_name, model,
            name or f"agent-{uuid4().hex[:8]}",
        )
    return agent_id


async def _seed_usage_log(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_id: UUID,
    cost_usd: Decimal,
    input_tokens: int = 14,
    output_tokens: int = 4,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
    created_at: datetime | None = None,
    provider: str = "openrouter",
    model: str = "anthropic/claude-haiku-4.5",
) -> UUID:
    log_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_logs
              (id, user_id, agent_instance_id, provider, model,
               input_tokens, output_tokens,
               cache_read_tokens, cache_creation_tokens,
               cost_usd, status, source, created_at)
            VALUES ($1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, 'success', 'inapp',
                    COALESCE($11, NOW()))
            """,
            log_id, user_id, agent_id, provider, model,
            input_tokens, output_tokens,
            cache_read_tokens, cache_creation_tokens,
            cost_usd, created_at,
        )
    return log_id


# ---------------------------------------------------------------------------
# /v1/usage/summary
# ---------------------------------------------------------------------------


async def test_usage_summary_401_without_cookie(
    async_client: httpx.AsyncClient,
) -> None:
    """No cookie → 401 + Stripe envelope code=UNAUTHORIZED."""
    r = await async_client.get("/v1/usage/summary")
    assert r.status_code == 401, r.text
    body = r.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert body["error"]["param"] == "ap_session"


async def test_usage_summary_empty_state(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
) -> None:
    """No usage_logs rows for the user → total_usd='0', count=0, by_agent=[]."""
    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # USD as string, never float (D-14)
    assert isinstance(body["total_usd"], str)
    assert Decimal(body["total_usd"]) == Decimal("0")
    assert body["message_count"] == 0
    assert body["by_agent"] == []


async def test_usage_summary_with_seeded_data_aggregates_per_agent(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """2 agents, 3 calls — totals + by_agent in cost-DESC order."""
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_a = await _seed_agent(db_pool, user_id=user_id, name="agent-A")
    agent_b = await _seed_agent(db_pool, user_id=user_id, name="agent-B")

    # Agent A: 2 calls totaling $0.0070
    await _seed_usage_log(db_pool, user_id=user_id, agent_id=agent_a, cost_usd=Decimal("0.00350000"))
    await _seed_usage_log(db_pool, user_id=user_id, agent_id=agent_a, cost_usd=Decimal("0.00350000"))
    # Agent B: 1 call totaling $0.0010
    await _seed_usage_log(db_pool, user_id=user_id, agent_id=agent_b, cost_usd=Decimal("0.00100000"))

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["total_usd"]) == Decimal("0.00800000")
    assert body["message_count"] == 3

    by_agent = body["by_agent"]
    assert len(by_agent) == 2
    # Ordered by cost DESC — agent-A first ($0.0070 > $0.0010)
    assert by_agent[0]["agent_id"] == str(agent_a)
    assert by_agent[0]["agent_name"] == "agent-A"
    assert Decimal(by_agent[0]["cost_usd"]) == Decimal("0.00700000")
    assert by_agent[0]["message_count"] == 2

    assert by_agent[1]["agent_id"] == str(agent_b)
    assert Decimal(by_agent[1]["cost_usd"]) == Decimal("0.00100000")
    assert by_agent[1]["message_count"] == 1

    # Each entry carries recipe_name + model + last_activity for the screen
    for entry in by_agent:
        assert "recipe_name" in entry
        assert "model" in entry
        assert "last_activity" in entry


async def test_usage_summary_isolates_users(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
    second_authenticated_cookie: dict,
) -> None:
    """User A only sees A's logs — B's spending invisible to A."""
    user_a = UUID(authenticated_cookie["_user_id"])
    user_b = UUID(second_authenticated_cookie["_user_id"])
    agent_a = await _seed_agent(db_pool, user_id=user_a)
    agent_b = await _seed_agent(db_pool, user_id=user_b)
    await _seed_usage_log(db_pool, user_id=user_a, agent_id=agent_a, cost_usd=Decimal("0.001"))
    await _seed_usage_log(db_pool, user_id=user_b, agent_id=agent_b, cost_usd=Decimal("9.99"))

    r = await async_client.get(
        "/v1/usage/summary",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    body = r.json()
    assert Decimal(body["total_usd"]) == Decimal("0.00100000")
    assert body["message_count"] == 1
    assert len(body["by_agent"]) == 1


# ---------------------------------------------------------------------------
# /v1/agents/:id/usage
# ---------------------------------------------------------------------------


async def test_agent_usage_401_without_cookie(
    async_client: httpx.AsyncClient,
) -> None:
    r = await async_client.get(f"/v1/agents/{uuid4()}/usage")
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


async def test_agent_usage_404_on_nonexistent(
    async_client: httpx.AsyncClient,
    authenticated_cookie: dict,
) -> None:
    r = await async_client.get(
        f"/v1/agents/{uuid4()}/usage",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_agent_usage_404_when_owned_by_other_user(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
    second_authenticated_cookie: dict,
) -> None:
    """User B owns the agent; User A asks for it → 404 (Pattern A hides existence)."""
    user_b = UUID(second_authenticated_cookie["_user_id"])
    agent_id = await _seed_agent(db_pool, user_id=user_b)

    r = await async_client.get(
        f"/v1/agents/{agent_id}/usage",
        headers={"Cookie": authenticated_cookie["Cookie"]},  # user A
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "AGENT_NOT_FOUND"


async def test_agent_usage_happy_path_with_temporal_series(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Cumulative + 7d + 30d series with day-grouping; omits empty days."""
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = await _seed_agent(db_pool, user_id=user_id)

    now = datetime.now(timezone.utc)
    # 3 calls today (will collapse into 1 day-bucket)
    await _seed_usage_log(
        db_pool, user_id=user_id, agent_id=agent_id,
        cost_usd=Decimal("0.001"), input_tokens=10, output_tokens=5,
        created_at=now,
    )
    await _seed_usage_log(
        db_pool, user_id=user_id, agent_id=agent_id,
        cost_usd=Decimal("0.002"), input_tokens=20, output_tokens=10,
        created_at=now - timedelta(minutes=5),
    )
    # 1 call 5 days ago (inside 7d window)
    await _seed_usage_log(
        db_pool, user_id=user_id, agent_id=agent_id,
        cost_usd=Decimal("0.003"), input_tokens=30, output_tokens=15,
        cache_read_tokens=100,
        created_at=now - timedelta(days=5),
    )
    # 1 call 20 days ago (outside 7d, inside 30d)
    await _seed_usage_log(
        db_pool, user_id=user_id, agent_id=agent_id,
        cost_usd=Decimal("0.004"), input_tokens=40, output_tokens=20,
        created_at=now - timedelta(days=20),
    )
    # 1 call 60 days ago (outside both windows but still in cumulative)
    await _seed_usage_log(
        db_pool, user_id=user_id, agent_id=agent_id,
        cost_usd=Decimal("0.005"), input_tokens=50, output_tokens=25,
        created_at=now - timedelta(days=60),
    )

    r = await async_client.get(
        f"/v1/agents/{agent_id}/usage",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # --- cumulative (all rows ever) ----
    cum = body["cumulative"]
    assert Decimal(cum["cost_usd"]) == Decimal("0.01500000")  # 0.001+0.002+0.003+0.004+0.005
    assert cum["input_tokens"] == 10 + 20 + 30 + 40 + 50
    assert cum["output_tokens"] == 5 + 10 + 15 + 20 + 25
    assert cum["cache_read_tokens"] == 100
    assert cum["cache_creation_tokens"] == 0
    assert cum["message_count"] == 5
    assert cum["last_activity"] is not None

    # --- 7d series — today (3 calls) + 5d-ago (1 call) = 2 day buckets ----
    series_7d = body["series_7d"]
    assert len(series_7d) == 2, f"expected 2 day buckets in 7d, got {series_7d}"
    days_7d = {row["day"]: row for row in series_7d}
    today_iso = now.date().isoformat()
    five_days_ago_iso = (now - timedelta(days=5)).date().isoformat()
    assert today_iso in days_7d
    assert five_days_ago_iso in days_7d
    assert Decimal(days_7d[today_iso]["cost_usd"]) == Decimal("0.00300000")
    assert days_7d[today_iso]["message_count"] == 2
    assert days_7d[today_iso]["tokens"] == 10 + 5 + 20 + 10  # input+output for both today calls
    assert Decimal(days_7d[five_days_ago_iso]["cost_usd"]) == Decimal("0.00300000")
    assert days_7d[five_days_ago_iso]["message_count"] == 1

    # --- 30d series — today + 5d-ago + 20d-ago = 3 day buckets ----
    series_30d = body["series_30d"]
    assert len(series_30d) == 3, f"expected 3 day buckets in 30d, got {series_30d}"
    days_30d = {row["day"] for row in series_30d}
    twenty_days_ago_iso = (now - timedelta(days=20)).date().isoformat()
    assert today_iso in days_30d
    assert five_days_ago_iso in days_30d
    assert twenty_days_ago_iso in days_30d
    # 60d-ago call is NOT in series (outside window) but IS in cumulative
    sixty_days_ago_iso = (now - timedelta(days=60)).date().isoformat()
    assert sixty_days_ago_iso not in days_30d


async def test_agent_usage_empty_state_has_zero_cumulative_and_empty_series(
    async_client: httpx.AsyncClient,
    db_pool: asyncpg.Pool,
    authenticated_cookie: dict,
) -> None:
    """Newly-created agent with zero usage → cumulative is zero, series empty."""
    user_id = UUID(authenticated_cookie["_user_id"])
    agent_id = await _seed_agent(db_pool, user_id=user_id)

    r = await async_client.get(
        f"/v1/agents/{agent_id}/usage",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    cum = body["cumulative"]
    assert Decimal(cum["cost_usd"]) == Decimal("0")
    assert cum["input_tokens"] == 0
    assert cum["output_tokens"] == 0
    assert cum["message_count"] == 0
    assert cum["last_activity"] is None
    assert body["series_7d"] == []
    assert body["series_30d"] == []
