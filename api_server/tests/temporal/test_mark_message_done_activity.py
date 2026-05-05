"""Phase 28 Plan 28-07 Task 2 — mark_message_done atomic dual-write tests.

Real Postgres via the shared ``db_pool`` fixture (testcontainers PG 17).
Per Golden Rule #1, NO in-memory mocks for the substrate.

Coverage matrix per Plan 28-07 frontmatter ``must_haves.truths``:

* ``test_mark_done_atomic_success``
    Pre-seed an inapp_messages row in status='forwarded' and a matching
    agent_containers row. Run mark_message_done. Assert the row is now
    status='done' AND an agent_events row exists with kind='inapp_outbound'
    and published=False.

* ``test_mark_done_atomic_rollback``
    Monkey-patch ``insert_agent_event`` (the late-imported helper inside
    the activity body) to raise RuntimeError. Run mark_message_done.
    Assert the activity raised, and the inapp_messages row is STILL
    status='forwarded' (the transaction rolled the mark_done UPDATE
    back).

The atomicity is the load-bearing invariant per RESEARCH §7 R2: the
outbox pump (services/inapp_outbox.py) must NEVER see a 'done' row
without its matching 'inapp_outbound' agent_events row, or vice versa.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.mark_message_done import MarkActivities


@pytest_asyncio.fixture
async def seed_inapp_message_forwarded(db_pool):
    """Seed users/agent_instances/agent_containers/inapp_messages so the
    activity has a forwarded row to flip to done.

    Returns ``(message_id, container_row_id, user_id, agent_id)``.
    """
    user_id = uuid4()
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    name = f"agent-{uuid4().hex[:8]}"

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "mark-done-test",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes-test', 'm-test', $3)
            """,
            agent_id, user_id, name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
                (id, agent_instance_id, user_id, recipe_name,
                 deploy_mode, container_status, container_id, ready_at)
            VALUES ($1, $2, $3, 'hermes-test', 'persistent', 'running',
                    $4, NOW())
            """,
            container_row_id, agent_id, user_id, docker_container_id,
        )
        message_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages
                (agent_id, user_id, content, status, attempts, last_attempt_at)
            VALUES ($1, $2, $3, 'forwarded', 1, NOW())
            RETURNING id
            """,
            agent_id, user_id, "hello bot",
        )
    return (message_id, container_row_id, user_id, agent_id)


# ---------------------------------------------------------------------------
# 1. atomic success — mark_done + insert_agent_event in one transaction
# ---------------------------------------------------------------------------


async def test_mark_done_atomic_success(
    db_pool, seed_inapp_message_forwarded,
) -> None:
    message_id, container_row_id, user_id, agent_id = seed_inapp_message_forwarded
    acts = MarkActivities(db_pool=db_pool)

    env = ActivityEnvironment()
    await env.run(
        acts.mark_message_done,
        {
            "message_id": str(message_id),
            "container_row_id": str(container_row_id),
            "user_id": str(user_id),
            "agent_id": str(agent_id),
            "bot_response": "hi back",
        },
    )

    async with db_pool.acquire() as conn:
        msg = await conn.fetchrow(
            "SELECT status, bot_response FROM inapp_messages WHERE id=$1",
            message_id,
        )
        assert msg is not None
        assert msg["status"] == "done", "row must transition forwarded→done"
        assert msg["bot_response"] == "hi back"

        events = await conn.fetch(
            """
            SELECT kind, payload, published
            FROM agent_events
            WHERE agent_container_id = $1
            ORDER BY seq ASC
            """,
            container_row_id,
        )
    assert len(events) == 1
    assert events[0]["kind"] == "inapp_outbound"
    # The outbox pump scans for published=False rows and fans out.
    assert events[0]["published"] is False, (
        "atomic dual-write must leave published=False so the outbox pump "
        "fans out to Redis"
    )


# ---------------------------------------------------------------------------
# 2. atomic rollback — insert_agent_event raises → mark_done is rolled back
# ---------------------------------------------------------------------------


async def test_mark_done_atomic_rollback(
    db_pool, seed_inapp_message_forwarded, monkeypatch,
) -> None:
    """If ``insert_agent_event`` raises after ``mark_done`` has run inside
    the transaction, both writes must roll back. The inapp_messages row
    stays at status='forwarded'.

    The activity body uses a function-local ``from ...services.event_store
    import insert_agent_event`` import (mark_message_done.py:61); the
    monkey-patch must therefore target ``api_server.services.event_store
    .insert_agent_event`` (the source) so the late import resolves to the
    failing function.
    """
    message_id, container_row_id, user_id, agent_id = seed_inapp_message_forwarded

    async def _failing_insert(
        conn, agent_container_id, kind, payload,
        *, correlation_id=None,
    ):
        raise RuntimeError("simulated outbox write failure")

    monkeypatch.setattr(
        "api_server.services.event_store.insert_agent_event",
        _failing_insert,
    )

    acts = MarkActivities(db_pool=db_pool)
    env = ActivityEnvironment()

    with pytest.raises(RuntimeError, match="simulated outbox write failure"):
        await env.run(
            acts.mark_message_done,
            {
                "message_id": str(message_id),
                "container_row_id": str(container_row_id),
                "user_id": str(user_id),
                "agent_id": str(agent_id),
                "bot_response": "hi back",
            },
        )

    # Rollback verified: status STILL forwarded; bot_response is NULL.
    async with db_pool.acquire() as conn:
        msg = await conn.fetchrow(
            "SELECT status, bot_response FROM inapp_messages WHERE id=$1",
            message_id,
        )
        assert msg is not None
        assert msg["status"] == "forwarded", (
            "rollback must leave the row at status='forwarded' — the "
            "atomic transaction guarantees mark_done + insert_agent_event "
            "either both commit or both roll back"
        )
        assert msg["bot_response"] is None

        # And no agent_events row was committed.
        events = await conn.fetch(
            "SELECT kind FROM agent_events WHERE agent_container_id=$1",
            container_row_id,
        )
        assert len(events) == 0
