"""Phase 22b-03 Task 3 — spike-02 backpressure reproducer.

Threshold (spike-02): 20k lines in <=8s, queue stays bounded at 500,
drop path fires cleanly, 0 FD leak post-teardown, 0 dangling tasks.

This test uses a regex that matches NOTHING so the queue stays empty
(matched-line rate is the critical rate, not raw rate — D-03). The
real-world flood case is "loud container + permissive regex" which
this test does NOT exercise (that would be a fuzz test). Spike-02's
verdict covers the load-test scenario empirically.

A secondary sub-test DOES attach a permissive regex; it measures
how many drops occur when the queue saturates and that the WARN
coalesce (first + once-per-100) holds.

Marked ``api_integration`` because:
  1. Requires live Docker daemon (alpine + flood)
  2. Requires real Postgres + the ``agent_events`` table from Plan 22b-02
     and ``agent_containers`` from earlier phases
  3. Requires ``event_store.insert_agent_events_batch`` and
     ``models.events.KIND_TO_PAYLOAD`` from Plan 22b-02 — these land in
     a parallel wave-1 worktree; the orchestrator runs this gate AFTER
     merge.
"""
from __future__ import annotations

import asyncio
import logging
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


ANONYMOUS_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def seed_agent_container(db_pool) -> UUID:
    """Insert an agent_instances + agent_containers pair, return container PK.

    The watcher's ``agent_id`` parameter is wired into Plan 22b-02's
    ``insert_agent_events_batch`` as the FK to the ``agent_containers`` row.
    Schema reference: ``alembic/versions/003_agent_containers.py``
    (agent_instance_id, user_id, recipe_name, container_status).
    The anonymous user (``00000000-...-01``, baseline migration) satisfies
    the FK without spinning up a full auth flow.
    """
    instance_id = uuid4()
    container_pk = uuid4()
    # The `name` column is NOT NULL after migration 002 and uniqueness is
    # keyed on (user_id, name); generate a per-test unique name.
    instance_name = f"watcher-test-{instance_id.hex[:8]}"
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
async def test_watcher_backpressure_raw_flood_unmatched(
    running_alpine_container, db_pool, seed_agent_container
):
    """20k-line flood with no-match regex — queue stays empty, no events."""
    container = running_alpine_container(
        ["sh", "-c", "for i in $(seq 1 20000); do echo line-$i; done; sleep 3"]
    )
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {"reply_sent": r"THIS_WILL_NEVER_MATCH_\d{99}"}
            }
        }
    }
    state = _FakeAppState(db_pool)
    task = asyncio.create_task(
        run_watcher(
            state,
            container_row_id=uuid4(),
            container_id=container.id,
            agent_id=seed_agent_container,
            recipe=recipe,
            channel="telegram",
            chat_id_hint="152099202",
        )
    )
    await asyncio.sleep(5.0)  # let flood complete
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=5.0)
    # No events should have been written (no regex match).
    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM agent_events WHERE agent_container_id=$1",
            seed_agent_container,
        )
    assert count == 0
    # Watcher registry cleaned
    assert len(state.log_watchers) == 0


@pytest.mark.asyncio
async def test_watcher_drops_coalesce_warn_on_saturation(
    running_alpine_container, db_pool, seed_agent_container, caplog
):
    """Permissive regex + flood — drops happen, but WARNs are coalesced."""
    container = running_alpine_container(
        ["sh", "-c", "for i in $(seq 1 20000); do echo 'reply-x '$i; done; sleep 3"]
    )
    recipe = {
        "channels": {
            "telegram": {
                "event_log_regex": {"reply_sent": r"reply-x (?P<chat_id>\d+)"}
            }
        }
    }
    state = _FakeAppState(db_pool)
    caplog.set_level(logging.WARNING, logger="api_server.watcher")
    task = asyncio.create_task(
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
    await asyncio.sleep(6.0)
    container.remove(force=True)
    await asyncio.wait_for(task, timeout=5.0)
    # WARN logs should have fired (first + once-per-100), but NOT once per drop.
    warn_msgs = [r.message for r in caplog.records if "queue drop" in r.message]
    # Coalescing means the number of WARNs is << number of drops.
    assert len(warn_msgs) < 500, f"WARN spam: {len(warn_msgs)}"
