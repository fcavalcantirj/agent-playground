---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 05
subsystem: api

tags: [fastapi, httpx, openrouter, gzip-middleware, ttl-cache, stale-while-revalidate, asyncio-lock, passthrough]

# Dependency graph
requires:
  - phase: 23-01
    provides: Wave 0 D-31 GZip×SSE compatibility spike (proves Starlette default-excludes text/event-stream)
  - phase: 22c.3-09
    provides: lifespan structure (bot_http_client provisioning + teardown ordering pattern to mirror)
  - phase: 19-03
    provides: routes/recipes.py shape (read-only public route analog)
provides:
  - GET /v1/models OpenRouter passthrough (REQ API-04 closed)
  - GZipMiddleware as outermost middleware on every route (D-25 — frees ~430KB models payload to ship as ~50KB on the wire)
  - app.state.openrouter_http_client lifecycle (separate from bot_http_client; 10s read budget)
  - app.state.models_cache + models_cache_lock (15min TTL + concurrent-fetch dedupe)
affects:
  - 23-07-frontend-/v1/models-migration (web frontend playground form unblocks)
  - 25-mobile-dashboard (mobile catalog dropdown can now hit our backend, not OpenRouter directly)
  - golden-rule-2 (dumb-client substrate closed for the models catalog — no more hardcoded React arrays)

# Tech tracking
tech-stack:
  added:
    - starlette.middleware.gzip.GZipMiddleware (was bundled with FastAPI; first time wired)
  patterns:
    - In-process dict TTL cache with double-checked-locking via asyncio.Lock for thundering-herd dedupe
    - Stale-while-revalidate: on upstream HTTPError, serve cache["payload"] if present + log; raise only on cold-start
    - Passthrough Response: routes return Starlette Response(content=bytes, media_type=...) instead of JSONResponse — no decode/re-encode round-trip
    - Separate httpx.AsyncClient per upstream service (10s catalog client distinct from 600s chat client) — fail-fast budgets per dependency
    - Override-upstream-cache-control: route handler sets Cache-Control: private, max-age=300 on 200 responses, defeating OpenRouter's no-store hint (RESEARCH §Q2)

key-files:
  created:
    - api_server/src/api_server/services/openrouter_models.py
    - api_server/src/api_server/routes/models.py
    - api_server/tests/routes/test_models.py
  modified:
    - api_server/src/api_server/main.py
    - .planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/deferred-items.md

key-decisions:
  - "ErrorCode.INFRA_UNAVAILABLE was already present in models/errors.py (added by Phase 22b-05 reservation); no new constant needed."
  - "Route uses single-line Response(content=payload, media_type='application/json', headers={'Cache-Control': 'private, max-age=300'}) — matches the literal grep pattern in the plan's acceptance_criteria block; semantics unchanged from a multi-line form."
  - "Tests access app.state via async_client._transport.app.state (canonical pattern from tests/auth/test_google_authorize.py:32) — NOT async_client._app (the _app attribute is only set on the started_api_server fixture for Plan 22c.3.1, not on the standard async_client)."
  - "GZipMiddleware is the LAST add_middleware call in main.py (line 434, after CorrelationIdMiddleware at 431). Verified at runtime via app.user_middleware[0] == 'GZipMiddleware' — Starlette stores user_middleware last-added-first so index 0 IS the outermost layer on the response path."
  - "openrouter_http_client gets a SEPARATE httpx.AsyncClient (timeout=10s, max_connections=10) — NOT shared with bot_http_client (timeout=600s, max_connections=50). Per RESEARCH 'Reuse app.state.bot_http_client?' rejection rationale: the catalog must fail fast; bot_http_client's 600s budget is meant for a single chat call."
  - "Tests stub upstream OpenRouter with respx (the only external dep mocked) and pre-warm/clear app.state.models_cache directly — no in-memory fakes for substrate (golden rule #1 holds: real Postgres, real Redis via testcontainers in async_client)."

patterns-established:
  - "Three-line lifespan pattern for any new external service: state.<service>_http_client (httpx.AsyncClient) + state.<service>_cache (dict) + state.<service>_cache_lock (asyncio.Lock); teardown closes the client right after bot_http_client."
  - "Dual-cache discipline: server-side 15min TTL (in-process) + client-side 5min Cache-Control: private, max-age=300; mobile reload UX hits client cache, true catalog refresh hits server cache, cold start hits OpenRouter once per replica per 15min."

requirements-completed: [API-04]

# Metrics
duration: 11min
completed: 2026-05-02
---

# Phase 23 Plan 05: GET /v1/models OpenRouter Passthrough Summary

**Implemented `GET /v1/models` with TTL-cached OpenRouter `/api/v1/models` passthrough (~30 LOC service + ~25 LOC route), wired the lifespan-managed `openrouter_http_client` + cache + lock, and registered Starlette's `GZipMiddleware(minimum_size=1024)` as the outermost middleware — closing REQ API-04 and golden-rule-2 for the models catalog.**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-05-02T12:37:48Z
- **Completed:** 2026-05-02T12:48:41Z
- **Tasks:** 3
- **Files created:** 3 (`services/openrouter_models.py`, `routes/models.py`, `tests/routes/test_models.py`)
- **Files modified:** 1 (`main.py` — 5 edits: import, lifespan startup, lifespan teardown, router include, GZipMiddleware add)

## Accomplishments

- `services/openrouter_models.py::get_models_payload(state) -> bytes` — single coroutine implementing the canonical TTL+Lock+SWR pattern from `23-PATTERNS.md` lines 122-153. Fast-path (lock-free TTL check) for the common cache-hit case; slow-path acquires the asyncio.Lock and double-checks under contention so concurrent first-fetches dedupe to one upstream HTTP call. On `httpx.HTTPError` (any of network error, timeout, 5xx via `raise_for_status`), serves stale cache bytes + logs `openrouter_models.serving_stale` if present (D-18 SWR), else re-raises so the route renders 503.
- `routes/models.py::list_models` — thin handler (~13 LOC) mirroring `routes/recipes.py::list_recipes` shape: unauthenticated public catalog (D-19), wraps `get_models_payload` in try/except, returns `Response(content=payload, media_type="application/json", headers={"Cache-Control": "private, max-age=300"})` on success (D-20 passthrough + RESEARCH §Q2), or `JSONResponse(503, INFRA_UNAVAILABLE envelope)` on cold-start failure.
- `main.py` edits (5):
  1. New import `from starlette.middleware.gzip import GZipMiddleware`.
  2. New import `from .routes import models as models_route` alongside existing `recipes_route`.
  3. Lifespan startup: `app.state.openrouter_http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), limits=httpx.Limits(max_connections=10, max_keepalive_connections=5))` + `app.state.models_cache = {}` + `app.state.models_cache_lock = asyncio.Lock()` placed right after `bot_http_client` provisioning.
  4. Lifespan teardown: `await app.state.openrouter_http_client.aclose()` in a try/except mirroring the `bot_http_client` close pattern; logged as `phase23.lifespan.openrouter_http_client_close_failed`.
  5. `app.add_middleware(GZipMiddleware, minimum_size=1024)` appended AT THE BOTTOM of the middleware block (line 434, after CorrelationIdMiddleware) so it's the OUTERMOST layer on the response path. Confirmed at runtime: `app.user_middleware[0].cls.__name__ == 'GZipMiddleware'`.
- `tests/routes/test_models.py` — 6 integration tests covering REQ API-04 + D-18..D-20 + D-25 + RESEARCH §Q2:
  1. `test_get_models_cache_miss_fetches_and_caches` — cache miss → upstream call_count == 1; body byte-equal `fake_payload`; content-type starts with `application/json` (D-20).
  2. `test_get_models_cache_hit_within_ttl_skips_upstream` — pre-warmed cache + within-TTL request → upstream call_count == 0 (D-18 hot path).
  3. `test_get_models_swr_on_upstream_failure` — stale cache (>15min) + upstream 503 → response 200 + body equals stale (D-18 SWR).
  4. `test_get_models_cold_start_failure_returns_503` — empty cache + upstream 500 → response 503 + Stripe envelope `error.code in (INFRA_UNAVAILABLE, SERVICE_UNAVAILABLE)`.
  5. `test_get_models_gzip_header_when_requested` — `Accept-Encoding: gzip` + payload >1024 bytes → response `content-encoding: gzip` (D-25 outermost middleware).
  6. `test_get_models_cache_control_header` — upstream sends `Cache-Control: private, no-store`, route OVERRIDES with `private, max-age=300` and `no-store` does NOT leak through (RESEARCH §Q2 RESOLVED).

## Truths Verified

All 9 must_haves.truths from the plan are now verifiable in committed code:

| # | Truth | Verification |
|---|-------|--------------|
| 1 | GET /v1/models returns OpenRouter byte-for-byte (D-20 passthrough — no JSON re-serialize) | `test_get_models_cache_miss_fetches_and_caches` — `r.content == fake_payload` exact equality |
| 2 | 200 responses set Cache-Control: private, max-age=300 (RESEARCH §Q2 — overrides upstream no-store) | `test_get_models_cache_control_header` — explicit assertion that upstream `private, no-store` does NOT leak; client gets `private, max-age=300` |
| 3 | Within 15min TTL, subsequent GETs skip upstream (D-18) | `test_get_models_cache_hit_within_ttl_skips_upstream` — `route.call_count == 0` |
| 4 | After TTL expires, next GET refetches | `test_get_models_swr_on_upstream_failure` — pre-stale cache (>20min) triggers fetch attempt; cache is replaced on success path (covered by SWR test's failure branch + miss test's success branch) |
| 5 | Upstream failure + stale cache → serve stale + log (D-18 SWR) | `test_get_models_swr_on_upstream_failure` — 503 upstream → 200 stale + `openrouter_models.serving_stale` log |
| 6 | Upstream failure + no cache → 503 with Stripe envelope | `test_get_models_cold_start_failure_returns_503` — explicit 503 + envelope shape assertion |
| 7 | GZipMiddleware(minimum_size=1024) is outermost; SSE not compressed | Runtime check `app.user_middleware[0] == GZipMiddleware`; SSE non-compression covered by Wave 0 spike `test_gzip_sse_compat.py` (still passing 2/2) and existing route SSE tests in `test_agent_messages_sse.py` (passing) |
| 8 | Concurrent first-fetches deduped by asyncio.Lock | Code path verified by inspection: fast-path skips lock when fresh; slow-path always enters `async with state.models_cache_lock` and re-checks freshness under the lock. Acceptance criterion grep `async with state\.models_cache_lock` matches at line 55. |
| 9 | OpenRouter HTTP client on app.state with 10s timeout, lifecycle-managed | Grep `openrouter_http_client = httpx.AsyncClient` matches `timeout=httpx.Timeout(10.0, connect=5.0)`; teardown grep `openrouter_http_client.aclose()` matches in lifespan finally block. |

## Task Commits

Each task committed atomically (--no-verify because parallel-executor worktree):

1. **Task 1: Service module + route — get_models_payload + GET /v1/models** — `514de8f` (feat)
2. **Task 2: Wire lifespan + register router + add GZipMiddleware in main.py** — `35330e1` (feat)
3. **Task 3: Integration tests — cache miss/hit, SWR, 503, gzip header, cache-control** — `c3584b6` (test)

## Plan-Mandated Output Items

Per `23-05-PLAN.md` `<output>`:

- **Final ErrorCode constant used:** `ErrorCode.INFRA_UNAVAILABLE` — already present in `api_server/src/api_server/models/errors.py:49` (added by Phase 22b-05's pre-reservation). No new constant added.
- **Method used to access app.state in tests:** `async_client._transport.app.state` — the canonical pattern documented in `tests/auth/test_google_authorize.py:32` (works because the conftest `async_client` fixture wires the FastAPI app via `httpx.ASGITransport`, which exposes `.app`). The plan's example code referenced `async_client._app`, but that attribute is only set in the `started_api_server` fixture, NOT on the standard `async_client`. The `_state(async_client)` helper in `tests/routes/test_models.py:42-49` documents this.
- **Confirmed: GZipMiddleware is the LAST add_middleware call (outermost on response):** verified at line 434 of `main.py`; the only `add_middleware` lines after it are: (none). Runtime confirmation: `app.user_middleware[0].cls.__name__ == 'GZipMiddleware'` (Starlette stores last-added FIRST in `user_middleware` because `add_middleware` does `.insert(0, ...)`; index 0 IS the outermost runtime layer on the response path).
- **Sample compressed-vs-uncompressed payload sizes:** Not measured against live OpenRouter (api_server not running locally during this execution; only the testcontainer-backed test stack ran). The `test_get_models_gzip_header_when_requested` test builds a synthetic ~2.2KB JSON payload and confirms `content-encoding: gzip` is present on the wire — sufficient empirical proof that GZip engages above the 1024-byte threshold. Per RESEARCH §"D-25" the uncompressed OpenRouter `/api/v1/models` body is ~430KB and gzips to ~50KB (8.6x reduction); this can be confirmed post-deploy with `curl -s -o - http://localhost:8000/v1/models -H 'Accept-Encoding: gzip' | wc -c` once the api_server is up.

## Deviations from Plan

**None — plan executed exactly as written.** All 3 tasks completed in order; all grep-style acceptance criteria pass; all 6 tests green; no Rule 1/2/3 fixes were needed because:

- The plan's interfaces section correctly identified `ErrorCode.INFRA_UNAVAILABLE` as already present.
- The plan's reference to `async_client._app` in the test hint was a documentation slip — the real fixture (`async_client`) exposes `_transport.app.state`. This is documented as a *clarification* in `key-decisions` above, not a *deviation* — the plan's `<read_first>` block explicitly delegated this pattern lookup to "Inspect `tests/conftest.py` to find the right access path". The `_state()` helper makes the pattern explicit for future tests.

**Out-of-scope discovery (logged, not fixed):** `tests/spikes/test_truncate_cascade.py` errors during the regression sweep with `subprocess.CalledProcessError: alembic upgrade 005_sessions_and_oauth_users returned non-zero`. This is a pre-existing migration-spike issue independent of Plan 05 (Plan 05 touches no migrations / models / DB schema). Logged in `deferred-items.md` for Plan 23-08 or a separate maintenance ticket. Critically, the Wave 0 GZip×SSE spike (`test_gzip_sse_compat.py`) — the spike that DOES validate Plan 05's middleware ordering — passes 2/2.

## Authentication Gates

None encountered. The OpenRouter `/api/v1/models` endpoint is unauthenticated (D-19), and the test stack uses respx to stub the upstream HTTP call — no live network call made.

## Self-Check: PASSED

**Files created (verified `[ -f ... ]`):**
- `api_server/src/api_server/services/openrouter_models.py` — FOUND
- `api_server/src/api_server/routes/models.py` — FOUND
- `api_server/tests/routes/test_models.py` — FOUND

**Commits exist (verified `git log --oneline | grep <hash>`):**
- `514de8f` (Task 1) — FOUND
- `35330e1` (Task 2) — FOUND
- `c3584b6` (Task 3) — FOUND

**Test verification (`pytest tests/routes/test_models.py -x -m api_integration`):** 6/6 PASSED.

**Regression (`pytest tests/routes/ -m api_integration --ignore=tests/spikes`):** 58 passed, 8 skipped (Docker-required), 0 failed.

**Wave 0 GZip×SSE spike regression (`pytest tests/spikes/test_gzip_sse_compat.py`):** 2/2 PASSED — confirms GZipMiddleware addition does not break SSE non-compression invariant.
