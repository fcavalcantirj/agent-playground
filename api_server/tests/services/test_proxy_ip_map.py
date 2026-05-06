"""Phase 29 Plan 04 Task 1 — integration tests for ProxyIPMap.

Real PG17 via testcontainers (golden rule #1 — no mocks for core
substrate). Tests cover the 7 behaviors enumerated in the plan:

  1. ``test_refresh_populates_from_running_rows`` — happy path
  2. ``test_refresh_skips_non_running_rows`` (PROBE-VAL-15 scope filter)
  3. ``test_refresh_skips_null_bridge_ip``
  4. ``test_refresh_atomic_swap`` — concurrent get sees old or new, never partial
  5. ``test_refresh_loop_ticks`` — interval respected
  6. ``test_refresh_loop_swallows_exceptions`` — bad refresh does not kill loop
  7. ``test_refresh_loop_responds_to_stop_event`` — within 1s budget
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


async def _seed_user_and_agent(
    pool: asyncpg.Pool,
) -> tuple[UUID, UUID]:
    """INSERT a user + agent_instance; return (user_id, agent_instance_id)."""
    user_id = uuid4()
    agent_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, 'proxy-ip-map-test')",
            user_id,
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'recipe-x', 'm-test', 'agent-x')
            """,
            agent_id, user_id,
        )
    return user_id, agent_id


async def _seed_running_container(
    pool: asyncpg.Pool,
    *,
    user_id: UUID,
    agent_instance_id: UUID,
    bridge_ip: str | None = "172.18.0.42",
    inapp_auth_token: str | None = "test-token-32hex",
    container_status: str = "running",
) -> UUID:
    """INSERT one agent_containers row. Returns the row id.

    PROBE-VAL-15: the partial unique index
    ``ix_agent_containers_bridge_ip_running`` blocks two ``running``
    rows with the same ``bridge_ip``. Tests that need multiple running
    rows must use distinct IPs.
    """
    row_id = uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_containers (
                id, agent_instance_id, user_id, recipe_name,
                deploy_mode, container_status, container_id,
                bridge_ip, inapp_auth_token, ready_at
            ) VALUES (
                $1, $2, $3, 'recipe-x',
                'persistent', $4, $5,
                $6::inet, $7,
                CASE WHEN $4 = 'running' THEN NOW() ELSE NULL END
            )
            """,
            row_id, agent_instance_id, user_id,
            container_status, f"deadbeef{uuid4().hex[:24]}",
            bridge_ip, inapp_auth_token,
        )
    return row_id


# ---------------------------------------------------------------------------
# Test 1 — refresh populates from running rows
# ---------------------------------------------------------------------------


async def test_refresh_populates_from_running_rows(db_pool: asyncpg.Pool) -> None:
    """Two running containers with distinct bridge IPs → both visible in cache."""
    from api_server.services.proxy_ip_map import ProxyIPMap

    u1, a1 = await _seed_user_and_agent(db_pool)
    u2, a2 = await _seed_user_and_agent(db_pool)
    await _seed_running_container(
        db_pool, user_id=u1, agent_instance_id=a1,
        bridge_ip="172.18.0.10", inapp_auth_token="tok-aaa",
    )
    await _seed_running_container(
        db_pool, user_id=u2, agent_instance_id=a2,
        bridge_ip="172.18.0.11", inapp_auth_token="tok-bbb",
    )

    ip_map = ProxyIPMap(db_pool)
    count = await ip_map.refresh()
    assert count == 2

    got_a = await ip_map.get("172.18.0.10")
    assert got_a is not None
    user_a, agent_a, token_a = got_a
    assert user_a == u1
    assert agent_a == a1
    assert token_a == "tok-aaa"

    got_b = await ip_map.get("172.18.0.11")
    assert got_b is not None
    user_b, agent_b, token_b = got_b
    assert user_b == u2
    assert agent_b == a2
    assert token_b == "tok-bbb"


# ---------------------------------------------------------------------------
# Test 2 — running-only scope (PROBE-VAL-15)
# ---------------------------------------------------------------------------


async def test_refresh_skips_non_running_rows(db_pool: asyncpg.Pool) -> None:
    """A stopped row with a bridge_ip MUST NOT pollute the cache.

    PROBE-VAL-15 documented IP reuse (Docker bridge re-allocates IPs);
    a freshly-stopped user A's IP could be mis-attributed to a freshly-
    started user B unless the SELECT scopes to ``container_status='running'``.
    """
    from api_server.services.proxy_ip_map import ProxyIPMap

    u, a = await _seed_user_and_agent(db_pool)
    # The partial unique index allows multiple non-running rows with the
    # same bridge_ip; we deliberately add one stopped row and assert it
    # is NOT visible after refresh.
    await _seed_running_container(
        db_pool, user_id=u, agent_instance_id=a,
        bridge_ip="172.18.0.99", inapp_auth_token="tok-stopped",
        container_status="stopped",
    )

    ip_map = ProxyIPMap(db_pool)
    count = await ip_map.refresh()
    assert count == 0
    assert await ip_map.get("172.18.0.99") is None


# ---------------------------------------------------------------------------
# Test 3 — NULL bridge_ip filter
# ---------------------------------------------------------------------------


async def test_refresh_skips_null_bridge_ip(db_pool: asyncpg.Pool) -> None:
    """Rows with NULL bridge_ip don't appear in the cache.

    Pre-Phase-29 (and during the rolling deploy window) some running
    rows may have ``bridge_ip IS NULL`` — the dispatcher fills it on
    the next deploy. The cache must skip those rather than crash on a
    None key.
    """
    from api_server.services.proxy_ip_map import ProxyIPMap

    u1, a1 = await _seed_user_and_agent(db_pool)
    u2, a2 = await _seed_user_and_agent(db_pool)
    await _seed_running_container(
        db_pool, user_id=u1, agent_instance_id=a1,
        bridge_ip=None, inapp_auth_token="tok-nullip",
    )
    await _seed_running_container(
        db_pool, user_id=u2, agent_instance_id=a2,
        bridge_ip="172.18.0.55", inapp_auth_token="tok-real",
    )

    ip_map = ProxyIPMap(db_pool)
    count = await ip_map.refresh()
    # Only the row with a non-NULL bridge_ip should be cached.
    assert count == 1
    assert await ip_map.get("172.18.0.55") is not None


# ---------------------------------------------------------------------------
# Test 4 — refresh atomic swap
# ---------------------------------------------------------------------------


async def test_refresh_atomic_swap(db_pool: asyncpg.Pool) -> None:
    """A concurrent get during refresh sees the OLD or NEW dict, never partial.

    Implementation contract: the SELECT runs OUTSIDE the lock; the dict
    swap is a single reference assignment under the lock. A get() in
    flight either holds the old reference (and returns the old value)
    or has not yet taken the lock (and returns the new value). It can
    never observe a partially-built dict.

    We can't directly observe a partial state because the cache is
    ``dict[str, tuple]`` and all mutations are reference swaps; instead
    we prove the invariant by running 50 gets in parallel with a
    refresh and checking every observed value is either the OLD value
    or the NEW value (never None mid-update, never a torn tuple).
    """
    from api_server.services.proxy_ip_map import ProxyIPMap

    u, a = await _seed_user_and_agent(db_pool)
    container_id = await _seed_running_container(
        db_pool, user_id=u, agent_instance_id=a,
        bridge_ip="172.18.0.77", inapp_auth_token="tok-old",
    )

    ip_map = ProxyIPMap(db_pool)
    await ip_map.refresh()
    assert (await ip_map.get("172.18.0.77"))[2] == "tok-old"

    # Mutate the row to a new token value.
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE agent_containers SET inapp_auth_token=$1 WHERE id=$2",
            "tok-new", container_id,
        )

    # Run 50 gets concurrent with a refresh; every observation must be
    # either "tok-old" or "tok-new" (NOT None, NOT a partial value).
    observations: list[str | None] = []

    async def _spy() -> None:
        for _ in range(50):
            got = await ip_map.get("172.18.0.77")
            observations.append(got[2] if got else None)
            await asyncio.sleep(0)

    await asyncio.gather(_spy(), ip_map.refresh())
    # No torn / missing observations.
    assert all(v in ("tok-old", "tok-new") for v in observations), (
        f"saw torn observation: {set(observations) - {'tok-old', 'tok-new'}}"
    )
    # And after the refresh resolves, the NEW value is canonical.
    final = await ip_map.get("172.18.0.77")
    assert final is not None
    assert final[2] == "tok-new"


# ---------------------------------------------------------------------------
# Test 5 — refresh_loop ticks at the configured interval
# ---------------------------------------------------------------------------


async def test_refresh_loop_ticks(db_pool: asyncpg.Pool) -> None:
    """A 50ms interval over a 200ms window calls refresh at least 3 times."""
    from api_server.services.proxy_ip_map import ProxyIPMap, refresh_loop

    ip_map = ProxyIPMap(db_pool)

    # Wrap refresh to count invocations.
    counter = {"n": 0}
    real_refresh = ip_map.refresh

    async def _counting_refresh() -> int:
        counter["n"] += 1
        return await real_refresh()

    ip_map.refresh = _counting_refresh  # type: ignore[method-assign]

    stop = asyncio.Event()
    task = asyncio.create_task(refresh_loop(ip_map, stop, interval_s=0.05))
    try:
        await asyncio.sleep(0.20)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)
    # Loop runs refresh once, sleeps 50ms, runs again, etc.
    # 0..200ms inclusive ≥ 3 ticks (one immediate + ≥2 after sleeps).
    assert counter["n"] >= 3, (
        f"expected ≥3 refresh calls in 200ms window with 50ms interval, got {counter['n']}"
    )


# ---------------------------------------------------------------------------
# Test 6 — refresh_loop swallows exceptions
# ---------------------------------------------------------------------------


async def test_refresh_loop_swallows_exceptions(db_pool: asyncpg.Pool) -> None:
    """A refresh that raises must NOT kill the loop; next tick must succeed.

    Real-world failure: a transient DB blip during one refresh shouldn't
    leave the proxy without IP-map updates forever.
    """
    from api_server.services.proxy_ip_map import ProxyIPMap, refresh_loop

    ip_map = ProxyIPMap(db_pool)

    raised = {"first": False}
    succeeded = {"after": 0}

    async def _flaky_refresh() -> int:
        if not raised["first"]:
            raised["first"] = True
            raise RuntimeError("simulated DB blip")
        succeeded["after"] += 1
        return 0

    ip_map.refresh = _flaky_refresh  # type: ignore[method-assign]

    stop = asyncio.Event()
    task = asyncio.create_task(refresh_loop(ip_map, stop, interval_s=0.02))
    try:
        await asyncio.sleep(0.10)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)

    assert raised["first"] is True
    assert succeeded["after"] >= 1, (
        "loop must continue after exception; expected ≥1 successful refresh"
    )
    assert task.exception() is None


# ---------------------------------------------------------------------------
# Test 7 — refresh_loop responds to stop_event in <1s
# ---------------------------------------------------------------------------


async def test_refresh_loop_responds_to_stop_event(db_pool: asyncpg.Pool) -> None:
    """Setting stop_event during a sleep returns within 1s budget."""
    from api_server.services.proxy_ip_map import ProxyIPMap, refresh_loop

    ip_map = ProxyIPMap(db_pool)

    stop = asyncio.Event()
    # Long interval so the loop is mid-sleep when we set the event.
    task = asyncio.create_task(refresh_loop(ip_map, stop, interval_s=10.0))
    # Let the first refresh + sleep start.
    await asyncio.sleep(0.05)
    assert not task.done()

    stop.set()
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
    assert task.exception() is None
