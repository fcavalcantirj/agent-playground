"""FastAPI application factory.

Mounts:

- Async lifespan that owns the asyncpg pool + the process-wide
  ``app.state.run_semaphore`` + per-image-tag lock dict + fresh ``recipes``
  dict (Plan 19-03 populates the recipes dict at startup; Plan 19-04 uses
  the semaphore + locks inside the runner bridge).
- Middleware stack in declaration-ordered shape — read bottom-up to get
  the request-in traversal order: ``CorrelationIdMiddleware`` →
  ``AccessLogMiddleware`` → ``RateLimitMiddleware`` →
  ``IdempotencyMiddleware`` → routers. Declaration order here is
  *outermost last*, which is how ``FastAPI.add_middleware`` stacks.
- Env-gated OpenAPI UIs per CONTEXT.md D-10 (``/docs`` and ``/redoc``
  exist only when ``AP_ENV=dev``; ``/openapi.json`` always exists so the
  Phase 20 frontend type-gen works against prod).

Plans 19-03 and 19-04 include their own routers under ``/v1`` — they are
NOT included here. Only the always-present operational router (``health``)
lives at the root.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .config import get_settings
from .db import close_pool, create_pool
from .log import configure_logging
from .middleware.correlation_id import CorrelationIdMiddleware
from .middleware.idempotency import IdempotencyMiddleware
from .middleware.log_redact import AccessLogMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .routes import agent_lifecycle as agent_lifecycle_route
from .routes import agents as agents_route
from .routes import health
from .routes import recipes as recipes_route
from .routes import runs as runs_route
from .routes import schemas as schemas_route
from .services.recipes_loader import load_all_recipes

# Phase 22b-04: dedicated logger for lifespan-time re-attach + drain telemetry.
# Reuses the same handler chain configure_logging set up — no separate config.
_log = logging.getLogger("api_server.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Boot + teardown the process-wide resources Plans 03/04/05 rely on.

    On startup:

    - ``app.state.db`` — asyncpg pool (verified via ``SELECT 1``)
    - ``app.state.recipes`` — empty dict; Plan 19-03 loads ``recipes/*.yaml``
    - ``app.state.image_tag_locks`` — per-image-tag ``asyncio.Lock`` dict
      for ``ensure_image`` serialization (Plan 19-04 populates)
    - ``app.state.locks_mutex`` — guards mutations to ``image_tag_locks``
    - ``app.state.run_semaphore`` — global concurrency cap on ``run_cell``

    On shutdown:

    - Closes the asyncpg pool.
    """
    settings = app.state.settings
    app.state.db = await create_pool(settings.database_url)
    # Plan 19-03: populate the recipes dict from `recipes/*.yaml` at
    # startup. Fail-loud on malformed / duplicate-named recipes so the
    # app refuses to boot with a broken catalog rather than serving a
    # half-loaded `/v1/recipes`.
    app.state.recipes = load_all_recipes(settings.recipes_dir)
    app.state.image_tag_locks = {}   # Plan 19-04 runner_bridge reads/writes
    app.state.locks_mutex = asyncio.Lock()
    app.state.run_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
    # Phase 22b-04: event-watcher registry + signal + per-agent poll lock.
    # locks_mutex (above) guards setdefault races on event_poll_locks
    # (watcher_service._get_poll_lock acquires it before the dict mutation).
    # log_watchers values are (asyncio.Task, asyncio.Event) tuples — keyed
    # on container_row_id (the agent_containers.id PK).
    app.state.log_watchers = {}            # container_row_id -> (Task, Event)
    app.state.event_poll_signals = {}      # agent_container_id -> asyncio.Event
    app.state.event_poll_locks = {}        # agent_container_id -> asyncio.Lock

    # Phase 22b-04 D-11: re-attach log-watchers for containers that survived
    # an API restart. Rows whose container_id no longer exists in Docker are
    # marked stopped + skipped (Claude's Discretion in 22b-CONTEXT.md).
    # Failure of this loop is non-fatal for app startup — events are
    # observability, not correctness.
    try:
        import docker as _docker

        from .services.run_store import mark_agent_container_stopped
        from .services.watcher_service import run_watcher

        _dclient = _docker.from_env()
        try:
            async with app.state.db.acquire() as _conn:
                _rows = await _conn.fetch(
                    "SELECT id, agent_instance_id, recipe_name, container_id, "
                    "channel_type "
                    "FROM agent_containers WHERE container_status='running'"
                )
            for _row in _rows:
                _cid = _row["container_id"]
                _rid = _row["id"]
                # Cheap existence probe — inspect is O(1); 404 = container gone.
                try:
                    _dclient.containers.get(_cid)
                except _docker.errors.NotFound:
                    _log.info(
                        "phase22b.reattach.container_missing",
                        extra={
                            "container_row_id": str(_rid),
                            "container_id": _cid,
                        },
                    )
                    async with app.state.db.acquire() as _conn:
                        await mark_agent_container_stopped(
                            _conn,
                            _rid,
                            last_error="container_missing_at_reattach",
                        )
                    continue
                except Exception:
                    _log.exception(
                        "phase22b.reattach.inspect_failed",
                        extra={"container_row_id": str(_rid)},
                    )
                    continue
                _recipe = app.state.recipes.get(_row["recipe_name"])
                if _recipe is None:
                    _log.warning(
                        "phase22b.reattach.recipe_missing",
                        extra={"recipe_name": _row["recipe_name"]},
                    )
                    continue
                # Spawn the watcher fire-and-forget. agent_id slot is the
                # agent_containers row PK (event_store keys events by it).
                # chat_id_hint=None on re-attach — sources that need it
                # degrade gracefully per Plan 22b-03 contract.
                asyncio.create_task(run_watcher(
                    app.state,
                    container_row_id=_rid,
                    container_id=_cid,
                    agent_id=_rid,
                    recipe=_recipe,
                    channel=_row["channel_type"],
                    chat_id_hint=None,
                ))
        finally:
            try:
                _dclient.close()
            except Exception:
                pass
    except Exception:
        _log.exception("phase22b.reattach.init_failed")
    try:
        yield
    finally:
        # Phase 22b-04: drain all watchers before closing the DB pool.
        # 2s aggregate budget; tasks still running after budget are cancelled.
        # Spike-03 has never observed teardown >2s; the cancel branch is the
        # documented fallback (T-22b-04-05 mitigation).
        try:
            if getattr(app.state, "log_watchers", None):
                for _task, _stop in list(app.state.log_watchers.values()):
                    _stop.set()
                _tasks = [
                    t for t, _ in list(app.state.log_watchers.values())
                    if not t.done()
                ]
                if _tasks:
                    _, _pending = await asyncio.wait(_tasks, timeout=2.0)
                    for _p in _pending:
                        _p.cancel()
        except Exception:
            _log.exception("phase22b.shutdown.drain_failed")
        await close_pool(app.state.db)


def create_app() -> FastAPI:
    """Build a fresh FastAPI app with settings loaded from the current env.

    Settings are read at ``create_app`` time (not inside ``lifespan``) so
    tests can ``monkeypatch.setenv`` before calling and have the change
    observed by the factory.
    """
    settings = get_settings()
    configure_logging(settings.env)
    app = FastAPI(
        title="Agent Playground API",
        version="0.1.0",
        openapi_url="/openapi.json",                            # always public (frontend type-gen)
        docs_url="/docs" if settings.env == "dev" else None,    # D-10
        redoc_url="/redoc" if settings.env == "dev" else None,  # D-10
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Middleware order: outermost declared last. Effective order request-in:
    # correlation-id -> access-log -> rate-limit -> idempotency -> router.
    # (AccessLogMiddleware wraps the request id so access log records
    # reflect the minted X-Request-Id — Plan 19-06 SUMMARY guidance.)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(health.router)
    # Plan 19-03: read-only recipe + schema + lint routes under /v1.
    app.include_router(schemas_route.router, prefix="/v1", tags=["schemas"])
    app.include_router(recipes_route.router, prefix="/v1", tags=["recipes"])
    # Plan 19-04: POST /v1/runs + GET /v1/runs/{id} — the load-bearing
    # endpoint that wraps tools/run_recipe.py::run_cell via the
    # per-image-tag Lock + global Semaphore in app.state.
    app.include_router(runs_route.router, prefix="/v1", tags=["runs"])
    # Phase 20: GET /v1/agents — list user's deployed agents.
    app.include_router(agents_route.router, prefix="/v1", tags=["agents"])
    # Phase 22-05: persistent-mode agent lifecycle (start / stop / status /
    # channels pair). Shares the /v1/agents URL namespace with
    # ``agents_route`` (GET list) — distinct paths so FastAPI's router
    # matches unambiguously.
    app.include_router(
        agent_lifecycle_route.router, prefix="/v1", tags=["agents"]
    )
    return app


app = create_app()
