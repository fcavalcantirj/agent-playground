"""Phase 22b-04 Task 1 — D-11 lifespan re-attach + missing-container graceful degrade.

Two integration tests:

1. ``test_lifespan_reattach_spawns_watcher_for_live_container`` — seeds
   agent_containers(container_status='running') with a REAL live alpine
   container; enters the FastAPI lifespan; asserts ``app.state.log_watchers``
   contains the row id within ~1s of startup. Then removes the container
   externally to verify the watcher self-exits cleanly when the lifespan
   shutdown drain fires (spike-03 teardown applies in the reattach path too).

2. ``test_lifespan_reattach_marks_stopped_when_container_missing`` — seeds a
   running row pointing at a fabricated container_id that does NOT exist in
   docker; lifespan must call ``mark_agent_container_stopped`` and SKIP the
   spawn (Claude's Discretion in 22b-CONTEXT.md: "mark stopped + skip").

Both tests run against real Docker daemon + real Postgres via testcontainers
(Golden Rule 1 — no mocks, no stubs).

Marked ``api_integration`` because:
  1. Requires live Docker daemon
  2. Requires real Postgres + ``agent_events`` table from Plan 22b-02
"""
from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

# Phase 22c-06: ANONYMOUS_USER_ID constant deleted. Use a deterministic
# local seed UUID for DB-layer fixtures that don't exercise the HTTP auth
# surface (this file seeds rows directly via asyncpg to exercise the
# lifespan re-attach path).
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000042")

pytestmark = pytest.mark.api_integration


@pytest_asyncio.fixture
async def seed_running_container_with_live_docker(
    db_pool, running_alpine_container
) -> tuple[UUID, str]:
    """Insert agent_instances + agent_containers row tied to a REAL live
    alpine container; return (container_row_id, docker_container_id).

    The container runs `sleep 30` so it survives the test body. Test cleanup
    relies on ``running_alpine_container`` factory's auto-removal.
    """
    container = running_alpine_container(["sh", "-c", "echo ready; sleep 30"])
    instance_id = uuid4()
    row_id = uuid4()
    instance_name = f"reattach-test-{instance_id.hex[:8]}"
    async with db_pool.acquire() as conn:
        # Phase 22c-06: seed FK target (migration 006 purged ANONYMOUS row).
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1, 'lifespan-reattach-test-owner')
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
            row_id,
            instance_id,
            TEST_USER_ID,
            container.id,
        )
    return row_id, container.id


@pytest_asyncio.fixture
async def seed_running_row_with_dead_container(db_pool) -> UUID:
    """Insert a row whose container_id refers to a container that does not
    (and never did) exist in Docker. Returns the container_row_id.
    """
    instance_id = uuid4()
    row_id = uuid4()
    instance_name = f"reattach-dead-{instance_id.hex[:8]}"
    fake_container_id = "deadbeef" * 8  # 64 hex — looks plausible, never existed
    async with db_pool.acquire() as conn:
        # Phase 22c-06: seed FK target (migration 006 purged ANONYMOUS row).
        await conn.execute(
            """
            INSERT INTO users (id, display_name)
            VALUES ($1, 'lifespan-reattach-test-owner')
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
            row_id,
            instance_id,
            TEST_USER_ID,
            fake_container_id,
        )
    return row_id


def _isolated_recipes_dir(tmp_path) -> str:
    """Copy only `hermes.yaml` into a tmp dir so the recipes loader doesn't
    trip over the pre-existing openclaw.yaml duplicate-key bug (DI-01,
    documented in 22b-01-SUMMARY.md). Tests in this file only need 'hermes'
    to exist in app.state.recipes for the re-attach to resolve recipe_name.
    """
    api_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repo_root = os.path.dirname(api_server_dir)
    src = os.path.join(repo_root, "recipes", "hermes.yaml")
    dst = tmp_path / "hermes.yaml"
    dst.write_text(open(src).read())
    return str(tmp_path)


@pytest.mark.asyncio
async def test_lifespan_reattach_spawns_watcher_for_live_container(
    seed_running_container_with_live_docker, db_pool, migrated_pg, monkeypatch, tmp_path
):
    row_id, docker_id = seed_running_container_with_live_docker

    # Wire env so create_app() resolves the same testcontainers DSN.
    from tests.conftest import _normalize_testcontainers_dsn

    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("AP_RECIPES_DIR", _isolated_recipes_dir(tmp_path))

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Lifespan re-attach is a fire-and-forget create_task — give it
        # a moment to run + register itself.
        for _ in range(30):
            if row_id in app.state.log_watchers:
                break
            await asyncio.sleep(0.1)
        assert row_id in app.state.log_watchers, (
            f"lifespan failed to re-attach watcher for {row_id} within 3s; "
            f"current watchers: {list(app.state.log_watchers.keys())}"
        )
        # Stop the container externally — the watcher should observe iterator
        # end (spike-03 PASS) and the lifespan shutdown drain should reap it.
        import docker as _docker

        _client = _docker.from_env()
        try:
            _client.containers.get(docker_id).remove(force=True)
        finally:
            _client.close()
    # After lifespan shutdown, registry must be empty.
    assert app.state.log_watchers == {}, (
        f"lifespan shutdown did not drain watchers; remaining: "
        f"{list(app.state.log_watchers.keys())}"
    )


@pytest.mark.asyncio
async def test_lifespan_reattach_marks_stopped_when_container_missing(
    seed_running_row_with_dead_container, db_pool, migrated_pg, monkeypatch, tmp_path
):
    row_id = seed_running_row_with_dead_container

    from tests.conftest import _normalize_testcontainers_dsn

    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("AP_RECIPES_DIR", _isolated_recipes_dir(tmp_path))

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Allow re-attach pass to complete.
        await asyncio.sleep(1.5)
        # No watcher should have been spawned for the dead-container row.
        assert row_id not in app.state.log_watchers, (
            f"lifespan spawned watcher for missing-container row {row_id}; "
            f"watchers: {list(app.state.log_watchers.keys())}"
        )
    # Verify the row was marked stopped/start_failed/crashed by the
    # graceful-degrade path.
    async with db_pool.acquire() as conn:
        status = await conn.fetchval(
            "SELECT container_status FROM agent_containers WHERE id=$1", row_id
        )
    assert status in ("stopped", "start_failed", "failed", "crashed"), (
        f"expected non-running status after re-attach degrade, got {status!r}"
    )
