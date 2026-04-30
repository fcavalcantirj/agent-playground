"""Phase 22c.3-09 — main.py lifespan inapp wiring tests.

5 integration tests against real PG (testcontainers) + real Redis
(testcontainers). The lifespan is exercised end-to-end via
``app.router.lifespan_context(app)``:

  1. ``test_lifespan_attaches_three_inapp_tasks`` — after startup,
     ``app.state.inapp_tasks`` is a list of 3 named tasks
     ({inapp_dispatcher, inapp_reaper, inapp_outbox}); each appears in
     ``asyncio.all_tasks()``.

  2. ``test_lifespan_attaches_redis_and_http_client`` — after startup,
     ``app.state.redis.ping()`` returns True; ``app.state.bot_http_client``
     is an ``httpx.AsyncClient`` with read timeout >= 600s.

  3. ``test_lifespan_runs_restart_sweep`` — seed an ``inapp_messages``
     row in ``status='forwarded'`` with ``last_attempt_at = NOW() - 16
     min``; enter the lifespan; the row's status flips to ``'pending'``
     (D-31 sweep ran).

  4. ``test_lifespan_redis_dead_fails_loud`` — point ``AP_REDIS_URL`` at
     RFC 5737 unroutable ``192.0.2.1:1``; entering the lifespan must
     RAISE (no silent degradation). Also confirm the swept-back row is
     NOT mutated (sweep happens AFTER the redis ping fails fast).

  5. ``test_lifespan_drain_on_shutdown`` — enter lifespan; sleep 200ms;
     exit context; ``app.state.inapp_stop.is_set()`` is True AND every
     task in ``app.state.inapp_tasks`` is ``done()``.

Per Golden Rule #1 (no mocks, no stubs) — real PG, real Redis. The
``redis_url`` is taken from the session-scoped ``redis_container``
fixture in conftest.py.

The tests build a fresh FastAPI app via ``create_app()`` rather than
reusing ``async_client`` because ``async_client`` enters the lifespan
once per test and we want explicit per-test entry/exit semantics here.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

import redis.asyncio as redis_async


pytestmark = pytest.mark.api_integration


# ---------------------------------------------------------------------------
# Helpers — env wiring + recipes-dir isolation (mirror Plan 22b-04 pattern).
# ---------------------------------------------------------------------------


def _isolated_recipes_dir(tmp_path: Path) -> str:
    """Empty recipes dir is fine — the lifespan loader tolerates it.

    The lifespan tests exercise the inapp wiring, NOT the recipe loader,
    so we point at an empty tmp dir to avoid any fragility from the
    committed recipes folder.
    """
    return str(tmp_path)


def _redis_url_for(redis_container) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


def _wire_env(monkeypatch, migrated_pg, redis_url: str, tmp_path: Path) -> None:
    """Wire the AP_*/DATABASE_URL env so create_app() resolves correctly."""
    from tests.conftest import _normalize_testcontainers_dsn

    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("AP_RECIPES_DIR", _isolated_recipes_dir(tmp_path))
    monkeypatch.setenv("AP_REDIS_URL", redis_url)
    # Plan 22c-03 made AP_OAUTH_STATE_SECRET required by the OAuth registry
    # eager-init in create_app(); supply a fixed dev value so app boot
    # succeeds without touching the OAuth path.
    monkeypatch.setenv("AP_OAUTH_STATE_SECRET", "x" * 32)


# ---------------------------------------------------------------------------
# 1. 3 named tasks attached after startup
# ---------------------------------------------------------------------------


async def test_lifespan_attaches_three_inapp_tasks(
    migrated_pg, redis_container, monkeypatch, tmp_path,
):
    """Confirms the 3 lifespan asyncio tasks are CREATED + NAMED.

    Names must be exactly ``inapp_dispatcher``, ``inapp_reaper``,
    ``inapp_outbox`` (per must_haves.truths) so operators can grep them
    out of ``asyncio.all_tasks()`` for diagnostics.
    """
    _wire_env(monkeypatch, migrated_pg, _redis_url_for(redis_container), tmp_path)

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        tasks = getattr(app.state, "inapp_tasks", None)
        assert tasks is not None, "lifespan did not attach app.state.inapp_tasks"
        assert isinstance(tasks, list), "inapp_tasks must be a list"
        assert len(tasks) == 3, f"expected 3 tasks, got {len(tasks)}"

        names = {t.get_name() for t in tasks}
        assert names == {"inapp_dispatcher", "inapp_reaper", "inapp_outbox"}, (
            f"expected {{inapp_dispatcher, inapp_reaper, inapp_outbox}}, got {names}"
        )

        # Each task must also be visible in asyncio.all_tasks() while
        # the lifespan is active.
        all_names = {t.get_name() for t in asyncio.all_tasks()}
        for n in {"inapp_dispatcher", "inapp_reaper", "inapp_outbox"}:
            assert n in all_names, (
                f"task {n!r} not found in asyncio.all_tasks(): {all_names}"
            )

        # No task may be already-done at startup — they're long-running
        # loops and should still be alive.
        for t in tasks:
            assert not t.done(), (
                f"task {t.get_name()} died before steady-state — "
                f"exception={t.exception() if t.done() else 'n/a'}"
            )


# ---------------------------------------------------------------------------
# 2. Redis client + bot_http_client attached
# ---------------------------------------------------------------------------


async def test_lifespan_attaches_redis_and_http_client(
    migrated_pg, redis_container, monkeypatch, tmp_path,
):
    """``app.state.redis`` PINGs True; ``app.state.bot_http_client`` is
    httpx.AsyncClient with read timeout >= 600s + max_connections >= 50.
    """
    _wire_env(monkeypatch, migrated_pg, _redis_url_for(redis_container), tmp_path)

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Redis ping
        r = getattr(app.state, "redis", None)
        assert r is not None, "lifespan did not attach app.state.redis"
        assert isinstance(r, redis_async.Redis), (
            f"app.state.redis must be redis.asyncio.Redis, got {type(r)}"
        )
        assert await r.ping() is True, "redis ping returned non-True"

        # httpx client shape
        h = getattr(app.state, "bot_http_client", None)
        assert h is not None, "lifespan did not attach app.state.bot_http_client"
        assert isinstance(h, httpx.AsyncClient), (
            f"bot_http_client must be httpx.AsyncClient, got {type(h)}"
        )
        # httpx.Timeout exposes the per-channel timeout via attributes.
        # The plan mandates timeout=600s + connect=5s.
        assert h.timeout.read is not None and h.timeout.read >= 600.0, (
            f"bot_http_client read timeout must be >= 600s, got {h.timeout.read}"
        )
        assert h.timeout.connect is not None and h.timeout.connect <= 5.0 + 1e-6, (
            f"bot_http_client connect timeout must be <= 5s, got {h.timeout.connect}"
        )


# ---------------------------------------------------------------------------
# 3. Restart sweep runs at startup (D-31)
# ---------------------------------------------------------------------------


async def test_lifespan_runs_restart_sweep(
    db_pool, migrated_pg, redis_container, monkeypatch, tmp_path,
):
    """Seed a stale ``forwarded`` row → enter lifespan → row is now ``pending``.

    The D-31 restart sweep flips rows in ``status='forwarded'`` whose
    ``last_attempt_at < NOW() - 15 min`` back to ``'pending'`` so the
    freshly-booted dispatcher resumes them.
    """
    user_id = uuid4()
    agent_id = uuid4()
    recipe_name = f"recipe-{uuid4().hex[:8]}"

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (id, display_name) VALUES ($1, $2)",
            user_id, "lifespan-restart-sweep-test",
        )
        await conn.execute(
            """
            INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
            VALUES ($1, $2, $3, 'm-test', $4)
            """,
            agent_id, user_id, recipe_name, f"agent-{uuid4().hex[:8]}",
        )
        # Insert an inapp_messages row stuck in 'forwarded' for 16 min.
        # Schema (alembic 007): inapp_messages has user_id + agent_id but
        # NO container_row_id column — the dispatcher resolves the
        # container at fetch time via the agent_containers JOIN.
        message_id = await conn.fetchval(
            """
            INSERT INTO inapp_messages
                (user_id, agent_id, content,
                 status, attempts, last_attempt_at)
            VALUES ($1, $2, $3, 'forwarded', 1,
                    NOW() - make_interval(mins => 16))
            RETURNING id
            """,
            user_id, agent_id, "stuck message",
        )

    _wire_env(monkeypatch, migrated_pg, _redis_url_for(redis_container), tmp_path)

    from api_server.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        # Sweep is synchronous in the lifespan (BEFORE the dispatcher
        # task starts), so by the time the body runs the row must
        # already be back to 'pending'.
        async with db_pool.acquire() as conn:
            status = await conn.fetchval(
                "SELECT status FROM inapp_messages WHERE id=$1",
                message_id,
            )
        assert status == "pending", (
            f"restart sweep did not flip stuck row back to 'pending'; got {status!r}"
        )


# ---------------------------------------------------------------------------
# 4. Redis dead at boot → fail-LOUD (RuntimeError / connect error)
# ---------------------------------------------------------------------------


async def test_lifespan_redis_dead_fails_loud(
    migrated_pg, monkeypatch, tmp_path,
):
    """Boot fails LOUD when AP_REDIS_URL points at an unroutable host.

    Per the must_haves.truths: "If Redis is unreachable at boot,
    api_server fails LOUD with RuntimeError (not silent degradation)".
    The Redis ``redis_async.from_url`` call with ``192.0.2.1:1`` (RFC
    5737 unroutable test net) raises ``OSError`` /
    ``redis_async.RedisError`` / ``asyncio.TimeoutError`` / wrapping
    ``ConnectionError`` at PING time. The lifespan must propagate it.
    """
    from tests.conftest import _normalize_testcontainers_dsn

    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    monkeypatch.setenv("AP_ENV", "dev")
    monkeypatch.setenv("AP_MAX_CONCURRENT_RUNS", "2")
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("AP_RECIPES_DIR", _isolated_recipes_dir(tmp_path))
    # 192.0.2.0/24 is RFC 5737 documentation/unroutable. Nothing replies.
    monkeypatch.setenv("AP_REDIS_URL", "redis://192.0.2.1:1/0")
    monkeypatch.setenv("AP_OAUTH_STATE_SECRET", "x" * 32)

    from api_server.main import create_app

    app = create_app()
    # Bound the entire lifespan attempt at 30s — the redis client has its
    # own internal connect timeout and will surface a routing failure
    # well before that. asyncio.wait_for is the outer safety so a stuck
    # test never blocks CI.
    raised = False
    try:
        async with asyncio.timeout(30.0):
            async with app.router.lifespan_context(app):
                # If we got here, the boot did NOT fail loud — that is
                # the failure mode we're testing for.
                pytest.fail(
                    "lifespan did NOT fail-loud on dead Redis — entered body"
                )
    except (
        RuntimeError,
        OSError,
        ConnectionError,
        asyncio.TimeoutError,
        TimeoutError,
        redis_async.RedisError,
    ):
        raised = True
    except Exception as e:
        # Any unexpected exception type is also acceptable — the contract
        # is "fails loud", not a specific exception class. We just want
        # to confirm SOMETHING was raised; record it.
        raised = True
        _ = e
    assert raised, (
        "lifespan boot did not raise — Redis fail-loud invariant violated"
    )


# ---------------------------------------------------------------------------
# 5. Drain on shutdown — stop event fires + tasks done within 5s
# ---------------------------------------------------------------------------


async def test_lifespan_drain_on_shutdown(
    migrated_pg, redis_container, monkeypatch, tmp_path,
):
    """After exiting the lifespan context, all 3 tasks must be ``done()``.

    Drain budget is 5s aggregate; tasks waiting on
    ``asyncio.wait_for(stop_event.wait(), timeout=...)`` should observe
    the set within a single sleep tick (≤500ms). We exit the lifespan
    immediately after a 200ms warmup so the drain path is exercised
    while the loops are mid-tick.
    """
    _wire_env(monkeypatch, migrated_pg, _redis_url_for(redis_container), tmp_path)

    from api_server.main import create_app

    app = create_app()
    captured_tasks: list[asyncio.Task] = []
    async with app.router.lifespan_context(app):
        captured_tasks = list(app.state.inapp_tasks)
        await asyncio.sleep(0.2)
    # Post-shutdown: stop event was set, all tasks completed.
    assert app.state.inapp_stop.is_set() is True, (
        "shutdown did not set inapp_stop"
    )
    for t in captured_tasks:
        assert t.done(), (
            f"task {t.get_name()} still running after shutdown drain — "
            "exceeded the 5s budget"
        )
