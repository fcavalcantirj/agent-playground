# Phase 22c: oauth-google — Pattern Map

**Mapped:** 2026-04-19
**Files analyzed:** 29 (7 new backend + 11 modified backend + 6 frontend + 12 tests + 4 config/deps/env/errors)
**Analogs found:** 26 / 29 (3 flagged as "no analog" — see bottom section)
**Source-tree scope:** `api_server/src/api_server/**`, `api_server/alembic/versions/**`, `api_server/tests/**`, `frontend/**`, `deploy/**`

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `api_server/alembic/versions/005_sessions_and_oauth_users.py` | migration (additive) | schema DDL | `api_server/alembic/versions/003_agent_containers.py` | exact |
| `api_server/alembic/versions/006_purge_anonymous.py` | migration (destructive) | schema DDL | `api_server/alembic/versions/001_baseline.py` (docstring idiom) + `003_agent_containers.py` (revision header) | role-match (destructive migration is new kind) |
| `api_server/src/api_server/middleware/session.py` | middleware (ASGI) | request-response; PG lookup per request | `api_server/src/api_server/middleware/correlation_id.py` (re-export template shape) + `middleware/idempotency.py` (body of an ASGI middleware that hits `app.state.db`) + `middleware/rate_limit.py` (fail-open + `app.state` access) | role-match (composite) |
| `api_server/src/api_server/auth/deps.py` (new dir) | auth helper | in-process dispatch | `api_server/src/api_server/routes/agent_events.py::_err` (inline helper shape) | role-match (new module folder) |
| `api_server/src/api_server/auth/oauth.py` (new dir) | oauth-client registry (module-level singleton) | outbound HTTP (httpx) | `api_server/src/api_server/crypto/age_cipher.py::_master_key` (env-read + fail-loud pattern) | partial (nearest shape) |
| `api_server/src/api_server/routes/auth.py` | route | request-response (OAuth redirect round-trip) | `api_server/src/api_server/routes/agent_events.py` (Bearer auth + `_err` envelope) + `routes/runs.py` (9-step flow + inline _err) | role-match |
| `api_server/src/api_server/routes/users.py` | route | request-response (GET user-scoped) | `api_server/src/api_server/routes/agents.py` (simple GET + `request.app.state.db.acquire`) | exact |
| `api_server/src/api_server/main.py` (modify L208–211 + router include block L213+) | config/wiring | lifespan + middleware stack | (self — modify existing) | exact |
| `api_server/src/api_server/middleware/idempotency.py` (L36, L43, L159) | middleware (modify) | request-response | (self — swap ANONYMOUS_USER_ID for request.state.user_id; skip-on-None) | exact |
| `api_server/src/api_server/middleware/rate_limit.py` (modify subject derivation) | middleware (modify) | request-response | (self — keep IP fallback; prefer user_id when present) | exact |
| `api_server/src/api_server/middleware/log_redact.py::_redact_creds` | middleware (modify) | logging | (self — extend cookie allow/deny list) | exact |
| `api_server/src/api_server/constants.py` | constants (modify) | — | (self — delete `ANONYMOUS_USER_ID`, keep `AP_SYSADMIN_TOKEN_ENV`) | exact |
| `api_server/src/api_server/config.py` | config (modify) | env load | `api_server/src/api_server/config.py::Settings` (same file; add 7 Fields) | exact |
| `api_server/src/api_server/models/errors.py` | error codes (modify) | — | (self — `UNAUTHORIZED` already exists at L46 + `_CODE_TO_TYPE` mapping at L69; verify + no change expected) | exact |
| `api_server/src/api_server/routes/runs.py` (L38, L173) | route (modify) | request-response | (self — drop `ANONYMOUS_USER_ID` import; call `require_user` at top of `create_run`) | exact |
| `api_server/src/api_server/routes/agents.py` (L12, L23) | route (modify) | request-response | (self — drop `ANONYMOUS_USER_ID`; call `require_user`) | exact |
| `api_server/src/api_server/routes/agent_lifecycle.py` (L48, L245, L320, L338) | route (modify) | request-response | (self — 4 call-sites of `ANONYMOUS_USER_ID` migrate to `require_user`-resolved `user_id`) | exact |
| `api_server/src/api_server/routes/agent_events.py` (L76, L190) | route (modify) | request-response | (self — KEEP sysadmin bypass at L183–184; replace `ANONYMOUS_USER_ID` at L190 with `require_user`-derived `user_id`) | exact |
| `api_server/pyproject.toml` | deps (modify) | — | (self — L5-46 Structure; add `authlib`, `itsdangerous`, `respx`) | exact |
| `deploy/.env.prod.example` | config template (modify) | — | (self — file ALREADY contains AP_OAUTH_{GOOGLE,GITHUB}_* entries; add `AP_OAUTH_STATE_SECRET` stanza) | exact |
| `frontend/proxy.ts` (NEW; supersedes middleware.ts per AMD-06) | frontend-gate (edge matcher) | request-response | `frontend/middleware.ts` (existing; shape + matcher + `NextResponse.next()` + cookie read) | exact (renaming + stripping extra logic) |
| `frontend/app/login/page.tsx` | frontend-page (rewrite) | request-response | `frontend/lib/api.ts::apiPost` (the `credentials: 'include'` contract) + current `login/page.tsx` buttons at 54–66 (shape to preserve; replace handler) | role-match |
| `frontend/app/dashboard/layout.tsx` | frontend-page (rewrite) | client-side fetch | `frontend/lib/api.ts::apiGet` + `SessionUser` type + current `layout.tsx` (shape to preserve; replace L42 hardcode) | role-match |
| `frontend/components/navbar.tsx` (L231–236) | frontend-component (modify) | request-response | `frontend/lib/api.ts::apiPost` + same-file dropdown pattern at L231 | exact |
| `frontend/next.config.mjs` | frontend-config (modify) | request-response | (self — already contains `rewrites()`; append `redirects()`) | exact |
| `frontend/app/signup/page.tsx` + `frontend/app/forgot-password/page.tsx` | frontend-page (redirect target) | request-response | N/A (handled by `next.config.mjs::redirects()`) | n/a |
| `api_server/tests/auth/test_*.py` (multiple) | test | integration | `api_server/tests/test_rate_limit.py` (real PG + httpx AsyncClient + api_integration mark) + `api_server/tests/test_idempotency.py` (pytest-asyncio + cookie/header manipulation + monkeypatch counter) | exact |
| `api_server/tests/spikes/test_respx_authlib.py` | test (spike) | integration | `api_server/tests/test_rate_limit.py` (same harness) | role-match |
| `api_server/tests/spikes/test_truncate_cascade.py` | test (spike) | integration | `api_server/tests/test_migration.py` + existing `conftest.py::migrated_pg` (migration-aware fixture) | role-match |
| `api_server/tests/conftest.py` (augment) | test harness (modify) | fixture | (self — add respx + session-cookie + sessions-table TRUNCATE additions; NB current L120-124 TRUNCATE omits new `sessions` + `users` + `agent_events` + `agent_containers`) | exact |

---

## Pattern Assignments

### Migrations

#### `api_server/alembic/versions/005_sessions_and_oauth_users.py` (new-migration, additive)

**Analog:** `api_server/alembic/versions/003_agent_containers.py`

**Revision header pattern** (lines 45–57 of 003):
```python
"""Phase 22-02 — persistent-container audit table (agent_containers).

...

Revision ID: 003_agent_containers
Revises: 002_agent_name_personality
Create Date: 2026-04-18
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003_agent_containers"
down_revision = "002_agent_name_personality"
branch_labels = None
depends_on = None
```

**`create_table` + PK + FK + server_default idiom** (lines 60–111 of 003):
```python
def upgrade() -> None:
    op.create_table(
        "agent_containers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        ...
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
```

**Partial unique index idiom** (lines 125–131 of 003):
```python
op.create_index(
    "ix_agent_containers_agent_instance_running",
    "agent_containers",
    ["agent_instance_id"],
    unique=True,
    postgresql_where=sa.text("container_status = 'running'"),
)
```

**Adaptation notes:**
- `revision = "005_sessions_and_oauth_users"`, `down_revision = "004_agent_events"`.
- **TWO concerns in one migration** (D-22c-MIG-02): (a) `ALTER TABLE users ADD COLUMN sub TEXT`, `avatar_url TEXT`, `last_login_at TIMESTAMPTZ`; (b) `CREATE UNIQUE INDEX ON users(provider, sub) WHERE sub IS NOT NULL` (partial — preserves the ANONYMOUS row that has `provider=NULL, sub=NULL`); (c) `CREATE TABLE sessions(id UUID PK gen_random_uuid, user_id UUID FK users ON DELETE CASCADE, created_at, expires_at, last_seen_at, revoked_at, user_agent TEXT, ip_address INET)` + `CREATE INDEX ON sessions(user_id)` (per D-22c-MIG-04 — PK + btree(user_id) only).
- Use `op.add_column("users", sa.Column(...))` for the additive columns (idiom not shown in 003 because 003 is a create_table; see `002_agent_name_personality.py` for `add_column`).
- Downgrade path reverses: `op.drop_table("sessions")` + `op.drop_column("users", ...)` + drop the unique index. Mirror 003's 141–158 reverse-order pattern.

---

#### `api_server/alembic/versions/006_purge_anonymous.py` (new-migration, destructive — FIRST of its kind)

**Analog:** `api_server/alembic/versions/001_baseline.py::upgrade()` at lines 51–54 (uses `op.execute()` for raw SQL) + 001 downgrade shape (182–189).

**Raw SQL via `op.execute` pattern** (lines 26–28, 51–54 of 001):
```python
op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
...
op.execute(
    "INSERT INTO users (id, display_name) VALUES "
    "('00000000-0000-0000-0000-000000000001', 'anonymous')"
)
```

**Docstring idiom for load-bearing intent** (lines 1–13 of 001):
```python
"""Baseline schema for Phase 19 API foundation.

Creates the 5 platform tables per `.planning/phases/19-api-foundation/19-CONTEXT.md`
D-06 plus the Pitfall 6 mitigation column (`idempotency_keys.request_body_hash`)
and the `pgcrypto` extension required for `gen_random_uuid()`.

Table order matches FK dependency direction on upgrade, and the reverse on
downgrade. ...
"""
```

**Adaptation notes:**
- This is the FIRST destructive migration in the repo — docstring MUST warn about irreversibility (RESEARCH Pattern 6 has the exact body to copy).
- Single statement in `upgrade()`: `op.execute("TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users CASCADE")`. FK graph is TRUNCATE-CASCADE-safe per Spike B (Wave 0 D-22c-TEST-03).
- `def downgrade() -> None: raise NotImplementedError("006_purge_anonymous is irreversible. Data was dev-mock only; restore from PG dump if truly needed.")` — matches RESEARCH Pattern 6 lines 540–555.
- `revision = "006_purge_anonymous"`, `down_revision = "005_sessions_and_oauth_users"`.

---

### Middleware

#### `api_server/src/api_server/middleware/session.py` (new-middleware, ASGI)

**Analog (shape template):** `api_server/src/api_server/middleware/correlation_id.py` (thin re-export pattern — for docstring voice + import spot)
**Analog (body template):** `api_server/src/api_server/middleware/idempotency.py` (ASGI class + `app.state.db` + cookie header parsing)
**Analog (fail-open discipline):** `api_server/src/api_server/middleware/rate_limit.py` lines 126–136 (try/except → log + pass through)

**ASGI class skeleton + `app.state.db` acquire pattern** (from `middleware/idempotency.py`, lines 115–173):
```python
class IdempotencyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        ...
        app = scope["app"]
        try:
            async with app.state.db.acquire() as conn:
                tag, cached = await check_or_reserve(
                    conn, user_id, key, body_hash,
                )
        except Exception:
            _log.exception("idempotency backend error; failing open (not cached)")
            await self.app(scope, _replay_receive(body), send)
            return
```

**Header parsing via raw `scope["headers"]`** (from `middleware/idempotency.py` lines 50–55):
```python
def _get_header(scope: Scope, name_lower: bytes) -> bytes | None:
    for n, v in scope.get("headers", []):
        if n == name_lower:
            return v
    return None
```

**Fail-open try/except** (from `middleware/rate_limit.py` lines 126–136):
```python
try:
    async with app.state.db.acquire() as conn:
        allowed, retry_after = await check_and_increment(
            conn, subject, bucket, limit, window_s,
        )
except Exception:
    _log.exception("rate_limit backend error; failing open")
    await self.app(scope, receive, send)
    return
```

**Adaptation notes:**
- New body per RESEARCH Pattern 4 (lines 397–462): parse `Cookie: ap_session=...` inline (minimal `.split(';')`), `SELECT user_id, last_seen_at FROM sessions WHERE id=$1 AND revoked_at IS NULL AND expires_at > NOW()`, set `scope.setdefault("state", {})["user_id"] = user_id` (UUID|None), then await downstream.
- Add **throttled `last_seen_at` update** (D-22c-MIG-05) via Redis: `SET NX EX 60` on `ap:session:last_seen:<session_id>`; if SET returned 1 (new key), fire `UPDATE sessions SET last_seen_at=NOW() WHERE id=$1`.
- **NEW INFRA NOTE (gap flag):** Redis is NOT currently a service in this repo. Grep for `redis|Redis` in `api_server/src/` returned zero files. Planner must decide (a) bring in redis client + compose service, OR (b) amend D-22c-MIG-05 back to per-worker dict (RESEARCH Pitfall 7 accepts worker-count amplification). **Recommendation: flag in Wave 0 spike; if Redis not landed by then, use per-worker dict.**
- Keep `_log.exception` on PG lookup failure (fail-closed on unknown user: `user_id = None`).

---

#### `api_server/src/api_server/middleware/idempotency.py` (modify — L36, L43, L159)

**Analog:** self (existing implementation)

**Current problem lines:**
- L43: `from ..constants import ANONYMOUS_USER_ID`
- L159: `user_id = ANONYMOUS_USER_ID  # Phase 19 — Phase 21+ resolves real user`
- L20–L21 (docstring): `"...Phase 21+ swaps ``ANONYMOUS_USER_ID`` for a session-resolved user id; no middleware change needed."` — docstring is **now wrong**; this IS the change.

**Adaptation notes (per RESEARCH Pitfall 4, Option A — lines 686–691):**
- Drop `ANONYMOUS_USER_ID` import.
- Replace L159 with:
  ```python
  # Resolved by SessionMiddleware; None when anonymous.
  user_id = getattr(scope.get("state") or {}, "get", lambda *_: None)("user_id")
  # When scope.state isn't a dict (shouldn't happen after SessionMiddleware),
  # fall through to pass-through rather than 500.
  if user_id is None:
      # Anonymous request — no cache semantics. Any protected route will
      # 401 downstream via require_user; caching anonymous replays is moot.
      await self.app(scope, _replay_receive(body), send)
      return
  ```
- Update module docstring L18–21 to say "Phase 22c resolves `user_id` via SessionMiddleware; anonymous requests skip the cache."

---

#### `api_server/src/api_server/middleware/rate_limit.py` (modify — subject derivation)

**Analog:** self (existing `_subject_from_scope` at lines 70–91).

**Current pattern:**
```python
def _subject_from_scope(scope: Scope, trusted_proxy: bool) -> str:
    if trusted_proxy:
        for name, value in scope.get("headers", []):
            if name == b"x-forwarded-for":
                first = value.decode(errors="ignore").split(",")[0].strip()
                if first:
                    return first
                break
    client = scope.get("client")
    return client[0] if client else "unknown"
```

**Adaptation notes:**
- Prepend a user_id check: if `scope.get("state", {}).get("user_id")` is a UUID, return its stringified form as the subject (user-scoped rate-limit).
- Keep IP fallback for anonymous public routes (`/v1/recipes`, `/v1/lint`, OAuth authorize redirect).
- No change to `_bucket_for` or the class body.

---

#### `api_server/src/api_server/middleware/log_redact.py::_redact_creds` (modify)

**Analog:** self (`_LOG_HEADERS` allowlist at lines 27–33 — the existing BYOK-leak defense pattern).

**Current pattern:**
```python
_LOG_HEADERS = {
    "user-agent",
    "content-length",
    "content-type",
    "accept",
    "x-request-id",
}
```

**Adaptation notes:**
- The allowlist is already a **subtraction-not-addition** model: `cookie` is NOT in `_LOG_HEADERS`, so cookie values never land in logs. No-op for this phase — BUT verify + extend docstring to explicitly call out `Cookie`, `Set-Cookie`, `ap_session`, `ap_oauth_state` as redacted-by-construction.
- Only change needed: if a new future log line emits raw `scope["headers"]` outside this middleware (none today), the planner must confirm redaction coverage. Grep for `Set-Cookie` / `ap_session` in `api_server/src` should return zero hits outside of auth.py + session.py.

---

### Auth Layer (new)

#### `api_server/src/api_server/auth/deps.py` (new — `require_user` helper)

**Analog:** `api_server/src/api_server/routes/agent_events.py::_err` (lines 87–106).

**Inline envelope helper pattern** (lines 87–106):
```python
def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Build a Stripe-shape error envelope ``JSONResponse``.

    Mirrors ``routes/agent_lifecycle.py::_err`` byte-for-byte so every
    4xx/5xx response across the persistent-mode + event-stream surface
    uses the same construction.
    """
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )
```

**Adaptation notes (per CONTEXT D-22c-AUTH-03 + RESEARCH Open Question 1):**
- Function signature: `def require_user(request: Request) -> JSONResponse | UUID:` — NOT a FastAPI `Depends`. Planner decision locked: **return `JSONResponse | UUID`**; route handlers check `isinstance(result, JSONResponse)` and early-return.
- Body:
  ```python
  from uuid import UUID
  from fastapi import Request
  from fastapi.responses import JSONResponse
  from ..models.errors import ErrorCode, make_error_envelope

  def require_user(request: Request) -> JSONResponse | UUID:
      user_id = getattr(request.state, "user_id", None)
      if user_id is None:
          return JSONResponse(
              status_code=401,
              content=make_error_envelope(
                  ErrorCode.UNAUTHORIZED,
                  "Authentication required",
                  param="ap_session",
              ),
          )
      return user_id
  ```
- `ErrorCode.UNAUTHORIZED` and the `unauthorized` type mapping already exist in `models/errors.py` (lines 46, 69) — no new error code to add.

---

#### `api_server/src/api_server/auth/oauth.py` (new — authlib OAuth registry)

**Analog (nearest by shape):** `api_server/src/api_server/crypto/age_cipher.py::_master_key` (lines 49–75) for env-var fail-loud discipline + module-level singleton pattern.

**Env-var fail-loud pattern** (lines 49–75 of `crypto/age_cipher.py`):
```python
def _master_key() -> bytes:
    """Load AP_CHANNEL_MASTER_KEY from env; enforce 32-byte base64.

    Production (``AP_ENV=prod``) fails loud if the env is missing; dev
    falls back to a deterministic 32-zero-byte key so local tests round-
    trip without ops setup. The fallback is NEVER to ship to prod.
    """
    raw = os.environ.get("AP_CHANNEL_MASTER_KEY")
    env = os.environ.get("AP_ENV", "dev")
    if not raw:
        if env == "prod":
            raise RuntimeError(
                "AP_CHANNEL_MASTER_KEY required when AP_ENV=prod"
            )
        return b"\x00" * 32
    ...
    return key
```

**Adaptation notes (per RESEARCH Pattern 1 + Code Examples):**
- Module-level singleton `_oauth: OAuth | None = None` and `def get_oauth(settings) -> OAuth` factory. Register `google` (via `server_metadata_url` for OIDC discovery) + `github` (manual `access_token_url`/`authorize_url`/`api_base_url`).
- Apply the **fail-loud discipline** from `age_cipher::_master_key`: if `settings.env == "prod"` and any of `oauth_google_client_id / oauth_google_client_secret / oauth_github_client_id / oauth_github_client_secret / oauth_state_secret` is missing, `raise RuntimeError`. In dev, fall back to placeholder strings (matches `age_cipher` zero-byte fallback semantic).
- Add helpers `upsert_user(conn, provider, sub, email, display_name, avatar_url) -> UUID` and `mint_session(conn, user_id, request) -> str` in this module (both asyncpg one-liners; `mint_session` uses `secrets.token_urlsafe(32)` per RESEARCH "Don't Hand-Roll").

---

### Routes

#### `api_server/src/api_server/routes/auth.py` (new — 5 endpoints: google, google/callback, github, github/callback, logout)

**Analog:** `api_server/src/api_server/routes/runs.py` (9-step flow + `_err` pattern at lines 60–78) + `routes/agent_events.py` (Bearer parse at 165–180 — NOT used here; OAuth has its own state).

**9-step flow skeleton + `_err` helper** (from `routes/runs.py` lines 60–80):
```python
router = APIRouter()
_log = logging.getLogger("api_server.runs")

def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(
            code, message, param=param, category=category
        ),
    )
```

**Route declaration + Request-object pattern** (from `routes/runs.py` line 81–92):
```python
@router.post("/runs")
async def create_run(
    request: Request,
    body: RunRequest,
    authorization: str = Header(default=""),
):
    """...inline docstring...
    """
    if not authorization.startswith("Bearer "):
        return _err(
            401,
            ErrorCode.UNAUTHORIZED,
            "Bearer token required",
            param="Authorization",
        )
```

**DB scope discipline** (from `routes/runs.py` lines 169–179):
```python
pool = request.app.state.db
async with pool.acquire() as conn:
    agent_instance_id = await upsert_agent_instance(...)
    await insert_pending_run(conn, run_id, agent_instance_id, prompt)
```

**Adaptation notes (per RESEARCH Pattern 2 + Pattern 3):**
- 5 handlers. All use `@router.get` (`/auth/google`, `/auth/google/callback`, `/auth/github`, `/auth/github/callback`) except `POST /auth/logout`.
- authlib's `oauth.google.authorize_redirect(request, redirect_uri)` / `oauth.google.authorize_access_token(request)` do the heavy lifting (RESEARCH Pattern 2 lines 322–352).
- GitHub callback: extra round-trip `oauth.github.get("user/emails", token=token)` on null `/user.email` — RESEARCH Pattern 3 lines 358–393.
- Cookie setter helper `_set_session_cookie(resp, session_id, settings)` — SameSite=Lax, HttpOnly, Path=/, Max-Age=2592000; `Secure` only when `settings.env == "prod"`. D-22c-OAUTH-04.
- Error paths: `except OAuthError` → `return RedirectResponse("/login?error=oauth_failed", status_code=302)`; state-mismatch → `/login?error=state_mismatch`; denied consent (`request.query_params.get("error") == "access_denied"`) → `/login?error=access_denied`. D-22c-FE-03.
- Logout handler uses `require_user(request)` → DELETE session row → build RedirectResponse with `Set-Cookie: ap_session=; Max-Age=0; Path=/` to clear the browser cookie.
- **DO NOT** use FastAPI `Depends(require_user)` — per D-22c-AUTH-03, inline the check at the top of logout/users-me handlers.

---

#### `api_server/src/api_server/routes/users.py` (new — `GET /v1/users/me`)

**Analog:** `api_server/src/api_server/routes/agents.py` (the entire 24-line file — exactly the shape).

**Full template file** (`routes/agents.py`):
```python
"""``GET /v1/agents`` — list the logged user's deployed agents.
..."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..constants import ANONYMOUS_USER_ID
from ..models.agents import AgentListResponse, AgentSummary
from ..services.run_store import list_agents

router = APIRouter()


@router.get("/agents", response_model=AgentListResponse)
async def list_user_agents(request: Request) -> AgentListResponse:
    pool = request.app.state.db
    async with pool.acquire() as conn:
        rows = await list_agents(conn, ANONYMOUS_USER_ID)
    return AgentListResponse(agents=[AgentSummary(**r) for r in rows])
```

**Adaptation notes:**
- Replace `ANONYMOUS_USER_ID` call with `require_user(request)` inline check (CONTEXT D-22c-AUTH-03 canonical form):
  ```python
  result = require_user(request)
  if isinstance(result, JSONResponse):
      return result
  user_id: UUID = result
  async with pool.acquire() as conn:
      row = await conn.fetchrow(
          "SELECT id, email, display_name, avatar_url, provider, created_at "
          "FROM users WHERE id=$1", user_id,
      )
  ```
- Response shape matches `frontend/lib/api.ts::SessionUser` (lines 80–87) — `{id, email?, display_name, avatar_url?, provider?}`. Use a new Pydantic model `SessionUserResponse` in `models/users.py` (mirrors `models/agents.py` shape).

---

#### `api_server/src/api_server/routes/{runs,agents,agent_lifecycle,agent_events}.py` (modify — drop ANONYMOUS)

**Analog:** self.

**Current hardcode locations:**
- `routes/runs.py` L38 (import), L173 (`ANONYMOUS_USER_ID` passed to `upsert_agent_instance`).
- `routes/agents.py` L12 (import), L23 (`list_agents(conn, ANONYMOUS_USER_ID)`).
- `routes/agent_lifecycle.py` L48 (import), L245 / L320 / L338 / L558 / L679 / L791 (6 call-sites of `fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)` + `encrypt_channel_config(ANONYMOUS_USER_ID, ...)`).
- `routes/agent_events.py` L76 (import), L190 (`fetch_agent_instance(conn, agent_id, ANONYMOUS_USER_ID)`) — KEEP sysadmin bypass at L183–184 unchanged.

**Adaptation notes (per D-22c-AUTH-04):**
- Every handler prepends `result = require_user(request); if isinstance(result, JSONResponse): return result; user_id = result` at the top (AFTER Bearer parse in agent_events.py — the sysadmin bypass short-circuits BEFORE require_user).
- All `ANONYMOUS_USER_ID` references swap to the local `user_id`.
- Drop the `from ..constants import ANONYMOUS_USER_ID` import line from all 4 files.
- `routes/agent_lifecycle.py::agent_status` currently has NO Bearer check (lines 650–676) — adding `require_user` changes behavior. Planner decision: SPEC says `/v1/users/me` and `/v1/auth/logout` are protected; `/v1/agents/:id/status` was not listed but the RESEARCH treats the whole `/v1/agents/:id/*` surface as protected (CONTEXT D-22c-AUTH-03: "`/v1/agents/:id/*`"). **Flag: add require_user to status as well.**

---

#### `api_server/src/api_server/main.py` (modify — middleware stack + router include)

**Analog:** self (L185–249).

**Current middleware stack** (L208–211):
```python
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```

**Current router include block** (L213+):
```python
app.include_router(health.router)
app.include_router(schemas_route.router, prefix="/v1", tags=["schemas"])
app.include_router(recipes_route.router, prefix="/v1", tags=["recipes"])
app.include_router(runs_route.router, prefix="/v1", tags=["runs"])
app.include_router(agents_route.router, prefix="/v1", tags=["agents"])
app.include_router(
    agent_lifecycle_route.router, prefix="/v1", tags=["agents"]
)
app.include_router(
    agent_events_route.router, prefix="/v1", tags=["agents"]
)
```

**Adaptation notes (per RESEARCH "Wire Starlette SessionMiddleware" example lines 748–769 + CONTEXT D-22c-AUTH-01):**
- Insert TWO new middlewares into the existing declaration-order (outermost-last). Target effective request-in order:
  `CorrelationId → AccessLog → StarletteSession → (our) SessionMiddleware → RateLimit → Idempotency → routers`
- Code (replaces current L208–211):
  ```python
  from starlette.middleware.sessions import SessionMiddleware as StarletteSessionMiddleware
  from .middleware.session import SessionMiddleware as OurSessionMiddleware

  app.add_middleware(IdempotencyMiddleware)
  app.add_middleware(RateLimitMiddleware)
  app.add_middleware(OurSessionMiddleware)                      # ap_session → request.state.user_id
  app.add_middleware(                                           # authlib CSRF state store
      StarletteSessionMiddleware,
      secret_key=settings.oauth_state_secret,
      session_cookie="ap_oauth_state",
      max_age=600,
      same_site="lax",
      https_only=(settings.env == "prod"),
      path="/",
  )
  app.add_middleware(AccessLogMiddleware)
  app.add_middleware(CorrelationIdMiddleware)
  ```
- Add `app.include_router(auth_route.router, prefix="/v1", tags=["auth"])` and `app.include_router(users_route.router, prefix="/v1", tags=["users"])` after the existing event-stream router include.
- Lifespan: **no additional state** needed. Sessions are a PG lookup per request; no in-memory registry. (If Redis-throttled `last_seen_at` lands, add `app.state.redis` in lifespan — currently NOT present; gap flagged.)

---

### Config

#### `api_server/src/api_server/config.py` (modify — Pydantic settings fields)

**Analog:** self (`Settings` class, L28–50).

**Current pattern** (L36–50):
```python
# Not AP_ prefixed — industry convention.
database_url: str = Field(..., validation_alias="DATABASE_URL")

# AP_-prefixed knobs.
env: Literal["dev", "prod"] = Field("dev", validation_alias="AP_ENV")
max_concurrent_runs: int = Field(
    2, validation_alias="AP_MAX_CONCURRENT_RUNS"
)
recipes_dir: Path = Field(
    Path("recipes"), validation_alias="AP_RECIPES_DIR"
)
trusted_proxy: bool = Field(
    False, validation_alias="AP_TRUSTED_PROXY"
)
```

**Adaptation notes:**
- Append 7 fields (required in prod, optional in dev per the `age_cipher::_master_key` discipline — but Pydantic settings enforce required fields at INSTANTIATION time regardless of env. Solution: make them `Optional[str] = Field(None, ...)` and do the env-based fail-loud in `auth/oauth.py::get_oauth()`):
  ```python
  oauth_google_client_id: str | None = Field(None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_ID")
  oauth_google_client_secret: str | None = Field(None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_SECRET")
  oauth_google_redirect_uri: str | None = Field(None, validation_alias="AP_OAUTH_GOOGLE_REDIRECT_URI")
  oauth_github_client_id: str | None = Field(None, validation_alias="AP_OAUTH_GITHUB_CLIENT_ID")
  oauth_github_client_secret: str | None = Field(None, validation_alias="AP_OAUTH_GITHUB_CLIENT_SECRET")
  oauth_github_redirect_uri: str | None = Field(None, validation_alias="AP_OAUTH_GITHUB_REDIRECT_URI")
  oauth_state_secret: str | None = Field(None, validation_alias="AP_OAUTH_STATE_SECRET")
  ```
- The boot-time fail-loud lives in `auth/oauth.py::get_oauth()` (mirrors `crypto/age_cipher.py::_master_key` discipline).

---

#### `api_server/pyproject.toml` (modify — add deps)

**Analog:** self (L10–46).

**Current dependency block pattern** (L10–38):
```toml
dependencies = [
  "fastapi==0.136.0",
  "uvicorn[standard]>=0.44.0,<0.45",
  "asyncpg>=0.31.0,<0.32",
  ...
  "pyrage>=1.2",
  "cryptography>=42",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "testcontainers[postgres]>=4.14.2",
  "httpx>=0.27",
]
```

**Adaptation notes (per RESEARCH Standard Stack):**
- Append to `dependencies`:
  ```toml
  "authlib>=1.6.11,<1.7",
  "itsdangerous>=2.2.0,<3",
  ```
- Append to `dev`:
  ```toml
  "respx>=0.21,<0.22",
  ```
- `httpx` is already a dev dep (L45); authlib picks it up transitively as a prod dep. **Note:** this elevates `httpx` from dev-only to prod-transitive — planner should verify that's intentional (it is — authlib needs it at runtime for OAuth outbound).

---

#### `deploy/.env.prod.example` (modify — add `AP_OAUTH_STATE_SECRET`)

**Analog:** self.

**Current file already contains** (verified via `cat`):
- `AP_CHANNEL_MASTER_KEY=` (L21)
- `AP_SYSADMIN_TOKEN=` (L26)
- `AP_OAUTH_GOOGLE_{CLIENT_ID,CLIENT_SECRET,REDIRECT_URI}=` (L29–31)
- `AP_OAUTH_GITHUB_{CLIENT_ID,CLIENT_SECRET,REDIRECT_URI}=` (L36–38)

**Adaptation notes (per AMD-07):**
- Append a new stanza mirroring `AP_CHANNEL_MASTER_KEY`'s docstring shape:
  ```
  # Phase 22c: secret for Starlette SessionMiddleware CSRF-state cookie signing.
  # MUST be set in production; dev (AP_ENV=dev) falls back to a fixed dev-only
  # placeholder so local dev works without ops setup.
  # Generate: openssl rand -hex 32
  AP_OAUTH_STATE_SECRET=
  ```

---

#### `api_server/src/api_server/models/errors.py` (verify — `unauthorized` already present)

**Analog:** self.

**Verified existing:**
- `ErrorCode.UNAUTHORIZED = "UNAUTHORIZED"` at L46.
- `_CODE_TO_TYPE[ErrorCode.UNAUTHORIZED] = "unauthorized"` at L69.

**Adaptation notes:** No change required. Planner can verify + skip.

---

### Frontend

#### `frontend/proxy.ts` (NEW — supersedes `frontend/middleware.ts`)

**Analog:** `frontend/middleware.ts` (existing file at lines 1–41 — shape + matcher template).

**Full current template** (`frontend/middleware.ts`):
```typescript
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const session = request.cookies.get("ap_session");
  const res = NextResponse.next();
  if (session) {
    res.headers.set("x-ap-has-session", "1");
  }
  return res;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
```

**Adaptation notes (per AMD-06 + RESEARCH Pattern 7 lines 562–581):**
- Rename file → `frontend/proxy.ts` (Next 16.2 convention; old `middleware.ts` emits deprecation warning).
- Rename export `middleware` → default-export `proxy`.
- Narrow matcher: `["/dashboard/:path*"]` only (per D-22c-FE-01). Landing page stays public.
- Body: if no `ap_session` cookie, 307 redirect to `/login`; else `NextResponse.next()`.
- Concrete body:
  ```typescript
  import { NextResponse } from "next/server";
  import type { NextRequest } from "next/server";

  export default function proxy(request: NextRequest) {
    const session = request.cookies.get("ap_session");
    if (!session) {
      const loginUrl = new URL("/login", request.url);
      return NextResponse.redirect(loginUrl, 307);
    }
    return NextResponse.next();
  }

  export const config = {
    matcher: ["/dashboard/:path*"],
  };
  ```
- **Delete** `frontend/middleware.ts` in the same plan (incorrect comment + redundant matcher + unused `x-ap-has-session` header per RESEARCH Assumption A9).

---

#### `frontend/app/login/page.tsx` (rewrite)

**Analog (API contract):** `frontend/lib/api.ts::apiPost` + `credentials: "include"` (lines 28–52) — but login uses **top-level nav**, not `fetch`.
**Analog (shape to preserve):** existing `frontend/app/login/page.tsx` lines 52–66 (Google + GitHub button JSX).

**Current setTimeout theater** (lines 20–26 — REPLACE):
```typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault()
  setIsLoading(true)
  await new Promise(resolve => setTimeout(resolve, 1000))
  router.push("/dashboard")
}
```

**Adaptation notes (per R6 + D-22c-FE-03 + D-22c-UI-01):**
- DROP `handleSubmit`. Email/password form becomes `<form onSubmit={(e) => e.preventDefault()}>` with inputs + submit button all `disabled` — keep visual shape, no handler.
- Wire the **existing** Google button (L58–66) + GitHub button (L54–57) to real OAuth:
  ```typescript
  const onGoogle = () => { window.location.href = "/api/v1/auth/google"; };
  const onGitHub = () => { window.location.href = "/api/v1/auth/github"; };
  ```
- Add `?error=` param handling on mount (D-22c-FE-03). Use `sonner` toast (already in package.json per RESEARCH line 65):
  ```typescript
  import { toast } from "sonner";
  useEffect(() => {
    const err = new URLSearchParams(window.location.search).get("error");
    if (err === "access_denied") toast.error("Sign-in cancelled");
    else if (err === "state_mismatch") toast.error("Security check failed — try again");
    else if (err === "oauth_failed") toast.error("Sign-in failed — try again");
  }, []);
  ```
- Remove the `<Link href="/forgot-password">Forgot password?</Link>` (D-22c-UI-03 — avoid dead-end loop).
- Remove `setTimeout`, `setIsLoading(true)`, `await new Promise` — grep must return 0 setTimeout hits post-change (SPEC acceptance criterion).

---

#### `frontend/app/dashboard/layout.tsx` (rewrite)

**Analog (API contract):** `frontend/lib/api.ts::apiGet<SessionUser>('/api/v1/users/me')` (lines 54–59 + 80–87).
**Analog (shape to preserve):** existing `frontend/app/dashboard/layout.tsx` lines 36–104 (sidebar + Navbar + overlay).

**Current hardcode** (lines 39–45 — REPLACE):
```typescript
<Navbar
  isLoggedIn={true}
  user={{
    name: "Alex Chen",
    email: "alex@example.com",
  }}
/>
```

**Adaptation notes (per R7 + D-22c-FE-02):**
- Add `useUser()` hook (new file `frontend/hooks/use-user.ts`) that wraps `apiGet<SessionUser>('/api/v1/users/me')`. On 401 `ApiError`, `router.push('/login')`.
- Hook skeleton:
  ```typescript
  // frontend/hooks/use-user.ts
  "use client";
  import { useEffect, useState } from "react";
  import { useRouter } from "next/navigation";
  import { apiGet, ApiError, SessionUser } from "@/lib/api";

  export function useUser() {
    const router = useRouter();
    const [user, setUser] = useState<SessionUser | null>(null);
    useEffect(() => {
      let cancelled = false;
      apiGet<SessionUser>("/api/v1/users/me")
        .then(u => { if (!cancelled) setUser(u); })
        .catch(err => {
          if (err instanceof ApiError && err.status === 401) {
            router.push("/login");
          }
        });
      return () => { cancelled = true; };
    }, [router]);
    return user;
  }
  ```
- Layout eager-renders (no Suspense, no full-page spinner — D-22c-FE-02). Navbar receives `user={user ?? undefined}` and renders its avatar/name fallback (existing `AvatarFallback` at `navbar.tsx:192–194` already handles missing `user`).
- `name` → `display_name` mapping. The `NavbarProps.user` shape is `{name, email, avatar?}` (L33–38 of `navbar.tsx`); `SessionUser` is `{id, email?, display_name, avatar_url?, provider?}`. Pass:
  ```typescript
  user={user ? {
    name: user.display_name,
    email: user.email ?? "",
    avatar: user.avatar_url,
  } : undefined}
  ```
- `isLoggedIn={true}` stays unconditional — the `proxy.ts` gate already 307'd unauthenticated users.

---

#### `frontend/components/navbar.tsx` (modify — L231–236)

**Analog:** self.

**Current dead-theater link** (L231–236):
```tsx
<DropdownMenuItem asChild className="text-destructive focus:text-destructive">
  <Link href="/login">
    <LogOut className="mr-2 h-4 w-4" />
    Log out
  </Link>
</DropdownMenuItem>
```

**Adaptation notes (per D-22c-UI-04):**
- Replace `<Link href="/login">` with a real `<button>`:
  ```tsx
  <DropdownMenuItem
    className="text-destructive focus:text-destructive"
    onSelect={async (e) => {
      e.preventDefault();
      try { await apiPost("/api/v1/auth/logout", {}); }
      catch { /* server-side session may already be gone; fall through */ }
      router.push("/login");
    }}
  >
    <LogOut className="mr-2 h-4 w-4" />
    Log out
  </DropdownMenuItem>
  ```
- Add `import { apiPost } from "@/lib/api";` + `import { useRouter } from "next/navigation";` + `const router = useRouter();` at the top of `Navbar`.

---

#### `frontend/next.config.mjs` (modify — add `redirects()`)

**Analog:** self (L16–31 `rewrites()` is the shape).

**Current pattern** (L16–31):
```javascript
async rewrites() {
  return [
    {
      source: "/api/v1/:path*",
      destination: `${API_PROXY_TARGET}/v1/:path*`,
    },
    ...
  ]
},
```

**Adaptation notes (per D-22c-UI-02 + D-22c-UI-03 + RESEARCH Pattern 8):**
- Add a sibling `redirects()` async function:
  ```javascript
  async redirects() {
    return [
      { source: "/signup", destination: "/login", permanent: false },
      { source: "/forgot-password", destination: "/login", permanent: false },
    ];
  },
  ```
- `permanent: false` ⇒ 307 temporary (so future dedicated signup/forgot-password flows can be re-enabled without breaking browser caches).

---

### Tests

#### `api_server/tests/auth/test_*.py` (new — OAuth flow tests)

**Analog:** `api_server/tests/test_rate_limit.py` + `test_idempotency.py` (both use `async_client` fixture + `api_integration` mark + `mock_run_cell` when needed).

**Integration test pattern** (from `test_rate_limit.py` L26–64):
```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_429_after_limit(async_client, mock_run_cell):
    mock_run_cell(verdict_category="PASS")
    for i in range(10):
        r = await async_client.post(
            "/v1/runs",
            headers=AUTH,
            json={"recipe_name": "hermes", "model": "m", "prompt": "p"},
        )
        assert r.status_code == 200, (...)
    r = await async_client.post("/v1/runs", headers=AUTH, json={...})
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["type"] == "rate_limit_error"
```

**Monkeypatch + counter pattern** (from `test_idempotency.py` L39–55):
```python
call_count = {"n": 0}
async def counted_to_thread(fn, *a, **kw):
    call_count["n"] += 1
    return {...}
monkeypatch.setattr("asyncio.to_thread", counted_to_thread)
```

**Adaptation notes (per D-22c-TEST-01 + AMD-05):**
- Every OAuth integration test marks `@pytest.mark.api_integration` + `@pytest.mark.asyncio`.
- Use `respx` (RESEARCH Code Examples line 771–799) to stub Google/GitHub endpoints. Decorator: `@respx.mock` or `with respx.mock:` context manager.
- Canonical shape for `test_google_callback_success`:
  ```python
  @pytest.mark.api_integration
  @pytest.mark.asyncio
  @respx.mock
  async def test_google_callback_success(async_client):
      respx.post("https://oauth2.googleapis.com/token").mock(
          return_value=httpx.Response(200, json={
              "access_token": "ya29.test", "token_type": "Bearer",
              "expires_in": 3600, "id_token": "<test-jwt>", "scope": "openid email profile",
          })
      )
      respx.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
          return_value=httpx.Response(200, json={
              "sub": "1234567890", "email": "test@gmail.com",
              "name": "Test User", "picture": "https://example.com/a.png",
          })
      )
      # drive the full /v1/auth/google → Google round-trip → /v1/auth/google/callback
      # and assert sessions row inserted + ap_session Set-Cookie + 302 Location: /dashboard
  ```
- `test_cross_user_isolation.py`: seed TWO users via direct DB insert, mint TWO sessions, issue `GET /v1/agents` with each cookie → assert each sees only their own agents. Mirrors `test_idempotency.py::test_same_key_returns_cache` pattern (direct DB inserts + httpx cookie header).

---

#### `api_server/tests/spikes/test_respx_authlib.py` (new — Wave 0 Spike A)

**Analog:** `api_server/tests/test_rate_limit.py` (minimal test harness).

**Adaptation notes (per D-22c-TEST-03):**
- ~10-line pytest. Register an authlib `StarletteOAuth2App`, call its token-exchange path, assert `respx` intercepted the call. Evidence artifact lives at `.planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md`.
- NO DB needed — the conftest `db_pool` / `async_client` fixtures can be skipped (test just wires authlib + respx, no asyncpg).

---

#### `api_server/tests/spikes/test_truncate_cascade.py` (new — Wave 0 Spike B)

**Analog:** `api_server/tests/test_migration.py` + `conftest.py::migrated_pg` (session-scoped migrated testcontainer).

**Fixture pattern** (from `conftest.py` L46–73):
```python
@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17-alpine") as pg:
        yield pg

@pytest.fixture(scope="session")
def migrated_pg(postgres_container):
    ...
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_SERVER_DIR,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return postgres_container
```

**Adaptation notes (per D-22c-TEST-03 Spike B):**
- Spike runs alembic 001..005 (NOT 006 — 006 is the thing being tested). Seeds each data-bearing table with one row. Issues `TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users CASCADE`. Asserts all 8 tables have COUNT=0 AND `alembic_version` still holds `'005_sessions_and_oauth_users'`.
- Evidence artifact at `.planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md`.

---

#### `api_server/tests/conftest.py` (augment — add OAuth fixtures + fix TRUNCATE coverage)

**Analog:** self.

**Current TRUNCATE gap** (L120–124):
```python
await conn.execute(
    "TRUNCATE TABLE rate_limit_counters, idempotency_keys, runs, "
    "agent_instances RESTART IDENTITY CASCADE"
)
```

**Adaptation notes (post-Phase 22c):**
- Add `sessions` to the TRUNCATE list. The docstring at L99–102 says "``users`` is intentionally NOT truncated — the anonymous seed row ... must survive" — **AMD-03 deletes the ANONYMOUS row in migration 006**, so this rationale collapses. Planner decides: TRUNCATE `users` too (per test-isolation purity) OR keep the anonymous-row seed semantics for back-compat with any legacy tests. **Recommendation:** TRUNCATE `users` + `sessions` + `agent_containers` + `agent_events`; each OAuth test creates its own user explicitly.
- Add `@pytest.fixture def authenticated_cookie(...)` — creates a user row + session row + returns `{"Cookie": "ap_session=<id>"}` for httpx.
- Add `@pytest.fixture` wrapping `respx.mock()` for consistent stubs across auth tests.

---

## Shared Patterns

### Authentication (401 envelope + inline `_err` discipline)

**Source:** `api_server/src/api_server/routes/agent_events.py::_err` (lines 87–106) + `models/errors.py::make_error_envelope` (lines 124–147).

**Apply to:** Every new or modified route file. Planner must NOT introduce FastAPI `Depends(require_user)` raising `HTTPException` — it double-wraps the envelope (RESEARCH anti-pattern confirmed lines 602–603).

```python
from fastapi.responses import JSONResponse
from ..models.errors import ErrorCode, make_error_envelope

def _err(status: int, code: str, message: str, *, param: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param),
    )
```

### require_user inline check (applied at top of every protected handler)

**Source:** new `api_server/src/api_server/auth/deps.py::require_user` (see Auth Layer above).

**Apply to:** `/v1/runs` (POST+GET), `/v1/agents` (GET), `/v1/agents/:id/start`, `/stop`, `/status`, `/channels/:cid/pair`, `/events`, `/events/inject-test-event` (AFTER sysadmin bypass), `/v1/users/me`, `/v1/auth/logout`.

**Shape (applied at top of handler body, after Bearer parse where applicable):**
```python
result = require_user(request)
if isinstance(result, JSONResponse):
    return result
user_id: UUID = result
```

### DB scope discipline (Pitfall 4)

**Source:** `api_server/src/api_server/routes/runs.py` lines 169–179 (scope 1 before await) + 217–218 (scope 2 after await).

**Apply to:** SessionMiddleware PG lookup, `/v1/auth/*/callback` upsert + session insert, `/v1/users/me` SELECT, `/v1/auth/logout` DELETE.

Every DB interaction uses its own `async with pool.acquire() as conn:` scope. Never hold a conn across a long await (OAuth round-trip is a long await).

### Cookie redaction by construction (log safety)

**Source:** `api_server/src/api_server/middleware/log_redact.py::_LOG_HEADERS` (lines 27–33 — allowlist model).

**Apply to:** Verify that no new log line (in `routes/auth.py`, `middleware/session.py`, `auth/oauth.py`) emits raw `Cookie:` or `Set-Cookie:` header values. The existing allowlist mechanism makes this safe by default — no positive change required, just a grep check during review.

### Fail-loud env-var discipline

**Source:** `api_server/src/api_server/crypto/age_cipher.py::_master_key` (lines 49–75).

**Apply to:** `auth/oauth.py::get_oauth()` — in prod, raise `RuntimeError` if any of the 7 OAuth env vars is missing. In dev, fall back to deterministic placeholder strings.

### Stripe-envelope error codes (already present)

**Source:** `api_server/src/api_server/models/errors.py::ErrorCode.UNAUTHORIZED` (L46) + `_CODE_TO_TYPE` map (L69).

**Apply to:** Every 401 in the new auth routes. The `unauthorized` type → `UNAUTHORIZED` code mapping is already registered.

---

## No Analog Found (flagged gaps)

Three files/patterns have no close match in the repo. Planner must draw from RESEARCH.md / external docs directly:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `api_server/src/api_server/auth/oauth.py` (authlib registry + `upsert_user` + `mint_session`) | oauth-client + session-mint service | outbound HTTP via httpx | No prior OAuth/authlib integration anywhere in the repo. Nearest shape is `crypto/age_cipher.py` for the env-var + singleton pattern, but the authlib registration API is entirely new. Consume RESEARCH Pattern 1 + Code Examples lines 722–744 verbatim. |
| `api_server/src/api_server/middleware/session.py` Redis-backed throttle for `last_seen_at` | middleware-adjacent cache | pub-sub style (SET NX EX) | Redis is NOT in the current stack. `go-redis/v9` is listed in CLAUDE.md as the intended library but Python side has no `redis-py` dep + no compose service + no `app.state.redis`. Planner flags: (a) add Redis client + compose service + pyproject dep this phase, OR (b) amend D-22c-MIG-05 to per-worker dict (acceptable per RESEARCH Pitfall 7). **Strong recommendation: defer Redis to a follow-up phase; use `app.state.session_last_seen: dict[str, float]` in this phase.** |
| `frontend/proxy.ts` (Next 16.2 filename) | edge matcher | request-response | `frontend/middleware.ts` is the direct shape template (rename + narrow matcher). Gap is nomenclature + matcher shape — copy from RESEARCH Pattern 7 lines 562–581. |

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/middleware/` (4 files)
- `api_server/src/api_server/routes/` (8 files)
- `api_server/src/api_server/models/errors.py`
- `api_server/src/api_server/crypto/age_cipher.py`
- `api_server/src/api_server/config.py`, `constants.py`, `main.py`, `db.py`
- `api_server/alembic/versions/` (4 existing migrations)
- `api_server/tests/conftest.py` + `test_idempotency.py` + `test_rate_limit.py` + `test_migration.py`
- `api_server/pyproject.toml`
- `frontend/app/login/page.tsx`, `frontend/app/dashboard/layout.tsx`, `frontend/components/navbar.tsx`, `frontend/middleware.ts`, `frontend/next.config.mjs`, `frontend/lib/api.ts`
- `deploy/.env.prod.example`

**Files scanned:** ~35 source files + 4 migrations + 3 test files + 6 frontend files = ~48 load-bearing reads.

**Pattern extraction date:** 2026-04-19

---

## PATTERN MAPPING COMPLETE

**Phase:** 22c - oauth-google
**Files classified:** 29
**Analogs found:** 26 / 29

### Coverage
- Files with exact analog: 19
- Files with role-match analog: 7
- Files with no analog: 3 (flagged — oauth registry, Redis throttle cache, proxy.ts filename)

### Key Patterns Identified
- **All new/modified routes use the inline `_err()` → `JSONResponse` pattern with `make_error_envelope`** — NOT FastAPI `HTTPException`. Planner must resist introducing `Depends(require_user)` that raises; use the `JSONResponse | UUID` return pattern instead.
- **ASGI middlewares share a uniform body shape** — `if scope["type"] != "http": pass through`, raw-header scan over `scope["headers"]`, `try: app.state.db.acquire() ... except: log + fail-open`. `middleware/session.py` composes `correlation_id.py` (shape) + `idempotency.py` (body) + `rate_limit.py` (fail-open discipline).
- **Alembic migrations follow a rigid revision-header + `op.create_table` → PK UUID + server_default gen_random_uuid() + FK → nullable + timestamped audit columns + partial-unique indexes** shape. Migration 005 is purely additive; 006 is the FIRST destructive migration and must carry the `NotImplementedError` downgrade + warning docstring pattern from RESEARCH Pattern 6.
- **Env-var fail-loud discipline** (`crypto/age_cipher.py::_master_key`) extends cleanly to the 7 new OAuth env vars — prod raises, dev falls back. Pydantic settings fields stay `Optional[str]` because the fail-loud check happens at `get_oauth()` time, not Settings instantiation time.
- **Frontend is a dumb client** — `apiGet<SessionUser>('/api/v1/users/me')` + `apiPost('/api/v1/auth/logout', {})` via the existing `lib/api.ts` wrapper. Zero new frontend deps (sonner already present). Auth state flows via HTTP-only cookie; React never sees the session_id value.

### Gaps Flagged for Planner
1. **Redis is NOT in the stack** (D-22c-MIG-05 mandates Redis-backed throttle cache). Recommendation: use per-worker dict per RESEARCH Pitfall 7; defer Redis to a follow-up phase. If planner insists on Redis, add: `redis` compose service, `redis-py` to `pyproject.toml` deps, `app.state.redis = redis.Redis(...)` in `main.py::lifespan`, `.env.prod.example` `REDIS_URL=` entry.
2. **`conftest.py` TRUNCATE list is stale** — doesn't include the new `sessions` + existing `agent_containers` + `agent_events`; relies on anonymous-user seed (about to be purged by migration 006). Must be fixed IN THIS PHASE or tests bleed state between runs.
3. **`routes/agent_lifecycle.py::agent_status` currently has NO Bearer check** (lines 650–676). D-22c-AUTH-03's `/v1/agents/:id/*` pattern says protect it — but that's a behavior change beyond pure ANONYMOUS replacement. Planner confirms: apply `require_user` to `agent_status` too.
4. **The existing `middleware/idempotency.py` docstring (L18–21) lies** — "Phase 21+ swaps ANONYMOUS_USER_ID ... no middleware change needed." The middleware DOES need changes (Pitfall 4 pass-through on None). Docstring must be updated in the same plan that modifies the code.
5. **The existing `frontend/middleware.ts` has an INCORRECT comment** (L17–19) asserting "The middleware file convention remains `middleware.ts` in Next.js 16. There is no `proxy.ts` rename — that claim was incorrect." Next 16.2 DID rename it (AMD-06). Plan must delete this file + replace with `frontend/proxy.ts`.

### File Created
`.planning/phases/22c-oauth-google/22c-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files. Every new file has at least one concrete code excerpt to copy from; every modification has its source line-range called out. Three gaps require planner decisions (Redis vs per-worker-dict, conftest.py TRUNCATE scope, agent_status protection); all are flagged above with recommendations.
