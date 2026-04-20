"""Phase 22b-03 Task 3 — spike-03 teardown reproducer.

Threshold (spike-03): docker rm -f ends iterator <270ms; watcher task
transitions to done within 2s; ``asyncio.all_tasks()`` delta == 0.

Marked ``api_integration`` because:
  1. Requires live Docker daemon
  2. Requires real Postgres + ``agent_events`` (Plan 22b-02) and
     ``agent_containers`` (earlier phases)
  3. Imports ``run_watcher`` which deferred-imports ``event_store`` and
     ``models.events`` from Plan 22b-02 — orchestrator runs this gate
     after the wave-1 merge.
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from api_server.services.watcher_service import run_watcher

pytestmark = pytest.mark.api_integration


class _FakeAppState:
    """Minimal substitute for ``app.state`` shape used by the watcher."""

    def __init__(self, db_pool):
        self.db = db_pool
        self.log_watchers: dict = {}
        self.event_poll_signals: dict = {}
        self.event_poll_locks: dict = {}
        self.locks_mutex = asyncio.Lock()


# Phase 22c-06: local test placeholder user id (was named ANONYMOUS_USER_ID
# pre-22c; renamed to avoid confusion with the deleted global constant).
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def seed_agent_container(db_pool) -> UUID:
    """Insert test user + agent_instances + agent_containers pair; return container PK.

    Same shape as the backpressure-test fixture; lives here to keep each
    integration test file self-contained (no shared conftest leakage).
    Schema reference: ``alembic/versions/003_agent_containers.py``.
    Phase 22c-06: migration 006 purged the old ANONYMOUS seed, so the
    fixture now seeds its own user row (ON CONFLICT-safe).
    """
    instance_id = uuid4()
    container_pk = uuid4()
    instance_name = f"watcher-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1, 'watcher-teardown-test-owner')
            ON CONFLICT (id) DO NOTHING
            """,
            TEST_USER_ID,
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes', 'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            TEST_USER_ID,
            instance_name,
        )
        await conn.execute(
            """
            INSERT INTO agent_containers
              (id, agent_instance_id, user_id, recipe_name,
               container_id, container_status, channel_type)
            VALUES ($1, $2, $3, 'hermes', $4, 'running', 'telegram')
            """,
            container_pk,
            instance_id,
            TEST_USER_ID,
            f"docker-{container_pk.hex[:12]}",
        )
    return container_pk


@pytest.mark.asyncio
async def test_watcher_teardown_on_remove_force(
    running_alpine_container, db_pool, seed_agent_container
):
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {"reply_sent": r"reply (?P<chat_id>\d+)"}
            }
        }
    }
    state = _FakeAppState(db_pool)
    tasks_before = set(asyncio.all_tasks())
    watcher_task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=uuid4(),
            container_id=container.id,
            agent_id=seed_agent_container,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="0",
        )
    )
    await asyncio.sleep(0.5)
    container.remove(force=True)
    # Watcher must complete within 5s (spike-03 budget + slack for consumer drain)
    await asyncio.wait_for(watcher_task, timeout=5.0)
    # Registry must be empty
    assert len(state.log_watchers) == 0
    # No dangling tasks introduced by this test (besides the set we started with)
    tasks_after = set(asyncio.all_tasks()) - tasks_before - {asyncio.current_task()}
    still_alive = [t for t in tasks_after if not t.done()]
    assert still_alive == [], f"dangling tasks: {still_alive}"


@pytest.mark.asyncio
async def test_watcher_teardown_on_stop_event(
    running_alpine_container, db_pool, seed_agent_container
):
    """``stop_event.set()`` from registry also terminates cleanly."""
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo reply 123; sleep 0.05; done"]
    )
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {"reply_sent": r"reply (?P<chat_id>\d+)"}
            }
        }
    }
    state = _FakeAppState(db_pool)
    crid = uuid4()
    task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=crid,
            container_id=container.id,
            agent_id=seed_agent_container,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="0",
        )
    )
    await asyncio.sleep(0.5)
    # Signal stop via registry
    _task, stop_event = state.log_watchers[crid]
    stop_event.set()
    # Also remove the container so the source iterator can end (the flood
    # consumer will keep pulling lines otherwise — stop_event handles the
    # producer loop but the inner source.lines() loop honors stop_event
    # between yields).
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=5.0)
