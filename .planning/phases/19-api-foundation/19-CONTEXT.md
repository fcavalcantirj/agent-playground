---
phase: 19-api-foundation
status: ready_for_planning
gathered: 2026-04-16
source: /gsd-discuss-phase interactive questioning + 4-agent API critique synthesis
---

# Phase 19: API Foundation — Context

## Phase Boundary

FastAPI service at `api_server/` that wraps the hardened Python runner (`tools/run_recipe.py`) and exposes it over HTTP as the public API for web, app, CLI, and future clients. The API IS the product surface — everything else (frontend, terminal, billing) consumes it.

**NOT touching** the abandoned `api/` Go substrate — per CLAUDE.md banner.

## Implementation Decisions (locked)

### D-01: Idempotency-Key storage — Postgres from day 1
- Real Postgres. No in-memory dict, no SQLite. "No mocks, no stubs — real infra from day one for core substrate" (see `memory/feedback_no_mocks_no_stubs.md`).
- Table: `idempotency_keys(id, user_id, key, run_id, verdict_json, created_at, expires_at)` with 24h TTL.
- `POST /v1/runs` with `Idempotency-Key: <uuid>` header: if key exists for this user within TTL, return the original `run_id` + cached verdict instead of re-running.
- Driver: `asyncpg` (async), or `psycopg` 3.x with `psycopg_pool`. **No ORM** — raw SQL or `SQLAlchemy Core` only (matches CLAUDE.md "No GORM" posture applied to Python). Alembic for migrations.

### D-02: BYOK delivery — `Authorization: Bearer <provider-key>` per request
- Industry-standard for BYOK pass-through services (Cloudflare Workers AI, Replicate, OpenRouter itself).
- Server holds the key **in-process memory only** during a single run — never persisted, never logged.
- Passes to runner via the already-hardened `--env-file` code path (no `-e KEY=val` leaks).
- **Log-redaction middleware** (new) allowlists which headers get logged and explicitly drops `Authorization`, `X-Api-Key`, cookies, and request body.
- Widen `_redact_api_key()` in runner to also redact the literal key value (not just `VAR=value` pattern) — per runner-integration critique §5.
- Rejected alternatives: ephemeral run_token (overengineering for pre-auth phase), encrypted vault (requires auth which is deferred).

### D-03: Synchronous execution only — SSE deferred to Phase 19.5
- `POST /v1/runs` blocks until runner finishes, returns final verdict JSON. CLI-style.
- **SSE streaming** (`GET /v1/runs/{id}/events`), `run_cell_streaming()` refactor, keep-alive heartbeats, `request.is_disconnected() → docker kill` — all defer to **Phase 19.5** (new phase to be added after 19 completes).
- Clock-of-record: runner's `time.time()` at `run_cell` entry. No additional FastAPI-level timeouts that could cause orphan containers.
- Client must use reasonable HTTP read timeouts (≥ `smoke.timeout_s` + build slack). Document this.

### D-04: Split `/healthz` (thin) + `/readyz` (rich)
- `GET /healthz` → `{"ok": true}` always. Never hits Docker, never hits Postgres. For LB/uptime probes.
- `GET /readyz` → `{"ok": bool, "docker_daemon": bool, "postgres": bool, "schema_version": "ap.recipe/v0.1", "recipes_count": N, "concurrency_in_use": K}` for operator debugging + deploy gates.
- Both in OpenAPI schema; `/healthz` tagged as internal, `/readyz` tagged as operational.

### D-05: Rate limiting — soft per-user throttle via Postgres
- Per-user limits (per-IP as fallback when user is `anonymous`):
  - `POST /v1/runs`: 10/min
  - `POST /v1/lint`: 120/min
  - `GET /v1/*`: 300/min
- Table: `rate_limit_counters(user_id_or_ip, endpoint_bucket, window_start, count)` — sliding-window counter in Postgres.
- Not aggressive. Fair-use defaults. Comes with `Retry-After` headers on 429 responses.
- Rate-limit state lives in the same Postgres instance as idempotency + runs (no Redis in phase 19).

### D-06: Full platform DB schema — users + agent_instances + runs from day 1
- Even though auth is deferred, the schema is shaped for multi-user multi-agent from the start. Matches "alicerce" directive.
- Tables (Alembic migration 001):
  - `users (id uuid PK, email text null, display_name text, provider text null, created_at timestamptz)` — phase 19 seeds a single `anonymous` user row with `id = '00000000-0000-0000-0000-000000000001'`.
  - `agent_instances (id uuid PK, user_id uuid FK users, recipe_name text, model text, created_at, last_run_at, total_runs int)` — unique on `(user_id, recipe_name, model)`. One row per distinct agent a user has ever deployed. Each new `POST /v1/runs` either inserts or updates this.
  - `runs (id uuid PK (ULID-shaped), agent_instance_id uuid FK, prompt text, verdict text, category text, detail text, exit_code int, wall_time_s numeric, filtered_payload text, stderr_tail text, created_at, completed_at)`.
  - `idempotency_keys (id uuid PK, user_id uuid FK, key text, run_id uuid FK runs, verdict_json jsonb, created_at, expires_at)` — unique on `(user_id, key)`.
  - `rate_limit_counters (user_or_ip text, endpoint_bucket text, window_start timestamptz, count int)` — unique on `(user_or_ip, endpoint_bucket, window_start)`.
- FKs everywhere. When auth lands (phase 21+), the only change is swapping how `user_id` is resolved from request context; schema stays.

### D-07: `POST /v1/runs` semantics — one-shot execution + full DB persistence
- Body: `{recipe_name: string, prompt?: string, model?: string, no_lint?: bool, no_cache?: bool, metadata?: object}` — no inline recipe YAML accepted.
- Headers: `Authorization: Bearer <provider-key>` (required), `Idempotency-Key: <uuid>` (optional), `X-Request-Id: <uuid>` (optional, server mints if absent).
- Flow:
  1. Resolve user (anonymous seed for phase 19).
  2. Check idempotency table — return cached result if hit.
  3. Upsert `agent_instances(user_id, recipe_name, model)`.
  4. Mint ULID `run_id`, insert `runs` row with status `pending`.
  5. Acquire per-image-tag `asyncio.Lock` (prevents concurrent build of same image).
  6. Acquire global `asyncio.Semaphore(N)` (bounds concurrent docker runs; N from env, default 2).
  7. Call `run_cell()` via `asyncio.to_thread()` (runner is sync).
  8. Write verdict, category, detail, filtered_payload, stderr_tail, wall_time into `runs` row.
  9. Write idempotency record (if key provided).
  10. Return `{run_id, agent_instance_id, verdict, category, detail, wall_time_s, exit_code, filtered_payload, stderr_tail}`.
- `writeback_cell` — **always off** in the server. Only the CLI writes back wall_time to recipe files.
- Per-image-tag lock key: `image_tag` (e.g. `ap-recipe-hermes`). `ensure_image()` is serialized per-tag; different tags build in parallel.

### D-08: Full Hetzner deployment in phase 19
- Actually deployed to the Hetzner box. Live domain. TLS.
- Production artifacts:
  - `tools/Dockerfile.api` — multi-stage build, uvicorn + gunicorn workers entrypoint.
  - `deploy/docker-compose.prod.yml` — api_server + postgres services, named volumes for Postgres data, bind-mount for Docker socket (the runner shells out to `docker`).
  - `deploy/Caddyfile` — reverse proxy with automatic Let's Encrypt TLS.
  - `deploy/deploy.sh` — idempotent script: pull latest, migrate DB, roll the api_server container.
- Dev artifacts:
  - `docker-compose.dev.yml` — api_server + postgres for `make dev`.
  - `.env.example` updated.
- **Security posture:** Docker socket mount is the escape-hatch. Document it as a known trust boundary. Phase 19 runs on a single-tenant box; multi-tenant isolation (Sysbox, gVisor) is phase 22+ per CLAUDE.md stack spec.
- **Secrets:** `DATABASE_URL`, `AP_ENV`, never `OPENROUTER_API_KEY` baked into image (BYOK).

### D-09: Terminal WebSocket — deferred to phase 22+
- Out of scope. No `/v1/agents/{id}/terminal` route, even a stub.
- Current API is request/response only. Sessions that hold containers alive are a separate architecture track.

### D-10: OpenAPI docs exposure — curate + env-gated
- `include_in_schema=False` on internal health probes (`/healthz` is LB-only).
- `/docs` (Swagger UI) and `/redoc`: exposed when `AP_ENV=dev`, 404 in production.
- `/openapi.json`: always exposed (frontend type-gen needs it).
- Declare explicit `response_model=...` on every endpoint; don't leak incidental dict fields.
- Pin `openapi_version` and `servers: [{"url": "https://{domain}", "description": "..."}]` so generated SDK clients work.

## Carried-forward decisions (4-agent critique — all still apply)

These were locked before discuss-phase started. Keeping for the record:

- **Error envelope (Stripe shape):** `{"error": {"type": "lint_error", "code": "LINT_FAIL", "category": "LINT_FAIL", "message": "...", "param": "smoke.pass_if", "request_id": "..."}}`. `error.category` mirrors the runner's `Category` enum exactly.
- **`run_id` as ULID** (sortable by time). Emitted in response body + `X-Request-Id` header on every response.
- **Separate API version from schema version.** `/v1/` = API contract. `/v1/schemas/{apiVersion}` = JSON Schema registry. `GET /v1/schemas` lists all supported schema versions (today: `["ap.recipe/v0.1"]`).
- **Endpoints:** `GET /healthz`, `GET /readyz`, `GET /v1/schemas`, `GET /v1/schemas/{version}`, `GET /v1/recipes`, `GET /v1/recipes/{name}`, `POST /v1/recipes/lint`, `POST /v1/runs`, `GET /v1/runs/{id}` (fetch stored result).
- **`POST /v1/lint`** accepts arbitrary body up to 256 KB hard cap (YAML bombs are real). Also uses `ruamel.yaml` for parse + jsonschema for validation.
- **`POST /v1/runs` rejects inline recipe YAML.** Committed recipes only — host won't clone+build arbitrary user-supplied repos.
- **Runner concurrency:** per-image-tag `asyncio.Lock` (in-memory dict keyed by image_tag), global `asyncio.Semaphore` (bound from env `AP_MAX_CONCURRENT_RUNS`, default 2). Disk guard moves to the semaphore layer (check once per acquire).
- **`_yaml` module singleton:** replace with per-call `YAML()` instances in the server-consumed paths (load_recipe, writeback_cell). CLI keeps the singleton; server constructs fresh. Prevents ruamel-shared-state races under concurrent requests.
- **Log-redaction middleware:** allowlist on what to log (method, path, status, duration, request_id, user_agent, content-length). Drop everything else including `Authorization`, `X-Api-Key`, cookies, body.

## Deferred to future phases

- **Phase 19.5 (NEW — add after 19 ships):** SSE streaming (`GET /v1/runs/{id}/events`), `run_cell_streaming()` refactor, keep-alive heartbeats, `request.is_disconnected() → docker kill`.
- **Phase 21+:** Real auth (Google + GitHub OAuth via authlib/authomatic Python equivalent of goth), per-user API keys, replacing `anonymous` seed with real identity.
- **Phase 22+:** WebSocket terminal route, ttyd-in-container, persistent sessions, stdio bridge for chat.
- **Phase 23+:** `runtime.limits` with token/turn/cost budgets (smuggled into argv today).
- **Later:** Stripe billing, metering proxy, GPU declaration, capability advertisement block, `known_issues[]` collapse, richer `verified_cells[]` with typed metrics.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema + runner (authoritative)
- `tools/ap.recipe.schema.json` — JSON Schema v0.1.1 (the API contract)
- `docs/RECIPE-SCHEMA.md` — narrative spec
- `tools/run_recipe.py` — the Python runner being wrapped
- `recipes/*.yaml` — 5 committed recipes to expose via `GET /v1/recipes`

### Prior phase artifacts
- `.planning/phases/18-schema-maturity/18-CONTEXT.md` — schema maturity decisions
- `.planning/phases/18-schema-maturity/18-VERIFICATION.md` — what shipped
- `memory/feedback_no_mocks_no_stubs.md` — golden rule for platform infra choices
- `memory/feedback_robustness.md` — prior robustness rule

### Project stack guidance
- `CLAUDE.md` §Technology Stack — NOT Go + Echo for phase 19 (we're going Python); still informs Python-analog choices (no ORM, coder/websocket equivalent when WS lands, etc.)
- `CLAUDE.md` banner — do NOT touch `api/`, `deploy/`, `test/`

### Go substrate (reference only — DO NOT modify)
- `api/internal/handler/devauth.go` — session cookie pattern (for later port if Python auth equivalent needed)
- `api/internal/middleware/auth.go` — `SessionProvider` interface pattern

### External refs
- FastAPI docs (OpenAPI auto-gen conventions)
- Stripe API Reference (error envelope, idempotency, run_id conventions)
- Anthropic Messages API (SSE event naming patterns — for Phase 19.5)
- Alembic migration patterns
- Caddy Caddyfile reference (TLS)

## Claude's Discretion

- Choice of async Postgres driver (`asyncpg` vs `psycopg` 3 with `psycopg_pool`). Planner can decide.
- Migration tool (Alembic vs plain `sqlalchemy.schema` + version table). Alembic is stdlib-ish; plain is leaner. Planner decides.
- Sliding-window algorithm for rate limiter (token bucket vs fixed window + soft cooldown vs leaky bucket). Planner decides based on simplicity.
- ULID implementation (pick a Python library or inline). Planner decides.
- Hetzner deploy specifics: which subdomain (`api.agentplayground.dev` vs `agentplayground.dev/api/*`)? Which CI pipeline to trigger deploys? Planner decides.
- `POST /v1/lint` response shape on errors: 200 with `{errors: [...]}` body, or 400 with error envelope? Planner decides; document in OpenAPI.

## Critical Sequencing Constraint

Phase 19 is large. Expect the planner to break this into 5–7 plans with real dependencies:

1. Database schema + Alembic migration (foundation)
2. FastAPI skeleton + /healthz + /readyz + OpenAPI config
3. Recipe endpoints (`GET /v1/recipes`, `GET /v1/recipes/{name}`, `GET /v1/schemas`, `POST /v1/lint`) — read-only, no runner calls
4. Run endpoint (`POST /v1/runs`, `GET /v1/runs/{id}`) — the load-bearing one, wraps runner
5. Rate limiter + idempotency middleware
6. Log-redaction middleware + `_yaml` singleton fix + widen `_redact_api_key`
7. Hetzner deployment (Dockerfile + compose + Caddyfile + deploy.sh)

TDD where applicable. Real Postgres in tests via `embedded-postgres`-equivalent (or `testcontainers` if simpler in Python), NOT mocks for the DB layer per D-01.

## Success Criteria (what must be TRUE after phase)

1. `curl https://<live-domain>/healthz` from the internet returns `{"ok": true}`.
2. `curl https://<live-domain>/readyz` returns the rich envelope with `postgres: true` and `docker_daemon: true`.
3. `curl https://<live-domain>/v1/schemas` returns `["ap.recipe/v0.1"]`.
4. `curl https://<live-domain>/v1/recipes` returns a JSON list of the 5 committed recipes with metadata.
5. `curl -X POST https://<live-domain>/v1/runs -H "Authorization: Bearer $OPENROUTER_API_KEY" -H "Idempotency-Key: $(uuidgen)" -d '{"recipe_name":"hermes","prompt":"who are you?","model":"openai/gpt-4o-mini"}'` returns a verdict JSON with `"category": "PASS"`.
6. A second identical POST with the same `Idempotency-Key` within 24h returns the same `run_id` WITHOUT re-running.
7. 50 concurrent `POST /v1/runs` requests do not spawn 50 docker containers — concurrency semaphore bounds it to N.
8. `psql $DATABASE_URL -c 'select count(*) from runs'` shows the runs were persisted.
9. Rate limit kicks in: 11th `POST /v1/runs` from the same anonymous IP within 1 minute returns HTTP 429 with `Retry-After`.
10. `pytest` (default suite) all green. Integration tests (new marker `api_integration`) exercise the full HTTP → runner → Docker → Postgres flow against a live `postgres` container.
11. All existing runner unit tests (171 from phase 18) still pass unchanged — no regression in runner code path.
12. `/docs` returns 404 in production, 200 in dev.
13. `/openapi.json` fetched and fed to `openapi-typescript` produces a valid TypeScript client.

---

*Phase: 19-api-foundation*
*Context gathered: 2026-04-16 via /gsd-discuss-phase + 4-agent critique synthesis*
