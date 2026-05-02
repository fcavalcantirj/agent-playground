# Phase 23: Backend Mobile API — Pattern Map

**Mapped:** 2026-05-01
**Files analyzed:** 17 (8 new, 7 extended, 1 frontend, 1 deploy)
**Analogs found:** 16/17 (one novel — `services/openrouter_models.py`, partial-match)

## File Classification

| File | New/Extended | Role | Data Flow | Closest Analog | Match |
|------|--------------|------|-----------|----------------|-------|
| `api_server/src/api_server/routes/models.py` | NEW | controller | request-response (in-process cache + outbound HTTP) | `routes/recipes.py` (read-only `/v1/recipes`) | role-match |
| `api_server/src/api_server/services/openrouter_models.py` | NEW | service | request-response (cache + httpx fetch + stale-while-revalidate) | NONE — first lifespan-owned cache service | partial / novel |
| `api_server/tests/auth/test_oauth_mobile.py` | NEW | test | integration (respx + asyncpg) | `tests/auth/test_google_callback.py` + `test_github_callback.py` | exact |
| `api_server/tests/routes/test_models.py` | NEW | test | integration (respx-mocked HTTP + cache state introspection) | `tests/spikes/test_respx_authlib.py` (respx pattern) + `test_users_me.py` (route shape) | role-match |
| `api_server/tests/spikes/test_gzip_sse_compat.py` | NEW (Wave 0) | test/spike | integration (real GZipMiddleware + SSE chunk timing) | `tests/spikes/test_respx_authlib.py` (spike file shape) | role-match |
| `api_server/tests/spikes/test_google_auth_multi_audience.py` | NEW (Wave 0, optional) | test/spike | unit (google-auth library probe) | `tests/spikes/test_respx_authlib.py` | role-match |
| `api_server/tests/spikes/test_respx_intercepts_pyjwk_fetch.py` | NEW (Wave 0, optional) | test/spike | unit (respx + pyjwt PyJWKClient probe) | `tests/spikes/test_respx_authlib.py` | exact |
| `api_server/tests/routes/test_messages_idempotency_required.py` | NEW | test | integration (httpx ASGITransport + db_pool) | `tests/test_idempotency.py` + `tests/routes/test_agent_messages_post.py` | exact |
| `api_server/tests/routes/test_agents_status_field.py` | NEW | test | integration (real PG, seed agent_containers row) | `tests/routes/test_agent_messages_post.py::_seed_agent_for_user` | role-match |
| `deploy/.env.prod.example` | EXTEND | config | env-template | self (existing Phase 22c OAuth env stanzas at lines 27-38) | exact |
| `api_server/src/api_server/routes/auth.py` | EXTEND | controller | request-response | self (existing `google_callback` / `github_callback`) | exact |
| `api_server/src/api_server/auth/oauth.py` | EXTEND | service | request-response (HTTP + DB) | self (existing `upsert_user` / `mint_session`) | exact |
| `api_server/src/api_server/services/run_store.py::list_agents` | EXTEND | service | CRUD (asyncpg) | self (existing LATERAL JOIN) | exact |
| `api_server/src/api_server/models/agents.py::AgentSummary` | EXTEND | model | shape | self (existing field declarations) | exact |
| `api_server/src/api_server/routes/agent_messages.py::post_message` | EXTEND | controller | request-response | self (existing `_err()` + `require_user` flow) | exact |
| `api_server/src/api_server/main.py` | EXTEND | config | middleware-wiring | self (existing `add_middleware` block + lifespan `bot_http_client`) | exact |
| `api_server/src/api_server/config.py` | EXTEND | config | env-loading | self (existing `oauth_*` Field declarations) | exact |
| `frontend/components/playground-form.tsx:169` | EXTEND | component | fetch → API client | line 154 (`apiGet<{recipes}>("/api/v1/recipes")`) | exact (same file, 15 lines up) |

> **Decision flag resolved (2026-05-01, plan-checker iter 1, W-04):** the `.env.dev.example` vs `.env.prod.example` decision flag (originally surfaced in this file's `deploy/.env.dev.example` section) is closed in favor of **EXTEND `deploy/.env.prod.example`**. No new dev env file is created — the dev OAuth fallback is already covered by `_DEV_PLACEHOLDER` in `auth/oauth.py` per RESEARCH. Plan 23-01 Task 6 implements this by appending a Phase 23 stanza to the existing prod env template.

---

## Pattern Assignments

### `api_server/src/api_server/routes/models.py` (NEW — controller, request-response)

**Analog:** `api_server/src/api_server/routes/recipes.py` (read-only `/v1/recipes` returning `request.app.state.recipes`).

**Why this analog:** both are read-only `/v1/<noun>` routes that pull pre-warmed data off `app.state`. Difference: `/v1/recipes` reads a static dict loaded at boot; `/v1/models` reads a TTL-bounded cache populated lazily by the new service module. Same shape: minimal handler, `request: Request`, `app.state.<thing>` lookup, return raw payload.

**Imports + module shape (mirror `routes/recipes.py:14-29`):**
```python
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response  # Response for raw-bytes passthrough

from ..models.errors import ErrorCode, make_error_envelope
from ..services.openrouter_models import get_models_payload  # NEW

router = APIRouter()
```
File: `api_server/src/api_server/routes/recipes.py:14-29`

**No `require_user` for `/v1/models`** — per D-19/D-20 the catalog is global, no per-user filter, no auth. Mirror `routes/recipes.py::list_recipes` which is also unauthenticated.

**Handler shape — mirror `routes/recipes.py:32-38`:**
```python
@router.get("/models")
async def list_models(request: Request):
    """OpenRouter passthrough — bytes from cache (D-18/D-19/D-20)."""
    try:
        payload = await get_models_payload(request.app.state)
    except Exception:
        return JSONResponse(
            status_code=503,
            content=make_error_envelope(
                ErrorCode.INFRA_UNAVAILABLE,
                "OpenRouter catalog temporarily unavailable",
            ),
        )
    # Passthrough raw bytes — Response, NOT JSONResponse, to avoid re-serialize.
    return Response(content=payload, media_type="application/json")
```
Pattern source: `routes/recipes.py:32-38` (router shape) + `routes/recipes.py:46-53` (404 envelope shape).

**Wire-up in `main.py`:** mirror `main.py:413` recipes include:
```python
# main.py existing pattern (line 413):
app.include_router(recipes_route.router, prefix="/v1", tags=["recipes"])
# NEW (Phase 23):
app.include_router(models_route.router, prefix="/v1", tags=["models"])
```

---

### `api_server/src/api_server/services/openrouter_models.py` (NEW — service, in-process cache)

**Analog:** **PARTIAL — no exact match exists.** Closest existing pattern: `app.state.bot_http_client` lifespan-owned httpx client at `main.py:137-140`, plus `app.state.recipes` static dict at `main.py:83`. The cache+lock+TTL+stale-while-revalidate combo is novel for this codebase. Planner should design from scratch following the lifespan-owned client pattern.

**Lifespan-owned httpx client pattern to mirror — `main.py:137-140`:**
```python
# Existing (Phase 22c.3-09 / D-40):
app.state.bot_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(600.0, connect=5.0),
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
)
```
File: `api_server/src/api_server/main.py:137-140`

**Lifespan teardown pattern to mirror — `main.py:313-317`:**
```python
# Existing teardown (must be replicated for openrouter_http_client):
try:
    if getattr(app.state, "bot_http_client", None) is not None:
        await app.state.bot_http_client.aclose()
except Exception:
    _log.exception("phase22c3.lifespan.http_client_close_failed")
```
File: `api_server/src/api_server/main.py:313-317`

**Phase 23 extension — add separate client with 10s timeout** (per RESEARCH "Reuse `app.state.bot_http_client`?" rejection rationale):
```python
# In lifespan startup (alongside bot_http_client):
app.state.openrouter_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
app.state.models_cache = {}        # {fetched_at: datetime, payload: bytes}
app.state.models_cache_lock = asyncio.Lock()
```

**Service module shape (NEW — see RESEARCH §Pattern 3 for the full implementation; ~30 LOC):**
```python
# api_server/src/api_server/services/openrouter_models.py (NEW)
import asyncio, logging
from datetime import datetime, timedelta, timezone

_log = logging.getLogger("api_server.openrouter_models")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL = timedelta(minutes=15)


async def get_models_payload(state) -> bytes:
    """Return cached payload bytes; fetch on miss/stale; SWR on failure (D-18)."""
    cache = state.models_cache
    now = datetime.now(timezone.utc)
    if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
        return cache["payload"]
    async with state.models_cache_lock:
        if cache.get("fetched_at") and (now - cache["fetched_at"]) < _CACHE_TTL:
            return cache["payload"]  # raced refresh
        try:
            r = await state.openrouter_http_client.get(_OPENROUTER_URL)
            r.raise_for_status()
            cache["fetched_at"] = now
            cache["payload"] = r.content  # raw bytes (D-20 passthrough)
            return cache["payload"]
        except Exception:
            _log.exception("openrouter_models.fetch_failed")
            if cache.get("payload"):
                return cache["payload"]   # SWR
            raise
```

---

### `api_server/src/api_server/routes/auth.py` (EXTEND — append 2 mobile-credential endpoints)

**Analog:** **self** — existing `google_callback` (lines 147-204) and `github_callback` (lines 227-297) handlers. Same file, append-only.

**Critical: do NOT modify the browser callbacks.** They are already integration-tested by `tests/auth/test_google_callback.py` + `test_github_callback.py`. Phase 23 is purely additive.

**Existing `_err()` helper to reuse — `routes/auth.py:68-80`:**
```python
def _err(
    status: int,
    code: str,
    message: str,
    *,
    param: str | None = None,
    category: str | None = None,
) -> JSONResponse:
    """Stripe-shape error envelope — mirrors ``routes/agent_events.py::_err``."""
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```
File: `api_server/src/api_server/routes/auth.py:68-80`

**Existing upsert_user + mint_session call shape — `routes/auth.py:188-198` (Google) and `:281-291` (GitHub):**
```python
# Google branch — verbatim from routes/auth.py:188-198:
display_name = userinfo.get("name") or userinfo.get("email") or "user"
pool = request.app.state.db
async with pool.acquire() as conn:
    user_id = await upsert_user(
        conn,
        provider="google",
        sub=str(userinfo["sub"]),
        email=userinfo.get("email"),
        display_name=display_name,
        avatar_url=userinfo.get("picture"),
    )
    session_id = await mint_session(conn, user_id=user_id, request=request)
```
File: `api_server/src/api_server/routes/auth.py:188-198` (Google) + `:281-291` (GitHub).

**Mobile endpoint pattern (NEW — append below `github_callback`, before `# Logout` divider at line 300):**
```python
class MobileGoogleAuthRequest(BaseModel):
    id_token: str = Field(..., min_length=1)


class MobileGitHubAuthRequest(BaseModel):
    access_token: str = Field(..., min_length=1)


class MobileSessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
    user: SessionUserResponse  # reuse existing models/users.py shape


@router.post("/auth/google/mobile", status_code=200)
async def google_mobile(request: Request, body: MobileGoogleAuthRequest):
    settings = request.app.state.settings
    try:
        claims = await verify_google_id_token(
            body.id_token, settings.oauth_google_mobile_client_ids,
        )
    except ValueError as e:
        return _err(401, ErrorCode.UNAUTHORIZED, str(e), param="id_token")
    if not claims.get("sub") or not claims.get("email"):
        return _err(401, ErrorCode.UNAUTHORIZED, "missing required claims",
                    param="id_token")
    pool = request.app.state.db
    async with pool.acquire() as conn:
        user_id = await upsert_user(
            conn, provider="google",
            sub=str(claims["sub"]),
            email=claims["email"],
            display_name=claims.get("name") or claims["email"],
            avatar_url=claims.get("picture"),
        )
        session_id = await mint_session(conn, user_id=user_id, request=request)
        sess_row = await conn.fetchrow(
            "SELECT expires_at FROM sessions WHERE id = $1", UUID(session_id),
        )
        user_row = await conn.fetchrow(
            "SELECT id, email, display_name, avatar_url, provider, created_at "
            "FROM users WHERE id = $1", user_id,
        )
    return JSONResponse(status_code=200, content={
        "session_id": session_id,
        "expires_at": sess_row["expires_at"].isoformat(),
        "user": SessionUserResponse(**dict(user_row)).model_dump(mode="json"),
    })
```

**Mobile-cookie discipline (D-17):** the response body returns `session_id`; the response does NOT need to `Set-Cookie` (mobile has no cookie jar). Web browser callbacks call `_set_session_cookie` (line 200/293); mobile endpoints **do NOT** — they return the UUID in the body for the Flutter app to store and re-send as `Cookie: ap_session=<uuid>`.

---

### `api_server/src/api_server/auth/oauth.py` (EXTEND — append `verify_google_id_token` + `verify_github_access_token`)

**Analog:** **self** — append helpers below `mint_session()` at line 238. Existing module already has the import-as-needed style + `_log` + module-level constants pattern (lines 44-56).

**Existing module-level pattern to mirror — `auth/oauth.py:44-56`:**
```python
_log = logging.getLogger("api_server.auth.oauth")
_oauth: OAuth | None = None  # module-level cache (line 48)
_DEV_PLACEHOLDER = "dev-placeholder-not-for-prod"  # line 53
```
File: `api_server/src/api_server/auth/oauth.py:44-56`

**`verify_google_id_token` (NEW — see RESEARCH §Pattern 5; planner picks whether to add 6h JWKS cache or rely on google-auth defaults — RESEARCH recommends skipping the cache for MVP):**
```python
import asyncio
from google.oauth2 import id_token as _google_id_token
from google.auth.transport import requests as _google_ga_requests
from google.auth import exceptions as _google_exceptions

_GOOGLE_REQUEST = _google_ga_requests.Request()


async def verify_google_id_token(
    id_token: str, mobile_client_ids: list[str]
) -> dict:
    """Verify Google-issued ID token; raise ValueError on any failure."""
    if not mobile_client_ids:
        raise ValueError("no mobile client IDs configured")

    def _verify_sync():
        return _google_id_token.verify_oauth2_token(
            id_token, _GOOGLE_REQUEST, audience=mobile_client_ids,
        )

    try:
        return await asyncio.to_thread(_verify_sync)
    except _google_exceptions.GoogleAuthError as e:
        raise ValueError(f"google id_token rejected: {e}") from e
```

**`verify_github_access_token` (NEW — mirrors browser callback flow byte-for-byte; refactor opportunity is to extract this helper and have BOTH `routes/auth.py::github_callback` AND the new mobile endpoint call it).**

The exact existing browser-callback fallback logic to mirror — `routes/auth.py:246-278`:
```python
try:
    user_resp = await oauth.github.get("user", token=token)
    profile = user_resp.json()
except Exception:
    _log.exception("github /user fetch failed")
    return _login_redirect_with_error(settings, "oauth_failed")

sub = profile.get("id")
if sub is None:
    return _login_redirect_with_error(settings, "oauth_failed")

# GitHub returns a null ``email`` when the user set their primary email
# to private. Fall back to ``/user/emails`` and pick the first
# primary+verified entry. If still null, refuse to create the account.
email = profile.get("email")
if not email:
    try:
        emails_resp = await oauth.github.get("user/emails", token=token)
        emails = emails_resp.json()
        email = next(
            (
                e["email"]
                for e in emails
                if e.get("primary") and e.get("verified") and e.get("email")
            ),
            None,
        )
    except Exception:
        _log.exception("github /user/emails fetch failed")
        email = None

if not email:
    return _login_redirect_with_error(settings, "oauth_failed")
```
File: `api_server/src/api_server/routes/auth.py:246-278`. The mobile helper raises `ValueError` instead of returning a 302 redirect; logic is otherwise identical.

---

### `api_server/src/api_server/services/run_store.py::list_agents` (EXTEND — LATERAL JOIN extension for D-10 + D-27)

**Analog:** **self** — existing `list_agents` at lines 78-114 already uses a LATERAL JOIN for `last_verdict`. Phase 23 adds a SECOND LATERAL JOIN for `agent_containers.container_status` (status field, D-10) AND a sub-SELECT for `MAX(im.created_at)` (last_activity, D-27).

**Existing LATERAL JOIN pattern — `services/run_store.py:87-114`:**
```python
rows = await conn.fetch(
    """
    SELECT
        ai.id,
        ai.name,
        ai.recipe_name,
        ai.model,
        ai.personality,
        ai.created_at,
        ai.last_run_at,
        ai.total_runs,
        lr.verdict AS last_verdict,
        lr.category AS last_category,
        lr.run_id AS last_run_id
    FROM agent_instances ai
    LEFT JOIN LATERAL (
        SELECT id AS run_id, verdict, category
        FROM runs
        WHERE agent_instance_id = ai.id
        ORDER BY created_at DESC
        LIMIT 1
    ) lr ON TRUE
    WHERE ai.user_id = $1
    ORDER BY ai.created_at DESC
    """,
    user_id,
)
return [dict(r) for r in rows]
```
File: `api_server/src/api_server/services/run_store.py:87-114`

**Phase 23 extension** — add `ac` LATERAL (D-10/D-11) + `last_activity` GREATEST sub-select (D-27). Full target shape lives in `23-RESEARCH.md` lines 405-455. Container resolution policy is exactly D-11: `WHERE agent_instance_id=ai.id AND stopped_at IS NULL ORDER BY created_at DESC LIMIT 1`.

**Index assumption (verify before sealing per RESEARCH A3):** migration 007 creates `ix_inapp_messages_agent_status` on `(agent_id, status)` — for the `MAX(im.created_at) WHERE im.agent_id=ai.id` aggregate, planner should verify the index supports it OR document that the aggregate is a sequential per-agent scan (cheap at MVP volumes).

---

### `api_server/src/api_server/models/agents.py::AgentSummary` (EXTEND — add `status` + `last_activity` fields)

**Analog:** **self** — existing `AgentSummary` at lines 32-43.

**Existing field-declaration pattern — `models/agents.py:32-43`:**
```python
class AgentSummary(BaseModel):
    id: UUID
    name: str
    recipe_name: str
    model: str
    personality: str | None = None
    created_at: datetime
    last_run_at: datetime | None = None
    total_runs: int
    last_verdict: str | None = None
    last_category: str | None = None
    last_run_id: str | None = None
```
File: `api_server/src/api_server/models/agents.py:32-43`

**Phase 23 additions** (mirror existing optional-field shape — both new fields are nullable per D-27 NULL-on-cold-account semantics):
```python
status: str | None = None       # D-10 — from agent_containers.container_status
last_activity: datetime | None = None  # D-27 — GREATEST(last_run_at, MAX(im.created_at))
```

**Type for `status`:** Claude's Discretion per CONTEXT.md — `str | None` is safest (matches the existing `container_status` column shape used by `AgentStartResponse.container_status: str` at `models/agents.py:102`). Planner MAY tighten to `Literal["running","stopped","starting",...]` if `agent_containers.container_status` enum is canonical, but `str | None` is the conservative pick.

---

### `api_server/src/api_server/routes/agent_messages.py::post_message` (EXTEND — Idempotency-Key REQUIRED check at top)

**Analog:** **self** — existing handler at lines 119-180.

**Critical ordering rule (D-09 + RESEARCH Pitfall 8):** the new check goes **BEFORE** `require_user`. Missing-header is a request-shape failure (400), independent of auth state. Reordering risks the cross-user idempotency leak documented in RESEARCH Pitfall 8.

**Existing handler signature + step-1 (require_user) pattern — `routes/agent_messages.py:119-146`:**
```python
@router.post("/agents/{agent_id}/messages", status_code=202)
async def post_message(
    request: Request,
    agent_id: UUID,
    body: PostMessageRequest,
):
    """..."""
    # --- Step 1: require_user (D-18) ---
    sess = require_user(request)
    if isinstance(sess, JSONResponse):
        return sess
    user_id: UUID = sess
    # --- Step 2: ownership (D-19) --- ...
```
File: `api_server/src/api_server/routes/agent_messages.py:119-146`

**Existing `_err()` helper to reuse — `routes/agent_messages.py:78-97`:**
```python
def _err(
    status: int, code: str, message: str,
    *, param: str | None = None, category: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```
File: `api_server/src/api_server/routes/agent_messages.py:78-97`

**Phase 23 D-09 patch (~3 LOC, inserted between line 124 and line 142):**
```python
# `Header` is ALREADY IMPORTED at line 34 ("from fastapi import APIRouter, Header, Request").
# Add the parameter to post_message's signature:
async def post_message(
    request: Request,
    agent_id: UUID,
    body: PostMessageRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),  # NEW
):
    # --- D-09: REQUIRED-presence enforcement (PRE-AUTH per Pitfall 8) ---
    if not idempotency_key or not idempotency_key.strip():
        return _err(
            400, ErrorCode.INVALID_REQUEST,
            "Idempotency-Key header is required",
            param="Idempotency-Key",
        )
    # --- existing Step 1: require_user (D-18) ---
    sess = require_user(request)
    ...
```

**`Header` is already imported** at `routes/agent_messages.py:34` — verified live: `from fastapi import APIRouter, Header, Request`. Zero new imports.

---

### `api_server/src/api_server/main.py` (EXTEND — add GZipMiddleware + lifespan additions)

**Analog:** **self** — existing `add_middleware` block at lines 392-408 + lifespan init at lines 117-141.

**Existing middleware-wiring pattern — `main.py:384-408`:**
```python
# Middleware order: outermost declared last.
# Effective request-in order:
#   CorrelationId -> AccessLog -> StarletteSession -> OurSession
#     -> RateLimit -> Idempotency -> route.
app.add_middleware(IdempotencyMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ApSessionMiddleware)  # ap_session cookie -> request.state.user_id
app.add_middleware(StarletteSessionMiddleware, ...)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(CorrelationIdMiddleware)
```
File: `api_server/src/api_server/main.py:384-408`

**Phase 23 GZipMiddleware placement — RESEARCH Pitfall 1 says place AT THE BOTTOM** (outermost declared last → outermost on response → compresses final response). New import + `add_middleware` call:
```python
from starlette.middleware.gzip import GZipMiddleware  # NEW import at top

# At the BOTTOM of the add_middleware block (AFTER CorrelationIdMiddleware,
# making GZip the OUTERMOST middleware on the response path):
app.add_middleware(GZipMiddleware, minimum_size=1024)
```
**SSE compatibility — verified at source level** (Starlette ≥0.46.0 has `DEFAULT_EXCLUDED_CONTENT_TYPES = ("text/event-stream",)`); D-31 Wave 0 spike validates regression. No additional config needed for SSE exclusion.

**Lifespan additions — mirror `bot_http_client` pattern from `main.py:137-140`:**
```python
# In lifespan startup, alongside bot_http_client (line 137-140):
app.state.openrouter_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=5.0),
    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
)
app.state.models_cache = {}
app.state.models_cache_lock = asyncio.Lock()
```
**Lifespan teardown — mirror `main.py:313-317`** (close openrouter_http_client BEFORE close_pool, after inapp tasks drain).

---

### `api_server/src/api_server/config.py` (EXTEND — add `oauth_google_mobile_client_ids: list[str]`)

**Analog:** **self** — existing `oauth_*` Field declarations at lines 80-106.

**Existing pattern — `config.py:80-99`:**
```python
oauth_google_client_id: str | None = Field(
    None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_ID"
)
oauth_google_client_secret: str | None = Field(
    None, validation_alias="AP_OAUTH_GOOGLE_CLIENT_SECRET"
)
oauth_google_redirect_uri: str | None = Field(
    None, validation_alias="AP_OAUTH_GOOGLE_REDIRECT_URI"
)
```
File: `api_server/src/api_server/config.py:80-99`

**`list[str]` field — NO existing `list[str]` pattern in config.py.** Pydantic v2 + `pydantic-settings` parses comma-separated env vars into `list[str]` natively when the field type is `list[str]`. Recommended pattern for D-23:
```python
# Phase 23 (D-23): comma-separated mobile client IDs.
# Pydantic-settings parses comma-separated strings into list[str] via JSON-or-CSV
# detection. Keep a sane default ([]) so dev boots without the env var; prod
# fail-loud check belongs in auth/oauth.py::_resolve_or_fail (extended).
oauth_google_mobile_client_ids: list[str] = Field(
    default_factory=list,
    validation_alias="AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS",
)
```
**Caveat:** if pydantic-settings v2 needs an explicit parser hint for CSV (no JSON brackets), planner adds a `field_validator`:
```python
from pydantic import field_validator

@field_validator("oauth_google_mobile_client_ids", mode="before")
@classmethod
def _split_csv(cls, v):
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return v
```
**Verification step (planner runs during execute):** instantiate `Settings()` with `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS=a.com,b.com` and assert the value parses to `["a.com", "b.com"]`. If it parses as `["a.com,b.com"]` (single string), add the validator.

---

### `frontend/components/playground-form.tsx:169` (EXTEND — replace direct OpenRouter fetch with `apiGet("/api/v1/models")`)

**Analog:** **self** — same file, line 154 already uses `apiGet<{recipes: RecipeSummary[]}>("/api/v1/recipes")`. Mirror that EXACT pattern for the OpenRouter migration.

**Existing pattern (15 lines above the migration site) — `frontend/components/playground-form.tsx:150-163`:**
```typescript
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const data = await apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes");
      if (cancelled) return;
      const sorted = [...data.recipes].sort((a, b) => a.name.localeCompare(b.name));
      setRecipes(sorted);
    } catch (e) {
      if (!cancelled) setUiError(parseApiError(e));
    }
  })();
  return () => { cancelled = true; };
}, []);
```
File: `frontend/components/playground-form.tsx:150-163`

**Current site to migrate — `frontend/components/playground-form.tsx:165-179`:**
```typescript
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const r = await fetch("https://openrouter.ai/api/v1/models");  // LINE 169 — DIRECT FETCH
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = (await r.json()) as { data: OpenRouterModel[] };
      if (cancelled) return;
      setOrModels(d.data ?? []);
    } catch (e) {
      if (!cancelled) setOrError(e instanceof Error ? e.message : "load failed");
    }
  })();
  return () => { cancelled = true; };
}, []);
```
File: `frontend/components/playground-form.tsx:165-179`

**Phase 23 D-21 migration (~5 LOC change):**
```typescript
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const d = await apiGet<{ data: OpenRouterModel[] }>("/api/v1/models");
      if (cancelled) return;
      setOrModels(d.data ?? []);
    } catch (e) {
      if (!cancelled) setOrError(e instanceof Error ? e.message : "load failed");
    }
  })();
  return () => { cancelled = true; };
}, []);
```
`apiGet` already imported at line 23 (`import { apiGet, apiPost } from "@/lib/api";`). Zero new imports. The `next.config.ts` rewrites already proxy `/api/*` → Go API per the comment in `frontend/lib/api.ts:3`.

---

### `deploy/.env.dev.example` (NEW — add `AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS` placeholder)

**Analog:** `deploy/.env.prod.example` (existing OAuth env stanzas at lines 27-38).

**Existing OAuth env stanza pattern — `deploy/.env.prod.example:27-38`:**
```bash
# Phase 22c: Google OAuth. Register at https://console.cloud.google.com/apis/credentials
# Callback must match exactly (http://localhost:8000 for dev, https://... for prod).
AP_OAUTH_GOOGLE_CLIENT_ID=
AP_OAUTH_GOOGLE_CLIENT_SECRET=
AP_OAUTH_GOOGLE_REDIRECT_URI=http://localhost:8000/v1/auth/google/callback

# Phase 22c: GitHub OAuth. Register at https://github.com/settings/developers (OAuth Apps → New).
# Scopes requested at authorize time: read:user user:email (needed for email when private).
AP_OAUTH_GITHUB_CLIENT_ID=
AP_OAUTH_GITHUB_CLIENT_SECRET=
AP_OAUTH_GITHUB_REDIRECT_URI=http://localhost:8000/v1/auth/github/callback
```
File: `deploy/.env.prod.example:27-38`

**Phase 23 addition (mirror the comment-block + empty-value pattern):**
```bash
# Phase 23 (D-23): Mobile native-SDK Google sign-in client IDs.
# Google Cloud Console issues SEPARATE client IDs per platform (Android, iOS) —
# both are different from AP_OAUTH_GOOGLE_CLIENT_ID (the web client).
# Comma-separated list; the mobile JWT verifier accepts tokens whose ``aud``
# claim matches any entry. NOT a credential — these IDs ship in the mobile
# app binary and are not secret.
AP_OAUTH_GOOGLE_MOBILE_CLIENT_IDS=
```

**Decision flag for planner:** CONTEXT.md `<code_context>` lists `deploy/.env.dev.example` as NEW, but only `deploy/.env.prod.example` exists today. The planner should decide between (a) creating a new `deploy/.env.dev.example` with the mobile var + the existing dev-OAuth surface, OR (b) appending to `deploy/.env.prod.example`. Pick by consistency with how dev currently configures OAuth (likely the latter since `_DEV_PLACEHOLDER` covers the dev fallback already).

---

### Test Patterns

#### `api_server/tests/auth/test_oauth_mobile.py` (NEW — covers D-30 9-cell matrix)

**Analog:** `tests/auth/test_google_callback.py` (lines 1-120) and `test_github_callback.py` (lines 1-60).

**Imports + module shape to mirror — `tests/auth/test_google_callback.py:1-32`:**
```python
from __future__ import annotations

import pytest
from authlib.integrations.starlette_client import OAuthError

from api_server.auth.oauth import get_oauth
from api_server.config import Settings
```
File: `api_server/tests/auth/test_google_callback.py:1-32`

**Test marker pattern — `tests/auth/test_google_callback.py:33-34`:**
```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_<scenario>(async_client, monkeypatch, db_pool):
    ...
```
This decorates EVERY integration test in `tests/auth/`. Mobile tests follow the same shape.

**Fixture composition — `tests/auth/test_google_callback.py:99` (existing happy-path test):**
```python
async def test_happy_path_upserts_user_mints_session_sets_cookie(
    async_client, monkeypatch, db_pool,
):
```
Mobile equivalents request `async_client + db_pool + respx_oauth_providers + cryptography-signed test JWT helper`. Per CONTEXT.md Claude's Discretion, the planner picks whether to add an `authenticated_mobile_session` fixture mirroring `authenticated_cookie` (RESEARCH recommends yes, mirroring `tests/conftest.py:510-553` shape).

**Test JWT generation pattern (RESEARCH §Pitfall 3) — see `23-RESEARCH.md:802-848` for the full `_make_test_jwt_and_jwks()` helper using `cryptography` + `pyjwt`. Both libs are already in deps.**

**respx fixture extension pattern — existing fixture at `tests/conftest.py:590-655`:**
```python
@pytest.fixture
def respx_oauth_providers():
    @contextmanager
    def _ctx():
        with respx.mock(assert_all_called=False) as m:
            m.get("https://accounts.google.com/.well-known/openid-configuration") \
                .mock(return_value=httpx.Response(200, json=_GOOGLE_DISCOVERY))
            m.get("https://www.googleapis.com/oauth2/v3/certs") \
                .mock(return_value=httpx.Response(200, json={"keys": []}))
            stubs = {
                "google_token": m.post("https://oauth2.googleapis.com/token"),
                "google_userinfo": m.get("https://openidconnect.googleapis.com/v1/userinfo"),
                "github_token": m.post("https://github.com/login/oauth/access_token"),
                "github_user": m.get("https://api.github.com/user"),
                "github_user_emails": m.get("https://api.github.com/user/emails"),
            }
            yield stubs
    return _ctx
```
File: `api_server/tests/conftest.py:590-655`

**Phase 23 extension pattern:** the mobile tests USE `respx_oauth_providers` AS-IS, then OVERRIDE the JWKS stub per-test with the real test public key. The fixture's `assert_all_called=False` + `_ctx()` shape supports this directly — call `respx.get("https://www.googleapis.com/oauth2/v3/certs").mock(return_value=httpx.Response(200, json=test_jwks))` inside the `with respx_oauth_providers() as stubs:` block.

#### `api_server/tests/routes/test_messages_idempotency_required.py` (NEW)

**Analog:** `tests/test_idempotency.py:29-71` (existing replay-cache test) + `tests/routes/test_agent_messages_post.py:33-80` (`_seed_agent_for_user` helper + auth flow).

**Auth + body pattern — `tests/routes/test_agent_messages_post.py:65-80`:**
```python
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_post_message_returns_202_with_message_id(
    async_client, db_pool, authenticated_cookie,
):
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},
        json={"content": "hi"},
    )
    assert r.status_code == 202, r.text
```
File: `api_server/tests/routes/test_agent_messages_post.py:65-80`

**Phase 23 D-09 test — same shape, but assert 400 + envelope when Idempotency-Key absent:**
```python
async def test_post_message_returns_400_when_idempotency_key_missing(
    async_client, db_pool, authenticated_cookie,
):
    agent_id = await _seed_agent_for_user(
        db_pool, authenticated_cookie["_user_id"],
    )
    r = await async_client.post(
        f"/v1/agents/{agent_id}/messages",
        headers={"Cookie": authenticated_cookie["Cookie"]},  # NO Idempotency-Key
        json={"content": "hi"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["param"] == "Idempotency-Key"
```

The `_seed_agent_for_user` helper to copy/import lives at `tests/routes/test_agent_messages_post.py:34-63`.

#### `api_server/tests/routes/test_agents_status_field.py` (NEW)

**Analog:** `tests/routes/test_agent_messages_post.py::_seed_agent_for_user` (already inserts both `agent_instances` AND `agent_containers` rows).

**Existing pattern — `tests/routes/test_agent_messages_post.py:45-62`:**
```python
async with pool.acquire() as conn:
    await conn.execute(
        """
        INSERT INTO agent_instances (id, user_id, recipe_name, model, name)
        VALUES ($1, $2, $3, 'm-test', $4)
        """,
        agent_id, UUID(user_id), recipe_name, name,
    )
    await conn.execute(
        """
        INSERT INTO agent_containers
            (id, agent_instance_id, user_id, recipe_name,
             deploy_mode, container_status, container_id, ready_at)
        VALUES ($1, $2, $3, $4, 'persistent', 'running', $5, NOW())
        """,
        container_row_id, agent_id, UUID(user_id), recipe_name,
        docker_container_id,
    )
```
File: `api_server/tests/routes/test_agent_messages_post.py:45-62`

**Phase 23 status_field test** — seed the rows above (note `container_status='running'` → `status` field returned), then GET `/v1/agents` and assert the new fields:
```python
r = await async_client.get("/v1/agents",
    headers={"Cookie": authenticated_cookie["Cookie"]})
assert r.status_code == 200
agents = r.json()["agents"]
assert agents[0]["status"] == "running"
assert agents[0]["last_activity"] is None  # no runs/messages yet
```

**Cold-account semantics test** (RESEARCH Pitfall 4) — seed agent_instances BUT skip agent_containers, assert `status is None` and `last_activity is None`. Then INSERT an inapp_messages row, refetch, assert `last_activity == im.created_at`.

#### `api_server/tests/spikes/test_gzip_sse_compat.py` (NEW Wave 0 spike — D-31 BLOCKING)

**Analog:** `tests/spikes/test_respx_authlib.py` (existing spike file shape).

**Spike module shape to mirror — `tests/spikes/test_respx_authlib.py:1-22`:**
```python
"""SPIKE A (Wave 0 gate) — respx x authlib 1.6.11 interop.

Proves that ... BEFORE any downstream test authors a real OAuth
integration test against respx stubs.

PASS criterion: ...
FAIL -> phase goes back to discuss-phase; ...
"""
from __future__ import annotations
import httpx, pytest, respx

@pytest.mark.asyncio
@respx.mock
async def test_<spike_question>():
    ...
```
File: `api_server/tests/spikes/test_respx_authlib.py:1-22`

**D-31 spike specifics:** boot a FastAPI app with `GZipMiddleware(minimum_size=1024)` configured, fire a SSE request to `/v1/agents/:id/messages/stream`, immediately POST a message via `/v1/agents/:id/messages`, capture the SSE chunk delivery TIMESTAMPS, assert the `inapp_inbound` event chunk arrives BEFORE the response stream closes (not just at end-of-stream).

**Test harness reuse:** the `started_api_server` fixture (`tests/conftest.py:247-305`) already boots a real FastAPI app + Postgres + Redis + Docker network — use this as the harness, monkeypatch the env to ENABLE GZipMiddleware (or mod the spike to construct the app inline with GZip added), then drive SSE via `httpx.AsyncClient`'s streaming-response path.

**TRUNCATE CASCADE list — UNCHANGED for Phase 23.** Per CONTEXT.md `<code_context>`, the 8-table list is identical: `agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users`. File: `tests/conftest.py:175-180`. Phase 23 adds NO new tables (D-01 reuse mandate), so this list does not change.

---

## Shared Patterns

### Authentication (inline `require_user` early-return)

**Source:** `api_server/src/api_server/auth/deps.py:37-72`
**Apply to:** ALL Phase 23 controllers EXCEPT `/v1/models` (public) AND `/v1/auth/{google,github}/mobile` (the credential-exchange routes themselves don't have a session yet — that's what they're creating).

**The exact 3-line shape downstream handlers ALL use** (verified across `routes/users.py:42-45`, `routes/agents.py:27-30`, `routes/auth.py::logout:327-329`, `routes/agent_messages.py:143-146`, `routes/agent_lifecycle.py:*`):
```python
result = require_user(request)
if isinstance(result, JSONResponse):
    return result
user_id: UUID = result   # name varies: "user_id", "sess", or unpacked inline
```

**Phase 23 handlers MUST use this exact shape — NOT FastAPI Depends.** Rationale at `auth/deps.py:1-26`.

### Error envelope (Stripe-shape)

**Source:** `api_server/src/api_server/models/errors.py:124-147` (`make_error_envelope`) + `models/errors.py:31-58` (`ErrorCode` constants).
**Apply to:** All 4xx/5xx responses across Phase 23.

**The exact `_err()` helper shape EVERY Phase 23 route reuses** (already exists in `routes/agent_messages.py:78-97`, `routes/auth.py:68-80`, `routes/agent_events.py::_err`, `routes/agent_lifecycle.py::_err`, etc — copied per-file by convention, NOT shared):
```python
def _err(
    status: int, code: str, message: str,
    *, param: str | None = None, category: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=make_error_envelope(code, message, param=param, category=category),
    )
```

**Error codes used in Phase 23** (all already in `ErrorCode` — no new codes needed):
- `ErrorCode.UNAUTHORIZED` — 401 (mobile token rejected, missing claims)
- `ErrorCode.INVALID_REQUEST` — 400 (missing Idempotency-Key, malformed body)
- `ErrorCode.AGENT_NOT_FOUND` — 404 (existing — Phase 23 doesn't need a new one)
- `ErrorCode.INFRA_UNAVAILABLE` — 503 (`/v1/models` cold + OpenRouter down)

### Lifespan-owned httpx.AsyncClient

**Source:** `api_server/src/api_server/main.py:137-140` (startup) + `:313-317` (teardown).
**Apply to:** the new `app.state.openrouter_http_client` (Phase 23 mirrors this exactly with 10s timeout instead of 600s).

### Module-level `_log` logger

**Source:** every service + route + middleware uses `_log = logging.getLogger("api_server.<module>")` at module top.
**Apply to:** the new `services/openrouter_models.py` (`_log = logging.getLogger("api_server.openrouter_models")` per RESEARCH §Pattern 3). Mirror `routes/agent_messages.py:46`, `auth/oauth.py:44`, `main.py:57`.

### Test marker for integration tests

**Source:** every test in `tests/auth/`, `tests/routes/`, `tests/test_idempotency.py` etc decorates with:
```python
pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]
# OR per-test:
@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_xxx(...): ...
```
**Apply to:** every new test file in Phase 23 EXCEPT `tests/spikes/test_gzip_sse_compat.py` (spikes can run with `@pytest.mark.asyncio` only — see `tests/spikes/test_respx_authlib.py:23`).

### Migration discipline (informational only — Phase 23 ADDS NO MIGRATION)

Migration files live at `api_server/alembic/versions/` (existing series 001-008). **Phase 23 ADDS NO MIGRATION per D-01 / D-32 amendment** — the `inapp_messages` table from migration 007 is the single chat-history source. The TRUNCATE CASCADE 8-table list at `tests/conftest.py:175-180` is unchanged.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `api_server/src/api_server/services/openrouter_models.py` | service | request-response (cache + httpx + asyncio.Lock + stale-while-revalidate) | First lifespan-owned in-process cache service in this codebase. The closest references are `app.state.bot_http_client` (lifespan-owned httpx) at `main.py:137-140` AND `app.state.recipes` (static dict loaded once at boot) at `main.py:83`. NEITHER has a TTL+lock+SWR pattern. Planner must design from scratch — RESEARCH §Pattern 3 has the canonical implementation (~30 LOC). |

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/{routes,services,auth,middleware,models,config.py,main.py}` — full read
- `api_server/tests/{auth,routes,spikes,conftest.py,test_idempotency.py}` — full read of relevant files
- `api_server/alembic/versions/007_inapp_messages.py` — schema confirmed for D-01 reuse
- `frontend/{components/playground-form.tsx,lib/api.ts,lib/api-types.ts}` — direct read of D-21 migration site
- `deploy/.env.prod.example` — analog for new dev env stanza

**Files scanned (live-source reads):**
- `api_server/src/api_server/auth/deps.py` (full)
- `api_server/src/api_server/auth/oauth.py` (full)
- `api_server/src/api_server/routes/auth.py` (full)
- `api_server/src/api_server/routes/users.py` (full)
- `api_server/src/api_server/routes/recipes.py` (full)
- `api_server/src/api_server/routes/agents.py` (full)
- `api_server/src/api_server/routes/agent_messages.py:1-200`
- `api_server/src/api_server/services/run_store.py:1-200, 440-480`
- `api_server/src/api_server/middleware/idempotency.py:1-120`
- `api_server/src/api_server/middleware/session.py` (full)
- `api_server/src/api_server/models/agents.py` (full)
- `api_server/src/api_server/models/users.py` (full)
- `api_server/src/api_server/models/errors.py` (full)
- `api_server/src/api_server/main.py` (full)
- `api_server/src/api_server/config.py` (full)
- `api_server/tests/conftest.py:130-200, 500-655`
- `api_server/tests/auth/test_google_callback.py:1-120`
- `api_server/tests/auth/test_github_callback.py:1-60`
- `api_server/tests/routes/test_users_me.py` (full)
- `api_server/tests/routes/test_agent_messages_post.py:1-80`
- `api_server/tests/spikes/test_respx_authlib.py` (full)
- `api_server/tests/test_idempotency.py:1-90`
- `api_server/alembic/versions/007_inapp_messages.py:1-60`
- `frontend/components/playground-form.tsx:1-50, 140-180`
- `frontend/lib/api.ts:1-90`
- `deploy/.env.prod.example` (full)

**Pattern extraction date:** 2026-05-01
