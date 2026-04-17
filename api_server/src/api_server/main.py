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
from .routes import agents as agents_route
from .routes import health
from .routes import recipes as recipes_route
from .routes import runs as runs_route
from .routes import schemas as schemas_route
from .services.recipes_loader import load_all_recipes


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
    try:
        yield
    finally:
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
    return app


app = create_app()
