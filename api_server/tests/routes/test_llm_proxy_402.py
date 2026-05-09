"""Phase B Plan B-stripe-08 Task 2 — pre-flight 402 in llm_proxy.

Real Postgres (testcontainers, alembic-migrated 014) + respx-mocked
upstream provider per CLAUDE.md golden rule #1.

Coverage matrix per PLAN.md ``<behavior>``:

* ``test_proxy_passes_through_for_free_tier_with_zero_balance``
* ``test_proxy_passes_through_for_pro_tier_with_zero_balance``
* ``test_proxy_passes_through_for_ultra_tier_with_one_cent_balance``
* ``test_proxy_returns_402_INSUFFICIENT_BALANCE_for_ultra_tier_with_zero_balance``
* ``test_proxy_returns_402_for_ultra_tier_with_negative_balance``
* ``test_proxy_402_skips_upstream_call``

Test setup mirrors ``tests/routes/test_llm_proxy.py``: ``async_client``
fixture from conftest boots create_app() lifespan; we override
``app.state.proxy_byok_cache`` with a tiny in-memory fake; we re-instantiate
``app.state.proxy_ip_map`` post-fixture so it sees our seeded
``agent_containers`` row. Predicate ``balance_cents < 1`` (D-12) catches
both 0 and negative balances per RESEARCH §Pitfall 6.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient


pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# Helpers (mirror test_llm_proxy.py shape)
# ---------------------------------------------------------------------------


class FakeBYOKCache:
    """In-memory stub for app.state.proxy_byok_cache."""

    def __init__(self, entries: dict[tuple[UUID, UUID], tuple[str, str]]) -> None:
        self._entries = entries

    async def get(
        self, user_id: UUID, agent_instance_id: UUID,
    ) -> tuple[str | None, str | None]:
        v = self._entries.get((user_id, agent_instance_id))
        if v is None:
            return (None, None)
        return v


async def _seed_user(pool: asyncpg.Pool, *, tier: str) -> UUID:
    uid = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, tier, display_name) VALUES ($1, $2, $3)",
            uid, tier, f"proxy-402-{tier}",
        )
    return uid


async def _seed_balance(
    pool: asyncpg.Pool, *, user_id: UUID, balance_cents: int,
) -> None:
    """INSERT a credit_balances row at the requested cents (signed).

    Phase B's negative balance state (D-16) is reachable when refunds
    drain a previously-positive balance below zero. We seed the cache
    directly here; the activity-level tests in
    ``test_debit_balance_activity.py`` exercise the SUM-from-ledger
    rebuild path. For 402 tests we only need the cache to disagree with
    the predicate's input.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO credit_balances (user_id, balance_cents) "
            "VALUES ($1, $2)",
            user_id, balance_cents,
        )


async def _seed_agent_and_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    bridge_ip: str,
    inapp_auth_token: str,
) -> tuple[UUID, UUID]:
    """INSERT agent_instances + agent_containers (running, with bridge_ip).

    Returns ``(agent_instance_id, container_row_id)``.
    """
    agent_id = uuid4()
    container_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'nanobot', 'openai/gpt-3.5-turbo', $3)
            """,
            agent_id, user_id, f"agent-{uuid4().hex[:8]}",
        )
        await conn.execute(
            """
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name,
                deploy_mode, container_status, container_id,
                bridge_ip, inapp_auth_token, upstream_provider, ready_at
            ) VALUES (
                $1, $2, $3, 'nanobot',
                'persistent', 'running', $4,
                $5::inet, $6, 'openrouter', NOW()
            )
            """,
            container_id, agent_id, user_id,
            f"deadbeef{uuid4().hex[:24]}", bridge_ip, inapp_auth_token,
        )
    return agent_id, container_id


def _build_proxy_client(app: Any, bridge_ip: str) -> AsyncClient:
    """An httpx.AsyncClient whose ASGI transport reports ``client.host = bridge_ip``."""
    transport = ASGITransport(app=app, client=(bridge_ip, 12345))
    return AsyncClient(transport=transport, base_url="http://test")


async def _wire_proxy_state(
    async_client: AsyncClient,
    db_pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    bridge_ip: str = "172.18.0.42",
    byok_key: str = "sk-or-v1-test-byok-key",
) -> None:
    """Wire app.state.proxy_byok_cache + refresh proxy_ip_map post-seed."""
    app = async_client._app  # type: ignore[attr-defined]
    app.state.proxy_byok_cache = FakeBYOKCache(
        {(user_id, agent_instance_id): ("openrouter", byok_key)}
    )
    from api_server.services.proxy_ip_map import ProxyIPMap
    app.state.proxy_ip_map = ProxyIPMap(db_pool=db_pool)
    await app.state.proxy_ip_map.refresh()


# ---------------------------------------------------------------------------
# 1. free tier @ balance=0 → passes through (BYOK; no 402 gate)
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_passes_through_for_free_tier_with_zero_balance(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="free")
    # No credit_balances row at all (LEFT JOIN→0); free tier doesn't
    # exercise the 402 gate either way.
    bridge_ip = "172.18.0.42"
    token = "tok-free-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(
            200,
            content=b'{"id":"x","choices":[{"message":{"content":"ok"}}]}',
            headers={"Content-Type": "application/json"},
        ),
    )
    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200, resp.text
    assert upstream_route.call_count == 1, (
        "free-tier MUST pass through to upstream"
    )


# ---------------------------------------------------------------------------
# 2. pro tier @ balance=0 → passes through (BYOK; no 402 gate)
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_passes_through_for_pro_tier_with_zero_balance(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="pro")
    # Pro tier with an explicit zero-balance cache row — predicate must
    # NOT trigger because tier != 'ultra'.
    await _seed_balance(db_pool, user_id=user_id, balance_cents=0)
    bridge_ip = "172.18.0.43"
    token = "tok-pro-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(
            200,
            content=b'{"id":"y","choices":[]}',
            headers={"Content-Type": "application/json"},
        ),
    )
    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200, resp.text
    assert upstream_route.call_count == 1


# ---------------------------------------------------------------------------
# 3. ultra tier @ balance=1 cent → passes through (just at the floor)
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_passes_through_for_ultra_tier_with_one_cent_balance(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """``balance_cents == 1`` is NOT ``< 1`` → predicate false, passes through."""
    user_id = await _seed_user(db_pool, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=1)
    bridge_ip = "172.18.0.44"
    token = "tok-ultra1-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(
            200,
            content=b'{"id":"z","choices":[]}',
            headers={"Content-Type": "application/json"},
        ),
    )
    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200, resp.text
    assert upstream_route.call_count == 1, (
        "ultra-tier with balance=1¢ MUST pass through (just at the floor)"
    )


# ---------------------------------------------------------------------------
# 4. ultra tier @ balance=0 → 402 INSUFFICIENT_BALANCE
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_returns_402_INSUFFICIENT_BALANCE_for_ultra_tier_with_zero_balance(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    user_id = await _seed_user(db_pool, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=0)
    bridge_ip = "172.18.0.45"
    token = "tok-ultra0-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    # Mount a respx route that would FAIL LOUDLY if hit — the proxy must
    # NOT call upstream after the 402.
    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(500, content=b"upstream-not-allowed"),
    )

    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 402, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert body["error"]["type"] == "payment_required"
    assert "credits" in body["error"]["message"].lower(), (
        f"402 message MUST mention credits/topup; got {body['error']['message']!r}"
    )
    assert upstream_route.call_count == 0, (
        "402 path MUST NOT forward to upstream"
    )


# ---------------------------------------------------------------------------
# 5. ultra tier @ negative balance → 402 (D-16 + Pitfall 6)
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_returns_402_for_ultra_tier_with_negative_balance(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """``balance_cents < 0`` (post-refund drain) MUST also trigger 402.

    D-16 allows negative balance until admin write-off; predicate ``< 1``
    catches both 0 and any negative value (RESEARCH §Pitfall 6).
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=-50)
    bridge_ip = "172.18.0.46"
    token = "tok-ultraneg-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(500, content=b"upstream-not-allowed"),
    )

    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 402, resp.text
    body = resp.json()
    assert body["error"]["code"] == "INSUFFICIENT_BALANCE"
    assert upstream_route.call_count == 0


# ---------------------------------------------------------------------------
# 6. Combined: 402 SKIPS upstream call (load-bearing for cost-prevention)
# ---------------------------------------------------------------------------


@respx.mock
async def test_proxy_402_skips_upstream_call(
    async_client: AsyncClient, db_pool: asyncpg.Pool,
) -> None:
    """Same shape as #4 but explicitly asserts ``call_count == 0`` as the
    sole gate — covers the regression where the predicate fires AND the
    upstream is still called (e.g. a future refactor that mistakenly
    moves the check below body mutation).
    """
    user_id = await _seed_user(db_pool, tier="ultra")
    await _seed_balance(db_pool, user_id=user_id, balance_cents=0)
    bridge_ip = "172.18.0.47"
    token = "tok-skipupstream-32hex"
    agent_id, _ = await _seed_agent_and_container(
        db_pool,
        user_id=user_id, bridge_ip=bridge_ip, inapp_auth_token=token,
    )
    await _wire_proxy_state(
        async_client, db_pool,
        user_id=user_id, agent_instance_id=agent_id,
        bridge_ip=bridge_ip,
    )
    app = async_client._app  # type: ignore[attr-defined]

    upstream_route = respx.post(
        "https://openrouter.ai/api/v1/chat/completions",
    ).mock(
        return_value=httpx.Response(500, content=b"upstream-not-allowed"),
    )

    proxy_client = _build_proxy_client(app, bridge_ip)
    async with proxy_client:
        resp = await proxy_client.post(
            "/v1/llm/forward/chat/completions",
            headers={
                "Authorization": f"Bearer ap-proxy-{token}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )

    assert resp.status_code == 402
    assert upstream_route.call_count == 0, (
        "402 path MUST short-circuit BEFORE upstream forward — "
        "regressions here cost real money"
    )
