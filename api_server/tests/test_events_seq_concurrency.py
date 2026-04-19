"""Phase 22b-02 — spike-05 port: concurrent seq allocation reproducer.

Spike-05 (``.planning/phases/22b-agent-event-stream/22b-SPIKES/spike-05-seq-ordering.md``)
proved that ``pg_advisory_xact_lock(hashtext($1::text))`` + ``MAX(seq)+1``
produces gap-free 1..N seq allocation when 4 concurrent writers race
against the SAME ``agent_container_id``.

This test ports the spike reproducer verbatim and asserts:

  - 4 writers x 50 inserts each → exactly 200 rows
  - seqs are exactly 1..200 (gap-free, monotonic, no duplicates)
  - 0 ``UniqueViolationError`` exceptions
  - 0 ``DeadlockDetectedError`` exceptions

If this test starts failing the advisory lock has regressed and the
batching path likely also leaks (spike-05 + spike-04 share the same
seq-allocation invariant).

Marked ``api_integration`` — opt-in via ``pytest -m api_integration``.
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import asyncpg
import pytest

from api_server.services.event_store import insert_agent_event

pytestmark = pytest.mark.api_integration


ANON_USER_ID = "00000000-0000-0000-0000-000000000001"


async def _seed_container_via_pool(pool: asyncpg.Pool) -> UUID:
    """Insert agent_instance + agent_container, return container UUID."""
    recipe_name = f"seq-conc-{uuid4().hex[:8]}"
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
async def seed_agent_container(real_db_pool):
    cid = await _seed_container_via_pool(real_db_pool)
    return cid


@pytest.mark.asyncio
async def test_seq_concurrent_4_writers_gap_free(
    real_db_pool, seed_agent_container
):
    """4 concurrent writers x 50 rows each → 200 gap-free seqs."""
    payload = {
        "chat_id": "1",
        "length_chars": 1,
        "captured_at": "2026-04-18T00:00:00Z",
    }

    async def writer(wid: int) -> dict[str, int]:
        counts = {"successes": 0, "uv": 0, "dl": 0}
        for i in range(50):
            async with real_db_pool.acquire() as conn:
                try:
                    await insert_agent_event(
                        conn,
                        seed_agent_container,
                        "reply_sent",
                        payload,
                        correlation_id=f"w{wid}-{i}",
                    )
                    counts["successes"] += 1
                except asyncpg.UniqueViolationError:
                    counts["uv"] += 1
                except asyncpg.DeadlockDetectedError:
                    counts["dl"] += 1
        return counts

    results = await asyncio.gather(*[writer(w) for w in range(4)])

    async with real_db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT seq FROM agent_events "
            "WHERE agent_container_id=$1 ORDER BY seq",
            seed_agent_container,
        )
    seqs = [r["seq"] for r in rows]

    assert seqs == list(range(1, 201)), (
        f"gaps detected — first 5: {seqs[:5]} ... last 5: {seqs[-5:]} "
        f"(len={len(seqs)})"
    )
    total_successes = sum(r["successes"] for r in results)
    assert total_successes == 200, (
        f"expected 200 successes; got {total_successes} "
        f"(per-writer: {results})"
    )
    assert all(r["uv"] == 0 for r in results), (
        f"UniqueViolationError leaked through advisory lock — {results}"
    )
    assert all(r["dl"] == 0 for r in results), (
        f"DeadlockDetectedError observed — {results}"
    )
