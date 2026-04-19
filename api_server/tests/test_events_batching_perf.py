"""Phase 22b-02 — spike-04 port: batched-INSERT speedup reproducer.

Spike-04 (``.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-04-postgres-batching.md``)
measured a 12.4x speedup for ``insert_agent_events_batch`` (one
``executemany`` under one advisory lock) versus 100 sequential
``insert_agent_event`` calls (one transaction + advisory lock per row).

This test ports the spike reproducer with a 5x floor — well below the
measured 12.4x but high enough that "the per-row optimization regressed"
or "the advisory lock now stalls the batched path" both surface as a
loud failure. The exact ratio is environment-sensitive (testcontainers
docker-network latency varies); 5x has empirical headroom.

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.
"""
from __future__ import annotations

import time
from uuid import UUID, uuid4

import asyncpg
import pytest

from api_server.services.event_store import (
    insert_agent_event,
    insert_agent_events_batch,
)

pytestmark = pytest.mark.api_integration


ANON_USER_ID = "00000000-0000-0000-0000-000000000001"


async def _seed_container_via_pool(pool: asyncpg.Pool) -> UUID:
    recipe_name = f"batch-perf-{uuid4().hex[:8]}"
    name = f"agent-{uuid4().hex[:8]}"
    async with pool.acquire() as conn:
        instance = await conn.fetchrow(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES (gen_random_uuid(), $1, $2, 'm-test', $3)
            RETURNING id
            """,
            ANON_USER_ID,
            recipe_name,
            name,
        )
        container = await conn.fetchrow(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status)
            VALUES (gen_random_uuid(), $1, $2, $3,
                    'persistent', 'starting')
            RETURNING id
            """,
            instance["id"],
            ANON_USER_ID,
            recipe_name,
        )
    return container["id"]


@pytest.fixture
async def real_db_pool(db_pool):
    yield db_pool


@pytest.fixture
async def two_seed_containers(real_db_pool):
    """Return (agent_a_uuid, agent_b_uuid) — two fresh container rows.

    Two containers so per-row inserts don't fight the batched-insert
    seq counter for the same agent. Spike-04 used the same separation.
    """
    a = await _seed_container_via_pool(real_db_pool)
    b = await _seed_container_via_pool(real_db_pool)
    return a, b


@pytest.mark.asyncio
async def test_batch_speedup_vs_per_row(real_db_pool, two_seed_containers):
    """100-row batched INSERT must be >=5x faster than 100 per-row INSERTs.

    Spike-04 measured 12.4x; floor of 5x guards against regression while
    leaving headroom for testcontainers networking variability.
    """
    agent_a, agent_b = two_seed_containers
    payload = {
        "chat_id": "1",
        "length_chars": 1,
        "captured_at": "2026-04-18T00:00:00Z",
    }

    # Per-row path: 100 separate transactions on agent_a.
    t0 = time.perf_counter()
    for _ in range(100):
        async with real_db_pool.acquire() as conn:
            await insert_agent_event(conn, agent_a, "reply_sent", payload)
    per_row_s = time.perf_counter() - t0

    # Batched path: one transaction + one advisory lock + executemany on agent_b.
    t0 = time.perf_counter()
    async with real_db_pool.acquire() as conn:
        await insert_agent_events_batch(
            conn,
            agent_b,
            [("reply_sent", payload, None) for _ in range(100)],
        )
    batch_s = time.perf_counter() - t0

    speedup = per_row_s / batch_s if batch_s > 0 else float("inf")
    assert speedup >= 5.0, (
        f"batch speedup {speedup:.1f}x < 5x floor "
        f"(per_row={per_row_s:.3f}s, batch={batch_s:.3f}s)"
    )

    # Sanity: both paths actually inserted 100 rows each.
    async with real_db_pool.acquire() as conn:
        n_a = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            agent_a,
        )
        n_b = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            agent_b,
        )
    assert n_a == 100 and n_b == 100, (
        f"row counts wrong — per_row={n_a}, batch={n_b}"
    )
