"""Phase 28 Plan 28-07 Task 2 — emit_inapp_outbound success-path no-op lock-in.

Per RESEARCH §7 R2 + R7, the success-path agent_events row is written by
``mark_message_done`` in the SAME asyncpg transaction as the
inapp_messages status flip — atomic dual-write. The
``emit_inapp_outbound`` activity is preserved as a NO-OP for shape parity
with MSV's ``send_message.go`` and as a future-extension hook (see
emit_inapp_outbound.py docstring).

This single test locks in the design rationale so a future "tidy-up" PR
cannot silently re-introduce a real-DB side-effect on the success path
of emit_inapp_outbound — doing so would create a SECOND, non-atomic
agent_events row that the outbox pump (services/inapp_outbox.py) would
publish twice, breaking the SSE-stream contract.

If this test FAILS:

* The fix is NOT to delete this test.
* The fix is to delete the new ``insert_agent_event`` call inside
  ``emit_inapp_outbound``, OR — if the design is actually changing —
  to remove the matching call from ``mark_message_done`` so only ONE
  row is ever written.
"""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest_asyncio
from temporalio.testing import ActivityEnvironment

from api_server.temporal.activities.emit_inapp_outbound import (
    emit_inapp_outbound,
)


@pytest_asyncio.fixture
async def seed_container_row(db_pool):
    """Seed users/agent_instances/agent_containers so we have a
    container_row_id the test can reference. Returns the container's
    UUID and the matching user/agent UUIDs.
    """
    user_id = uuid4()
    agent_id = uuid4()
    container_row_id = uuid4()
    docker_container_id = f"deadbeef{uuid4().hex[:24]}"
    name = f"agent-{uuid4().hex[:8]}"

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "emit-noop-test",
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
    return (container_row_id, user_id, agent_id)


async def test_emit_inapp_outbound_is_noop_for_success(
    db_pool, seed_container_row,
) -> None:
    """Lock-in: ``emit_inapp_outbound`` must NOT insert an agent_events row.

    The atomic write happens inside ``mark_message_done`` (covered by
    ``test_mark_done_atomic_success`` in test_mark_message_done_activity.py).
    If a future refactor adds an ``insert_agent_event`` call here, the
    outbox pump would publish the inapp_outbound event TWICE — this test
    catches that regression.
    """
    container_row_id, user_id, agent_id = seed_container_row

    # Pre-count agent_events for this container.
    async with db_pool.acquire() as conn:
        pre = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            container_row_id,
        )

    sample_event_input = {
        "message_id": str(uuid4()),
        "container_row_id": str(container_row_id),
        "user_id": str(user_id),
        "agent_id": str(agent_id),
        "kind": "inapp_outbound",
        "payload": {"text": "hi back"},
        "reply": "hi back",
    }

    env = ActivityEnvironment()
    result = await env.run(emit_inapp_outbound, sample_event_input)
    assert result is None, "success-path no-op must return None"

    async with db_pool.acquire() as conn:
        post = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            container_row_id,
        )

    assert post == pre, (
        "emit_inapp_outbound MUST be a success-path no-op — the "
        "dual-write lives in mark_message_done (see "
        "test_mark_done_atomic_success). If this test fails because "
        "emit_inapp_outbound now inserts an agent_events row, the "
        "outbox pump will publish the event TWICE (once per row). "
        "Revert the change or rework mark_message_done to remove its "
        "insert_agent_event call so only ONE row is ever written."
    )
