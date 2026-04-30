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

import httpx
import redis.asyncio as redis_async
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware as StarletteSessionMiddleware

from .auth.oauth import get_oauth
from .config import get_settings
from .db import close_pool, create_pool
from .log import configure_logging
from .middleware.correlation_id import CorrelationIdMiddleware
from .middleware.idempotency import IdempotencyMiddleware
from .middleware.log_redact import AccessLogMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.session import SessionMiddleware as ApSessionMiddleware
from .routes import agent_events as agent_events_route
from .routes import agent_lifecycle as agent_lifecycle_route
from .routes import agent_messages as agent_messages_route
from .routes import agents as agents_route
from .routes import auth as auth_route
from .routes import health
from .routes import recipes as recipes_route
from .routes import runs as runs_route
from .routes import schemas as schemas_route
from .routes import users as users_route
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

    # ====================================================================
    # Phase 22c.3-09 — inapp chat channel: Redis + httpx + 3 background tasks
    # ====================================================================
    #
    # Ordering rationale (must come BEFORE the 22b watcher re-attach
    # below so the per-test lifespan exit time stays bounded — the
    # watcher block performs Docker calls that can hang on a dead
    # daemon, and a fail-loud Redis ping should NOT be gated on Docker
    # responding):
    #
    #   1. Redis client — fail loud at boot if PING fails (D-15/D-16:
    #      SSE + outbox depend on Redis; silent degradation would let
    #      the inapp channel start in a broken state).
    #   2. Shared httpx.AsyncClient (D-40 — 600s read timeout per
    #      single bot call; 5s connect; max_connections=50).
    #   3. Restart sweep (D-31) — re-queue rows stuck in 'forwarded'
    #      past 15 minutes BEFORE the dispatcher pump starts, so the
    #      first dispatcher tick has a clean state machine.
    #   4. Background tasks: dispatcher_loop (250ms), reaper_loop (15s),
    #      outbox_pump_loop (100ms). Each is named so operators can
    #      grep ``asyncio.all_tasks()`` output.

    # 1. Redis client — fail-loud at boot.
    app.state.redis = redis_async.from_url(
        settings.redis_url,
        decode_responses=False,        # outbox publishes str; SSE handler decodes
        max_connections=20,
    )
    try:
        await app.state.redis.ping()
    except Exception:
        _log.exception("phase22c3.redis.ping_failed_boot")
        # Close the half-open connection pool so the failed boot does
        # not leak file descriptors / sockets to the unreachable host.
        try:
            await app.state.redis.aclose()
        except Exception:
            pass
        raise   # boot fails — Redis is required for inapp channel

    # 2. Shared httpx.AsyncClient for the inapp dispatcher (D-40).
    app.state.bot_http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(600.0, connect=5.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )

    # 3. Restart sweep (D-31) — re-queue rows stuck in 'forwarded' past
    #    15 minutes. Runs BEFORE the dispatcher loop is created so the
    #    first dispatcher tick has a clean state machine to consume
    #    from. Failure here is non-fatal: a stuck row is worse than a
    #    sweep, but the reaper (Plan 22c.3-06) will catch them on its
    #    next 15s tick.
    try:
        from .services.inapp_messages_store import restart_sweep

        async with app.state.db.acquire() as _conn:
            _swept = await restart_sweep(_conn, threshold_minutes=15)
            _log.info(
                "phase22c3.restart_sweep",
                extra={"swept": _swept},
            )
    except Exception:
        _log.exception("phase22c3.restart_sweep_failed_nonfatal")

    # 4. Background tasks — cancellable via inapp_stop event.
    from .services.inapp_dispatcher import dispatcher_loop
    from .services.inapp_outbox import outbox_pump_loop
    from .services.inapp_reaper import reaper_loop

    app.state.inapp_stop = asyncio.Event()
    # Wire the stop_event onto state so dispatcher_loop (which takes
    # only ``state``) can read it via ``state.inapp_stop`` per the
    # source-of-truth ``getattr(state, "inapp_stop", ...)`` lookup.
    app.state.inapp_tasks = [
        asyncio.create_task(
            dispatcher_loop(app.state),
            name="inapp_dispatcher",
        ),
        asyncio.create_task(
            reaper_loop(app.state, app.state.inapp_stop),
            name="inapp_reaper",
        ),
        asyncio.create_task(
            outbox_pump_loop(app.state, app.state.inapp_stop),
            name="inapp_outbox",
        ),
    ]
    _log.info(
        "phase22c3.lifespan.inapp_tasks_started",
        extra={"task_names": [t.get_name() for t in app.state.inapp_tasks]},
    )

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
        # Phase 22c.3-09 — drain inapp tasks first (they may publish to
        # redis during teardown; flush them before closing the redis
        # client). 5s aggregate budget per the must_haves.truths.
        try:
            if getattr(app.state, "inapp_stop", None) is not None:
                app.state.inapp_stop.set()
            inapp_tasks = getattr(app.state, "inapp_tasks", []) or []
            if inapp_tasks:
                _done, _pending = await asyncio.wait(
                    inapp_tasks, timeout=5.0,
                )
                for _p in _pending:
                    _p.cancel()
                # Best-effort wait so cancelled tasks finish cleanly
                # (each loop awaits CancelledError → returns).
                if _pending:
                    try:
                        await asyncio.wait(_pending, timeout=1.0)
                    except Exception:
                        pass
                _log.info(
                    "phase22c3.lifespan.inapp_tasks_drained",
                    extra={
                        "done": len(_done),
                        "cancelled": len(_pending),
                    },
                )
        except Exception:
            _log.exception("phase22c3.lifespan.inapp_drain_failed")

        # Phase 22c.3-09 — close the shared httpx + redis clients AFTER
        # the inapp tasks drain so a still-running publish or http call
        # doesn't fault on a closed transport.
        try:
            if getattr(app.state, "bot_http_client", None) is not None:
                await app.state.bot_http_client.aclose()
        except Exception:
            _log.exception("phase22c3.lifespan.http_client_close_failed")
        try:
            if getattr(app.state, "redis", None) is not None:
                await app.state.redis.aclose()
        except Exception:
            _log.exception("phase22c3.lifespan.redis_close_failed")

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

    # Phase 22c — per-worker throttle cache for sessions.last_seen_at UPDATEs
    # (D-22c-MIG-05). SessionMiddleware lazy-inits this on first request, but
    # initializing here makes the test-harness path simpler (conftest can rely
    # on the attribute existing without triggering the middleware's setdefault).
    app.state.session_last_seen = {}

    # Phase 22c — eagerly construct the OAuth registry so prod boots fail loud
    # when AP_OAUTH_* env vars are missing. Dev uses placeholders (see
    # auth/oauth.py::_resolve_or_fail). Called BEFORE add_middleware so the
    # fail-loud RuntimeError fires during create_app, not on first request.
    get_oauth(settings)

    # Middleware order: outermost declared last.
    # Effective request-in order:
    #   CorrelationId -> AccessLog -> StarletteSession -> OurSession
    #     -> RateLimit -> Idempotency -> route.
    # (Plan 22c-04 ships OurSession; plan 22c-03 ships AP_OAUTH_STATE_SECRET
    # config. Starlette's built-in SessionMiddleware stores authlib's CSRF
    # state nonce in the ap_oauth_state cookie; our ApSessionMiddleware
    # resolves request.state.user_id from the ap_session cookie via PG.)
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ApSessionMiddleware)  # ap_session cookie -> request.state.user_id
    app.add_middleware(
        StarletteSessionMiddleware,          # authlib CSRF state (ap_oauth_state cookie)
        secret_key=(
            settings.oauth_state_secret
            or "dev-oauth-state-key-not-for-prod-0000000000000000"
        ),
        session_cookie="ap_oauth_state",
        max_age=600,
        same_site="lax",
        https_only=(settings.env == "prod"),
        path="/",
    )
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
    # Phase 22b-05: GET /v1/agents/:id/events — long-poll event stream
    # consumed by the SC-03 Gate B test harness (Plan 22b-06).
    app.include_router(
        agent_events_route.router, prefix="/v1", tags=["agents"]
    )
    # Phase 22c.3-08: in-app chat channel — POST /v1/agents/:id/messages
    # (D-07 fast-ack), GET /v1/agents/:id/messages/stream (D-01 SSE
    # replay + live), DELETE /v1/agents/:id/messages (D-43 history
    # clear). The lifespan attach for the dispatcher / reaper / outbox
    # background tasks lives in Plan 22c.3-09.
    app.include_router(
        agent_messages_route.router, prefix="/v1", tags=["agents"]
    )
    # Phase 22b-08: dev-only POST /v1/agents/:id/events/inject-test-event.
    # Conditional include keeps the route INVISIBLE in prod (FastAPI 404
    # for any path not registered). Mirrors the openapi.json/docs gating
    # at line 197-199 (D-10). Defense-in-depth gate #1 for T-22b-08-01.
    if app.state.settings.env != "prod":
        app.include_router(
            agent_events_route.inject_router,
            prefix="/v1",
            tags=["agents", "dev-only"],
        )
        _log.info(
            "phase22b.inject_test_event.route_registered",
            extra={"env": app.state.settings.env},
        )
    # Phase 22c: OAuth authorize/callback/logout + session user-me.
    # auth_route ships 5 endpoints (GET /auth/{google,github}[/callback],
    # POST /auth/logout); users_route ships GET /users/me. Both require
    # the middleware stack above (StarletteSessionMiddleware for authlib
    # state + ApSessionMiddleware for request.state.user_id resolution).
    app.include_router(auth_route.router, prefix="/v1", tags=["auth"])
    app.include_router(users_route.router, prefix="/v1", tags=["users"])
    return app


app = create_app()
