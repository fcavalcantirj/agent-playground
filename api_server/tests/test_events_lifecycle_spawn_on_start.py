"""Phase 22b-04 Task 2 — POST /start spawns a watcher.

Validates the SPAWN MECHANICS the route uses (run_watcher + registry +
teardown) without paying the cost of a real /start (docker pull + 60s+
container boot for hermes). A true route-integration test that hits
``POST /v1/agents/:id/start`` with a real hermes image is deferred to
Plan 22b-06's e2e harness.

The shape under test mirrors what `start_agent` does after Step 8:

    asyncio.create_task(run_watcher(
        request.app.state,
        container_row_id=container_row_id,
        container_id=container_id,
        agent_id=container_row_id,   # event_store keys by container_row_id
        recipe=recipe,
        channel=body.channel,
        chat_id_hint=body.channel_inputs.get("TELEGRAM_ALLOWED_USER"),
    ))

Marked ``api_integration`` because it requires:
  1. Live Docker daemon (alpine container)
  2. Real Postgres + agent_events table (Plan 22b-02)
  3. Real agent_containers row (FK chain)
"""
from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

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


ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture
async def seed_agent_container(db_pool) -> UUID:
    """Insert agent_instances + agent_containers pair, return container PK.

    Same shape as test_events_watcher_backpressure / teardown — kept inline
    per the per-file-isolation discipline of Plan 22b-03 SUMMARY decision 4.
    """
    instance_id = uuid4()
    container_pk = uuid4()
    instance_name = f"spawn-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, 'hermes', 'openrouter/anthropic/claude-haiku-4.5', $3)
            """,
            instance_id,
            ANONYMOUS_USER_ID,
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
            ANONYMOUS_USER_ID,
            f"docker-{container_pk.hex[:12]}",
        )
    return container_pk


@pytest.mark.asyncio
async def test_start_spawns_watcher(
    running_alpine_container, db_pool, seed_agent_container
):
    """Spawning run_watcher with the route's parameter shape registers it."""
    container = running_alpine_container(["sh", "-c", "echo hi; sleep 30"])
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
    # Give the watcher a moment to register itself.
    await asyncio.sleep(0.4)
    assert container_row_id in state.log_watchers, (
        f"watcher did not register itself; current: "
        f"{list(state.log_watchers.keys())}"
    )
    # Teardown — remove container so source iterator ends naturally
    # (spike-03: <270ms).
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=5.0)
    assert container_row_id not in state.log_watchers, (
        "watcher did not unregister on natural exit"
    )


@pytest.mark.asyncio
async def test_start_spawn_failure_does_not_register(
    db_pool, seed_agent_container
):
    """Watcher with unknown event_source_fallback.kind raises ValueError;
    failure path leaves no orphan registry entry.

    The /start handler wraps the spawn in try/except so an unknown source
    kind logs but does not fail the HTTP response — events are observability,
    not correctness. This test exercises run_watcher's behavior for the
    failure path (raises ValueError from _select_source); the route-level
    swallowing is asserted at the route file via grep_only.
    """
    state = _FakeAppState(db_pool)
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {
                    "reply_sent": r"reply (?P<chat_id>\d+)"
                },
                # Bogus kind — _select_source raises ValueError
                "event_source_fallback": {"kind": "made_up_kind", "spec": {}},
            }
        }
    }
    container_row_id = seed_agent_container
    task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=container_row_id,
            container_id="never-existed",
            agent_id=container_row_id,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="0",
        )
    )
    # The watcher will register itself THEN raise inside _select_source;
    # the finally pop removes the entry.
    with pytest.raises(ValueError, match="unknown event_source_fallback.kind"):
        await asyncio.wait_for(task, timeout=2.0)
    assert container_row_id not in state.log_watchers, (
        "registry leaked entry on watcher init failure"
    )
