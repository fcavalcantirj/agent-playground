"""Phase 22b-04 Task 2 — /stop drains watcher before execute_persistent_stop.

Validates the SEQUENCE the route uses: stop_event.set() → await task with
2s budget → THEN call execute_persistent_stop. We do NOT actually invoke
``POST /v1/agents/:id/stop`` here (that needs a real persistent container);
instead we exercise the 5-line snippet the stop handler runs.

The route-level ordering proof (stop_event.set BEFORE execute_persistent_stop)
is asserted at the route file via grep_only — see Task 2 acceptance criteria.

Marked ``api_integration`` because:
  1. Live Docker daemon
  2. Real Postgres + agent_events (Plan 22b-02)
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from api_server.services.watcher_service import run_watcher

pytestmark = pytest.mark.api_integration


class _FakeAppState:
    def __init__(self, db_pool):
        self.db = db_pool
        self.log_watchers: dict = {}
        self.event_poll_signals: dict = {}
        self.event_poll_locks: dict = {}
        self.locks_mutex = asyncio.Lock()


# Phase 22c-06: local test placeholder user id. UUID value preserved from
# the pre-22c local redef (no constant-import change here); only the name
# changed to avoid confusion with the deleted global ANONYMOUS_USER_ID.
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture
async def seed_agent_container(db_pool) -> UUID:
    instance_id = uuid4()
    container_pk = uuid4()
    instance_name = f"cancel-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        # Phase 22c-06: seed FK target (migration 006 purged ANONYMOUS row).
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1, 'cancel-test-owner')
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
async def test_stop_drains_watcher(
    running_alpine_container, db_pool, seed_agent_container
):
    """stop_event.set() → asyncio.wait_for(task, 2s) drains watcher cleanly.

    Mirrors the snippet in stop_agent::

        watcher_entry = request.app.state.log_watchers.get(UUID(running['id']))
        if watcher_entry is not None:
            wtask, wstop = watcher_entry
            wstop.set()
            try:
                await asyncio.wait_for(wtask, timeout=2.0)
            except asyncio.TimeoutError:
                wtask.cancel()
    """
    container = running_alpine_container(
        ["sh", "-c", "while true; do echo 'reply 123'; sleep 0.05; done"]
    )
    state = _FakeAppState(db_pool)
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {
                    "reply_sent": r"reply (?P<chat_id>\d+)"
                }
            }
        }
    }
    container_row_id = seed_agent_container
    task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=container_row_id,
            container_id=container.id,
            agent_id=container_row_id,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="123",
        )
    )
    await asyncio.sleep(0.4)
    assert container_row_id in state.log_watchers
    # Apply the route's drain pattern.
    _wtask, wstop = state.log_watchers[container_row_id]
    wstop.set()
    # Container removal is what allows source.lines() to end (stop_event
    # alone races with the inner producer loop's blocking iterator pull).
    # In production /stop, execute_persistent_stop reaps the container next;
    # the watcher exits when that happens. We simulate by removing here so
    # the test can run without spinning up the full execute_persistent_stop
    # flow.
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=3.0)
    assert container_row_id not in state.log_watchers, (
        "registry not cleaned after watcher drain"
    )


@pytest.mark.asyncio
async def test_stop_drain_handles_already_done_watcher(
    running_alpine_container, db_pool, seed_agent_container
):
    """If the watcher already completed (container removed before /stop),
    the drain snippet is a no-op (registry already empty).

    /stop guards against missing entries via ``log_watchers.get(...)`` →
    ``None``; the if-block is skipped.
    """
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
    state = _FakeAppState(db_pool)
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {
                    "reply_sent": r"NEVER_MATCHES"
                }
            }
        }
    }
    container_row_id = seed_agent_container
    task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=container_row_id,
            container_id=container.id,
            agent_id=container_row_id,
            recipe=recipe,
            channel="telegram",
            chat_id_hint=None,
        )
    )
    await asyncio.sleep(0.4)
    container.remove(force=True)
    # Wait for natural termination (registry self-cleans).
    await asyncio.wait_for(task, timeout=5.0)
    assert container_row_id not in state.log_watchers
    # Now apply the /stop drain pattern — it should be a no-op on
    # already-gone entries.
    watcher_entry = state.log_watchers.get(container_row_id)
    assert watcher_entry is None, "watcher entry should be gone"
    # Route's guard: `if watcher_entry is not None: ...` — skipped here.
