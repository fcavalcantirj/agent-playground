# Phase 19: API Foundation - Pattern Map

**Mapped:** 2026-04-16
**Files analyzed:** ~38 new files (api_server greenfield) + 1 in-place runner edit
**Analogs found:** 13 / 38 in-repo; 25 are greenfield with sibling-project cribs (MSV) or library-canon-only

## Repository Reality Check

This repo is **Python recipe runner + Go substrate (frozen)**. Phase 19 creates a brand-new `api_server/` FastAPI service. There is **no existing FastAPI / asyncpg / Alembic code in-repo**. The closest in-repo analogs are:

| Concern | Closest In-Repo Source | Notes |
|---------|------------------------|-------|
| CLI flag parsing → handler arg mapping | `tools/run_recipe.py` `parse_args` + `main` | The HTTP request/response envelope wraps these same controls |
| `run_cell()` signature being wrapped | `tools/run_recipe.py` lines 653-825 | THE function `POST /v1/runs` calls via `asyncio.to_thread` |
| `Category` enum (the 11-member taxonomy `POST /v1/runs` returns) | `tools/run_recipe.py` lines 66-86 | Mirror this enum verbatim in `api_server/src/api_server/models/runs.py` |
| BYOK env-file pattern | `tools/run_recipe.py` lines 684-693 | Already correct — server passes `provider_key` straight into the same code path |
| Pytest fixture shape | `tools/tests/conftest.py` lines 30-44 | `schema` + `mock_subprocess_*` factory style is the convention to mirror |
| Integration test marker | `tools/tests/test_integration_docker.py` lines 1-26 | `pytestmark = pytest.mark.integration` — mirror as `api_integration` |
| Schema file location | `tools/ap.recipe.schema.json` | The exact file `POST /v1/lint` validates against |
| Recipe YAML inventory | `recipes/*.yaml` (5 files) | The source `GET /v1/recipes` enumerates |
| Compose file shape | `docker-compose.dev.yml` lines 14-29 | Postgres service definition shape — mirror in `deploy/docker-compose.prod.yml` |
| Dockerfile multi-stage shape | `/Users/fcavalcanti/dev/meusecretariovirtual/api/Dockerfile` (sibling project) | Multi-stage + non-root + HEALTHCHECK pattern; Python equivalent for `tools/Dockerfile.api` |
| Postgres install on Hetzner | `deploy/hetzner/install-postgres.sh` | Reuse — phase 19 uses the same Postgres install path; only adds an `agent_playground_api` DB |
| Idempotent init script shape | `deploy/dev/init-db.sh` | One-liner DB-create idempotency pattern |
| Smoke-test script shape | `scripts/smoke-e2e.sh` lines 1-50 | Bash + curl + cleanup-trap shape for `make smoke-api` and `make smoke-api-live` |
| Makefile target shape | `Makefile` lines 180-191 | `install-tools` / `test` / `lint-recipes` / `check` quartet — mirror for api_server |
| Error envelope (Stripe shape) | `api/internal/handler/errors.go` lines 38-56 (REFERENCE ONLY — Go, frozen) | Conceptual mirror; FastAPI implementation lives in `api_server/src/api_server/models/errors.py` |
| Health check shape | `api/internal/handler/health.go` lines 30-66 (REFERENCE ONLY — Go, frozen) | Conceptual mirror; CONTEXT.md D-04 splits this into `/healthz` + `/readyz` |

Files marked **REFERENCE ONLY** are explicitly forbidden to modify per CLAUDE.md banner ("Do NOT touch `api/`, `deploy/`, `test/`, or the old substrate"). Read for shape; reimplement in Python.

---

## File Classification

Plan groups follow CONTEXT.md §Critical Sequencing Constraint (1-7).

### Plan 1 — Database schema + Alembic

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `api_server/alembic.ini` | config | n/a (build artifact) | none in-repo | greenfield (Alembic-canon) |
| `api_server/alembic/env.py` | migration runtime | DSN → engine → DDL | none in-repo | greenfield (Alembic async template) |
| `api_server/alembic/script.py.mako` | template | n/a | none in-repo | greenfield (Alembic-canon) |
| `api_server/alembic/versions/001_baseline.py` | migration | DDL emit | none in-repo | greenfield (CONTEXT.md D-06 spec) |
| `api_server/tests/test_migration.py` | test | DDL → introspect | none in-repo | greenfield |

### Plan 2 — FastAPI skeleton + health/readiness

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `api_server/pyproject.toml` | config | n/a | `tools/pyproject.toml` (lines 1-26) | role-match |
| `api_server/src/api_server/__init__.py` | package marker | n/a | `tools/__init__.py`-equivalent | role-match |
| `api_server/src/api_server/main.py` | app factory | startup → router mount | `api/internal/server/server.go` lines 36-120 (REFERENCE ONLY) | conceptual |
| `api_server/src/api_server/config.py` | settings | env → typed config | none in-repo (Pydantic Settings canon) | greenfield |
| `api_server/src/api_server/db.py` | DB pool lifecycle | DSN → asyncpg pool | none in-repo | greenfield (asyncpg-canon) |
| `api_server/src/api_server/log.py` | structured logger | log records → JSON stdout | none in-repo (structlog canon) | greenfield |
| `api_server/src/api_server/routes/health.py` | route | request → checker → JSON | `api/internal/handler/health.go` lines 30-66 (REFERENCE ONLY) | role-match (Go→Python port) |
| `api_server/tests/conftest.py` | test fixture | testcontainers Postgres + httpx ASGI client | `tools/tests/conftest.py` lines 30-44 | role-match (factory style) |
| `api_server/tests/test_health.py` | test | HTTP → assert JSON | `api/internal/handler/health_test.go` (REFERENCE ONLY) | role-match |

### Plan 3 — Recipe + lint endpoints

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `api_server/src/api_server/routes/schemas.py` | route | static JSON Schema list | `tools/run_recipe.py::_load_schema` (line 109) | role-match (file-read pattern) |
| `api_server/src/api_server/routes/recipes.py` | route | YAML files → public projection | `api/internal/handler/recipes.go` lines 30-100 (REFERENCE ONLY) | conceptual (Go→Python port) |
| `api_server/src/api_server/services/recipes_loader.py` | service | filesystem → in-memory dict | `tools/run_recipe.py::load_recipe` (line 114) | role-match (must use per-call YAML()) |
| `api_server/src/api_server/services/lint_service.py` | service | bytes → ruamel parse → jsonschema | `tools/run_recipe.py::lint_recipe` (line 119) | exact (wrap existing) |
| `api_server/src/api_server/models/recipes.py` | pydantic model | request/response shape | none in-repo | greenfield |
| `api_server/src/api_server/models/schemas.py` | pydantic model | response shape | none in-repo | greenfield |
| `api_server/src/api_server/models/errors.py` | pydantic model | error envelope | `api/internal/handler/errors.go` lines 38-56 (REFERENCE ONLY) | conceptual (Go→Python port, Stripe shape) |
| `api_server/tests/test_recipes.py` | test | HTTP → recipe list assertion | `api/internal/handler/recipes_test.go` (REFERENCE ONLY) | role-match |
| `api_server/tests/test_lint.py` | test | HTTP → schema validation result | `tools/tests/test_lint.py` lines 14-44 | exact (mirror class layout) |

### Plan 4 — Run endpoint (load-bearing)

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `api_server/src/api_server/routes/runs.py` | route | HTTP → bridge → DB persist | `tools/run_recipe.py::main` lines 971-1100 | role-match (CLI→HTTP wrap) |
| `api_server/src/api_server/services/runner_bridge.py` | service | per-tag lock → semaphore → to_thread(run_cell) | `tools/run_recipe.py::run_cell` lines 653-825 | exact (the wrapped function) |
| `api_server/src/api_server/services/run_store.py` | repository | asyncpg writes/reads runs+agent_instances | none in-repo | greenfield (asyncpg-canon) |
| `api_server/src/api_server/models/runs.py` | pydantic model | request/response + Category enum | `tools/run_recipe.py::Category` lines 66-86 | exact (mirror enum verbatim) |
| `api_server/src/api_server/util/ulid.py` | utility | n/a (thin wrap) | none in-repo | greenfield (python-ulid canon) |
| `api_server/tests/test_runs.py` | test | HTTP → mock(run_cell) → DB assert | `tools/tests/test_phase10_runner.py` (existing pattern) | role-match (mock_subprocess style) |
| `api_server/tests/test_run_concurrency.py` | test | 50 concurrent → semaphore caps to N | none in-repo | greenfield |

### Plan 5 — Rate limit + idempotency middleware

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `api_server/src/api_server/middleware/rate_limit.py` | middleware | request → Postgres counter → 429 | none in-repo | greenfield (advisory-lock pattern in RESEARCH.md) |
| `api_server/src/api_server/middleware/idempotency.py` | middleware | header → Postgres lookup → cache | none in-repo | greenfield (Stripe pattern in RESEARCH.md) |
| `api_server/src/api_server/services/idempotency.py` | service | advisory lock + INSERT/SELECT | none in-repo | greenfield |
| `api_server/tests/test_rate_limit.py` | test | 11 requests → 429 + Retry-After | none in-repo | greenfield |
| `api_server/tests/test_idempotency.py` | test | same key → cached response | none in-repo | greenfield |

### Plan 6 — Log redaction + ruamel hardening + redact widening

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|-------------------|------|-----------|----------------|-------|
| `api_server/src/api_server/middleware/correlation_id.py` | middleware | header inject/mint | none in-repo | greenfield (asgi-correlation-id wrap) |
| `api_server/src/api_server/middleware/log_redact.py` | middleware | scope → allowlist log | none in-repo | greenfield |
| `api_server/src/api_server/util/redaction.py` | utility | string → masked string | `tools/run_recipe.py::_redact_api_key` line 378 | exact (extract + extend) |
| `tools/run_recipe.py` (MODIFIED — `_redact_api_key`) | utility | regex broadening | itself, line 378 | self-extend |
| `tools/tests/test_hardening_api_key.py` (MODIFIED — add cases) | test | new redaction cases | itself | self-extend |
| `api_server/tests/test_log_redact.py` | test | log capture → assert no secrets | `tools/tests/test_hardening_api_key.py` (style) | role-match |

### Plan 7 — Hetzner deployment

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `tools/Dockerfile.api` | deploy artifact | source → multi-stage image | `/Users/fcavalcanti/dev/meusecretariovirtual/api/Dockerfile` (sibling) | role-match (Go→Python port) |
| `deploy/docker-compose.prod.yml` | deploy artifact | service compose | `docker-compose.dev.yml` lines 14-29 | role-match (postgres service shape) |
| `deploy/Caddyfile` | deploy artifact | reverse proxy + ACME | none in-repo | greenfield (Caddy-canon) |
| `deploy/deploy.sh` | deploy script | pull → migrate → roll | `scripts/smoke-e2e.sh` lines 25-50 (bash strict-mode header) | role-match (shape only) |
| `deploy/init-api-db.sh` | deploy script | idempotent CREATE DATABASE | `deploy/dev/init-db.sh` | exact (extend pattern) |
| `Makefile` (MODIFIED — add api-server targets) | build orchestration | n/a | `Makefile` lines 180-191 | self-extend (mirror `install-tools/test/lint-recipes/check` quartet) |
| `.env.example` (NEW or MODIFIED at root) | config example | n/a | none in-repo | greenfield |
| `test/smoke-api.sh` | integration test | curl sequence Success Criteria #1-9 | `scripts/smoke-e2e.sh` lines 25-50 | role-match (curl + cleanup-trap) |

---

## Pattern Assignments

### `api_server/src/api_server/services/runner_bridge.py` (service, request→runner)

**Wraps:** `tools/run_recipe.py::run_cell` (lines 653-825). This is the one function the entire HTTP API exists to invoke.

**`run_cell` signature to import** (`tools/run_recipe.py` lines 653-663):
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
) -> tuple[Verdict, dict]:
```

**Return shape — `details` dict** (`tools/run_recipe.py` lines 810-824):
```python
details = {
    "recipe": recipe["name"],
    "model": model,
    "prompt": prompt,
    "pass_if": pass_if_str,
    "verdict": verdict_obj.verdict,        # "PASS" | "FAIL"
    "category": verdict_obj.category.value, # one of Category enum
    "detail": verdict_obj.detail,
    "exit_code": rc,
    "wall_time_s": round(wall, 2),
    "filtered_payload": filtered,
    "stderr_tail": "\n".join(_redact_api_key(stderr, api_key_var).splitlines()[-20:]) or None,
}
```
The HTTP response model in `models/runs.py` MUST mirror these field names verbatim — the bridge passes `details` straight through (with `run_id` and `agent_instance_id` added).

**BYOK invariant to preserve** (`tools/run_recipe.py` lines 684-693):
```python
# Env file: keys delivered via `docker run -e KEY=VAL` leak to the kernel
# process listing (ps / /proc/*/cmdline). `--env-file` reads at docker CLI
# time and sets the var in the container without exposing the value on
# the argv. Chmod 600, unlinked in finally below.
env_file = Path(f"/tmp/ap-env-{uuid.uuid4().hex}")
env_file.write_text(f"{api_key_var}={api_key_val}\n")
try:
    env_file.chmod(0o600)
except OSError:
    pass
```
Bridge passes `api_key_val=provider_key` (the `Authorization: Bearer` extracted value) directly into this code path. **Do NOT** introduce any other key-passing path.

**Per-image-tag lock + global semaphore (RESEARCH.md Pattern 2):** instantiate at app lifespan; key `image_tag = f"ap-recipe-{recipe['name']}"` (matches `tools/run_recipe.py` line 1024).

**`asyncio.to_thread` is mandatory:** `run_cell` is sync and blocks 10-200s. Never call directly from `async def`.

---

### `api_server/src/api_server/models/runs.py` (pydantic model + enum)

**Mirror `Category` enum verbatim** from `tools/run_recipe.py` lines 66-86:
```python
class Category(str, Enum):
    """Phase 10 verdict category enum (9 live + 2 reserved per D-01)."""
    # Live (9)
    PASS = "PASS"
    ASSERT_FAIL = "ASSERT_FAIL"
    INVOKE_FAIL = "INVOKE_FAIL"
    BUILD_FAIL = "BUILD_FAIL"
    PULL_FAIL = "PULL_FAIL"
    CLONE_FAIL = "CLONE_FAIL"
    TIMEOUT = "TIMEOUT"
    LINT_FAIL = "LINT_FAIL"
    INFRA_FAIL = "INFRA_FAIL"
    # Reserved (2)
    STOCHASTIC = "STOCHASTIC"
    SKIP = "SKIP"
```
Re-import from `run_recipe` (`from run_recipe import Category`) is the simplest path — keeps a single source of truth. If the import couples too tightly, copy with a comment pointing back.

**Subclassing `str` (not `enum.StrEnum`)** — preserves Python 3.10 compat in case api_server stays at 3.10. RESEARCH.md Pitfall 8 recommends bumping to 3.11; if so, `StrEnum` is fine.

---

### `api_server/src/api_server/services/recipes_loader.py` (service, filesystem→cache)

**Analog to mirror:** `tools/run_recipe.py::load_recipe` (line 114):
```python
def load_recipe(path: Path) -> dict:
    """Load and parse a recipe YAML file. Returns the parsed dict."""
    return _yaml.load(path.read_text())
```

**CRITICAL deviation per CONTEXT.md (carried-forward from 4-agent critique):**
> `_yaml` module singleton: replace with per-call `YAML()` instances in the server-consumed paths (load_recipe, writeback_cell). CLI keeps the singleton; server constructs fresh.

So `recipes_loader.py` must NOT call `run_recipe.load_recipe` directly. Instead:
```python
from ruamel.yaml import YAML

def load_recipe(path: Path) -> dict:
    yaml = YAML(typ="rt")               # fresh per call — ruamel ticket #367
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml.load(path.read_text())
```

**Recipe inventory:** read all 5 files at app startup (per RESEARCH.md A9). They're <5KB each. Keep in `app.state.recipes: dict[str, dict]` keyed by `recipe["name"]`. The 5 names (verified from `recipes/` directory): `hermes`, `nanobot`, `nullclaw`, `openclaw`, `picoclaw`.

---

### `api_server/src/api_server/services/lint_service.py` (service, bytes→errors)

**Analog to mirror:** `tools/run_recipe.py::lint_recipe` (line 119):
```python
def lint_recipe(recipe: dict, schema: dict | None = None) -> list[str]:
    """Validate recipe dict against JSON Schema. Returns list of error messages (empty = valid)."""
```

**Reuse strategy:** `from run_recipe import lint_recipe, _load_schema` and call directly. No reimplementation needed. The schema file path is `tools/ap.recipe.schema.json` (per `_SCHEMA_PATH = Path(__file__).parent / "ap.recipe.schema.json"`).

**256 KB body cap (CONTEXT.md carried-forward):** enforce at FastAPI route level via Starlette's `Request.body()` size check or a body-size middleware before parse.

---

### `api_server/src/api_server/util/redaction.py` + `tools/run_recipe.py` `_redact_api_key` widening

**Existing function** (`tools/run_recipe.py` lines 378-390):
```python
def _redact_api_key(text: str, api_key_var: str) -> str:
    """Replace every <api_key_var>=<non-space-value> substring with <api_key_var>=<REDACTED>."""
    if not text:
        return ""
    return re.sub(
        rf"{re.escape(api_key_var)}=\S+",
        f"{api_key_var}=<REDACTED>",
        text,
    )
```

**CONTEXT.md D-02 mandate:** "Widen `_redact_api_key()` in runner to also redact the literal key value (not just `VAR=value` pattern)."

**Required widening shape (sketch):**
```python
def _redact_api_key(text: str, api_key_var: str, api_key_val: str | None = None) -> str:
    if not text:
        return ""
    out = re.sub(
        rf"{re.escape(api_key_var)}=\S+",
        f"{api_key_var}=<REDACTED>",
        text,
    )
    if api_key_val and len(api_key_val) >= 8:
        out = out.replace(api_key_val, "<REDACTED>")
    return out
```
Add regression cases to `tools/tests/test_hardening_api_key.py` for both pattern-redaction (existing) and literal-value redaction (new). All 171 existing runner tests must still pass (Success Criterion #11).

---

### `api_server/src/api_server/routes/health.py` (route, request→checker→JSON)

**Conceptual analog (REFERENCE ONLY — do not modify):** `api/internal/handler/health.go` lines 30-66.

**Critical departure per CONTEXT.md D-04:** SPLIT the Go file's single `/healthz` into two endpoints:

```python
@router.get("/healthz", include_in_schema=False)  # LB-only, internal
async def healthz():
    return {"ok": True}                            # ALWAYS 200, never touch deps

@router.get("/readyz", tags=["operational"])      # Operator-facing, in OpenAPI
async def readyz(request: Request):
    docker_ok = await _probe_docker()              # via asyncio.to_thread on `docker version`
    pg_ok = await _probe_postgres(request.app.state.db)
    return {
        "ok": docker_ok and pg_ok,
        "docker_daemon": docker_ok,
        "postgres": pg_ok,
        "schema_version": "ap.recipe/v0.1",
        "recipes_count": len(request.app.state.recipes),
        "concurrency_in_use": request.app.state.run_semaphore._value,  # introspect carefully
    }
```

**Docker probe pattern to mirror** (`tools/run_recipe.py::preflight_docker` line 409):
```python
result = subprocess.run(
    ["docker", "version", "--format", "{{.Server.Version}}"],
    timeout=DOCKER_DAEMON_PROBE_TIMEOUT_S,  # 5s
    capture_output=True, text=True, check=False,
)
```
Wrap the call in `asyncio.to_thread` since `subprocess.run` is sync.

---

### `api_server/src/api_server/models/errors.py` (pydantic model, error envelope)

**Conceptual analog (REFERENCE ONLY — Go, frozen):** `api/internal/handler/errors.go` lines 38-56.

**CONTEXT.md mandate (Stripe shape):**
```python
class ErrorBody(BaseModel):
    type: str          # "lint_error" | "rate_limit_error" | etc
    code: str          # "LINT_FAIL" | "RATE_LIMITED" | etc
    category: str | None = None  # mirrors Category enum when applicable
    message: str
    param: str | None = None     # JSON pointer or field name
    request_id: str              # ULID, also in X-Request-Id header

class ErrorEnvelope(BaseModel):
    error: ErrorBody
```

**Error code constants (mirror Go pattern lines 21-35, expand for Python concerns):**
- `INVALID_REQUEST`, `RECIPE_NOT_FOUND`, `LINT_FAIL`, `RATE_LIMITED`, `IDEMPOTENCY_BODY_MISMATCH`, `INTERNAL`, `UNAUTHORIZED`, `RUNNER_TIMEOUT`, `INFRA_UNAVAILABLE`.

**Use FastAPI `HTTPException` with `detail=ErrorEnvelope(...).model_dump()`** in all 4xx/5xx paths.

---

### `api_server/src/api_server/main.py` (app factory)

**Conceptual analog (REFERENCE ONLY):** `api/internal/server/server.go` lines 36-120 — functional-options + dependency injection style.

**Python equivalent — use `lifespan` + `app.state` (RESEARCH.md Pattern 1):**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool(settings.database_url)
    app.state.recipes = load_all_recipes(Path("recipes"))
    app.state.image_tag_locks = {}
    app.state.locks_mutex = asyncio.Lock()
    app.state.run_semaphore = asyncio.Semaphore(settings.max_concurrent_runs)
    yield
    await close_pool(app.state.db)
```

**Env-gated docs (CONTEXT.md D-10):**
```python
app = FastAPI(
    title="Agent Playground API", version="0.1.0",
    openapi_url="/openapi.json",                          # always on
    docs_url="/docs" if settings.env == "dev" else None,
    redoc_url="/redoc" if settings.env == "dev" else None,
    lifespan=lifespan,
)
```

---

### `api_server/tests/conftest.py` (test fixture)

**Style to mirror:** `tools/tests/conftest.py` lines 30-44 — factory fixtures returning configured callables.

**Existing pattern (study, then replace subprocess with httpx + testcontainers):**
```python
@pytest.fixture
def schema():
    """Load the JSON Schema for recipe validation."""
    schema_path = Path(__file__).parent.parent / "ap.recipe.schema.json"
    return json.loads(schema_path.read_text())
```

**Phase 19 fixtures needed:**
```python
@pytest.fixture(scope="session")
def postgres_container():
    """Real Postgres via testcontainers — D-01 mandate."""
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:17-alpine") as pg:
        # Run alembic upgrade head against pg.get_connection_url()
        yield pg

@pytest.fixture
async def db_pool(postgres_container):
    pool = await asyncpg.create_pool(postgres_container.get_connection_url())
    yield pool
    await pool.close()
    # TRUNCATE all tables between tests (RESEARCH.md §Test Framework)

@pytest.fixture
async def async_client(db_pool):
    """httpx ASGI client wired to the FastAPI app with the test pool injected."""
    from httpx import AsyncClient, ASGITransport
    app = create_app()
    app.state.db = db_pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.fixture
def mock_run_cell(monkeypatch):
    """Pattern-mirror tools/tests/conftest.py mock_subprocess factory."""
    def _configure(verdict_category="PASS", wall_s=1.0, exit_code=0):
        async def fake_to_thread(fn, *a, **kw):
            return (Verdict(Category(verdict_category), ""),
                    {"verdict": "PASS" if verdict_category == "PASS" else "FAIL",
                     "category": verdict_category, "wall_time_s": wall_s,
                     "exit_code": exit_code, "filtered_payload": "",
                     "stderr_tail": None, "detail": ""})
        monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    return _configure
```

---

### Integration test marker (`api_server/tests/test_runs.py`)

**Convention to mirror:** `tools/tests/test_integration_docker.py` lines 23-26:
```python
import pytest
pytestmark = pytest.mark.integration
```

**Phase 19 equivalent** — declare the new marker in `api_server/pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-x --tb=short -m 'not api_integration'"
markers = [
    "api_integration: spawn real Postgres + run real recipe; opt-in via pytest -m api_integration",
]
```
Mirrors `tools/pyproject.toml` lines 18-26 verbatim with `integration` → `api_integration`.

---

### `tools/Dockerfile.api` (deploy artifact, multi-stage build)

**Sibling-project analog (cribbable):** `/Users/fcavalcanti/dev/meusecretariovirtual/api/Dockerfile` (Go shape; below is the Python rewrite).

**Pattern to extract — multi-stage + non-root + HEALTHCHECK + EXPOSE:**
```dockerfile
# ---- Stage 1: builder ----
FROM python:3.11-slim AS build
WORKDIR /src
COPY api_server/pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install '.[deploy]'
COPY api_server/src ./src
COPY api_server/alembic ./alembic
COPY api_server/alembic.ini ./
COPY tools/run_recipe.py /install/lib/python3.11/site-packages/
COPY tools/ap.recipe.schema.json /install/lib/python3.11/site-packages/

# ---- Stage 2: runtime ----
FROM python:3.11-slim
ARG DOCKER_GID=999    # RESEARCH.md Pitfall 5
RUN apt-get update && apt-get install -y --no-install-recommends \
        docker.io curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupmod -g ${DOCKER_GID} docker \
    && useradd -m -u 1001 -G docker apiuser
COPY --from=build /install /usr/local
WORKDIR /app
COPY recipes /app/recipes:ro
USER apiuser
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=10s \
    CMD curl -sf http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "api_server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```
The shape (multi-stage, non-root user, EXPOSE, HEALTHCHECK with curl on `/healthz`) is a 1:1 conceptual port from MSV's Dockerfile.

---

### `deploy/docker-compose.prod.yml` (deploy artifact)

**Postgres service shape to mirror** (`docker-compose.dev.yml` lines 14-29):
```yaml
postgresql:
    image: postgres:17-alpine
    environment:
        POSTGRES_USER: temporal
        POSTGRES_PASSWORD: temporal
        POSTGRES_DB: temporal
    ports:
        - "127.0.0.1:5432:5432"
    volumes:
        - pgdata:/var/lib/postgresql/data
    healthcheck:
        test: ["CMD-SHELL", "pg_isready -U temporal"]
        interval: 5s
        timeout: 5s
        retries: 10
```

Phase 19 prod compose adapts this:
- `POSTGRES_DB`: `agent_playground_api` (not `temporal` — different concern)
- `POSTGRES_USER`/`POSTGRES_PASSWORD`: from `secrets:` block (not env literal)
- Drop public port mapping (api_server connects via the compose network)
- Keep healthcheck verbatim — `pg_isready` is the pattern.

**Full compose sketch** lives in RESEARCH.md lines 708-768.

---

### `deploy/init-api-db.sh` (deploy script, idempotent CREATE DATABASE)

**Analog to extend** (`deploy/dev/init-db.sh` lines 1-21):
```bash
#!/bin/bash
set -euo pipefail
COMPOSE_FILE="docker-compose.dev.yml"

if docker compose -f "$COMPOSE_FILE" exec -T postgresql \
    psql -U temporal -tAc "SELECT 1 FROM pg_database WHERE datname = 'agent_playground'" | grep -q 1; then
  echo "Database agent_playground already exists"
else
  docker compose -f "$COMPOSE_FILE" exec -T postgresql \
    psql -U temporal -c "CREATE DATABASE agent_playground OWNER temporal"
  echo "Database agent_playground created"
fi
```

Phase 19 prod equivalent: same shape, replace compose file path + DB name + user; **add `alembic upgrade head` after CREATE DATABASE** so the schema applies in the same script.

---

### `test/smoke-api.sh` (integration test, curl + cleanup)

**Analog to mirror** (`scripts/smoke-e2e.sh` lines 25-50):
```bash
set -euo pipefail
# arg parsing + skip-if-no-key guard
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
API_PORT="${API_PORT:-8000}"
API_BASE="${API_BASE:-http://localhost:${API_PORT}}"
COOKIE_JAR="$(mktemp -t ap-smoke-cookie.XXXXXX)"
API_LOG="$(mktemp -t ap-smoke-api.XXXXXX.log)"
# ... cleanup trap, then curl sequence
```

Phase 19 smoke executes the 9 checks from CONTEXT.md §Success Criteria (1-9) in order: `/healthz` → `/readyz` → `/v1/schemas` → `/v1/recipes` → `POST /v1/runs` → idempotency replay → `psql` count → 11th-request-429 → cleanup.

---

### `Makefile` (modified — add api-server target quartet)

**Analog to mirror** (`Makefile` lines 180-191):
```make
# --- Phase 09: Python recipe tools (D-10, D-20) ---
install-tools:
    pip install -e "tools/[dev]"

test:
    pytest tools/tests/ -v

lint-recipes:
    python3 tools/run_recipe.py --lint-all

check: lint-recipes test
```

**Phase 19 additions (mirror the quartet):**
```make
# --- Phase 19: API server (FastAPI) ---
install-api:
    pip install -e "api_server/[dev]"

test-api:
    cd api_server && pytest -q -m "not api_integration"

test-api-integration:
    cd api_server && pytest -m api_integration

migrate-api:
    cd api_server && alembic upgrade head

dev-api:
    cd api_server && uvicorn api_server.main:app --reload --port 8000

smoke-api:
    bash test/smoke-api.sh

smoke-api-live:
    API_BASE=https://api.agentplayground.dev bash test/smoke-api.sh

check-api: lint-recipes test-api
```

---

## Shared Patterns

### Pattern S-1: Stripe-shape error envelope

**Source:** `api/internal/handler/errors.go` lines 38-56 (REFERENCE ONLY — Go, frozen) + CONTEXT.md "Error envelope (Stripe shape)"

**Apply to:** every 4xx/5xx response in every route under `api_server/src/api_server/routes/*`

**Concrete:** `models/errors.py` defines `ErrorEnvelope`; routes raise `HTTPException(status_code=N, detail=ErrorEnvelope(error=ErrorBody(...)).model_dump())`. A FastAPI exception handler converts. Every error body carries `request_id` (the X-Request-Id contextvar from `asgi-correlation-id`).

---

### Pattern S-2: Per-call ruamel.yaml (no module singleton)

**Source:** CONTEXT.md "carried-forward decisions" + RESEARCH.md Pitfall 2 (ruamel ticket #367)

**Apply to:** `services/recipes_loader.py` and `services/lint_service.py` — every server-consumed YAML parse.

**Concrete:**
```python
from ruamel.yaml import YAML
yaml = YAML(typ="rt")  # FRESH per call — never module-level in server paths
```
The CLI runner (`tools/run_recipe.py` line 32) keeps its `_yaml = YAML(typ="rt")` singleton — that's a deliberate split.

---

### Pattern S-3: BYOK pass-through via runner's `--env-file`

**Source:** `tools/run_recipe.py` lines 684-693 + CONTEXT.md D-02

**Apply to:** `services/runner_bridge.py` (the only place `provider_key` flows from request → runner)

**Invariants:**
1. `Authorization: Bearer <key>` parsed at handler entry, held in local var only.
2. Passed as `api_key_val=<key>` kwarg to `run_cell` (which writes to `--env-file` chmod 0600).
3. **Never** logged — log middleware drops the `Authorization` header.
4. **Never** persisted — no DB column, no Redis, no disk.
5. After run completes, the local var goes out of scope; env_file is unlinked by the runner's `finally`.

---

### Pattern S-4: Pytest factory fixtures

**Source:** `tools/tests/conftest.py` lines 38-89 (`mock_subprocess`, `mock_subprocess_timeout`, `mock_subprocess_dispatch`)

**Apply to:** `api_server/tests/conftest.py` and every test that mocks the runner.

**Style:** the fixture returns a `_configure` callable; the test calls it with parameters. Avoids fixture parameter explosion, mirrors the existing convention.

---

### Pattern S-5: Integration marker (real-infra opt-in)

**Source:** `tools/pyproject.toml` lines 18-26 + `tools/tests/test_integration_docker.py` line 25

**Apply to:** `api_server/pyproject.toml` and any test that needs real Postgres + real Docker.

**Marker name:** `api_integration` (parallel to runner's `integration` — keeps them runnable independently).

**Default behavior:** `pytest -q` runs unit only. CI runs both as separate jobs.

---

### Pattern S-6: Idempotent bash deploy scripts

**Source:** `deploy/dev/init-db.sh` + `deploy/hetzner/install-postgres.sh`

**Apply to:** `deploy/init-api-db.sh`, `deploy/deploy.sh`

**Convention:**
- `set -euo pipefail` at top
- Check-before-create for every mutation (`SELECT 1 FROM pg_database WHERE...`, `if [ -f ... ]`, etc.)
- `[install-X] starting` / `[install-X] done` log markers
- Fall-back password generation when env unset (with file-write to `/root/agent-playground.secrets`)

---

### Pattern S-7: Compose service healthcheck + restart policy

**Source:** `docker-compose.dev.yml` lines 25-29:
```yaml
healthcheck:
    test: ["CMD-SHELL", "pg_isready -U temporal"]
    interval: 5s
    timeout: 5s
    retries: 10
```

**Apply to:** every service in `deploy/docker-compose.prod.yml`. The api_server healthcheck uses `curl -f http://localhost:8000/healthz` (mirrors MSV Dockerfile HEALTHCHECK).

---

## No Analog Found

These files are pure greenfield — no existing in-repo pattern matches. The planner consults RESEARCH.md (sections cited) for canonical-library patterns instead.

| File | Role | Data Flow | Reason | Use Instead |
|------|------|-----------|--------|-------------|
| `api_server/alembic/env.py` | migration runtime | DSN → engine → DDL | No existing migrations in repo (Go side uses `golang-migrate` embed, irrelevant for Python) | RESEARCH.md "Alembic async env.py baseline" lines 562-593 |
| `api_server/alembic/versions/001_baseline.py` | DDL migration | spec → tables | First migration ever | RESEARCH.md "DDL for baseline migration" lines 595-687 |
| `api_server/src/api_server/db.py` | asyncpg pool lifecycle | DSN → pool | No async DB code in repo | RESEARCH.md §Standard Stack + `asyncpg.create_pool` docs |
| `api_server/src/api_server/log.py` | structured logger | log records → JSON | No structured logging in Python codebase (Go side uses zerolog) | RESEARCH.md §Don't Hand-Roll (`structlog` 25.5.0) |
| `api_server/src/api_server/middleware/correlation_id.py` | middleware | X-Request-Id propagation | New concept | RESEARCH.md §Don't Hand-Roll (`asgi-correlation-id` 4.3.4) |
| `api_server/src/api_server/middleware/log_redact.py` | middleware | scope → allowlist log | New concept | RESEARCH.md "Pattern 5: Log redaction middleware" lines 372-410 |
| `api_server/src/api_server/middleware/rate_limit.py` | middleware | request → counter → 429 | No rate limit code in repo (Go side defers it) | RESEARCH.md "Pattern 4: Postgres-backed sliding-window-ish rate limit" lines 334-369 |
| `api_server/src/api_server/middleware/idempotency.py` | middleware | header → DB lookup | New concept | RESEARCH.md "Pattern 3: Idempotency with advisory lock" lines 289-332 |
| `api_server/src/api_server/services/idempotency.py` | service | advisory lock + INSERT | New concept | RESEARCH.md Pattern 3 + Pitfall 6 (request_body_hash) |
| `api_server/src/api_server/services/run_store.py` | repository | asyncpg writes/reads | No repository pattern in Python codebase yet | asyncpg parameterized-query canon; CONTEXT.md D-06 schema |
| `api_server/src/api_server/util/ulid.py` | utility | ULID gen/parse | No ULID in repo | `python-ulid` 3.1.0 docs |
| `api_server/src/api_server/config.py` | settings | env → typed config | First Python settings object | `pydantic-settings` canon |
| `deploy/Caddyfile` | reverse proxy + ACME | n/a | Caddy is new to repo (Go side used UFW + plain nginx-via-docker) | RESEARCH.md "Caddyfile" lines 690-706 |

---

## Metadata

**Analog search scope:**
- `tools/` (Python recipe runner — direct conceptual ancestor)
- `tools/tests/` (pytest convention)
- `recipes/` (data inventory)
- `api/` (Go substrate — REFERENCE ONLY for shape)
- `deploy/` (existing deploy artifacts — extend, do not modify the locked ones)
- `deploy/dev/` + `deploy/hetzner/` (Postgres install + DB init patterns)
- `scripts/` (bash convention)
- `Makefile` (build orchestration)
- `docker-compose.dev.yml` + `docker-compose.yml` (compose convention)
- `/Users/fcavalcanti/dev/meusecretariovirtual/api/Dockerfile` (sibling project, multi-stage Dockerfile shape)

**Files scanned:** ~40 in-repo + 1 sibling-project file

**Pattern extraction date:** 2026-04-16

**Repo posture for Phase 19:**
- ~33% of new files have a direct in-repo analog (mostly tests, Makefile additions, deploy scripts, schema/lint reuse).
- ~17% have a Go REFERENCE-ONLY analog (health, errors, server-factory shape) — reimplement in Python.
- ~50% are pure greenfield (FastAPI/asyncpg/Alembic/structlog) — planner uses RESEARCH.md library-canon patterns.

The single most important shared invariant the planner must enforce: **`tools/run_recipe.py` is read-only with one exception** — the `_redact_api_key` widening per CONTEXT.md D-02. Success Criterion #11 ("All existing runner unit tests (171 from phase 18) still pass unchanged") is the regression gate.
