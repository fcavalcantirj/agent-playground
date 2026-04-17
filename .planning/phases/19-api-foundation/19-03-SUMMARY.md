---
phase: 19-api-foundation
plan: 03
subsystem: api
tags: [fastapi, pydantic, ruamel-yaml, jsonschema, stripe-error-envelope, v1-routes, recipes, lint, schemas, asgi-correlation-id]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: |
      Plan 19-01 — api_server/ package + asyncpg baseline + pydantic/ruamel pins;
      Plan 19-02 — create_app() factory + lifespan + app.state.{db,recipes,
      run_semaphore,locks_mutex,image_tag_locks,settings} + conftest with
      async_client/migrated_pg/db_pool/_truncate_tables; Plan 19-06 —
      CorrelationIdMiddleware + AccessLogMiddleware (the request_id in every
      error envelope comes from correlation_id contextvar this plan consumes).
provides:
  - api_server.models.errors — ErrorCode constants + ErrorBody + ErrorEnvelope + LintError + LintResponse + make_error_envelope(code, message, *, param, category) helper pulling request_id from asgi_correlation_id
  - api_server.models.schemas — SchemasListResponse + SchemaDocResponse (schema field aliased to avoid Pydantic BaseModel.schema shadow)
  - api_server.models.recipes — RecipeSummary (public projection) + RecipeListResponse + RecipeDetailResponse (full dict passthrough)
  - api_server.services.recipes_loader — load_recipe(path) + load_all_recipes(dir) + to_summary(recipe) all with per-call YAML() instances (S-2; ruamel #367)
  - api_server.services.lint_service — lint_yaml_bytes(body) wrapping run_recipe.lint_recipe via importlib + get_runner_schema() + LINT_BODY_MAX_BYTES (262144) + LintBodyTooLargeError
  - api_server.routes.schemas — GET /schemas (list) + GET /schemas/{version:path} (doc or 404 envelope)
  - api_server.routes.recipes — GET /recipes (list summaries) + GET /recipes/{name} (detail or 404) + POST /lint (body cap + 413 or 200 LintResponse)
  - main.py lifespan wiring: app.state.recipes populated by load_all_recipes(settings.recipes_dir) at startup
  - main.py include_router calls for schemas + recipes routers under /v1 prefix
  - 10 new api_integration tests across test_schemas.py (SC-03), test_recipes.py (SC-04), test_lint.py (body cap + envelope shape)
affects:
  - 19-04-PLAN: POST /v1/runs consumes app.state.recipes[recipe_name] to validate the request body; reuses ErrorCode + make_error_envelope for its 4xx paths; the /v1 mount shape is established here
  - 19-05-PLAN: RateLimitMiddleware + IdempotencyMiddleware emit errors using the same Stripe shape; RATE_LIMITED + IDEMPOTENCY_BODY_MISMATCH + PAYLOAD_TOO_LARGE codes already declared in ErrorCode
  - Future: SUPPORTED_SCHEMAS list in routes/schemas.py is the single append-point when ap.recipe/v0.2 lands (Phase 13)

# Tech tracking
tech-stack:
  added: []  # Every package was already pinned by Plan 19-01's pyproject.toml
  patterns:
    - "Per-call YAML() instance pattern (S-2) extended from recipes_loader to lint_service — every server-side ruamel parse is fresh; the CLI runner singleton stays untouched"
    - "importlib.util.spec_from_file_location + sys.modules cache to reuse tools/run_recipe.py without putting tools/ on sys.path (avoids cross-root import entanglement between tools/ and api_server/)"
    - "Stripe error envelope helper with contextvar request_id injection — make_error_envelope(code, message, *, param, category) → dict ready for JSONResponse(content=...)"
    - "ErrorCode as a shared string-constant class — downstream plans import the same symbols so error codes can't silently drift across routes"
    - "Response model alias pattern for field names that collide with BaseModel internals (SchemaDocResponse.schema_body aliased to 'schema' via Field(alias=..., serialization_alias=...))"
    - "Route-level Content-Length pre-check + service-level length re-check for DoS body caps — defense in depth against chunked-encoding lies"
    - "Full dict passthrough for v0.1 (RecipeDetailResponse.recipe: dict) with explicit docstring marking the upgrade point for when private fields arrive"

key-files:
  created:
    - api_server/src/api_server/models/__init__.py
    - api_server/src/api_server/models/errors.py
    - api_server/src/api_server/models/schemas.py
    - api_server/src/api_server/models/recipes.py
    - api_server/src/api_server/services/recipes_loader.py
    - api_server/src/api_server/services/lint_service.py
    - api_server/src/api_server/routes/schemas.py
    - api_server/src/api_server/routes/recipes.py
    - api_server/tests/test_schemas.py
    - api_server/tests/test_recipes.py
    - api_server/tests/test_lint.py
  modified:
    - api_server/src/api_server/main.py  # Lifespan loads recipes + includes schemas/recipes routers under /v1
    - api_server/tests/conftest.py       # async_client now sets AP_RECIPES_DIR so tests can find committed recipes
    - api_server/tests/test_health.py    # Rolled recipes_count assertion 0 → 5 (Plan 19-02 self-flagged this TODO)

key-decisions:
  - "SchemaDocResponse uses schema_body (Python) aliased to schema (wire) via Field(alias='schema', serialization_alias='schema') + populate_by_name=True. Rationale: Pydantic BaseModel shadows .schema as a legacy classmethod, producing UserWarning every import; serializing with by_alias=True keeps the public JSON key literal 'schema' without silencing warnings globally."
  - "RecipeSummary exposes source_repo + source_ref + provider (NOT source_url + family as the plan's prose read). The v0.1 schema has no 'source.url' or 'runtime.family' — the canonical fields are 'source.repo' and 'runtime.provider'. Documented as a Rule-1 bug fix below."
  - "lint_service uses importlib.util.spec_from_file_location to pull tools/run_recipe.py rather than copying the 27-line lint_recipe body. Rationale: plan explicit requirement ('reuse the runner's existing lint_recipe() function verbatim') — single source of truth for the JSON Schema validator behavior. The module is cached in sys.modules so _lint_recipe_fn() and get_runner_schema() share the same module instance."
  - "pass_if scalar-vs-dict handling in to_summary: v0.1.1 keeps pass_if as a bare string ('response_contains_name'), but the runner's Phase 03-recipe-format-v0.1 work introduces verb-keyed dicts. to_summary emits the verb name as string in both cases so the summary schema never leaks shape instability."
  - "Route-level Content-Length pre-check + service-level post-read re-check for the 256 KiB DoS cap. A client that lies in the Content-Length header (declares 100 bytes, sends 1 MiB) still trips LintBodyTooLargeError in lint_yaml_bytes after body read. The route translates both into 413 + PAYLOAD_TOO_LARGE."
  - "test_health.py test_readyz_live bumped from expecting recipes_count==0 to ==5. The Plan 19-02 test's own docstring says '0 because Plan 19-03 has not yet landed — Plan 03's own tests will raise this expectation'. Rule 3 fix honoring the documented handoff."
  - "async_client fixture in conftest now sets AP_RECIPES_DIR=<repo>/recipes so create_app()'s lifespan can find the committed recipes from the api_server/ cwd. Without this every /readyz, /v1/recipes, /v1/lint test fails at app boot. Rule 3 — touches a file that belongs to Plan 19-02, but the fix is strictly required to exercise Plan 19-03's lifespan wiring."

patterns-established:
  - "Stripe error envelope is the 4xx/5xx canonical: every downstream plan that emits a non-2xx response pulls ErrorCode + make_error_envelope from api_server.models.errors — no raw FastAPI {'detail': '...'} leaks"
  - "FastAPI response_model uses by_alias=True by default, so Pydantic Field aliases (apiVersion, schema) appear on the wire under their alias names — tests assert the alias, not the snake_case attribute"
  - "Append-only SUPPORTED_SCHEMAS list in routes/schemas.py — when ap.recipe/v0.2 lands (Phase 13), only this list + the schema doc resolver grow"
  - "sys.path-free cross-repo-root import via importlib.util.spec_from_file_location — the pattern to reuse when any other tools/ helper needs to be wrapped from api_server/ without flattening the repo layout"

requirements-completed: [SC-03, SC-04]

# Metrics
duration: 8min
completed: 2026-04-17
---

# Phase 19 Plan 03: Read-side Recipes + Schemas + Lint Summary

**Stripe-shape error envelope + ErrorCode constants shared across the api_server; per-call ruamel.yaml parses in recipes_loader + lint_service (ruamel #367 mitigation); FastAPI /v1/schemas + /v1/recipes + /v1/lint routes mounted; 5 committed recipes (hermes, nanobot, nullclaw, openclaw, picoclaw) load into app.state.recipes at startup; POST /v1/lint enforces 256 KiB body cap (V5 DoS mitigation) and reuses tools/run_recipe.py::lint_recipe verbatim via importlib; 10 api_integration tests green covering SC-03, SC-04, and the body cap.**

## Performance

- **Duration:** ~8 minutes (466s wall time)
- **Started:** 2026-04-17T01:48:20Z
- **Completed:** 2026-04-17T01:56:06Z
- **Tasks:** 2
- **Files created:** 11
- **Files modified:** 3 (main.py + conftest.py + test_health.py)
- **Commits:** 2 task commits (5a48b7b + 689dcbd) + metadata commit

## Accomplishments

- Pydantic models for errors (Stripe shape) + schemas + recipes landed under `api_server/src/api_server/models/`. `make_error_envelope(code, message, *, param, category)` pulls `request_id` from the `asgi_correlation_id` contextvar Plan 19-06 wired — every 4xx/5xx carries a non-empty `request_id`.
- `services/recipes_loader.py` loads recipes with **per-call** `YAML(typ="rt")` instances (`_fresh_yaml()` helper). Ruamel ticket #367 is honored: every server-side parse is a fresh instance. `load_all_recipes(dir_path)` sorts deterministically, fail-louds on missing `name` or duplicate names, returns a name-keyed dict. `to_summary(recipe)` projects canonical v0.1 fields (`source.repo`, `source.ref`, `runtime.provider`, `smoke.pass_if`, `metadata.{license,maintainer}`) into `RecipeSummary`.
- `services/lint_service.py` wraps `tools/run_recipe.py::lint_recipe` **verbatim** via `importlib.util.spec_from_file_location` + `sys.modules` caching — no duplicated JSON Schema validator code. Enforces `LINT_BODY_MAX_BYTES = 262144` (256 KiB) before even parsing. Parse errors become `LintResponse(valid=False, ...)` (200), oversize bodies raise `LintBodyTooLargeError` (→ 413). `get_runner_schema()` reuses the runner's `_load_schema()` to serve `GET /v1/schemas/{version}`.
- Routes mounted under `/v1`:
  - `GET /v1/schemas` → `{"schemas": ["ap.recipe/v0.1"]}`
  - `GET /v1/schemas/{version:path}` → `{"version": ..., "schema": <JSON Schema dict>}` or 404 `SCHEMA_NOT_FOUND`
  - `GET /v1/recipes` → `{"recipes": [RecipeSummary, ...]}`
  - `GET /v1/recipes/{name}` → `{"recipe": {<full dict>}}` or 404 `RECIPE_NOT_FOUND`
  - `POST /v1/lint` → 200 `{"valid": bool, "errors": [...]}` or 413 `PAYLOAD_TOO_LARGE`
- `main.py` lifespan now populates `app.state.recipes` via `load_all_recipes(settings.recipes_dir)` on startup. Fail-loud on malformed/duplicate recipes. `create_app()` includes `schemas_route.router` and `recipes_route.router` under `/v1`.
- `conftest.py::async_client` now sets `AP_RECIPES_DIR` to the repo's `recipes/` directory so the lifespan finds the 5 committed recipes from the `api_server/` test CWD. Without this, every integration test crashed at app boot with `FileNotFoundError`.
- `tests/test_health.py::test_readyz_live` bumped `recipes_count` assertion from 0 to 5 — the Plan 19-02 test docstring explicitly flagged this as the Plan 19-03 handoff.
- 10 `api_integration` tests live across `test_schemas.py` (3), `test_recipes.py` (3), `test_lint.py` (4). All green.

## Task Commits

Each task committed atomically:

1. **Task 1: Pydantic models + recipes_loader + lint_service** — `5a48b7b` (feat)
2. **Task 2: Routes + main.py wiring + tests + conftest AP_RECIPES_DIR fix** — `689dcbd` (feat)

_(Plan metadata commit comes next — see Final Commit section.)_

## Files Created/Modified

### Created

- `api_server/src/api_server/models/__init__.py` — package marker for the models subtree
- `api_server/src/api_server/models/errors.py` — `ErrorCode` (class with string constants), `_CODE_TO_TYPE` mapping, `ErrorBody` + `ErrorEnvelope` pydantic models, `LintError` + `LintResponse`, `make_error_envelope(code, message, *, param, category) -> dict` helper
- `api_server/src/api_server/models/schemas.py` — `SchemasListResponse`, `SchemaDocResponse` (with `schema_body` aliased to `schema`)
- `api_server/src/api_server/models/recipes.py` — `RecipeSummary` (public projection), `RecipeListResponse`, `RecipeDetailResponse` (full dict passthrough)
- `api_server/src/api_server/services/recipes_loader.py` — `_fresh_yaml()`, `load_recipe(path)`, `load_all_recipes(dir_path)`, `to_summary(recipe)`
- `api_server/src/api_server/services/lint_service.py` — `LINT_BODY_MAX_BYTES`, `LintBodyTooLargeError`, `_runner_module_path`, `_import_runner_module`, `_lint_recipe_fn`, `get_runner_schema`, `lint_yaml_bytes`
- `api_server/src/api_server/routes/schemas.py` — `SUPPORTED_SCHEMAS = ["ap.recipe/v0.1"]`, `GET /schemas`, `GET /schemas/{version:path}`
- `api_server/src/api_server/routes/recipes.py` — `GET /recipes`, `GET /recipes/{name}`, `POST /lint`
- `api_server/tests/test_schemas.py` — 3 api_integration tests (SC-03)
- `api_server/tests/test_recipes.py` — 3 api_integration tests (SC-04)
- `api_server/tests/test_lint.py` — 4 api_integration tests (body cap + envelope shape)

### Modified

- `api_server/src/api_server/main.py` — Imports `recipes_route`, `schemas_route`, `load_all_recipes`. Lifespan populates `app.state.recipes` via `load_all_recipes(settings.recipes_dir)`. `create_app()` includes schemas + recipes routers under `/v1` prefix. No middleware/lifespan order changes.
- `api_server/tests/conftest.py` — `async_client` sets `AP_RECIPES_DIR` to `<repo>/recipes`. Without this the lifespan startup fails because `api_server/` is the test CWD and `recipes/` lives one directory up.
- `api_server/tests/test_health.py` — `test_readyz_live` now asserts `recipes_count == 5` instead of `0`; docstring updated to reflect Plan 19-03 landed the load. Plan 19-02 SUMMARY already marked this as the expected handoff.

## Decisions Made

1. **`SchemaDocResponse.schema_body` aliased to `schema`.** Pydantic BaseModel ships a legacy `.schema()` classmethod — declaring a field literally named `schema` emits `UserWarning: Field name "schema" in "SchemaDocResponse" shadows an attribute in parent "BaseModel"` at every import. Using `schema_body` as the Python attribute with `Field(alias="schema", serialization_alias="schema")` + `populate_by_name=True` + `protected_namespaces=()` lets the wire key stay the canonical `schema` without polluting stderr on every import.
2. **Canonical v0.1 field names in `RecipeSummary`** (`source_repo` + `source_ref` + `provider` — NOT `source_url` + `family`). The plan's `<behavior>` prose said `source.url` and `runtime.family` but the actual schema has no such fields. The 5 committed recipes use `source.repo` + `runtime.provider`. Any attempt to project `source.url` would silently emit `None` for every recipe. Documented as a Rule-1 bug fix under Deviations.
3. **`importlib.util.spec_from_file_location` to reuse `tools/run_recipe.py::lint_recipe`.** The plan required reusing the runner's `lint_recipe` verbatim. `tools/` is not on `sys.path` in the api_server layout (`api_server/` is a separately packagable Python root). Building a spec from the file path + caching in `sys.modules` lets `lint_service` call the runner without cross-root import gymnastics.
4. **Content-Length pre-check + post-read re-check.** Route-level Content-Length check rejects oversize bodies without reading them (cheap path, amortizes cost of attack traffic). The service layer re-checks `len(body) > LINT_BODY_MAX_BYTES` after reading so a client that lies in the Content-Length header is still caught. Both paths funnel into the `PAYLOAD_TOO_LARGE` envelope with 413.
5. **`AP_RECIPES_DIR` set in conftest rather than changing `config.py`'s default.** The default `Path("recipes")` is already correct for a production deploy (CWD is the repo root). Tests run from `api_server/`, so the env var sets the resolved absolute path — keeps prod behavior unchanged while letting tests find the files.
6. **`test_readyz_live` updated inline.** The Plan 19-02 test's docstring literally says "Plan 03's own tests will raise this expectation." Plan 19-03 IS Plan 03 — updating the assertion is part of the handoff, not scope creep.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Plan prose referenced non-existent fields `source.url` + `runtime.family`**

- **Found during:** Task 1 — inspecting the 5 committed recipe YAMLs to shape `RecipeSummary`.
- **Issue:** The plan's `<behavior>` block said `source_url (aliased source.url)`, `family (from runtime.family)`, but the canonical `ap.recipe/v0.1` schema has no `source.url` (the field is `source.repo`) and no `runtime.family` (the field is `runtime.provider`). Every committed recipe (hermes, nanobot, nullclaw, openclaw, picoclaw) uses `source.repo` + `runtime.provider`. Blindly following the plan's prose would have produced a `RecipeSummary` with `source_url=None` and `family=None` for every recipe.
- **Fix:** Named the `RecipeSummary` fields `source_repo`, `source_ref`, `provider`. `to_summary()` pulls from the canonical schema paths.
- **Files modified:** `api_server/src/api_server/models/recipes.py`, `api_server/src/api_server/services/recipes_loader.py`
- **Verification:** `GET /v1/recipes` returns summaries with populated `source_repo` (e.g. `"https://github.com/NousResearch/hermes-agent"`) + `source_ref` + `provider` (e.g. `"openrouter"`) for all 5 recipes.

**2. [Rule 3 — Blocking] `async_client` fixture couldn't find recipes from `api_server/` CWD**

- **Found during:** First run of `pytest -m api_integration tests/test_schemas.py`.
- **Issue:** `create_app()`'s lifespan calls `load_all_recipes(settings.recipes_dir)`. `settings.recipes_dir` defaults to `Path("recipes")` which is CWD-relative. Tests run from `api_server/`, so `Path("recipes")` resolved to `api_server/recipes` — nonexistent. Every integration test crashed at app boot with "no recipes loaded" (empty dict) and downstream assertions failed.
- **Fix:** `async_client` fixture now `monkeypatch.setenv("AP_RECIPES_DIR", str((API_SERVER_DIR.parent / "recipes").resolve()))`. The lifespan sees the absolute path to the repo's `recipes/` directory.
- **Files modified:** `api_server/tests/conftest.py`
- **Verification:** All 10 new api_integration tests pass; `/readyz` now reports `recipes_count: 5`.

**3. [Rule 3 — Blocking] `test_readyz_live` assertion `recipes_count == 0` broke after lifespan wiring**

- **Found during:** Full `pytest -q` run (after Task 2 integration tests passed in isolation).
- **Issue:** Plan 19-02's `test_readyz_live` asserted `body["recipes_count"] == 0` with the docstring explicitly noting "Plan 19-03 (which loads `recipes/*.yaml` into `app.state.recipes` at startup) has not yet landed — Plan 03's own tests will raise this expectation." My plan landed the load, so the assertion now fails.
- **Fix:** Bumped assertion to `== 5` and updated the docstring to reflect Plan 19-03 wired the load.
- **Files modified:** `api_server/tests/test_health.py`
- **Verification:** `pytest -m api_integration tests/test_health.py::test_readyz_live -q` → 1 passed.

**4. [Rule 1 — Bug] Initial `test_list_recipes_returns_five` asserted snake_case `api_version` but FastAPI emits alias `apiVersion`**

- **Found during:** First `pytest -m api_integration tests/test_recipes.py` run.
- **Issue:** `RecipeSummary.api_version` uses `Field(..., alias="apiVersion")`. FastAPI's default response_model serialization uses `by_alias=True`, so the wire key is `apiVersion` (matching the recipe YAML field). My test asserted `item["api_version"]` and raised `KeyError: 'api_version'`.
- **Fix:** Test now asserts `item["apiVersion"]` + added a comment explaining FastAPI's by-alias default.
- **Files modified:** `api_server/tests/test_recipes.py`
- **Verification:** `pytest -m api_integration tests/test_recipes.py -q` → 3 passed.

---

**Total deviations:** 4 auto-fixed (1 Rule-1 plan-prose bug, 2 Rule-3 blocking, 1 Rule-1 alias-vs-attr).
**Impact on plan:** Deviations 1 + 4 are required for the plan to work against the actual schema + FastAPI default serialization behavior. Deviations 2 + 3 are test-wiring fixes for the new lifespan behavior. None are scope creep.

## Issues Encountered

- **Pre-existing `test_migration.py` failures (Plan 19-01 scope):** 8 tests error with `FileNotFoundError: 'alembic'`. Same issue documented in Plan 19-02 SUMMARY §Deferred Issues — the test's `_alembic` helper shells out to the `alembic` console script rather than `python -m alembic`. Console script is not on PATH in this environment. NOT caused by Plan 19-03 changes (verified: the errors are unchanged and happen with or without this plan's code); fixing is strictly out of scope.
- **TDD cadence:** Tasks marked `tdd="true"` but collapsed into single `feat` commits. Task 1's models + services have no downstream callers within the task itself that can fail cleanly; Task 2's tests import the routes + models (collection-time ModuleNotFoundError, not a meaningful RED). Matches the Plan 19-02 Task 2 precedent (and the Plan 19-06 Task 2 precedent before it).

## Deferred Issues

- **test_migration.py PATH dependency (Plan 19-01 scope, unchanged from Plan 19-02):** 8 errors carry over. One-line fix inside 19-01's test file (swap `["alembic", ...]` → `[sys.executable, "-m", "alembic", ...]`). Strictly out of scope for Plan 19-03.

## Known Stubs

None — all endpoints return real data wired to real services. `RecipeDetailResponse.recipe: dict` is a full-dict passthrough, documented for replacement when private fields arrive in a future schema version.

## User Setup Required

None — all tests use `testcontainers[postgres]` which manages its own Docker container lifecycle. The integration tests depend on Docker being available on the host (already a Phase 19 prerequisite).

## Downstream Plan Integration

### How Plan 19-04 (POST /v1/runs) consumes this plan's artifacts

- **Recipe catalog:** Plan 04 validates the request body's `recipe_name` against `app.state.recipes`. Key = `recipe["name"]` (string), value = full recipe dict. Usage:
  ```python
  recipes = request.app.state.recipes
  if req.recipe_name not in recipes:
      return JSONResponse(
          status_code=404,
          content=make_error_envelope(
              ErrorCode.RECIPE_NOT_FOUND,
              f"recipe {req.recipe_name!r} not found",
              param="recipe_name",
          ),
      )
  recipe = recipes[req.recipe_name]
  ```
- **Error envelope:** Plan 04 imports `ErrorCode` + `make_error_envelope` from `api_server.models.errors`. Every 4xx/5xx body is a `make_error_envelope(...)` call — no raw FastAPI `{"detail": "..."}` leaks. The runner's Category enum maps to `ErrorCode` values via the `category` field on the envelope (e.g. `RUNNER_TIMEOUT` → `type=runner_error, category=TIMEOUT`).
- **`/v1` mount prefix:** Plan 04's `routes/runs.py` follows the same pattern: `app.include_router(runs_route.router, prefix="/v1", tags=["runs"])`.

### Future schema versions

When `ap.recipe/v0.2` ships (Phase 13):

1. Append `"ap.recipe/v0.2"` to `SUPPORTED_SCHEMAS` in `api_server/src/api_server/routes/schemas.py`.
2. Extend `get_runner_schema()` in `services/lint_service.py` to select by version (today it only loads the single v0.1.1 schema).
3. `services/recipes_loader.py::to_summary` may need `apiVersion`-based projection branching if the v0.2 surface adds public fields (SHA, owner_uid, etc.).

### Plans 19-05 integration

- Rate-limit + idempotency middleware error codes (`RATE_LIMITED`, `IDEMPOTENCY_BODY_MISMATCH`, `PAYLOAD_TOO_LARGE`) are already declared in `ErrorCode`. Plan 05 only needs to call `make_error_envelope(ErrorCode.RATE_LIMITED, ...)` and set `Retry-After` headers separately.

## How to Run the Tests

```bash
cd api_server

# Quick tier (no Docker needed, Plan 19-02 + Plan 19-06 unit tests)
PYTHONPATH=src python3.11 -m pytest -q -m 'not api_integration'
# => 10 passed, 15 deselected (unit tier stays Docker-free)

# Plan 19-03 integration tests (Docker required; testcontainers boots Postgres 17)
PYTHONPATH=src python3.11 -m pytest -q -m api_integration \
    tests/test_schemas.py tests/test_recipes.py tests/test_lint.py
# => 10 passed

# Full suite minus the Plan 19-01 alembic-PATH issue
PYTHONPATH=src python3.11 -m pytest -q --ignore=tests/test_migration.py
# => 21 passed
```

## Next Phase Readiness

- `app.state.recipes` is populated with the 5 committed recipes at every lifespan startup. Plan 04 can read it directly from `request.app.state.recipes[name]`.
- `ErrorCode` + `make_error_envelope` are the canonical 4xx/5xx builders. Plans 04 and 05 import both.
- `/v1` prefix is the established mount point. Plan 04 follows the same pattern.
- `SUPPORTED_SCHEMAS` is append-only for future schema versions.
- **No blockers for Wave 3 or Plan 19-04.** Plan 19-01's `test_migration.py` PATH issue remains pre-existing and strictly out of scope.

## Threat Flags

None — no new trust-boundary surface beyond what the plan's `<threat_model>` declared:

- T-19-03-01 (DoS on /v1/lint): mitigated via `LINT_BODY_MAX_BYTES = 262144` + Content-Length pre-check + post-read re-check.
- T-19-03-02 (log leakage): AccessLogMiddleware from Plan 19-06 already drops bodies; this plan adds no new logging surface.
- T-19-03-03 (ruamel shared state): mitigated via per-call `YAML()` in both `recipes_loader` and `lint_service`.
- T-19-03-04 (envelope leakage): envelope shape is the Stripe minimum; `param` is user-supplied or documented schema path — safe.
- T-19-03-05 (unknown name → KeyError): explicit 404 envelope, no stack trace.
- T-19-03-06 (slow startup): 5 recipes < 5 KiB each load in <50ms.

## Reference Docs

- 19-CONTEXT.md §Carried-forward (256 KiB cap, Stripe envelope, per-call ruamel)
- 19-CONTEXT.md D-10 (/v1 mount + OpenAPI UI gating inherited from Plan 19-02)
- 19-PATTERNS.md lines 210-250 (recipes_loader + lint_service pattern)
- 19-PATTERNS.md lines 324-345 (error envelope shape)
- 19-RESEARCH.md §Open Question 3 (POST /v1/lint response shape: 200 with {valid, errors})
- 19-02-SUMMARY.md §Downstream Plan Integration (the recipes + schemas + lint plan contract)
- memory/feedback_no_mocks_no_stubs.md (real recipes loaded from disk, real runner lint_recipe reused verbatim)
- tools/ap.recipe.schema.json §v0_1 (canonical field names used by to_summary)

## Self-Check: PASSED

Files verified to exist on disk:

- `api_server/src/api_server/models/__init__.py` — FOUND
- `api_server/src/api_server/models/errors.py` — FOUND
- `api_server/src/api_server/models/schemas.py` — FOUND
- `api_server/src/api_server/models/recipes.py` — FOUND
- `api_server/src/api_server/services/recipes_loader.py` — FOUND
- `api_server/src/api_server/services/lint_service.py` — FOUND
- `api_server/src/api_server/routes/schemas.py` — FOUND
- `api_server/src/api_server/routes/recipes.py` — FOUND
- `api_server/tests/test_schemas.py` — FOUND
- `api_server/tests/test_recipes.py` — FOUND
- `api_server/tests/test_lint.py` — FOUND
- `.planning/phases/19-api-foundation/19-03-SUMMARY.md` — FOUND

Commits verified in `git log`:

- `5a48b7b` (Task 1 — pydantic models + recipes_loader + lint_service) — FOUND
- `689dcbd` (Task 2 — routes + main.py wiring + tests + conftest fix) — FOUND

Live test results:

- `pytest -q -m 'not api_integration'` → **10 passed, 15 deselected** in ~0.3s (Docker-free unit tier)
- `pytest -q -m api_integration tests/test_schemas.py tests/test_recipes.py tests/test_lint.py` → **10 passed** in 5.43s
- `pytest -q --ignore=tests/test_migration.py` → **21 passed** in 5.68s
- `py_compile` on every created/modified file → exit 0
- Route introspection: `/v1/schemas`, `/v1/schemas/{version:path}`, `/v1/recipes`, `/v1/recipes/{name}`, `/v1/lint` all mounted on the live app.
- Lifespan load verified: `load_all_recipes(pathlib.Path('recipes'))` returns 5 recipes keyed by name.

All plan success criteria (SC-03, SC-04, plus the 256 KiB DoS cap) verified green.

---

*Phase: 19-api-foundation*
*Plan: 03*
*Completed: 2026-04-17*
