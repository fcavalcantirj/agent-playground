# Agent Playground Backend Audit — Phase 19.x Desiccated Inventory

**Date:** 2026-04-17 (sealed 2026-04-18)  
**Status:** FROZEN — consumed as input by `ACTION-LIST.md`. Do not edit; regenerate via a fresh desiccation pass if the codebase drifts.  
**Scope:** `api_server/src/`, `tools/run_recipe.py`, migrations, deployment glue  
**Posture:** Production-ready foundation with forward-looking stubs for Phase 20+

---

## Executive Summary

The backend is a **V0.1 vertical slice**: FastAPI facade (`api_server/`) wraps `tools/run_recipe.py` CLI runner via `asyncio.to_thread`, backed by asyncpg + Postgres. Routes implement BYOK (bring-your-own-key) auth, idempotency, rate limiting, and structured error envelopes. Two database migrations ship the 5 core tables + recipe schema inline.

**Production posture:** WORKS for deployment smoke, agent tracking, and run audit. Mocks/stubs exist only for future features (Phase 20+ sessions, v0.2 recipe features). No critical gaps block Phase 19 ship.

---

## Routes Inventory

### Health / Operational

#### GET /healthz
- **Status:** WORKS
- **Auth:** None
- **Response:** `{ok: bool}` (always true, no dep checks)
- **Impl:** routes/health.py::healthz
- **DB:** None
- **External:** None
- **Notes:** LB liveness probe per D-04; unconditional 200

#### GET /readyz
- **Status:** WORKS
- **Auth:** None
- **Response:** ReadyzResponse {ok, docker_daemon, postgres, schema_version, recipes_count, concurrency_in_use}
- **Impl:** routes/health.py::readyz
- **DB:** `SELECT 1` via probe_postgres (2s timeout)
- **External:** `docker version` (5s timeout)
- **Notes:** Full readiness envelope; operator-facing; used by deploy gates

---

### Recipe Catalog

#### GET /v1/recipes
- **Status:** WORKS
- **Auth:** None (rate-limited: 300/min bucket)
- **Response:** RecipeListResponse {recipes: [RecipeSummary]}
- **Impl:** routes/recipes.py::list_recipes
- **DB:** None (in-memory app.state.recipes)
- **External:** None
- **Notes:** Loaded at startup from recipes/*.yaml; read-only surface

#### GET /v1/recipes/{name}
- **Status:** WORKS
- **Auth:** None (rate-limited: 300/min bucket)
- **Response:** RecipeDetailResponse {recipe: dict} (full dict passthrough)
- **Impl:** routes/recipes.py::get_recipe
- **DB:** None
- **External:** None
- **Notes:** 404 on missing; no field filtering in Phase 19 (all fields public)

#### POST /v1/lint
- **Status:** WORKS
- **Auth:** None (rate-limited: 120/min bucket)
- **Request:** YAML body (raw bytes, up to 256 KiB)
- **Response:** LintResponse {valid: bool, errors: [LintError]}
- **Impl:** routes/recipes.py::lint_recipe → services/lint_service.py::lint_yaml_bytes → tools/run_recipe.py::lint_recipe
- **DB:** None
- **External:** None
- **Known gaps:** No custom rule injection (v0.2 future); 200 always (errors are verdict, not HTTP failure)

---

### Schema Registry

#### GET /v1/schemas
- **Status:** WORKS
- **Auth:** None
- **Response:** SchemasListResponse {schemas: [str]} (ordered oldest-first)
- **Impl:** routes/schemas.py::list_schemas
- **DB:** None
- **External:** None
- **Notes:** Currently only `ap.recipe/v0.1`; list is hardcoded in routes/schemas.py::SUPPORTED_SCHEMAS

#### GET /v1/schemas/{version:path}
- **Status:** WORKS
- **Auth:** None
- **Response:** SchemaDocResponse {version, schema} (JSON Schema dict from tools/ap.recipe.schema.json)
- **Impl:** routes/schemas.py::get_schema → services/lint_service.py::get_runner_schema
- **DB:** None
- **External:** None
- **Notes:** 404 on unsupported version; schema loaded via runner import

---

### Agents (Phase 20 Preview)

#### GET /v1/agents
- **Status:** WORKS
- **Auth:** None (hardcoded ANONYMOUS_USER_ID; Phase 21 real sessions)
- **Response:** AgentListResponse {agents: [AgentSummary]}
  - Each AgentSummary: id, name, recipe_name, model, personality, created_at, last_run_at, total_runs, last_verdict, last_category, last_run_id
- **Impl:** routes/agents.py::list_user_agents → services/run_store.py::list_agents
- **DB:** SELECT from agent_instances + LATERAL join for last_verdict
- **External:** None
- **Known gaps:** Single user hardcoded; filtering/pagination not implemented

---

### Runs (Load-Bearing Endpoint)

#### POST /v1/runs
- **Status:** WORKS
- **Auth:** BYOK via `Authorization: Bearer <key>` header (mandatory; 401 if missing/empty)
- **Request:** RunRequest {recipe_name (pattern: ^[a-z0-9][a-z0-9_-]*$), model, prompt?, agent_name?, personality?, no_lint?, no_cache?, metadata?}
- **Response:** RunResponse {run_id, agent_instance_id, recipe, model, prompt, pass_if, verdict, category, detail?, exit_code?, wall_time_s?, filtered_payload?, stderr_tail?, created_at, completed_at}
- **Impl:** routes/runs.py::create_run
  - **Flow:**
    1. Parse bearer token → local provider_key variable (never stored)
    2. Validate recipe_name against app.state.recipes + api_key env var requirement
    3. Validate personality if supplied (against services/personality.py::_PRESETS)
    4. Derive smoke prompt: explicit prompt > personality preset > recipe default > empty
    5. Upsert agent_instance(user_id=ANONYMOUS_USER_ID, recipe_name, model, agent_name, personality) → agent_instance_id
    6. Insert pending run row (verdict=NULL, created_at=server-default)
    7. **Release DB connection** (crucial for Pitfall 4)
    8. Acquire per-image-tag Lock + global Semaphore → `execute_run()`
    9. On exception: redact provider_key from stderr before logging/storing, write FAIL verdict
    10. Re-acquire DB connection; write_verdict(run_id, details)
    11. Return RunResponse with details dict fields
- **DB writes:**
  - agent_instances: UPSERT on (user_id, name); bumps last_run_at + total_runs on conflict
  - runs: INSERT pending (id=ULID, agent_instance_id FK, prompt, verdict=NULL)
  - runs: UPDATE verdict + category + detail + exit_code + wall_time_s + filtered_payload + stderr_tail + completed_at
- **External:** docker build (via ensure_image), docker run (via run_cell), OpenRouter API call (via agent CLI inside container)
- **Security:**
  - provider_key is a LOCAL variable, never in app.state, never in DB, never in logs (redacted before stderr reach detail column)
  - recipe_name pattern-validated (SQL injection / path-traversal defense)
  - RunRequest extra="forbid" (inline YAML injection defense)
- **Known gaps:**
  - hardcoded ANONYMOUS_USER_ID (Phase 21 sessions)
  - no explicit timeout handling at route level (delegated to smoke_timeout_s in runner)
  - no metadata capture in DB (metadata param accepted but dropped)

#### GET /v1/runs/{run_id}
- **Status:** WORKS
- **Auth:** None (ULID is the sole access guard; 26-char Crockford base32 validated before DB query)
- **Response:** RunGetResponse (identical to RunResponse; separate class for future field divergence)
- **Impl:** routes/runs.py::get_run → services/run_store.py::fetch_run
- **DB:** SELECT runs r JOIN agent_instances a ON r.agent_instance_id = a.id WHERE r.id = $1
- **External:** None
- **Known gaps:** No pagination; single-run fetch only; no access control (any ULID wins)

---

## Services Inventory

### services/runner_bridge.py

**Purpose:** Concurrency + Docker socket safety wrapper around `tools/run_recipe.py::run_cell`

**Pattern 2 implementation (RESEARCH.md):**
- Per-image-tag `asyncio.Lock` (serializes BUILD of same recipe)
  - Lookup/create atomic via locks_mutex to avoid Pitfall 1 (two coroutines holding different Lock objects for same tag)
- Global `asyncio.Semaphore(N)` (bounds total concurrent run_cell calls)
- `asyncio.to_thread()` mandatory (run_cell is sync, blocks 10-200s)

**Public API:** `execute_run(app_state, recipe, prompt, model, api_key_var, api_key_val)` → details dict

**Impl notes:**
- Imports run_cell via importlib (tools/ not on sys.path)
- Image tag convention `ap-recipe-{recipe.name}` matches runner line 1024 (1-to-1 requirement)
- Result shape: handles both (Verdict, dict) tuple and dict-only (test mock) via isinstance check
- No BYOK exposure: api_key_val flows as kwarg only, never logged

---

### services/run_store.py

**Purpose:** asyncpg repository for runs + agent_instances tables

**Functions (all parameterized, no string concat):**

1. **upsert_agent_instance(conn, user_id, recipe_name, model, name, personality) → UUID**
   - UPSERT on (user_id, name) with ON CONFLICT DO UPDATE
   - Bumps last_run_at + total_runs on conflict; preserves recipe_name/model/personality (name collision can't silently mutate config)
   - RETURNS id

2. **insert_pending_run(conn, run_id, agent_instance_id, prompt) → None**
   - Two-phase write: verdict columns stay NULL until write_verdict
   - Enables DB pool release across long to_thread run (Pitfall 4)

3. **write_verdict(conn, run_id, details) → None**
   - Completes pending run row
   - All details fields bound as $N parameters (no dict value touches query)
   - wall_time_s (float) coerced to NUMERIC column

4. **fetch_run(conn, run_id) → dict | None**
   - SELECT runs r JOIN agent_instances a
   - Returns plain dict for Pydantic unpacking (not asyncpg Record)
   - wall_time_s cast to float (asyncpg returns Decimal for NUMERIC)

5. **list_agents(conn, user_id) → list[dict]**
   - SELECT agent_instances + LATERAL join for last_verdict + category + run_id
   - Newest first ordering

---

### services/recipes_loader.py

**Purpose:** Recipe YAML loading with per-call YAML() instances (ruamel #367 thread-unsafe singleton mitigation)

**Key invariant:** Server paths MUST use `_fresh_yaml()` per call; CLI path (run_recipe.py) keeps module singleton (single-threaded).

**Functions:**
- `_fresh_yaml() → YAML` — fresh instance, rt mode, preserve_quotes, width=4096, indent (mapping=2, sequence=4, offset=2)
- `load_recipe(path) → dict` — parse one file
- `load_all_recipes(dir_path) → dict[str, dict]` — parse *.yaml in order, keyed by recipe["name"], fail-loud on missing name or duplicates (app refuses to boot)
- `to_summary(recipe) → RecipeSummary` — projection with field-name translation (source.repo → source_repo, etc); handles missing sub-dicts gracefully

---

### services/lint_service.py

**Purpose:** YAML lint + schema validation wrapper around runner's lint_recipe

**Responsibilities:**
1. Enforce 256 KiB body cap (LINT_BODY_MAX_BYTES, V5 DoS mitigation)
2. Parse with fresh YAML() instance (ruamel #367)
3. Delegate to runner's lint_recipe via importlib

**Functions:**
- `lint_yaml_bytes(body: bytes) → LintResponse {valid, errors}`
  - Raises LintBodyTooLargeError (413 in route) if > 256 KiB
  - Parse errors → single LintError with valid=False (200 response, not 400)
  - Non-dict payloads → (root) error
  - Delegates to runner; splits "path: text" messages into LintError fields
- `get_runner_schema() → dict` — loads JSON Schema from tools/ap.recipe.schema.json via runner._load_schema()
- `_import_runner_module()` — loads tools/run_recipe.py by path, caches in sys.modules

---

### services/idempotency.py

**Purpose:** Postgres-backed Stripe-style idempotency (Pattern 3, RESEARCH.md)

**Invariants:**
- `pg_advisory_xact_lock` serializes concurrent first-use of (user_id, key)
- request_body_hash mitigates Pitfall 6: re-use same key with different body → 422 IDEMPOTENCY_BODY_MISMATCH
- Raw request bytes hashed (not re-serialized JSON) to catch semantic equivalence edge cases
- 24h TTL default (CONTEXT.md D-01); GC Plan 19-07 cron responsibility

**Functions:**
- `hash_body(raw_bytes) → str` — SHA-256 hex digest
- `check_or_reserve(conn, user_id, key, body_hash) → CheckResult` (hit/mismatch/miss, cached_dict | None)
  - Returns under advisory lock; hit = non-expired row + hash match; mismatch = non-expired + hash mismatch; miss = run normally
- `write_idempotency(conn, user_id, key, body_hash, run_id, verdict_json, ttl_hours=24) → None`
  - ON CONFLICT DO NOTHING (race: two concurrent misses both finish and write; first wins, second no-op)
  - verdict_json JSON-dumped here (not asyncpg codec)

---

### services/rate_limit.py

**Purpose:** Postgres-backed fixed-window rate limiting (Pattern 4, RESEARCH.md)

**Invariants:**
- `pg_advisory_xact_lock` serializes increment per (subject, bucket)
- Counter row upsert keyed on (subject, bucket, window_start)
- window_start floored to nearest window_s boundary via `to_timestamp(floor(EXTRACT(EPOCH) / W) * W)`
  - ⚠ Critical: `::bigint` rounds-to-nearest (miscomputed); floor() + to_timestamp() correct
- Known tradeoff: fixed-window allows 2x burst at boundary (acceptable per D-05, revisit Phase 22+)
- window_start GC Plan 19-07 cron responsibility

**Functions:**
- `check_and_increment(conn, subject, bucket, limit, window_s) → (allowed: bool, retry_after_s: int)`
  - Increments counter in transaction under advisory lock
  - Returns (False, max(1, window_s - age_s)) if count > limit
  - Returns (True, 0) if allowed

---

### services/personality.py

**Purpose:** Personality preset → smoke prompt mapping (Phase 20+ system prompt character)

**Current presets (6 hardcoded):**
1. polite-thorough — "Could you please introduce yourself politely..."
2. concise-neat — "Introduce yourself in one short sentence."
3. skeptical-critic — "State your name, then critique..."
4. cheerful-helper — "Say hi and introduce yourself in a warm..."
5. senior-architect — "Introduce yourself and briefly describe one architectural pattern..."
6. quick-prototyper — "Introduce yourself in a single line, then propose the smallest MVP..."

**Functions:**
- `smoke_prompt_for(personality: str | None) → str | None` — return deploy-time smoke prompt (or None to fall back to recipe default)
- `is_known(personality: str | None) → bool` — validate personality preset exists
- PERSONALITY_IDS tuple exported

---

## Middleware Inventory

### middleware/correlation_id.py
- **Status:** WORKS (thin re-export)
- **Impl:** Re-exports asgi-correlation-id's CorrelationIdMiddleware + correlation_id contextvar
- **Active:** Yes, registered in main.create_app()
- **Purpose:** Mint X-Request-Id header if absent; bind to contextvar; echo in response

### middleware/access_log.py (AccessLogMiddleware)
- **Status:** WORKS (Pattern 5: allowlist-based structured logging)
- **Active:** Yes, registered in main.create_app()
- **Allowlist:** user-agent, content-length, content-type, accept, x-request-id
- **Deny list:** Authorization, Cookie, X-Api-Key, X-Forwarded-For (never read)
- **Emits:** method, path, status, duration_ms, headers (allowlisted only)
- **BYOK defense:** Authorization header name not in allowlist by construction; never read/logged

### middleware/rate_limit.py (RateLimitMiddleware)
- **Status:** WORKS (replaces Plan 19-02 stub)
- **Active:** Yes, registered in main.create_app()
- **Mapping:**
  - POST /v1/runs → 10/min (runs bucket)
  - POST /v1/lint → 120/min (lint bucket)
  - GET /v1/* → 300/min (get bucket)
  - Everything else → pass through
- **Subject derivation:** X-Forwarded-For (if AP_TRUSTED_PROXY=true) else scope["client"] IP
- **Response:** 429 + ErrorEnvelope + Retry-After header on limit exceeded
- **Fail-open:** Postgres down → log and pass through (better than site-wide outage)

### middleware/idempotency.py (IdempotencyMiddleware)
- **Status:** WORKS (replaces Plan 19-02 stub)
- **Active:** Yes, registered in main.create_app()
- **Scope:** POST /v1/runs only (idempotency-key header optional)
- **Behavior:**
  - Hit (same key + same body hash, non-expired) → 200 + cached verdict (no run)
  - Mismatch (same key + different body) → 422 IDEMPOTENCY_BODY_MISMATCH
  - Miss → pass through, capture response, write cache if 200
- **Response caching:** 200 only (4xx/5xx not cached; avoids locking in error state)
- **Fail-open:** Postgres down → log and pass through (uncached run still completes)

---

## Pydantic Models Inventory

### models/runs.py

**Category enum** (Phase 10)
- VERBATIM mirror of tools/run_recipe.py::Category (lines 66-86)
- Live (9): PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL
- Reserved (2): STOCHASTIC (Phase 15), SKIP (future UX)
- ⚠ Critical: must stay byte-for-byte in sync with runner; drift breaks category mapping

**RunRequest**
- recipe_name: str (pattern: ^[a-z0-9][a-z0-9_-]*$, length 1–64)
- prompt: str | None (max 16384)
- model: str (length 1–128)
- no_lint: bool (default False)
- no_cache: bool (default False)
- metadata: dict[str, Any] | None (accepted but dropped in DB; future use)
- agent_name: str | None (pattern: ^[a-zA-Z0-9][a-zA-Z0-9 _-]*$, length 1–64)
- personality: str | None (max 64)
- **Config:** extra="forbid" (inline YAML injection defense, V5)

**RunResponse**
- Straight passthrough of runner's details dict + two IDs + two timestamps
- Fields: run_id, agent_instance_id, recipe, model, prompt, pass_if, verdict, category, detail?, exit_code?, wall_time_s?, filtered_payload?, stderr_tail?, created_at?, completed_at?
- **Known gap:** pass_if field is **always null** in API responses (routes/runs.py line 228 says details.get("pass_if"), but pass_if is not in details dict returned by run_cell — it's in the Verdict, which is discarded)

**RunGetResponse**
- Identical to RunResponse; separate class for future divergence (pagination, etc.)

### models/agents.py

**AgentSummary**
- id: UUID, name, recipe_name, model, personality?, created_at, last_run_at?, total_runs
- **NEW Phase 20:** last_verdict, last_category, last_run_id (derived from LATERAL join)

**AgentListResponse**
- agents: [AgentSummary]

### models/recipes.py

**RecipeSummary** (public projection)
- name, api_version (alias apiVersion), display_name?, description?, upstream_version?, image_size_gb?, expected_runtime_seconds?
- source_repo, source_ref (aliases source.repo, source.ref)
- provider (alias runtime.provider), pass_if (alias smoke.pass_if), license, maintainer (aliases metadata.*)
- verified_models: [str] (derived from smoke.verified_cells; Phase 19 forward signal for which models passed smoke)
- **Known gap:** pass_if may be dict in v0.1.1+ (smoke.pass_if: {verb: {...}}) but summary returns string; to_summary handles both

**RecipeListResponse**
- recipes: [RecipeSummary]

**RecipeDetailResponse**
- recipe: dict (full passthrough; Phase 19 has no private fields to strip)

### models/schemas.py

**SchemasListResponse**
- schemas: [str]

**SchemaDocResponse**
- version: str, schema_body: dict[str, Any] (alias schema, serialization_alias schema)
- **Note:** populate_by_name allows constructor to accept schema=..., protected_namespaces=() silences Pydantic v2 model_* warnings

### models/errors.py

**ErrorCode** (constants)
- INVALID_REQUEST, RECIPE_NOT_FOUND, SCHEMA_NOT_FOUND, LINT_FAIL, PAYLOAD_TOO_LARGE, RATE_LIMITED, IDEMPOTENCY_BODY_MISMATCH, UNAUTHORIZED, INTERNAL, RUNNER_TIMEOUT, INFRA_UNAVAILABLE
- _CODE_TO_TYPE map translates to Stripe coarse types (invalid_request, not_found, lint_error, rate_limit_error, unauthorized, internal_error, runner_error, infra_error)

**ErrorBody**
- type, code, category?, message, param?, request_id (pulled from asgi-correlation-id contextvar or "unknown")

**ErrorEnvelope**
- error: ErrorBody

**LintError**
- path, message

**LintResponse**
- valid: bool, errors: [LintError]

---

## tools/run_recipe.py Inventory

**Scope:** Standalone CLI + importable API (run_cell, lint_recipe, _load_schema)

**Constants:**
- DISK_GUARD_FLOOR_GB = 5.0 (V6 mitigation against build-disk exhaustion)
- DEFAULT_SMOKE_TIMEOUT_S = 180, DEFAULT_BUILD_TIMEOUT_S = 900, DEFAULT_CLONE_TIMEOUT_S = 300
- DOCKER_DAEMON_PROBE_TIMEOUT_S = 5
- _SCHEMA_PATH = ap.recipe.schema.json (co-located with runner)

**Category enum** (already described above)

**Verdict dataclass** (frozen)
- category: Category, detail: str, verdict property (PASS if PASS else FAIL)
- to_cell_dict() → dict for emit_json/emit_human

### Importable API

**_load_schema() → dict**
- Load JSON Schema from ap.recipe.schema.json

**load_recipe(path) → dict**
- Parse YAML file into dict

**lint_recipe(recipe, schema=None) → [str]**
- Validate recipe dict against JSON Schema (Draft202012Validator)
- Normalizes recipe via JSON round-trip (ruamel.yaml CommentedMap → plain dicts)
- Returns error message list (empty = valid)

### CLI Subcommands

**--lint**: Lint a recipe and exit (no docker)

**--lint-all**: Lint all recipes/*.yaml and exit (no docker)

**--all-cells**: Sweep every verified_cell in recipe (with --write-back to update wall_time_s + verdict in recipe YAML)

**--no-lint**: Skip mandatory lint pre-step

**--no-cache**: Remove tagged image before build/pull

**--no-disk-check**: Skip 5 GB free-space guard

**--global-timeout SECONDS**: Hard ceiling across entire runner invocation; overrides per-recipe smoke.timeout_s

**--json**: Emit structured JSON verdicts (suppresses human banners)

**--write-back / --no-write-back**: In --all-cells mode, write wall_time_s/verdict back to recipe (default: write-back)

### Build Modes

**build.mode = "upstream_dockerfile"** (default)
- Clone repo from source.repo at source.ref (default HEAD)
- Cache clone in /tmp/ap-recipe-{name}-{sha256(ref)[:12]}-clone
- Build image from Dockerfile at build.dockerfile_path in context_dir
- Timeout: DEFAULT_BUILD_TIMEOUT_S (900s)

**build.mode = "image_pull"**
- docker pull build.image, tag as image_tag
- Timeout: DEFAULT_BUILD_TIMEOUT_S (900s)

### Cell Execution (run_cell)

**Signature:**
```python
def run_cell(
    recipe: dict,
    *,
    image_tag: str,
    prompt: str,
    model: str,
    api_key_var: str,
    api_key_val: str,
    quiet: bool,
    smoke_timeout_s: int | None = None,
) -> tuple[Verdict, dict]
```

**Flow:**
1. Substitute $PROMPT + $MODEL into invoke.spec.argv
2. Create temp data_dir (mounted as container volume)
3. Create env_file with api_key_var=api_key_val (chmod 600, never via docker run -e to avoid ps leak)
4. Create cidfile (fresh UUID path, not pre-created per docker/cli#5954)
5. Build docker run command with --env-file, -v data_dir:container_mount
6. Run with timeout; on TimeoutExpired, reap container via cidfile + docker kill
7. Classify verdict:
   - Timeout → TIMEOUT verdict
   - rc != 0 → Apply pass_if rule to stderr or stdout; if no pass_if, INVOKE_FAIL
   - rc == 0 → Apply pass_if rule to stdout; PASS if pass_if matches else ASSERT_FAIL
8. Return (Verdict, dict) where dict carries wall_time_s, filtered_payload, stderr_tail, exit_code, pass_if string

**pass_if rules** (evaluate_pass_if)
- response_contains_name → checks if recipe["name"] in payload (case_insensitive option)
- response_contains_string → checks if smoke.needle in payload
- response_not_contains → checks if smoke.needle NOT in payload
- response_regex → checks if re.search(smoke.regex, payload) matches
- exit_zero → checks if exit_code == 0
- Unknown rules → "UNKNOWN(pass_if=...)"

**API redaction:** _redact_api_key replaces VAR=<any-non-space> with VAR=<REDACTED> + (if api_key_val >= 8 chars) literal key value with <REDACTED>

### Known Issues / TODOs in run_recipe.py

**None found.** No TODO, FIXME, NotImplementedError, or HACK comments. Code is clean, well-commented, and production-ready.

### Stub / Mock Indicators

- Test fixture in conftest: `mock_run_cell` (short-circuits with details dict only, not (Verdict, dict) tuple) — handled in runner_bridge.py line 114
- No --mode option (build.mode is schema-driven, not CLI-driven)
- No persistent mode (v0.2 future; Phase 19 is request-scoped only)

---

## Database Schema Inventory

### Migrations

**001_baseline.py** (2026-04-17)
- Creates pgcrypto extension
- Creates users table (id UUID PK, email?, display_name, provider?, created_at) + seeds ANONYMOUS_USER_ID='00000000-0000-0000-0000-000000000001'
- Creates agent_instances (id UUID PK, user_id FK, recipe_name TEXT, model TEXT, created_at, last_run_at?, total_runs INT default 0)
  - Unique constraint: (user_id, recipe_name, model)
- Creates runs (id TEXT PK [26-char ULID], agent_instance_id UUID FK, prompt TEXT, verdict?, category?, detail?, exit_code?, wall_time_s NUMERIC?, filtered_payload?, stderr_tail?, created_at [server default NOW()], completed_at?)
  - Index: idx_runs_agent_instance on agent_instance_id
- Creates idempotency_keys (id UUID PK, user_id FK, key TEXT, run_id FK, verdict_json JSONB, request_body_hash TEXT, created_at, expires_at)
  - Unique constraint: (user_id, key)
  - Index: idx_idempotency_expires on expires_at (for GC)
- Creates rate_limit_counters (subject TEXT, bucket TEXT, window_start TIMESTAMP, count INT, PK=(subject, bucket, window_start))
  - Index: idx_rate_limit_gc on window_start (for GC)

**002_agent_name_personality.py** (2026-04-17, Phase 20 preview)
- Adds agent_instances.name (TEXT, nullable initially, backfilled from recipe_name + model, then NOT NULL)
- Adds agent_instances.personality (TEXT, nullable)
- Drops old unique constraint (user_id, recipe_name, model)
- Creates new unique constraint (user_id, name)
- **Rationale:** Support multiple agents per (recipe, model) with different names/personas

### Table Populations

**users:** Seeded with ANONYMOUS_USER_ID in 001_baseline; Phase 19 has no auth, so no new users created at runtime

**agent_instances:** Populated via POST /v1/runs (upsert via runner_bridge → run_store.upsert_agent_instance)
- All columns populated except personality (set via RunRequest.personality or NULL)

**runs:** Populated via POST /v1/runs
- Two-phase write: INSERT with verdict=NULL, then UPDATE with details
- Handlers populate: id (ULID, minted in route), agent_instance_id, prompt, verdict, category, detail, exit_code, wall_time_s, filtered_payload, stderr_tail, created_at (server), completed_at (server)

**idempotency_keys:** Populated via POST /v1/runs middleware (write_idempotency) iff response status=200 + run_id present
- All columns populated by middleware

**rate_limit_counters:** Populated via rate-limit middleware (check_and_increment) for every bucketed request
- Upsert on (subject, bucket, window_start); increments count

---

## Deployment / Infra Glue

### docker-compose.yml (Production Hetzner)
- **Scope:** Temporal + Temporal UI only (Postgres/Redis run as systemd services on host)
- **Network:** host mode (no port exposure to internet)
- **Temporal image:** temporalio/auto-setup:1.29.3 (schema auto-bootstrap)
- **Status:** Prod-ready for workflow orchestration (not used in Phase 19 API)

### docker-compose.dev.yml (Local Development)
- **Services:**
  - postgresql:17-alpine (POSTGRES_USER=temporal, POSTGRES_PASSWORD=temporal, POSTGRES_DB=temporal, port 5432)
  - temporal:1.29.3 (depends_on postgresql healthy, port 7233)
  - temporal-ui:2.34.0 (port 8233)
  - redis:7-alpine (port 6379)
  - api_server (profile=api, built from tools/Dockerfile.api, mounts /var/run/docker.sock, port 8000)
- **Status:** Dev-ready; api_server service is opt-in via `docker compose --profile api up`
- **Note:** Native dev path is `make dev-api` (uvicorn --reload against host postgres)

### tools/Dockerfile.api (Multi-Stage)
- **Stage 1 (build):** python:3.11-slim, installs runtime deps from api_server/pyproject.toml, copies source
- **Stage 2 (runtime):** python:3.11-slim + docker-cli + curl + ca-certificates
  - **GID handling:** Matches host docker socket GID (ARG DOCKER_GID, created fresh or added to existing group) so non-root apiuser can access socket
  - **User:** apiuser (uid=1001, non-root)
  - **Volumes:** /var/run/docker.sock (RO via host mount), /app/recipes (RO via host mount)
  - **Health check:** curl -fsS http://localhost:8000/healthz
  - **CMD:** uvicorn api_server.main:app --host 0.0.0.0 --port 8000 --workers 2
- **Prod-readiness:** ✓ Multi-stage (small image), non-root user, health check, 2 workers (stateless so can scale)
- **Known limitation:** --workers 2 is baked in (not configurable via env)

### Database Boot Script
- `deploy/dev/init-db.sh` required after first docker compose up to create `agent_playground_api` database (referenced in docker-compose.dev.yml DATABASE_URL)

---

## Configuration & Constants

### api_server/config.py (Settings)
- DATABASE_URL (required env, no AP_ prefix, industry convention)
- AP_ENV (dev | prod, default dev) — gates /docs + /redoc exposure
- AP_MAX_CONCURRENT_RUNS (int, default 2) — size of run_semaphore
- AP_RECIPES_DIR (path, default recipes) — directory for recipe/*.yaml discovery
- AP_TRUSTED_PROXY (bool, default False) — whether to trust X-Forwarded-For for rate-limit subject derivation

### api_server/constants.py
- ANONYMOUS_USER_ID = UUID('00000000-0000-0000-0000-000000000001')

### Main App Lifecycle (main.py)

**Lifespan (async context manager):**
- **Startup:**
  - Create asyncpg pool (min_size=2, max_size=10, command_timeout=5s)
  - Load recipes from AP_RECIPES_DIR into app.state.recipes dict (fail-loud on malformed/duplicates)
  - Initialize image_tag_locks dict (empty) for per-image-tag Lock objects
  - Initialize locks_mutex (asyncio.Lock for mutations to image_tag_locks)
  - Initialize run_semaphore (asyncio.Semaphore(AP_MAX_CONCURRENT_RUNS))
- **Shutdown:**
  - Close asyncpg pool

**Middleware stack** (declared outermost-last, effective request-in order):
1. CorrelationIdMiddleware (mint/bind X-Request-Id)
2. AccessLogMiddleware (allowlist-based structured logging)
3. RateLimitMiddleware (fixed-window rate limiting)
4. IdempotencyMiddleware (Stripe-style idempotency)
5. Routers

**Router registration:**
- health.router (root, /healthz + /readyz)
- schemas_route.router (prefix=/v1)
- recipes_route.router (prefix=/v1)
- runs_route.router (prefix=/v1)
- agents_route.router (prefix=/v1)

**OpenAPI:**
- /openapi.json always public (Phase 20 frontend type-gen)
- /docs + /redoc only when AP_ENV=dev (D-10)

---

## Top Priorities to Address

### 1. **pass_if field is always NULL in RunResponse** (Impact: MEDIUM, User-Facing)
   - **Issue:** routes/runs.py::create_run line 228 returns `pass_if=details.get("pass_if")`, but run_cell does not include pass_if in details dict; pass_if is in the Verdict (discarded)
   - **Fix:** Add pass_if string to details dict in tools/run_recipe.py run_cell return, or pull from smoke dict in route
   - **Phase:** 19.1 patch
   - **Test:** Verify RunResponse.pass_if is populated when smoke.pass_if exists

### 2. **Agent personality defaults to NULL when not supplied** (Impact: LOW, Future-Proof)
   - **Issue:** Phase 20 assumes personality drives system-prompt selection; current API doesn't default personality if caller omits it (both agent_name + personality optional)
   - **Fix:** Define default personality in RunRequest (suggested: null, or default to "polite-thorough")
   - **Phase:** 20-planning
   - **Test:** Verify personality is sensible when omitted

### 3. **ANONYMOUS_USER_ID blocks true multi-tenancy** (Impact: HIGH, Blocking Phase 21)
   - **Issue:** Phase 19 hardcodes all requests to ANONYMOUS_USER_ID; Phase 21 sessions must swap this for session-resolved real user
   - **Mitigation:** Auth paths are already prepared (see comments in runs.py, agents.py, idempotency middleware); only the resolution point needs to change
   - **Phase:** 21
   - **Work:** Replace ANONYMOUS_USER_ID lookup with session.user_id extraction

### 4. **Metadata field accepted but dropped** (Impact: LOW, Technical Debt)
   - **Issue:** RunRequest.metadata dict is accepted but never written to DB; future phases may want audit trail
   - **Fix:** Add metadata JSONB column to runs table (migration 003), populate in routes/run_store
   - **Phase:** 20+ (post-Phase 19 ship)
   - **Test:** Verify metadata round-trips for an audit endpoint (future)

### 5. **No graceful schema evolution path for recipe v0.2+** (Impact: MEDIUM, Blocks v0.2)
   - **Issue:** SUPPORTED_SCHEMAS is hardcoded in routes/schemas.py; v0.2 recipe features (persistent mode, multi-step workflows) need new schema + new loader
   - **Fix:** Define migration path in CLAUDE.md (Phase 13 planning); add SUPPORTED_SCHEMAS loader to services
   - **Phase:** 13 (research), 15+ (implementation)
   - **Scope:** Out of Phase 19; flagged here for forward planning

---

## End Notes

**Production Readiness:** Phase 19 backend is **WORKS-grade**. Core endpoints (POST /v1/runs, GET /v1/runs/{id}, GET /v1/agents, GET /v1/recipes, POST /v1/lint, GET /readyz) are fully functional, parameterized, and hardened against BYOK leaks, injection, and concurrency pitfalls. Two migrations ship the schema; middleware stack enforces rate limits, idempotency, and structured logging.

**Future Hooks:** Phase 20 (agents, personalities) adds agent_instances.name/personality columns + AgentSummary projection + personality presets service. Phase 21 (OAuth sessions) swaps ANONYMOUS_USER_ID for session-resolved user. Phase 22+ (workflow, persistent mode, stochastic) depends on recipe schema v0.2 + Temporal integration + new verdict categories.

**Audit Trail:** All run-relevant tables (runs, agent_instances, idempotency_keys) are fully populated by handlers. Rate-limit and idempotency counters enable fine-grained operational visibility. Access logs (allowlist-based) provide non-leaky request audit. No sensitive data (API keys, auth tokens) reaches logs, DB, or error responses by construction.

**Prepared by:** Desiccation scan of api_server/, tools/run_recipe.py, migrations, and deploy glue. Cross-section of routes (5 endpoints), services (7 modules), models (8 types), middleware (4 active), DB (5 tables, 2 migrations), and runner (1182 lines CLI + importable API).
