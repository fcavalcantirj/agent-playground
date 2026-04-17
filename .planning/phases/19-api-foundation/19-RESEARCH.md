# Phase 19: API Foundation (FastAPI) - Research

**Researched:** 2026-04-16
**Domain:** Python async HTTP API foundation wrapping a sync recipe runner with full Postgres persistence, live Hetzner TLS deployment
**Confidence:** HIGH on the framework + driver + deploy decisions; MEDIUM on rate-limiter SQL + idempotency concurrency corners; LOW on ruamel.yaml thread-safety exact failure modes (documented ticket exists but narrow repro)

## Summary

Phase 19 builds `api_server/` — a FastAPI service that wraps `tools/run_recipe.py` as the public API surface. The CONTEXT.md locks the ten big shape decisions (Postgres from day 1, BYOK via `Authorization: Bearer`, sync-only `POST /v1/runs`, split `/healthz`+`/readyz`, Postgres rate limiter, full 5-table schema, ULID run_id, per-image-tag asyncio.Lock + global Semaphore, live Hetzner deploy with Caddy TLS, env-gated `/docs`). This research lands recommendations on the discretionary technical choices (driver, migration tool, ULID library, rate-limit algorithm, idempotency concurrency, test infra, correlation-id, structured logging, server topology).

**Primary recommendations** (each expanded below):
1. **Driver: `asyncpg` 0.31.0 + raw SQL.** 5x faster than psycopg3, lowest latency at the concurrency levels this phase will see. No ORM (per CLAUDE.md "No GORM" posture in Python).
2. **Migrations: Alembic 1.18.4 async template + SQLAlchemy 2.0 Core (metadata-only, no models).** Minimal weight, matches Postgres-from-day-1 discipline.
3. **ULID: `python-ulid` 3.1.0 (mdomke).** Actively maintained, Pydantic v2 support, `time.time_ns()` internally. Store as TEXT(26) for clarity; v0.2 migration path to UUIDv7 if desired.
4. **Rate limit: fixed-window-per-endpoint-bucket with `pg_advisory_xact_lock` + `INSERT ... ON CONFLICT DO UPDATE`.** Not true sliding window — explicit trade for SQL simplicity.
5. **Idempotency: `INSERT ... ON CONFLICT DO NOTHING` for key reservation + `pg_advisory_xact_lock(hashtext(key))` during the run to serialize duplicates.** Stripe-style.
6. **Log redaction: ASGI middleware that never logs request body + allowlists response headers.** No dependency on `asgi-correlation-id` for redaction; use it only for X-Request-Id propagation.
7. **Concurrency: `asyncio.to_thread()` (stdlib, Python 3.9+) wrapping `run_cell()`. Per-image-tag Lock via `collections.defaultdict` guarded by a single module-level `asyncio.Lock` on the dict itself. Global `asyncio.Semaphore(N)` from `AP_MAX_CONCURRENT_RUNS` env (default 2).**
8. **Testing: `testcontainers` 4.14.2 Postgres fixture, session-scoped, `TRUNCATE` between tests.** Docker integration test marker already exists in the runner's pytest conftest — extend the convention.
9. **Server: `uvicorn` 0.44.0 directly, NO gunicorn, 2 workers via `--workers 2`. Hetzner box is single-host shared with docker-for-recipes; more workers than cores = context-switch cost, and uvicorn natively supports workers now.**
10. **TLS: Caddy 2.x auto-HTTPS, 3-line Caddyfile.** Zero cert management.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Recipe validation + schema lint | FastAPI (sync endpoint) | `tools/run_recipe.py::lint_recipe` | Lint is fast, pure-Python, already extracted |
| Image build/pull + container run | asyncio thread pool offloading to runner | `tools/run_recipe.py::run_cell` (sync) | Runner is battle-tested; wrap don't rewrite |
| Idempotency key dedup | Postgres (`idempotency_keys` table + advisory lock) | FastAPI middleware (key parse) | State must survive API restart |
| Rate limiting | Postgres (`rate_limit_counters` + advisory lock) | FastAPI middleware (bucket key derivation) | No Redis in phase 19 per D-05 |
| BYOK key handling | FastAPI dependency (per-request, memory-only) | Runner via `--env-file` code path | Never persisted |
| Run persistence | Postgres (`runs`, `agent_instances`, `users`) | FastAPI (upsert logic) | Full relational model |
| TLS termination | Caddy | Hetzner box | Let Caddy handle ACME |
| Health + readiness | FastAPI routes | Docker daemon probe + asyncpg ping | `/healthz` must never touch deps |
| Docker daemon access | Shelled-out `docker` CLI via runner | Docker socket mount | Same path as `tools/run_recipe.py` |

**Note — misassignment risk:** The instinct is to put retries/back-pressure inside the handler. The correct answer is: the handler is a thin wrapper, `asyncio.Semaphore` is the back-pressure primitive, and the runner already handles its own timeouts via `--cidfile` + `docker kill`. Do NOT add FastAPI-level timeouts that can orphan containers — per CONTEXT.md D-03 "Clock-of-record: runner's `time.time()` at `run_cell` entry."

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | **0.136.0** | HTTP framework + OpenAPI auto-gen | De-facto Python HTTP API choice; OpenAPI auto-gen drives Phase 20 frontend client [VERIFIED: `pip3 index versions fastapi`] |
| uvicorn | **0.44.0** | ASGI server | FastAPI's reference server; native multi-worker support [VERIFIED: `pip3 index versions uvicorn`] |
| asyncpg | **0.31.0** | Async Postgres driver | 5x faster than psycopg3 per official MagicStack benchmarks; lowest latency [VERIFIED: `pip3 index versions asyncpg`; CITED: https://github.com/MagicStack/asyncpg] |
| SQLAlchemy | **2.0.49** | Core (metadata + migration DDL only — NO ORM) | Needed by Alembic for autogenerate; Core gives us DDL expression w/o ORM overhead [VERIFIED: `pip3 index versions sqlalchemy`] |
| Alembic | **1.18.4** | Migration tool | Standard Python migration system; async template is first-class [VERIFIED: `pip3 index versions alembic`] |
| Pydantic | **v2 (≥2.11)** | Request/response validation | Bundled with FastAPI 0.136; required by FastAPI [VERIFIED: installed 2.11.7] |
| python-ulid | **3.1.0** | ULID generation | Actively maintained (mdomke), Pydantic v2 support, time.time_ns() internal [VERIFIED: `pip3 index versions python-ulid`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `structlog` | 25.5.0 | Structured JSON logging | All log output; JSONRenderer in prod, ConsoleRenderer in dev [VERIFIED: pip index] |
| `asgi-correlation-id` | 4.3.4 | X-Request-Id propagation middleware | Plugs into structlog via contextvars; auto-mints UUID if header absent [CITED: https://github.com/snok/asgi-correlation-id] |
| `testcontainers[postgres]` | 4.14.2 | Real Postgres in pytest | Session-scoped fixture; module-scoped truncate between tests [VERIFIED: pip index] |
| `pytest` | ≥8.0 | Test runner (already installed) | Existing runner test suite convention |
| `pytest-asyncio` | ≥0.23 | Async test support | Standard for FastAPI testing |
| `httpx` | latest | ASGI test client (bundled in FastAPI test utils) | `from fastapi.testclient import TestClient` |
| `jsonschema` | ≥4.23 | Already in pyproject.toml | Reused for `POST /v1/lint` |
| `ruamel.yaml` | ≥0.17.21 | Already in pyproject.toml | **Per-call `YAML()` in server paths, not the module singleton** — see Pitfall 3 |

### Alternatives Considered (with rejection rationale)
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncpg` | `psycopg3` + `psycopg_pool` | 5x slower on paper; friendlier API. **Rejected** because the synchronous `run_cell` already dominates request latency (docker runs are 10–200s); the driver only matters for idempotency/rate-limit middleware paths where asyncpg's speed keeps tail latency low [CITED: https://github.com/fastapi/fastapi/discussions/13732] |
| `python-ulid` | `ulid-py` (ahawker) | ahawker package is also maintained but less Pydantic v2 integration and less narrow feature set |
| `python-ulid` | UUIDv7 | Python 3.14's stdlib `uuid.uuid7()` is now native, but 3.14 is too new for a production pin. Phase 19 targets **Python 3.10+** per existing `pyproject.toml`. Revisit at v0.2 |
| `Alembic` | Raw SQL files + a `schema_version` table | 5-table schema is big enough that autogen + rollback are real wins. `alembic init -t async` is 60 seconds. |
| `uvicorn --workers 2` | gunicorn + uvicorn worker class | Gunicorn was the old best practice pre-uvicorn-0.30. uvicorn 0.44 has native workers. Hetzner box is shared with docker-for-recipes; fewer processes = less memory [CITED: https://fastapi.tiangolo.com/deployment/server-workers/] |
| `testcontainers` | `pytest-postgresql` | `pytest-postgresql` needs a system-installed `postgres` binary; `testcontainers` just needs Docker (already a dep). Cleaner CI story. |
| Raw FastAPI middleware | `slowapi` (Flask-Limiter port) | `slowapi` defaults to in-memory; moving it to Postgres is nearly as much work as writing the middleware. **Rejected** — D-05 mandates Postgres. |

**Installation** (tentative `api_server/pyproject.toml`):
```bash
pip install 'fastapi>=0.136' 'uvicorn[standard]>=0.44' \
    'asyncpg>=0.31' 'sqlalchemy>=2.0' 'alembic>=1.18' \
    'pydantic>=2.11' 'python-ulid>=3.1' \
    'structlog>=25.4' 'asgi-correlation-id>=4.3'
# dev-only
pip install 'pytest>=8' 'pytest-asyncio>=0.23' 'testcontainers[postgres]>=4.14' 'httpx'
```

**Version verification performed 2026-04-16 via `pip3 index versions`:**
- fastapi 0.136.0 (latest), asyncpg 0.31.0, alembic 1.18.4, python-ulid 3.1.0, uvicorn 0.44.0, sqlalchemy 2.0.49, structlog 25.5.0, asgi-correlation-id 4.3.4, testcontainers 4.14.2.

## Architecture Patterns

### System Architecture Diagram

```
+-------------+     +---------+     +-----------+     +-------------+
|  Client     |---->|  Caddy  |---->| uvicorn   |---->|  FastAPI    |
|  (curl/SDK) | TLS | :80/443 | HTTP| :8000     | ASGI|  routes     |
+-------------+     +---------+     +-----------+     +------+------+
                                                             |
                            +--------------------------------+--------------+
                            |                                |              |
                      +-----v------+               +---------v-----+  +-----v-----+
                      | Middleware |               | Request       |  | Readiness |
                      | stack      |               | handlers      |  | probes    |
                      | (corr-id,  |               |               |  |           |
                      |  log-redac,|               |               |  | docker    |
                      |  rate-lim, |               |               |  | version   |
                      |  idempot)  |               |               |  | pg ping   |
                      +-----+------+               +-----+---------+  +-----------+
                            |                            |
                            |                  +---------+-----------+
                            |                  | POST /v1/runs       |
                            |                  | flow:               |
                            |                  | 1. idempot lookup   |
                            |                  | 2. upsert agent_inst|
                            |                  | 3. insert run row   |
                            |                  | 4. acquire img lock |
                            |                  | 5. acquire global   |
                            |                  |    semaphore        |
                            |                  | 6. to_thread(       |
                            |                  |    run_cell)        |
                            |                  | 7. persist verdict  |
                            |                  +----+-----------+----+
                            |                       |           |
                     +------v----------+     +------v----+  +---v-----------+
                     | asyncpg pool    |     | BYOK key  |  | asyncio.      |
                     | PostgreSQL 17   |     | (request  |  | to_thread +   |
                     |                 |     | memory    |  | Semaphore     |
                     | tables:         |     | only)     |  +---+-----------+
                     | - users         |     +-----------+      |
                     | - agent_inst    |                 +------v----------+
                     | - runs          |                 | tools/          |
                     | - idempot_keys  |                 | run_recipe.py   |
                     | - rate_limit    |                 | (sync, no chg)  |
                     +-----------------+                 +--+--------------+
                                                            |
                                                      +-----v-----+
                                                      | docker    |
                                                      | (socket   |
                                                      | mount)    |
                                                      +-----------+
```

Data flow for `POST /v1/runs`: client → Caddy → uvicorn → middleware chain (correlation-id, rate-limit, idempotency, log-redac) → handler → asyncpg (read idempot, upsert agent_inst, insert run) → per-tag lock → global semaphore → `asyncio.to_thread(run_cell, ...)` → runner shells out to `docker` → container runs → runner returns Verdict → handler persists verdict + writes idempot → response.

### Recommended Project Structure
```
api_server/
├── pyproject.toml                 # FastAPI + asyncpg + alembic deps
├── README.md
├── alembic.ini                    # generated by `alembic init -t async alembic/`
├── alembic/
│   ├── env.py                     # async env, reads DATABASE_URL
│   ├── script.py.mako
│   └── versions/
│       └── 001_baseline.py        # all 5 tables in one migration
├── src/
│   └── api_server/
│       ├── __init__.py
│       ├── main.py                # FastAPI() app factory; docs_url env-gated
│       ├── config.py              # Settings (pydantic-settings) — AP_ENV, DATABASE_URL, AP_MAX_CONCURRENT_RUNS
│       ├── db.py                  # asyncpg pool; pool lifecycle via FastAPI lifespan
│       ├── log.py                 # structlog config + uvicorn log config override
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── correlation_id.py  # thin wrapper around asgi-correlation-id
│       │   ├── log_redact.py      # allowlist-based access log
│       │   ├── rate_limit.py      # Postgres-backed
│       │   └── idempotency.py     # Postgres-backed
│       ├── models/                # Pydantic request/response schemas
│       │   ├── __init__.py
│       │   ├── errors.py          # Stripe-shape error envelope
│       │   ├── recipes.py
│       │   ├── runs.py
│       │   └── schemas.py
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── health.py          # /healthz, /readyz
│       │   ├── schemas.py         # /v1/schemas, /v1/schemas/{version}
│       │   ├── recipes.py         # /v1/recipes, /v1/recipes/{name}, /v1/recipes/lint
│       │   └── runs.py            # /v1/runs, /v1/runs/{id}
│       ├── services/
│       │   ├── __init__.py
│       │   ├── runner_bridge.py   # asyncio.to_thread(run_cell) + per-tag lock + global semaphore
│       │   ├── idempotency.py     # advisory-lock based idempot check
│       │   ├── recipes_loader.py  # reads recipes/*.yaml via per-call YAML()
│       │   └── run_store.py       # asyncpg queries for runs/agent_instances
│       └── util/
│           ├── ulid.py            # thin wrap over python-ulid for consistency
│           └── redaction.py       # header + string redaction helpers
└── tests/
    ├── conftest.py                # testcontainers Postgres fixture
    ├── test_health.py
    ├── test_recipes.py
    ├── test_runs.py               # integration — @pytest.mark.api_integration
    ├── test_idempotency.py
    └── test_rate_limit.py
```

Two-tier test organization:
- **Default** (`pytest`): uses testcontainers Postgres, NO docker runs, mocks `asyncio.to_thread(run_cell)` via `unittest.mock.patch`.
- **Integration** (`pytest -m api_integration`): boots real Postgres + actually calls `run_cell` against one recipe. Matches the runner's existing `-m integration` pattern.

### Pattern 1: Application factory + lifespan for asyncpg pool

```python
# main.py
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from .db import create_pool, close_pool
from .middleware.correlation_id import CorrelationIdMiddleware
from .middleware.log_redact import AccessLogMiddleware
from .routes import health, schemas, recipes, runs

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool(os.environ["DATABASE_URL"])
    app.state.image_tag_locks = {}  # defaultdict-like, guarded by app.state.locks_mutex
    app.state.locks_mutex = asyncio.Lock()
    app.state.run_semaphore = asyncio.Semaphore(
        int(os.environ.get("AP_MAX_CONCURRENT_RUNS", "2"))
    )
    yield
    await close_pool(app.state.db)

def create_app() -> FastAPI:
    env = os.environ.get("AP_ENV", "dev")
    app = FastAPI(
        title="Agent Playground API",
        version="0.1.0",
        openapi_url="/openapi.json",                          # always on (frontend type-gen)
        docs_url="/docs" if env == "dev" else None,           # D-10
        redoc_url="/redoc" if env == "dev" else None,         # D-10
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.include_router(health.router)
    app.include_router(schemas.router, prefix="/v1")
    app.include_router(recipes.router, prefix="/v1")
    app.include_router(runs.router, prefix="/v1")
    return app

app = create_app()
```
**Source:** synthesized from FastAPI lifespan docs + CONTEXT.md D-04/D-10 constraints.

### Pattern 2: Per-image-tag Lock + global Semaphore

```python
# services/runner_bridge.py
import asyncio
from collections import defaultdict
from typing import Any

async def _get_tag_lock(app_state, image_tag: str) -> asyncio.Lock:
    """Double-checked dict insert: guard the dict access with a single mutex,
    release it before awaiting on the per-tag lock itself."""
    async with app_state.locks_mutex:
        lock = app_state.image_tag_locks.get(image_tag)
        if lock is None:
            lock = asyncio.Lock()
            app_state.image_tag_locks[image_tag] = lock
    return lock

async def execute_run(app_state, recipe: dict, *, prompt: str, model: str,
                     api_key_var: str, api_key_val: str) -> dict:
    from run_recipe import run_cell  # the vendored sync runner
    image_tag = f"ap-recipe-{recipe['name']}"
    tag_lock = await _get_tag_lock(app_state, image_tag)
    async with tag_lock:                         # serialize SAME-tag builds
        async with app_state.run_semaphore:      # bound total concurrent runs
            verdict_obj, details = await asyncio.to_thread(
                run_cell,
                recipe,
                image_tag=image_tag,
                prompt=prompt,
                model=model,
                api_key_var=api_key_var,
                api_key_val=api_key_val,
                quiet=True,
            )
    return details
```
**Race note:** the naive approach `app_state.image_tag_locks[image_tag] = asyncio.Lock()` without the mutex is UNSAFE — two coroutines racing on first use for the same tag can each create a fresh Lock, so they don't actually serialize. The `locks_mutex` double-check above is the correct pattern and only contends on first-use of each tag.

**Source:** synthesized from CPython asyncio docs + prior-art in aiohttp application state patterns.

### Pattern 3: Idempotency with advisory lock

```python
# services/idempotency.py
import hashlib
from typing import Optional

async def check_or_reserve(conn, user_id: str, key: str) -> tuple[bool, Optional[dict]]:
    """Returns (cache_hit, cached_verdict_json_or_None).
    If cache_hit: True, verdict is populated — caller returns immediately.
    If cache_hit: False, caller must run AND call write_idempotency afterwards.
    Serializes concurrent first-use of the same key via advisory lock.
    """
    # 64-bit key from user_id + key — cheap hash, no collisions that matter
    lock_key = int.from_bytes(
        hashlib.sha256(f"{user_id}:{key}".encode()).digest()[:8], "big", signed=True
    )
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
        row = await conn.fetchrow(
            "SELECT run_id, verdict_json FROM idempotency_keys "
            "WHERE user_id = $1 AND key = $2 AND expires_at > NOW()",
            user_id, key,
        )
        if row:
            return (True, {"run_id": row["run_id"], "verdict_json": row["verdict_json"]})
        return (False, None)

async def write_idempotency(conn, user_id: str, key: str, run_id: str,
                             verdict_json: dict, ttl_hours: int = 24):
    await conn.execute(
        """INSERT INTO idempotency_keys (id, user_id, key, run_id, verdict_json,
               created_at, expires_at)
           VALUES (gen_random_uuid(), $1, $2, $3, $4, NOW(),
                   NOW() + ($5 || ' hours')::interval)
           ON CONFLICT (user_id, key) DO NOTHING""",
        user_id, key, run_id, verdict_json, str(ttl_hours),
    )
```
**Stripe-matching semantics:**
- First request: inserts a reservation, runs, writes result, releases.
- Concurrent second request: blocks on advisory lock until first completes, re-reads, returns cached result.
- Third request after TTL: expires_at filter misses, re-runs.
**Source:** https://brandur.org/idempotency-keys + Stripe docs on idempotent requests. CITED.

### Pattern 4: Postgres-backed sliding-window-ish rate limit

```python
# services/rate_limit.py (algorithm sketch)
from datetime import datetime, timedelta

async def check_and_increment(conn, subject: str, bucket: str, limit: int,
                               window_s: int) -> tuple[bool, int]:
    """Fixed-window-with-advisory-lock. Returns (allowed, retry_after_s).
    `subject` is user_id or IP. `bucket` is endpoint_bucket ('runs'|'lint'|'get').
    """
    window_start_q = "date_trunc('second', NOW()) - (EXTRACT(EPOCH FROM NOW())::bigint % $1) * INTERVAL '1 second'"
    lock_key = hash((subject, bucket)) & ((1 << 63) - 1)  # fit int64 positive
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock($1)", lock_key)
        row = await conn.fetchrow(
            f"""INSERT INTO rate_limit_counters (subject, bucket, window_start, count)
                VALUES ($1, $2, {window_start_q}, 1)
                ON CONFLICT (subject, bucket, window_start)
                DO UPDATE SET count = rate_limit_counters.count + 1
                RETURNING count, window_start""",
            subject, bucket, window_s,
        )
        if row["count"] > limit:
            retry_after = max(1, window_s - int((datetime.utcnow() - row["window_start"]).total_seconds()))
            return (False, retry_after)
        return (True, 0)
```

**Rate-limit algorithm trade — locked recommendation: fixed-window.** True sliding-window requires per-request timestamps (bad for write volume) or multiple counters interpolated. Fixed-window is simpler, widely-used (Cloudflare "fixed"), and matches the CONTEXT.md D-05 "not aggressive, fair-use defaults" brief. **Accept** that a pathological client can 2x burst at the boundary. Sliding-window variant is a Phase 22+ polish.

**Alternative considered:** sliding-window-log (store each request timestamp, count rows in last N seconds). Rejected — write amplification at 300 req/min × users adds up, and the `rate_limit_counters` table gets huge unless you GC aggressively.

**Alternative considered:** token bucket. Rejected — needs a `last_refill_at` column and floating-point token math; harder to reason about than fixed-window in SQL.

**Source:** https://neon.com/guides/rate-limiting (CITED) + PostgreSQL advisory lock docs.

### Pattern 5: Log redaction middleware (allowlist)

```python
# middleware/log_redact.py
import time
from starlette.types import ASGIApp, Receive, Scope, Send
import structlog

_LOG_HEADERS = {"user-agent", "content-length", "content-type", "accept", "x-request-id"}

class AccessLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.log = structlog.get_logger("access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        t0 = time.monotonic()
        status_holder = {"status": 0}
        async def send_wrapper(msg):
            if msg["type"] == "http.response.start":
                status_holder["status"] = msg["status"]
            await send(msg)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            hdrs = {k.decode(): v.decode() for (k, v) in scope.get("headers", [])}
            safe = {k: v for k, v in hdrs.items() if k.lower() in _LOG_HEADERS}
            self.log.info(
                "access",
                method=scope["method"],
                path=scope["path"],
                status=status_holder["status"],
                duration_ms=int((time.monotonic() - t0) * 1000),
                headers=safe,
                # Notably absent: authorization, cookie, x-api-key, body
            )
```

**Key invariants:**
- `Authorization`, `Cookie`, `X-Api-Key` never appear in the log line — allowlist enforces this.
- Request body is never touched by this middleware (never captured = never leaked).
- Works with `asgi-correlation-id`'s `x-request-id` injection (it runs BEFORE this, so the header is already set).

### Anti-Patterns to Avoid

- **Using the module-level `_yaml` singleton from `tools/run_recipe.py` inside the server.** Documented thread-safety defect in ruamel.yaml (sourceforge ticket #367). **Use `YAML()` per-call in server-consumed paths** (`load_recipe` in `services/recipes_loader.py`). CITED: https://sourceforge.net/p/ruamel-yaml/tickets/367/.
- **`docker run -e KEY=value` for BYOK.** Leaks the key to `ps` and `/proc/*/cmdline`. The runner already uses `--env-file` — don't regress.
- **In-memory dict for idempotency "for now".** Forbidden by CONTEXT.md D-01 + `feedback_no_mocks_no_stubs.md`. Postgres from day 1.
- **Setting `openapi_url=None` in prod.** Phase 20 frontend needs `/openapi.json` for `openapi-typescript`. Hide `/docs` and `/redoc` only. [CITED: https://fastapi.tiangolo.com/tutorial/metadata/]
- **Adding request/response body to structured logs even when "only in dev".** Dev logs get copied into bug reports, bug reports get pasted into Slack. Never log body.
- **Running `docker exec -i` from inside the FastAPI process directly.** Use `asyncio.to_thread(run_cell)`. The runner is the sole caller of the docker CLI — keep the seam narrow.
- **Using gunicorn with uvicorn workers.** Obsolete pre-uvicorn-0.30 advice; uvicorn has native `--workers` now and is the documented path [CITED: https://fastapi.tiangolo.com/deployment/server-workers/].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| X-Request-Id generation + propagation | Custom middleware | `asgi-correlation-id` 4.3.4 | Handles missing-header mint, response injection, structlog contextvar binding, and sentry auto-link — 200 lines you don't have to maintain |
| JSON access log | Custom logging config | `structlog` 25.5.0 with `JSONRenderer` | Free context binding, battle-tested processors, first-class async |
| Postgres async driver | Raw libpq Python bindings | `asyncpg` 0.31.0 | Written by MagicStack specifically for asyncio workloads, native protocol, no ORM tax |
| ULID generation + parse | Handrolled base32 + time.time_ns() | `python-ulid` 3.1.0 | Spec edge cases (monotonicity, overflow) are not worth re-deriving |
| TLS cert management | Custom ACME loop, manual certbot | Caddy 2.x | Automatic HTTPS with zero config [CITED: https://caddyserver.com/docs/automatic-https] |
| Database migrations | Numbered `.sql` files + custom applier | Alembic 1.18.4 async | Autogenerate + rollback + branching are real; applier is not fun to write. (Go side uses embedded-FS migrator per STATE.md — Python side does NOT need to match that; different runtime, different ecosystem.) |
| Postgres test fixture | Per-test schema drop-and-create | `testcontainers[postgres]` session-scoped + TRUNCATE | Docker daemon is already a dep; zero system-level prereqs |
| Idempotency concurrency control | Polling `INSERT ... ON CONFLICT` retries | `pg_advisory_xact_lock(hashtext(user_id + key))` | One transaction, deterministic serialization, no retry loop needed [CITED: https://brandur.org/idempotency-keys] |

**Key insight:** the entire server is ~1200 lines of Python if you lean on the stack above. Hand-rolling any of these costs ~300 lines each + ongoing maintenance.

## Runtime State Inventory

Phase 19 is **greenfield code** (no rename/refactor/migration). Section intentionally omitted.

However, one rename-adjacent concern: **existing `tools/run_recipe.py` and its test suite MUST NOT be modified** per CONTEXT.md Success Criterion #11 ("All existing runner unit tests (171 from phase 18) still pass unchanged — no regression in runner code path"). The server imports from it; it does not edit it. The only exception is the CONTEXT.md-locked change: **widen `_redact_api_key()` to also redact literal key value** (runner-integration critique §5). This is a scope-expanding change to the runner, cleared by discuss-phase, and must have a regression test.

## Common Pitfalls

### Pitfall 1: Per-image-tag dict race
**What goes wrong:** `image_tag_locks[tag] = asyncio.Lock()` without a guard — two coroutines racing on first use for the same tag each create a fresh Lock, so they don't serialize.
**Why it happens:** `dict.setdefault` is not atomic across `await` suspensions — which is moot here since it's sync, but the hypothetical "check if absent, then create" pattern is the bug.
**How to avoid:** Use Pattern 2 above — a single `app_state.locks_mutex` guards the dict access, and coroutines release that mutex before awaiting on the per-tag lock.
**Warning signs:** Intermittent "two simultaneous builds of the same tag" in integration tests.

### Pitfall 2: ruamel.yaml shared state under load
**What goes wrong:** Concurrent `POST /v1/lint` or `POST /v1/runs` calls invoke the runner's module-level `_yaml = YAML(typ="rt")` from multiple asyncio threads. ruamel's internal parser state is not thread-safe (ticket #367 documents exceptions on concurrent dump; load has similar hazards).
**Why it happens:** `ruamel.yaml.YAML` instances memoize representer/resolver state; concurrent modification corrupts it.
**How to avoid:** CONTEXT.md already locks this: "`_yaml` module singleton: replace with per-call `YAML()` instances in the server-consumed paths (load_recipe, writeback_cell). CLI keeps the singleton; server constructs fresh."
**Warning signs:** Randomly-failing lint tests under parallel pytest execution.
**Source:** https://sourceforge.net/p/ruamel-yaml/tickets/367/ [CITED]

### Pitfall 3: Forgetting `asyncio.to_thread` wraps a sync function
**What goes wrong:** Accidentally calling `run_cell` directly in a `async def` handler blocks the entire event loop for the duration of the docker run (10–200s). All other requests stall.
**Why it happens:** `run_cell` doesn't raise if called from async context; it just blocks silently.
**How to avoid:** Linter rule — any import of `run_cell` must go through `services/runner_bridge.py`'s `execute_run()`, which always wraps in `asyncio.to_thread`. Add a unit test that mocks `run_cell` and verifies the call site uses the bridge.
**Warning signs:** `/healthz` latency explodes during a run; concurrent rate-limit 429s don't fire because nothing else completes.

### Pitfall 4: asyncpg connection pool size vs. global semaphore
**What goes wrong:** `asyncpg.create_pool(min_size=2, max_size=5)` with `AP_MAX_CONCURRENT_RUNS=2` leaves only 3 connections for ALL other traffic (health probes, rate limit writes, idempotency reads). Under burst load you deadlock because every connection is held open inside a long-running run.
**Why it happens:** Each `POST /v1/runs` holds a DB connection across the `asyncio.to_thread(run_cell)` await (200+ seconds) if you don't release it.
**How to avoid:** **Release the DB connection before entering the runner, re-acquire to write the verdict.** Pattern: 1) acquire conn, read idempot, insert run row, release conn. 2) run the cell. 3) acquire conn, write verdict, write idempot, release conn.
**Warning signs:** Under load, `/healthz` starts timing out even though it should never hit Postgres.

### Pitfall 5: Docker socket permission on Hetzner
**What goes wrong:** api_server container mounts `/var/run/docker.sock`, but the UID inside the container doesn't have docker group access → `permission denied`.
**Why it happens:** Docker socket gid on Hetzner host may not match the container's docker group gid.
**How to avoid:** Dockerfile creates a `docker` group inside the image with gid passed in as a build arg (`ARG DOCKER_GID`), and the run-user is added to it. Compose file sets `DOCKER_GID` from the host (`stat -c %g /var/run/docker.sock`).
**Warning signs:** `/readyz` returns `docker_daemon: false` immediately post-deploy.

### Pitfall 6: Idempotency key reused with different body
**What goes wrong:** Client sends `Idempotency-Key: abc` with `{"recipe_name": "hermes"}`, gets a run_id. Then sends `Idempotency-Key: abc` with `{"recipe_name": "picoclaw"}` — what happens?
**Why it happens:** Stripe's spec says the server should return HTTP 422 with "request body differs from cached one." Clients that reuse keys across bodies have a bug.
**How to avoid:** Store a `request_body_hash` column in `idempotency_keys` and reject mismatched reuse with 422. CITED: https://stripe.com/blog/idempotency.
**Warning signs:** Clients get unexpectedly cached results from a request that looks different.

### Pitfall 7: Caddy writes cert + key to ephemeral filesystem
**What goes wrong:** Caddy gets Let's Encrypt certs on first deploy, box reboots, Caddy re-requests from Let's Encrypt, hits rate limit (5 failed + 5 duplicate per hour per domain).
**Why it happens:** `/data` inside the Caddy container is not mounted to a persistent volume → cert storage is ephemeral.
**How to avoid:** `docker-compose.prod.yml` declares `caddy_data:` named volume mounted at `/data` in the Caddy service.
**Warning signs:** TLS cert reissue fails after reboot.

### Pitfall 8: Python 3.10 missing `asyncio.TaskGroup`
**What goes wrong:** Copy-paste from FastAPI 2026 tutorial uses `asyncio.TaskGroup` (added 3.11); breaks on the pinned 3.10 minimum.
**Why it happens:** `pyproject.toml` sets `requires-python = ">=3.10"` to match the existing runner.
**How to avoid:** Either bump to 3.11 in `api_server/pyproject.toml` (fine — runner and server can have different min-Python) OR use `asyncio.gather`. Recommend: **bump api_server to require Python 3.11+.** Runner's 3.10 pin is for recon-tool users; server has no such constraint.
**Warning signs:** CI fails with `AttributeError: module 'asyncio' has no attribute 'TaskGroup'`.

## Code Examples

### Run endpoint (happy path sketch)
```python
# routes/runs.py
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from ulid import ULID
from ..models.runs import RunRequest, RunResponse
from ..services.runner_bridge import execute_run
from ..services.idempotency import check_or_reserve, write_idempotency

router = APIRouter()

@router.post("/runs", response_model=RunResponse)
async def create_run(
    req: Request,
    body: RunRequest,
    authorization: str = Header(..., alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    provider_key = authorization.removeprefix("Bearer ").strip()

    # Resolve user — phase 19: always anonymous
    user_id = "00000000-0000-0000-0000-000000000001"

    async with req.app.state.db.acquire() as conn:
        if idempotency_key:
            cache_hit, cached = await check_or_reserve(conn, user_id, idempotency_key)
            if cache_hit:
                return cached["verdict_json"]

        # upsert agent_instance, insert pending run row
        agent_instance_id = await _upsert_agent_instance(
            conn, user_id, body.recipe_name, body.model
        )
        run_id = str(ULID())
        await _insert_pending_run(conn, run_id, agent_instance_id, body)

    # Release conn before running — Pitfall 4
    recipe = req.app.state.recipes[body.recipe_name]
    api_key_var = recipe["runtime"]["process_env"]["api_key"]

    details = await execute_run(
        req.app.state,
        recipe,
        prompt=body.prompt or recipe["smoke"]["prompt"],
        model=body.model,
        api_key_var=api_key_var,
        api_key_val=provider_key,
    )

    # Re-acquire to write verdict
    async with req.app.state.db.acquire() as conn:
        await _write_verdict(conn, run_id, details)
        if idempotency_key:
            await write_idempotency(conn, user_id, idempotency_key, run_id, details)

    return RunResponse(run_id=run_id, agent_instance_id=str(agent_instance_id), **details)
```
**Source:** synthesized from CONTEXT.md D-07 flow + Pattern 2 + Pattern 3.

### Alembic async env.py baseline
```python
# alembic/env.py (abridged)
import asyncio, os
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from sqlalchemy import MetaData, pool

config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])  # postgresql+asyncpg://...
target_metadata = MetaData()  # bare metadata — we author DDL via op.create_table directly

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

if context.is_offline_mode():
    raise RuntimeError("offline migrations not supported")
asyncio.run(run_async_migrations())
```
**Source:** https://testdriven.io/blog/fastapi-sqlmodel/ [CITED], adapted for bare-metadata (no ORM models) approach.

### DDL for baseline migration
```python
# alembic/versions/001_baseline.py
import sqlalchemy as sa
from alembic import op

revision = "001_baseline"
down_revision = None

def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text, nullable=True),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )
    # Seed anonymous user
    op.execute("""INSERT INTO users (id, display_name) VALUES
        ('00000000-0000-0000-0000-000000000001', 'anonymous')""")

    op.create_table(
        "agent_instances",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipe_name", sa.Text, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_runs", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "recipe_name", "model",
                            name="uq_agent_instances_user_recipe_model"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Text, primary_key=True),   # ULID 26-char
        sa.Column("agent_instance_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("agent_instances.id"), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("verdict", sa.Text, nullable=True),
        sa.Column("category", sa.Text, nullable=True),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("exit_code", sa.Integer, nullable=True),
        sa.Column("wall_time_s", sa.Numeric, nullable=True),
        sa.Column("filtered_payload", sa.Text, nullable=True),
        sa.Column("stderr_tail", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_runs_agent_instance", "runs", ["agent_instance_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("run_id", sa.Text, sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("verdict_json", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("request_body_hash", sa.Text, nullable=False),  # Pitfall 6
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_key"),
    )
    op.create_index("idx_idempotency_expires", "idempotency_keys", ["expires_at"])

    op.create_table(
        "rate_limit_counters",
        sa.Column("subject", sa.Text, nullable=False),   # user_id_as_text OR ip
        sa.Column("bucket", sa.Text, nullable=False),    # 'runs' | 'lint' | 'get'
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("subject", "bucket", "window_start"),
    )
    op.create_index("idx_rate_limit_gc", "rate_limit_counters", ["window_start"])

def downgrade():
    for t in ("rate_limit_counters", "idempotency_keys", "runs",
              "agent_instances", "users"):
        op.drop_table(t)
```
**Source:** synthesized from CONTEXT.md D-06 schema specification.

### Caddyfile
```caddy
# deploy/Caddyfile
{
    email ops@agentplayground.dev  # Let's Encrypt contact
}

api.agentplayground.dev {
    reverse_proxy api_server:8000
    encode gzip
    log {
        output stdout
        format json
    }
}
```
**Source:** https://caddyserver.com/docs/quick-starts/https [CITED]. 8 lines total; ACME handled automatically; `/data` mount in compose preserves certs across reboots.

### docker-compose.prod.yml (sketch)
```yaml
# deploy/docker-compose.prod.yml
services:
  postgres:
    image: postgres:17-alpine
    restart: always
    environment:
      POSTGRES_DB: agent_playground
      POSTGRES_USER: ap
      POSTGRES_PASSWORD_FILE: /run/secrets/pg_password
    volumes:
      - pg_data:/var/lib/postgresql/data
    secrets: [pg_password]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ap -d agent_playground"]
      interval: 10s
      timeout: 3s
      retries: 5

  api_server:
    build:
      context: ../api_server
      dockerfile: Dockerfile
      args:
        DOCKER_GID: ${DOCKER_GID}   # from `stat -c %g /var/run/docker.sock`
    restart: always
    environment:
      AP_ENV: prod
      AP_MAX_CONCURRENT_RUNS: "2"
      DATABASE_URL: postgres://ap@postgres:5432/agent_playground
    env_file: [.env.prod]
    depends_on:
      postgres: {condition: service_healthy}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock   # known trust boundary
      - recipes_ro:/app/recipes:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
      interval: 30s

  caddy:
    image: caddy:2
    restart: always
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data        # Pitfall 7
      - caddy_config:/config
    depends_on: [api_server]

volumes:
  pg_data:
  caddy_data:
  caddy_config:
  recipes_ro:

secrets:
  pg_password:
    file: ./secrets/pg_password
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| gunicorn + `uvicorn.workers.UvicornWorker` | `uvicorn --workers N` native | uvicorn 0.30 (mid-2024) | One fewer process manager; same behavior; simpler Docker cmd |
| `psycopg2` sync driver in threadpool | `asyncpg` native async | 2023+ | 3–10x throughput on IO-bound workloads [CITED: https://github.com/fastapi/fastapi/discussions/13732] |
| `docker/docker-py` Python SDK | Shell out `docker` CLI + subprocess | ongoing | docker-py has lagged Docker Engine features; CLI is always current. Runner already does this |
| Hand-rolled sliding-window rate limit | Advisory lock + fixed window | ongoing | Simpler SQL, bounded cardinality |
| `nhooyr.io/websocket` (Go-equivalent reference) | `coder/websocket` | 2024 | Python side: N/A until Phase 22+ |
| Next 15 Pages Router | Next 16 App Router | 2024+ | Frontend lands Phase 20; OpenAPI JSON is the Phase 19 / Phase 20 contract |

**Deprecated/outdated in this phase:**
- `httpx==0.x < 0.27` — TestClient semantics changed; make sure pins are current.
- `alembic < 1.11` — async template is broken; 1.18.4 is fine.
- `python-ulid 1.x` — pre-Pydantic-v2; use 3.1.0.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncpg` 5x faster than psycopg3 in this workload | Standard Stack | LOW — both are "fast enough"; driver is not the bottleneck. Benchmarks cited from third-party blogs [CITED + ASSUMED] |
| A2 | Hetzner box has Docker daemon running and socket at `/var/run/docker.sock` | Deployment | MEDIUM — if the host is systemd-managed podman or rootless docker, the socket path differs. Phase 1 set this up with `userns-remap` enabled. Verify during deploy. [ASSUMED] |
| A3 | ruamel.yaml module singleton is actually racy in practice for `load` | Pitfall 2 | LOW — CONTEXT.md already mandates per-call instances regardless, and it's a cheap defensive change. Ticket #367 documents `dump` races; `load` is less clearly documented as unsafe but the shared-resolver state pattern is the same. [CITED but narrow repro] |
| A4 | `pg_advisory_xact_lock` + `ON CONFLICT` is sufficient for idempotency concurrency | Pattern 3 | MEDIUM — Brandur's post is widely cited but doesn't explicitly walk through simultaneous duplicate arrivals. Advisory lock should serialize them. Write a concurrency test. [CITED + ASSUMED] |
| A5 | 2 uvicorn workers is right on a shared Hetzner box | Server topology | MEDIUM — depends on core count and docker memory pressure. FastAPI docs say "start small, measure." [CITED: fastapi.tiangolo.com + ASSUMED] |
| A6 | Python 3.11 is available on Hetzner base image | Pitfall 8 | LOW — Debian 13 (bookworm) ships 3.11; Ubuntu 24.04 ships 3.12. Either satisfies. [ASSUMED] |
| A7 | Caddy 2.x ACME rate limit (5 per hour) won't hit during normal deploys | Pitfall 7 | LOW — only hits on cert-not-persisted. Compose volume fixes this. [CITED: Let's Encrypt rate limit docs] |
| A8 | `docker.sock` mount is an acceptable trust boundary for phase 19 | Deployment | HIGH — CONTEXT.md D-08 explicitly accepts this: "Document it as a known trust boundary. Phase 19 runs on a single-tenant box; multi-tenant isolation (Sysbox, gVisor) is phase 22+." No further mitigation needed in this phase. [CITED: CONTEXT.md D-08] |
| A9 | The 5 recipe YAML files can be loaded at server startup and cached | Performance | LOW — they're tiny (<5KB each). Reload-on-SIGHUP is a nice-to-have (matches the Go-side 02.5 pattern) but not required for phase 19. [ASSUMED] |

## Open Questions

1. **Python-minimum for api_server — 3.10 or 3.11?**
   - What we know: runner is pinned to `>=3.10` for recon-tool compatibility.
   - What's unclear: server can be tighter.
   - Recommendation: **bump api_server to `>=3.11`** for TaskGroup + ExceptionGroup. Keep runner at 3.10. Documented in Pitfall 8.

2. **Subdomain vs. path-based routing — `api.agentplayground.dev` vs. `agentplayground.dev/api/*`?**
   - What we know: CONTEXT.md leaves this to planner discretion.
   - Recommendation: **subdomain** (`api.agentplayground.dev`). Cleaner CORS story for Phase 20 frontend at `agentplayground.dev`; API can evolve its cache/CDN policy independently; OpenAPI `servers:` block is unambiguous.

3. **`POST /v1/lint` response shape on errors — 200 with `{errors: [...]}` or 400 with error envelope?**
   - What we know: Linting is a validation service, not a failure state.
   - Recommendation: **200 with `{valid: bool, errors: [{path, message}]}`**. Returning 400 implies the REQUEST was malformed; 200 with errors body says "the request was fine, your recipe has issues." Matches JSON Schema validator services like ajv.dev.

4. **Should `GET /v1/runs/{id}` be rate-limited same as other GETs (300/min)?**
   - What we know: CONTEXT.md D-05 groups `GET /v1/*` at 300/min.
   - Recommendation: yes, one bucket. No need for per-endpoint GET buckets.

5. **Is there a Phase 19 frontend smoke test, or does that wait for Phase 20?**
   - What we know: Success Criterion #13 feeds `/openapi.json` into `openapi-typescript` and produces a valid TS client. That IS the frontend smoke test.
   - Recommendation: plan 19-07 (deploy) should include a `make smoke-api` target that does the full curl sequence from Success Criteria #1–#9, once against localhost and once against the deployed domain.

6. **What writes to `runs.completed_at`?**
   - What we know: schema has the column, not explicitly in D-07 flow.
   - Recommendation: set at "Write verdict" step (9 in D-07 flow). `created_at` is on insert, `completed_at` is on verdict write. Adds observability.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | api_server | ✓ (dev: 3.10 present; needs 3.11 added) | 3.10.10 | pyenv/conda to 3.11 |
| Docker Engine | runner wrapping | ✓ | 28.5.1 | — |
| uvicorn | server | ✓ | 0.35.0 installed, 0.44.0 latest | pip upgrade |
| PostgreSQL | data layer | ✓ (via testcontainers on-demand) | 17 image available | — |
| `psql` CLI | Success Criterion #8 | ✓ | homebrew libpq | — |
| gunicorn | (not required) | ✗ | — | uvicorn --workers |
| Caddy | deploy only | ✗ (dev: not installed) | — | Install via apt on Hetzner, or use caddy:2 Docker image (recommended) |
| FastAPI | server | ✓ | 0.116.1 installed, 0.136.0 latest | pip upgrade |
| Hetzner SSH access | deployment | ? | — | **Must verify** before plan 19-07 (Hetzner deploy plan) |
| Domain DNS | TLS | ? | — | **Must verify** — DNS A record for `api.agentplayground.dev` must exist before Caddy first-run, or ACME fails |

**Missing dependencies with no fallback:**
- Hetzner SSH access + DNS: blocks the deploy plan. Flag for human in planner.

**Missing dependencies with fallback:**
- gunicorn (use uvicorn native workers — already recommended).
- Caddy (use `caddy:2` Docker image — already recommended).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio ≥0.23 |
| Config file | `api_server/pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `cd api_server && pytest -q -x` |
| Full suite command | `cd api_server && pytest -q` (no -x, includes integration) |
| Integration marker | `@pytest.mark.api_integration` (parallel to runner's `integration`) |
| Postgres strategy | `testcontainers[postgres]` session-scoped fixture, TRUNCATE per test |

### Phase Requirements → Test Map

| Req | Behavior | Test Type | Automated Command | File Exists? |
|-----|----------|-----------|-------------------|-------------|
| SC-01 | `GET /healthz` returns `{"ok": true}` from internet | integration | `curl https://api.agentplayground.dev/healthz` | ❌ Wave 0 (needs deploy) — add to `make smoke-api-live` |
| SC-02 | `/readyz` shows postgres+docker true + recipes_count | integration | `pytest tests/test_health.py::test_readyz_live` | ❌ Wave 0 |
| SC-03 | `/v1/schemas` returns `["ap.recipe/v0.1"]` | unit | `pytest tests/test_schemas.py::test_list_schemas` | ❌ Wave 0 |
| SC-04 | `/v1/recipes` returns 5 recipes | unit | `pytest tests/test_recipes.py::test_list_recipes` | ❌ Wave 0 |
| SC-05 | `POST /v1/runs` happy-path PASS verdict | api_integration | `pytest -m api_integration tests/test_runs.py::test_run_hermes_gpt4o_mini` | ❌ Wave 0 |
| SC-06 | Idempotency-Key replays cached verdict, no re-run | api_integration | `pytest -m api_integration tests/test_idempotency.py::test_same_key_returns_cache` | ❌ Wave 0 |
| SC-07 | 50 concurrent runs bounded by semaphore to N | api_integration | `pytest -m api_integration tests/test_runs.py::test_concurrency_semaphore_caps` | ❌ Wave 0 |
| SC-08 | Runs persisted in Postgres | unit + integration | `pytest tests/test_runs.py::test_persist_run_row` | ❌ Wave 0 |
| SC-09 | 11th POST returns 429 with Retry-After | unit | `pytest tests/test_rate_limit.py::test_429_after_limit` | ❌ Wave 0 |
| SC-10 | Default suite + api_integration suite all green | all | `pytest -q` | ❌ Wave 0 (framework to build) |
| SC-11 | Runner's existing 171 tests still pass unchanged | regression | `cd /Users/fcavalcanti/dev/agent-playground && pytest tools/tests/ -q` | ✅ exists; must stay green |
| SC-12 | `/docs` 404 in prod, 200 in dev | unit | `pytest tests/test_docs_gating.py` | ❌ Wave 0 |
| SC-13 | `openapi.json` → `openapi-typescript` → valid TS client | integration | `make generate-ts-client` (manual smoke in 19-07) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest -q -x` (quick tier; no integration)
- **Per wave merge:** `pytest -q` (full suite + api_integration)
- **Phase gate:** Full suite green + live `make smoke-api-live` against deployed Hetzner box before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `api_server/pyproject.toml` — FastAPI/asyncpg/alembic deps
- [ ] `api_server/tests/conftest.py` — testcontainers Postgres fixture, `async_client` fixture, recipe-dir fixture
- [ ] Initial Alembic env.py + 001_baseline.py
- [ ] `api_server/src/api_server/main.py` — app factory with lifespan
- [ ] CI integration (if any exists) — add `api_server/` to path, install extra deps, run `pytest -q -m "not api_integration"` in unit job and `pytest -m api_integration` in a separate job with Postgres service

*No pre-existing test infra for api_server (it's greenfield). Runner test infra stays separate and unchanged.*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **no** (v1 is anonymous; BYOK is per-request key pass-through, not auth) | Deferred to Phase 21+ |
| V3 Session Management | no (no sessions; stateless) | — |
| V4 Access Control | partial | Rate limit per user_id or IP (D-05); no per-resource ACL |
| V5 Input Validation | **yes** | Pydantic v2 for all bodies; jsonschema 4.23+ for recipe YAML; ruamel.yaml 256KB cap on `POST /v1/lint` |
| V6 Cryptography | minimal | BYOK keys never persisted; no platform-owned secrets yet |
| V7 Error Handling | **yes** | Stripe-shape error envelope; no stack traces leaked; correlation-id in every error body |
| V8 Data Protection | **yes** | Log allowlist drops Authorization, X-Api-Key, Cookie, body; `_redact_api_key` widened to literal value per CONTEXT.md |
| V9 Communication | **yes** | TLS terminated at Caddy; HTTP→HTTPS redirect automatic; HSTS recommended default |
| V13 API | **yes** | OpenAPI auto-gen; versioned `/v1/*`; explicit `response_model` on every route |
| V14 Config | **yes** | `AP_ENV=prod` gates `/docs`; `/openapi.json` stays public (required by Phase 20 frontend) |

### Known Threat Patterns for FastAPI + shelled-out Docker

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| BYOK key leak via logs | Information disclosure | Allowlist-based access log middleware; `_redact_api_key` in runner |
| BYOK key leak via `ps`/`/proc/cmdline` | Information disclosure | Runner already uses `--env-file`, not `-e KEY=v` — preserve this |
| Idempotency-Key collision across users | Tampering | UNIQUE (user_id, key) prevents cross-user reuse |
| Idempotency-Key reuse with different body | Request forgery | Store `request_body_hash`, 422 on mismatch (Pitfall 6) |
| YAML bomb on `POST /v1/lint` | DoS | 256 KB request body cap (enforced at ASGI layer); ruamel.yaml loads with timeout |
| SSRF via `recipe_name` lookup | SSRF | Reject inline recipe YAML (D-07); only committed recipe names accepted |
| Docker socket escape | Elevation of privilege | Accepted trust boundary (A8); Phase 22+ moves to Sysbox |
| Postgres SQL injection | Tampering | asyncpg parameterized queries only; no string interp |
| Rate-limit bypass via IP spoofing | Repudiation | Use `X-Forwarded-For` from Caddy ONLY if we trust Caddy; default to peer IP |
| `git clone` option-as-value injection | Command injection | Already defended in Phase 18 by `source.ref` allowlist pattern `^[a-zA-Z0-9._/-]{1,255}$` |
| OpenAPI schema leak | Information disclosure | `/openapi.json` exposes route names and shapes; OK for OSS project (accepted) |

**Explicit non-goals (deferred to later phases):**
- No per-user API keys (Phase 21 OAuth).
- No CSRF protection (API is stateless, cross-origin CORS is the boundary — set `allow_origins` narrow).
- No mTLS.
- No WAF.

## Sources

### Primary (HIGH confidence)
- `tools/run_recipe.py` (direct code read) — existing runner shape, env-file BYOK handling, Category enum
- `tools/ap.recipe.schema.json` (direct read) — API contract for lint endpoint
- `.planning/phases/19-api-foundation/19-CONTEXT.md` (direct read) — all 10 locked decisions
- `.planning/phases/18-schema-maturity/18-VERIFICATION.md` (direct read) — confirmed schema state
- https://fastapi.tiangolo.com/deployment/server-workers/ — worker topology recommendations
- https://fastapi.tiangolo.com/tutorial/metadata/ — docs_url/redoc_url/openapi_url parameters
- https://caddyserver.com/docs/automatic-https — ACME automatic, 3-line Caddyfile
- https://caddyserver.com/docs/quick-starts/https — minimal Caddyfile
- https://github.com/MagicStack/asyncpg (PyPI 0.31.0 release) — verified via `pip3 index versions asyncpg`
- https://brandur.org/idempotency-keys — canonical Stripe-style Postgres idempotency pattern
- https://docs.stripe.com/api/idempotent_requests — Stripe spec (24h TTL, body-hash requirement)
- https://github.com/snok/asgi-correlation-id — X-Request-Id middleware
- https://neon.com/guides/rate-limiting — Postgres rate-limit patterns with advisory locks
- `pip3 index versions <pkg>` for fastapi, asyncpg, alembic, python-ulid, uvicorn, sqlalchemy, structlog, asgi-correlation-id, testcontainers — **all version claims verified 2026-04-16**

### Secondary (MEDIUM confidence)
- https://fernandoarteaga.dev/blog/psycopg-vs-asyncpg/ — asyncpg vs psycopg3 benchmark
- https://github.com/fastapi/fastapi/discussions/13732 — benchmarking async Postgres in FastAPI
- https://testdriven.io/blog/fastapi-sqlmodel/ — async Alembic setup pattern
- https://dzone.com/articles/performance-of-ulid-and-uuid-in-postgres-database — ULID performance in Postgres
- https://medium.com/@ciro-gomes-dev/uuidv4-vs-uuidv7-vs-ulid-choosing-the-right-identifier-for-database-performance-1f7d1a0fe0ba — UUIDv7 vs ULID tradeoffs
- https://gist.github.com/nymous/f138c7f06062b7c43c060bf03759c29e — structlog + uvicorn logging config
- https://wazaari.dev/blog/fastapi-structlog-integration — structlog integration recipe
- https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/ — official testcontainers Python guide

### Tertiary (LOW confidence — verify before asserting)
- https://sourceforge.net/p/ruamel-yaml/tickets/367/ — ruamel thread-safety ticket (narrow repro — exact failure mode in our code path is assumed, not reproduced)
- https://thehackernews.com/2026/04/docker-cve-2026-34040.html — referenced CVE; mitigation (accept trust boundary) unchanged
- Benchmark numbers ("5x", "15,000 qps") from various blog posts — directional, not absolute

## Metadata

**Confidence breakdown:**
- Standard stack (versions, packages): **HIGH** — all verified via pip index 2026-04-16
- Architecture patterns (Lock/Semaphore, idempotency, rate-limit): **HIGH** on the shape, **MEDIUM** on SQL exact form (untested in our codebase)
- Pitfalls: **HIGH** — each has a concrete code-visible signal; most are from direct code read + common-sense concurrency analysis
- Security: **MEDIUM** — ASVS mapping is standard, but the Docker socket trust boundary is explicitly accepted, not mitigated. Multi-tenant threat model is out of scope (Phase 22+)
- Hetzner deploy specifics: **LOW** — no SSH access from this research session; DNS state unverified. Flag human-in-the-loop for final deploy plan

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (30 days; FastAPI minor releases monthly but are non-breaking)
