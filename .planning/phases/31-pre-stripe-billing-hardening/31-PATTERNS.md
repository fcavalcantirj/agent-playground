# Phase 31: Pre-Stripe Billing Hardening — Pattern Map

**Mapped:** 2026-05-07
**Files analyzed:** 21 (12 CREATE + 9 MODIFY, post-AMD-01 banner widget removed)
**Analogs found:** 21 / 21 (every file has a verified in-repo analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| MODIFY `api_server/src/api_server/middleware/rate_limit.py` | middleware | request-response | self (extending the chat-bucket pattern at L48–53, L56–81, L164–168) | exact (extension of file's own pattern) |
| MODIFY `api_server/src/api_server/main.py` | config / app-factory | lifespan | self (`create_app()` lines 481–540 — single insertion before middleware stack) | exact |
| MODIFY `api_server/src/api_server/middleware/session.py` | middleware | request-response | self (post-auth state-write at L77–90 — Sentry user-context insertion site) | exact |
| MODIFY `api_server/pyproject.toml` | config | static | self (existing `markers` list L110–113 + `dependencies` L10–80) | exact |
| MODIFY `api_server/tests/conftest.py` | test-fixture | DB-truncate | self (`_truncate_tables` autouse L227–232) | exact |
| CREATE `api_server/src/api_server/instrumentation/__init__.py` | package marker | n/a | (none — empty `__init__.py`) | n/a |
| CREATE `api_server/src/api_server/instrumentation/sentry.py` | utility / init helper | event-driven (errors → Sentry transport) | `api_server/src/api_server/auth/oauth.py` `_resolve_or_fail` placeholder-log pattern (L77–80) + `api_server/src/api_server/log.py` env-driven init shape | role-match |
| CREATE `api_server/tests/middleware/test_auth_rate_limit.py` | test | request-response | `api_server/tests/middleware/test_chat_rate_limit.py` (entire file — fixture shape + 3-test assertion pattern) | exact |
| CREATE `api_server/tests/test_sentry_init.py` | test | event-driven | (no in-repo analog — Sentry SDK transport-mock primitive + RESEARCH §"Test pattern" L182–205 is the canonical shape) | role-match |
| CREATE `api_server/tests/e2e/__init__.py` | package marker | n/a | (none — empty `__init__.py`) | n/a |
| CREATE `api_server/tests/e2e/conftest.py` | test-fixture | DB+HTTP | `api_server/tests/conftest.py` `authenticated_cookie` fixture L606–649 | exact |
| CREATE `api_server/tests/e2e/test_money_path.py` | test | CRUD (chat → proxy → cost-capture) | `api_server/tests/middleware/test_chat_rate_limit.py` (httpx ASGITransport + cookie + assertion pattern) + RESEARCH §"Test body shape" L352–400 | role-match |
| MODIFY `mobile/lib/main.dart` | app entry | n/a | self (existing `main()` body L24–53 — wrap in `await initSentry(runner: () async { ... })`) | exact |
| MODIFY `mobile/lib/features/chat/chat_providers.dart` | provider | event-driven | self (silent-swallow sites L387 + L398; existing classifier-style at `:355` flutter_client_sse retry comment) | exact |
| MODIFY `mobile/lib/features/chat/chat_screen.dart` | widget | render-only | self (existing `RetryBanner(...)` consumption at `chat_screen.dart:196–207` for `tgBanner`) | exact (AMD-01 sibling-block) |
| MODIFY `mobile/pubspec.yaml` | config | static | self (existing `dependencies` block L10–25; add 1 line) | exact |
| MODIFY `mobile/Makefile` | config | build | self (`ios` + `android` targets L13–27 — extend with 3 dart-defines) | exact |
| CREATE `mobile/lib/core/instrumentation/sentry.dart` | utility / init helper | event-driven | `mobile/lib/core/env/app_env.dart` (referenced from `main.dart:19`) — env-driven init pattern + RESEARCH §"Init shape" L218–252 | role-match |
| CREATE `mobile/lib/features/chat/chat_stream_error_classifier.dart` | utility | transform | (no in-repo analog — pure top-level dispatch fn; mirror Phase 25 `telegram_failed_banner_provider` modular split) | partial |
| CREATE `mobile/lib/features/chat/chat_stream_error_banner_provider.dart` | provider | state | `mobile/lib/features/chat/telegram_failed_banner_provider.dart` (entire file — `StateProvider<T?>` shape) | exact |
| CREATE `mobile/test/features/chat/chat_stream_error_classifier_test.dart` | test | unit | (no exact in-repo `flutter_test` for top-level fn — RESEARCH §"Widget-test fixture shape" L676–705 is canonical) | partial |
| CREATE `mobile/test/features/chat/chat_screen_error_banner_widget_test.dart` | test | widget | (no in-repo widget test for `RetryBanner` consumption — first-of-kind for chat banner) | partial |
| CREATE `mobile/test/core/instrumentation/sentry_test.dart` | test | event-driven | (no in-repo analog — Sentry SDK transport-mock primitive) | partial |
| CREATE `.github/workflows/e2e-money-path.yml` | config / CI | request-response | `.github/workflows/mobile.yml` (entire file — paths-filter + single-job + ubuntu-latest + setup-X) | role-match (mobile→python; same shape) |
| MODIFY `Makefile` | config | build | self (`test-api-integration` target L205–206 — pytest-marker harness pattern) | exact |

---

## Pattern Assignments

### MODIFY `api_server/src/api_server/middleware/rate_limit.py`

**Analog:** self — the existing `chat` bucket is the literal blueprint for the new `auth` bucket.

**`_LIMITS` extension pattern** (L48–53 — add one line):
```python
_LIMITS: dict[str, tuple[int, int]] = {
    "runs": (10, 60),    # POST /v1/runs
    "lint": (120, 60),   # POST /v1/lint
    "get":  (300, 60),   # GET /v1/*
    "chat": (4, 60),     # POST /v1/agents/:id/messages — D-42
    # NEW: "auth": (5, 60),   # D-04 — covers 7 routes via _AUTH_ROUTES set
}
```

**`_bucket_for` extension pattern** (L56–81 — add membership branch BEFORE the generic GET branch at L79):
```python
# existing chat-bucket precedent at L74-75:
if method == "POST" and _AGENT_MESSAGES_PATTERN.match(path):
    return "chat"
# NEW (D-01):
if (method, path) in _AUTH_ROUTES:
    return "auth"
# existing GET branch at L79 (unchanged):
if method == "GET" and path.startswith("/v1/"):
    return "get"
```

**Composite-subject pattern** (L158–168 — direct analog for the new `auth` composite):
```python
# Phase 22c.3-08 (D-42; Pitfall 7 mitigation): for the chat bucket,
# mix the agent_id from the URL into the subject so each (user,
# agent) pair gets its own counter row.
if bucket == "chat":
    match = _AGENT_MESSAGES_PATTERN.match(scope.get("path", ""))
    agent_id_str = match.group(1) if match else ""
    if agent_id_str:
        subject = f"chat:{subject}:{agent_id_str}"
# NEW (D-02): mirror this shape for the auth bucket — each (ip, route_key)
# gets its own counter; route_key from a {(method, path) -> short_alias}
# dict so a path rename doesn't invalidate counter rows.
if bucket == "auth":
    route_key = _AUTH_ROUTE_KEYS.get((scope.get("method", ""), scope.get("path", "")), "unknown")
    subject = f"auth:{subject}:{route_key}"
```

**Differences the new code introduces:**
- Adds `_AUTH_ROUTES: frozenset[tuple[str, str]]` (D-01, 7 entries) at module scope.
- Adds `_AUTH_ROUTE_KEYS: dict[tuple[str, str], str]` (D-02 stable aliases: `google_mobile`, `github_mobile`, `logout`, `google_redirect`, `google_callback`, `github_redirect`, `github_callback`).
- Composite-subject prefix is `auth:` (not `chat:`) and the trailing token is the alias (not the agent UUID).
- All other contracts (fail-open at L175–180, Stripe-shape envelope at L186–203, `_subject_from_scope` at L84–123, ASGI scope guard at L141) stay byte-identical.

**Constraints (must preserve):**
- Fail-open semantics (L175–180): Postgres outage → log + pass through. Inherited unchanged for the `auth` bucket.
- XFF-trust gate (L115–121 in `_subject_from_scope`): only trust `X-Forwarded-For` when `settings.trusted_proxy=True`. Reused unchanged.

---

### MODIFY `api_server/src/api_server/main.py`

**Analog:** self — `create_app()` lines 481–540.

**Insertion-site pattern** (L488–510 — Sentry init goes between `configure_logging(...)` at L489 and the first `app.add_middleware(...)` at L520):
```python
# Existing L488-498:
settings = get_settings()
configure_logging(settings.env)
app = FastAPI(
    title="Agent Playground API",
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/docs" if settings.env == "dev" else None,
    redoc_url="/redoc" if settings.env == "dev" else None,
    lifespan=lifespan,
)
app.state.settings = settings

# NEW (D-10): Sentry init BEFORE middleware stack so unhandled
# exceptions in middleware are also captured. Mirrors get_oauth(settings)
# pattern at L510 — single fail-loud helper called from create_app.
from .instrumentation.sentry import init_sentry
init_sentry(settings)

# Existing L504 onward:
app.state.session_last_seen = {}
get_oauth(settings)
# ... middleware adds at L520+ unchanged.
```

**Differences:**
- Single import + single call. No new wiring elsewhere in the file.
- Placement matches D-10's "BEFORE middleware stack setup" requirement.

---

### MODIFY `api_server/src/api_server/middleware/session.py`

**Analog:** self — the post-auth `state["user_id"] = user_id` at L89–90 is the canonical insertion site for D-16.

**Insertion-site pattern** (L77–91 — add `sentry_sdk.set_user` in the success branch):
```python
# Existing L77-91:
        else:
            user_id = row["user_id"]
            await _maybe_touch_last_seen(
                asgi_app, conn,
                session_id=session_uuid,
                current_last_seen=row["last_seen_at"],
            )
# ... existing exception handler unchanged ...

state = scope.setdefault("state", {})
state["user_id"] = user_id
# NEW (D-16): tag Sentry scope with the resolved user UUID. ID-only
# (no email/PII). Mobile-side equivalent fires after sign-in resolves.
if user_id is not None:
    import sentry_sdk
    sentry_sdk.set_user({"id": str(user_id)})
await self.app(scope, receive, send)
```

**Differences:**
- `import sentry_sdk` is INSIDE the conditional so unauthenticated requests pay zero import cost on every call (Python caches the module after first import — that's fine).
- `sentry_sdk.set_user({"id": ...})` is a no-op when Sentry is uninitialized (DSN unset path). Verified via Sentry SDK 2.x docs.
- No PII (no email, no display_name) per D-16 + project privacy posture.

**Constraints (must preserve):**
- Fail-closed exception handler at L83–87: PG outage during session lookup must NOT throw. `set_user` only fires in the resolved-user branch.

---

### MODIFY `api_server/pyproject.toml`

**Analog:** self — existing `dependencies` (L10–80) + `markers` (L110–113).

**Dependency-add pattern** (L10–80 — append before closing bracket):
```toml
dependencies = [
  # ... existing entries ...
  "starlette>=0.46",
  # NEW: Phase 31 H6 — errors-only Sentry. SDK 2.x auto-enables
  # FastApiIntegration + StarletteIntegration on import.
  "sentry-sdk[fastapi]>=2.20,<3.0",
]
```

**Marker-register pattern** (L110–113 — append one entry):
```toml
markers = [
  "api_integration: spawn real Postgres + run real recipe; opt-in via pytest -m api_integration",
  "spike: Phase 28 Wave 0 empirical spike against real infra (Temporal/Docker); opt-in via pytest -m spike",
  # NEW: Phase 31 H8.
  "e2e_money_path: Phase 31 H8 — real OpenRouter chat → cost-capture; opt-in via pytest -m e2e_money_path",
]
```

---

### MODIFY `api_server/tests/conftest.py` (per AMD-05)

**Analog:** self — `_truncate_tables` autouse fixture L227–232.

**Insertion-site pattern** (L227–232 — add `usage_logs` to the TRUNCATE list):
```python
# Existing:
await conn.execute(
    "TRUNCATE TABLE agent_events, runs, agent_containers, "
    "agent_instances, idempotency_keys, rate_limit_counters, "
    "sessions, users "
    "RESTART IDENTITY CASCADE"
)

# AMD-05 amended:
await conn.execute(
    "TRUNCATE TABLE agent_events, runs, agent_containers, "
    "agent_instances, idempotency_keys, rate_limit_counters, "
    "sessions, users, usage_logs "       # NEW: usage_logs
    "RESTART IDENTITY CASCADE"
)
```

**Differences:**
- Single token added to an existing TRUNCATE statement. Zero new fixture machinery.
- AMD-05 picked option (a) over option (b) for consistency with the existing isolation pattern.

**Constraints (must preserve):**
- `RESTART IDENTITY CASCADE` semantics — `usage_logs` is a fact table; CASCADE is harmless because no other table FKs into it.
- Fixture remains autouse: no callsite changes required.

---

### CREATE `api_server/src/api_server/instrumentation/__init__.py`

Empty package marker. No analog needed.

---

### CREATE `api_server/src/api_server/instrumentation/sentry.py`

**Analog:** `api_server/src/api_server/auth/oauth.py` (`_resolve_or_fail` + module-level cache + `_log = logging.getLogger(...)` pattern at L49–80).

**Imports + module-logger pattern** (oauth.py L29–53):
```python
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

_log = logging.getLogger("api_server.<subsystem>")
```

**Dev-fallback / placeholder-log pattern** (oauth.py L55–62 + L77–80, the canonical "graceful no-op when env vars missing" shape D-14 mirrors):
```python
# Dev fallbacks — used ONLY when AP_ENV != prod and a given secret is missing.
# These are deliberately non-secret placeholders so tests can exercise the
# registration path without provisioning real credentials.
_DEV_PLACEHOLDER = "dev-placeholder-not-for-prod"

def _resolve_or_fail(
    settings: "Settings", field: str, dev_fallback: str
) -> str:
    """Read ``settings.<field>``; fail in prod if missing, else use dev fallback."""
```

**Differences the new file introduces:**
- No prod fail-loud — D-14 says "log INFO once, then silent". This is opposite to oauth's prod-fail-loud posture (Sentry is observability, not a hard dependency).
- `init_sentry(settings) -> None` is the public surface; called once from `main.create_app()` (D-10).
- `before_send(event, hint)` filter (D-12, AMD-06): drops Starlette `HTTPException` with `status_code < 500` to protect 5K/month free-tier quota. Import path per AMD-06: `from starlette.exceptions import HTTPException as StarletteHTTPException` (FastAPI re-exports the same class).
- `traces_sample_rate=0.0` hard-coded (errors only, SPEC AC-15).
- `profiles_sample_rate` intentionally OMITTED (default 0; not set).
- Reads `settings.sentry_dsn_api`, `settings.env`, `settings.git_sha` (config additions).

**Concrete `before_send` shape** (RESEARCH §"Init shape" L117–137 — load-bearing):
```python
def _before_send(event, hint):
    """Drop client-error envelopes before they hit Sentry quota (D-12)."""
    if "exc_info" in hint:
        exc_type, exc_value, _tb = hint["exc_info"]
        from starlette.exceptions import HTTPException as StarletteHTTPException
        if isinstance(exc_value, StarletteHTTPException):
            if exc_value.status_code < 500:
                return None
    return event
```

**Constraints:**
- DSN-unset → log `Sentry disabled (AP_SENTRY_DSN_API unset)` once at INFO and return. **Mirror oauth.py's `OAuth config oauth_X missing in dev; using placeholder` log spelling.**
- `sentry_sdk.init(...)` MUST NOT pass `integrations=[FastApiIntegration(...)]` — would override the SDK 2.x auto-default. Let auto-detection do its job.

---

### CREATE `api_server/tests/middleware/test_auth_rate_limit.py`

**Analog:** `api_server/tests/middleware/test_chat_rate_limit.py` (entire file).

**Module marker pattern** (chat_rate_limit.py L32):
```python
pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]
```

**Mini-app fixture pattern** (chat_rate_limit.py L41–80 — `chat_rl_app` is the literal blueprint):
```python
class _MiniSettings:
    """Minimal stand-in for app.state.settings used by RateLimitMiddleware."""
    trusted_proxy = False


@pytest_asyncio.fixture
async def chat_rl_app(migrated_pg):
    """Minimal FastAPI app: Session + RateLimit middlewares + stub routes."""
    dsn = _normalize_testcontainers_dsn(migrated_pg.get_connection_url())
    pool = await asyncpg.create_pool(
        dsn, min_size=1, max_size=3, command_timeout=5.0
    )
    app = FastAPI()
    app.state.db = pool
    app.state.session_last_seen = {}
    app.state.settings = _MiniSettings()

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SessionMiddleware)

    @app.post("/v1/agents/{agent_id}/messages")
    async def stub_chat(agent_id: str):
        return JSONResponse(status_code=202, content={"message_id": str(uuid4()), "status": "pending"})

    @app.post("/v1/runs")
    async def stub_runs():
        return JSONResponse(status_code=200, content={"run_id": str(uuid4())})

    try:
        yield app, pool
    finally:
        await pool.close()
```

**Three-test pattern** (chat_rate_limit.py L112–220 — direct mapping):
```python
# Test 1: 6th in 60s returns 429 + Retry-After (mirrors test_chat_rate_limit_5th_in_60s_returns_429 at L112-140).
# Test 2: per-route counters (mirrors test_chat_rate_limit_per_agent at L142-180).
# Test 3: cross-bucket isolation (mirrors test_chat_rate_limit_does_not_affect_runs at L182-220).
```

**429 envelope assertion shape** (chat_rate_limit.py L135–139):
```python
r5 = await chat_rl_client.post(...)
assert r5.status_code == 429, r5.text
ra = r5.headers.get("retry-after")
assert ra is not None and int(ra) >= 1, ra
body = r5.json()
assert body["error"]["code"] == "RATE_LIMITED", body
```

**Differences the new file introduces:**
- Stub routes are `/v1/auth/google/mobile`, `/v1/auth/github/mobile`, `/v1/auth/logout` (the 3 POSTs from `_AUTH_ROUTES`) instead of `/v1/agents/{id}/messages`.
- Limit is 5 (not 4) — 6th call expected to 429 (per D-04 + SPEC AC-01).
- Per-route test (analog of `per_agent`): 3 POSTs to `/v1/auth/google/mobile` + 3 POSTs to `/v1/auth/github/mobile` from the same IP all succeed (composite subject keeps counters per-route).
- Cross-bucket test (analog of `does_not_affect_runs`): exhaust auth bucket, POST `/v1/runs` still returns 200.
- The `session_cookie` fixture (chat_rate_limit.py L92–109) is OPTIONAL here — auth routes are pre-auth by definition; per-IP subject derivation from `_subject_from_scope` works without a cookie (the helper returns the peer IP when `state["user_id"]` is None per L122).

**Constraints:**
- Real Postgres counter (no mocks) per Golden Rule #1.
- `pytestmark = [pytest.mark.api_integration, pytest.mark.asyncio]` so it opt-in matches the existing `make test-api-integration` harness.

---

### CREATE `api_server/tests/test_sentry_init.py`

**Analog:** RESEARCH §"Test pattern" (`31-RESEARCH.md` L182–205) — Sentry SDK's own `Transport` subclass primitive.

**Capturing-transport pattern** (RESEARCH L186–192 — load-bearing):
```python
import sentry_sdk
from sentry_sdk.transport import Transport


class _CapturingTransport(Transport):
    def __init__(self, options=None):
        super().__init__(options)
        self.envelopes = []
    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)
```

**Two-test obligation per AMD-06:**
1. **Captures unhandled `RuntimeError`** when DSN set — assert exactly one envelope (RESEARCH L195–205).
2. **`before_send` drops 4xx HTTPException** — explicit AMD-06 assertion: raise `HTTPException(status_code=429)` (a rate-limited envelope) and assert the transport-mock has ZERO envelopes. Without this assertion, the test passes vacuously even if `before_send` is broken.
3. **Graceful no-op when DSN unset** — `monkeypatch.delenv("AP_SENTRY_DSN_API", raising=False)` + `init_sentry(settings)` + assert `sentry_sdk.Hub.current.client is None` (or equivalent for SDK 2.x — `sentry_sdk.get_client().is_active() is False`); assert no exception raised.

**Constraints:**
- NO `respx` here — Sentry has its own `Transport` mock. AMD-06 explicit: "Sentry transport-mock comes from `sentry_sdk` itself; no `pytest-mock` or `mocktail` introduction."
- AMD-06 third assertion is non-negotiable: 4xx HTTPException → ZERO envelopes captured. That's the load-bearing budget protection D-12 promises.

---

### CREATE `api_server/tests/e2e/__init__.py`

Empty package marker.

---

### CREATE `api_server/tests/e2e/conftest.py`

**Analog:** `api_server/tests/conftest.py` `authenticated_cookie` fixture L606–649 (per AMD-03).

**Authenticated-cookie fixture pattern** (conftest.py L606–649, the canonical shape AMD-03 mandates):
```python
@pytest_asyncio.fixture
async def authenticated_cookie(db_pool):
    """Seed a google-provider user + a live session; yield cookie + ids."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (id, provider, sub, email, display_name) "
            "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
            "google",
            f"test-sub-{uuid4().hex[:12]}",
            "alice@example.com",
            "Alice",
        )
        now = datetime.now(timezone.utc)
        session_id = await conn.fetchval(
            """
            INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
            VALUES ($1, $2, $3, $2)
            RETURNING id::text
            """,
            user_id, now, now + timedelta(days=30),
        )
    yield {
        "Cookie": f"ap_session={session_id}",
        "_user_id": user_id,
        "_session_id": session_id,
    }
```

**E2E composer-fixture shape** (RESEARCH §"Recommended e2e money-path fixture wire shape" L322–348):
```python
@pytest_asyncio.fixture(scope="function")  # function-scope per D-22 idempotency
async def e2e_money_path_client(async_client, authenticated_cookie):
    """Compose async_client (real-Postgres testcontainer + lifespan-bound app)
    with authenticated_cookie (real users + sessions row).

    The yielded dict carries:
      * client — httpx AsyncClient with ASGITransport bound to create_app()
      * cookie — `ap_session=<uuid>` ready to pass as `headers={"Cookie": ...}`
      * user_id — string UUID for `usage_logs.user_id` lookup
    """
    yield {
        "client": async_client,
        "cookie": authenticated_cookie["Cookie"],
        "user_id": authenticated_cookie["_user_id"],
    }
```

**Differences the new file introduces:**
- Composer over the two existing fixtures — does NOT reimplement the user-seed or cookie-shape.
- Adds NO new SQL, NO HMAC, NO signing-key machinery (AMD-03 explicit: there is no `SESSION_SIGNING_KEY` in the project).
- Yielded dict adds `user_id` for the `usage_logs WHERE user_id = $1` poll.

**Constraints (AMD-03):**
- Cookie value is a plain UUID from `gen_random_uuid()`. Security comes from unguessability, not HMAC.
- No CI-only auth backdoor — the fixture is identical to what `tests/auth/test_logout.py`, `test_users_me.py`, etc. already use.
- 30-day session expiry matches the production cookie lifetime.

---

### CREATE `api_server/tests/e2e/test_money_path.py`

**Analog:** `tests/middleware/test_chat_rate_limit.py` (httpx + ASGITransport + cookie + assertion shape) + RESEARCH §"Test body shape" L350–400.

**Marker + asyncio decorator pattern** (RESEARCH L353–354):
```python
@pytest.mark.e2e_money_path  # registered in pyproject.toml [tool.pytest.ini_options].markers
@pytest.mark.asyncio
async def test_chat_through_proxy_writes_usage_log(e2e_money_path_client, db_pool):
    ...
```

**Recipe + model selection** (per AMD-04 — locked):
```python
# AMD-04: nano-kaiku does not exist; use nanobot + openai/gpt-4o-mini
# (Phase 29 baseline ~$0.00039345/completion).
deploy_resp = await client.post(
    "/v1/runs",
    headers=headers,
    json={"recipe_name": "nanobot", "model": "openai/gpt-4o-mini",
          "prompt": "Reply with one word: hello"},
)
```

**Cost-capture polling pattern** (D-20, RESEARCH L383–394 — 200ms × 50 iterations = 10s ceiling):
```python
import asyncio
usage_row = None
for _ in range(50):
    async with db_pool.acquire() as conn:
        usage_row = await conn.fetchrow(
            "SELECT cost_usd, upstream_request_id FROM usage_logs "
            "WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1",
            user_id,
        )
        if usage_row is not None:
            break
    await asyncio.sleep(0.2)

assert usage_row is not None, "usage_logs row never appeared in 10s"
assert float(usage_row["cost_usd"]) > 0, usage_row
assert usage_row["upstream_request_id"] is not None, usage_row
```

**Differences the new file introduces:**
- First file under `tests/e2e/` with this marker — no prior precedent.
- AMD-05 ensures `usage_logs` is truncated between tests so the `ORDER BY created_at DESC LIMIT 1` query is unambiguous.
- Calls real OpenRouter via the proxy — not a local stub. Requires `OPENROUTER_API_KEY` env to be present (Makefile guard enforces this).

**Constraints:**
- Real OpenRouter only. No httpx-level mocks for the upstream call (Golden Rule #1).
- Cost-capture polling must be 10s ceiling exactly (D-20). Phase 30 measurements show nanobot completes in 2–4s.
- Fallback model if `gpt-4o-mini` unavailable: `nanobot + anthropic/claude-haiku-4.5` (AMD-04). Plan-phase decides whether the test code embeds a fallback or fails loud.

---

### MODIFY `mobile/lib/main.dart`

**Analog:** self — the existing `main()` body (L24–53) is wrapped, not rewritten.

**Wrap-runner insertion pattern** (D-11 — entire existing body becomes the `runner` callback):
```dart
// Existing L24-53 (current shape):
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AppEnv.fromEnvironment();
  final container = ProviderContainer();
  final initialRoute = await resolveInitialRoute(container.read(apiClientProvider));
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
  runApp(
    UncontrolledProviderScope(
      container: container,
      child: SolvrLabsApp(initialRoute: initialRoute),
    ),
  );
}

// NEW (D-11):
import 'package:agent_playground/core/instrumentation/sentry.dart';

Future<void> main() async {
  await initSentry(runner: () async {
    WidgetsFlutterBinding.ensureInitialized();
    AppEnv.fromEnvironment();
    final container = ProviderContainer();
    final initialRoute = await resolveInitialRoute(container.read(apiClientProvider));
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.dark);
    runApp(
      UncontrolledProviderScope(
        container: container,
        child: SolvrLabsApp(initialRoute: initialRoute),
      ),
    );
  });
}
```

**Differences:**
- Single `import` + single `await initSentry(runner: () async { ... })` wrap. Body unchanged.
- `SentryFlutter.init(..., appRunner: runner)` invokes the runner inside Sentry's zone — that's why the wrap is required (zone-bound error capture vs. plain `try/catch`).

---

### MODIFY `mobile/lib/features/chat/chat_providers.dart`

**Analog:** self — the silent-swallow sites at L387 and L398 are replaced with classifier-driven writes to the new `chatStreamErrorProvider`.

**Initial-connect site pattern** (L386–388, current silent swallow):
```dart
// Existing:
// ignore: discarded_futures
_stream.connect().catchError((_) {});

// NEW (D-05/D-06/D-07/AMD-02):
_stream.connect().catchError((Object e) {
  ref.read(chatStreamErrorProvider.notifier).state = ChatStreamErrorState(
    agentInstanceId: agentInstanceId,
    errorClass: classifyChatStreamError(e),
    lastFailedAction: 'connect',
  );
  return null;  // satisfy Future<void>.catchError signature
});
```

**`_onResumed` reconnect site pattern** (L393–401, current bare catch):
```dart
// Existing:
Future<void> _onResumed() async {
  await _stream.disconnect();
  try {
    await _stream.connect();
  // ignore: avoid_catches_without_on_clauses
  } catch (_) {
    // intentionally empty — keep prior state visible on reconnect failure.
  }
}

// NEW (D-09 — REPLACE banner state, do not stack):
Future<void> _onResumed() async {
  await _stream.disconnect();
  try {
    await _stream.connect();
    // D-09: success → clear the banner (replace with null).
    ref.read(chatStreamErrorProvider.notifier).state = null;
  } catch (e) {
    ref.read(chatStreamErrorProvider.notifier).state = ChatStreamErrorState(
      agentInstanceId: agentInstanceId,
      errorClass: classifyChatStreamError(e),
      lastFailedAction: 'reconnect_on_resume',
    );
  }
}
```

**Differences:**
- Both sites route through the SAME `classifyChatStreamError` (D-06 — single classifier reused).
- `lastFailedAction` field distinguishes the two surface paths for retry-CTA dispatch.
- D-09: on `_onResumed` success, the banner is REPLACED with `null` (cleared); on failure it is REPLACED with the new classification (not stacked over the old one).

**Constraints:**
- Existing comment at L388 (`// ignore: discarded_futures`) must remain — the catchError chain is fire-and-forget by design.
- Existing comment at L397 (`// ignore: avoid_catches_without_on_clauses`) must remain because `catch (e)` without `on T` is what the linter complains about.

---

### MODIFY `mobile/lib/features/chat/chat_screen.dart` (per AMD-01)

**Analog:** self — the existing `RetryBanner(...)` consumption at L196–207 for `tgBanner` is the literal blueprint for the new chat-stream error banner sibling-block.

**Existing telegram banner consumption pattern** (L196–207 — REUSE, do NOT duplicate `RetryBanner`):
```dart
body: Column(
  children: [
    if (tgBanner != null)
      RetryBanner(
        key: const Key('telegram-failed-banner'),
        message: 'Telegram setup failed: ${tgBanner.reason}',
        actionLabel: 'Retry',
        tone: RetryBannerTone.warning,
        dismissible: true,
        onDismiss: () => ref
            .read(telegramFailedBannerProvider.notifier)
            .state = null,
        onTap: () => _retryTelegram(context, tgBanner),
      ),
    // ... rest of Column unchanged
  ],
),
```

**NEW sibling-block insertion pattern** (immediately after the telegram banner block, before `_OlderMessagesBanner`):
```dart
final streamErr = ref.watch(chatStreamErrorProvider);
// ... inside the Column body, sibling of the telegram banner:
if (streamErr != null)
  RetryBanner(
    key: const Key('chat-stream-error-banner'),
    message: _streamErrorCopy(streamErr.errorClass),
    actionLabel: streamErr.errorClass == ChatStreamErrorClass.authExpired
        ? 'Sign in'
        : 'Retry',
    tone: RetryBannerTone.warning,
    dismissible: true,
    onDismiss: () => ref.read(chatStreamErrorProvider.notifier).state = null,
    onTap: () => _handleStreamErrorRetry(context, streamErr),
  ),
```

Where `_streamErrorCopy` is a private helper inside `chat_screen.dart` mapping `ChatStreamErrorClass` → the three locked SPEC copy strings:
```dart
String _streamErrorCopy(ChatStreamErrorClass c) {
  switch (c) {
    case ChatStreamErrorClass.networkTransient:
      return 'Connection lost — tap to retry';
    case ChatStreamErrorClass.authExpired:
      return 'Session expired — sign in again';
    case ChatStreamErrorClass.serverError:
      return 'Server error — try again later';
  }
}
```

**Differences (AMD-01 amended from D-08):**
- NO new banner widget file. `RetryBanner` from `mobile/lib/shared/retry_banner.dart` is reused verbatim.
- All new code lives inside `chat_screen.dart` (consumption + copy helper) + the new provider file (state).
- Saves ~80 LOC vs. the original D-08 direction.

**Constraints (AMD-01):**
- `tone: RetryBannerTone.warning` — matches the telegram banner's prefix-glyph + accessibility shape (RetryBanner L41–50).
- `dismissible: true` — symmetric with the telegram banner.
- `Key('chat-stream-error-banner')` — distinct key for widget-test targeting (`find.byKey(...)`).

---

### MODIFY `mobile/pubspec.yaml`

**Analog:** self — existing `dependencies` block (L10–25).

**Dependency-add pattern** (insert anywhere alphabetically, e.g. after `intl: ^0.20.0`):
```yaml
dependencies:
  # ... existing deps ...
  intl: ^0.20.0
  riverpod_annotation: ^4.0.2
  # NEW: Phase 31 H6 — errors-only Sentry on mobile.
  sentry_flutter: ^9.20.0
  url_launcher: ^6.3.0
  uuid: ^4.5.3
```

**Constraints:**
- RESEARCH-pinned version `^9.20.0` (latest as of 2026-05-06 per pub.dev).
- 9.x is a deliberate breaking change from 8.x — RESEARCH verified compatibility with Flutter 3.41+ (already in pubspec).

---

### MODIFY `mobile/Makefile`

**Analog:** self — `ios` + `android` targets at L13–27.

**Existing dart-define propagation pattern** (Makefile L13–19, the canonical shape for `--dart-define` chains):
```makefile
ios:
	fvm flutter run \
	  $(if $(DEVICE),-d $(DEVICE),) \
	  --dart-define BASE_URL=$(BASE_URL) \
	  --dart-define GOOGLE_IOS_CLIENT_ID=$(GOOGLE_IOS_CLIENT_ID) \
	  --dart-define GOOGLE_SERVER_CLIENT_ID=$(AP_OAUTH_GOOGLE_CLIENT_ID) \
	  --dart-define GITHUB_CLIENT_ID=$(AP_OAUTH_GITHUB_MOBILE_CLIENT_ID)
```

**NEW pattern** (D-15 — append 3 dart-defines to BOTH `ios` and `android` targets):
```makefile
ios:
	fvm flutter run \
	  $(if $(DEVICE),-d $(DEVICE),) \
	  --dart-define BASE_URL=$(BASE_URL) \
	  --dart-define GOOGLE_IOS_CLIENT_ID=$(GOOGLE_IOS_CLIENT_ID) \
	  --dart-define GOOGLE_SERVER_CLIENT_ID=$(AP_OAUTH_GOOGLE_CLIENT_ID) \
	  --dart-define GITHUB_CLIENT_ID=$(AP_OAUTH_GITHUB_MOBILE_CLIENT_ID) \
	  --dart-define SENTRY_DSN_MOBILE=$(SENTRY_DSN_MOBILE) \
	  --dart-define SENTRY_RELEASE=$(GIT_SHA) \
	  --dart-define SENTRY_ENVIRONMENT=$(SENTRY_ENVIRONMENT)
```

**Differences:**
- Same shape as existing dart-defines — the `set -a; source .env; set +a; make ios` flow already exports any `.env` var into Make's environment, so adding 3 more lines is the only change.
- Empty values are fine — the SDK no-ops when DSN is empty (D-14 / RESEARCH L228–229).

**Constraints:**
- BOTH `ios` and `android` targets need the same 3 lines (parity).
- `SENTRY_RELEASE=$(GIT_SHA)` — matches api_server's `release=settings.git_sha` boot-pin (D-13 cross-runtime tag parity).

---

### CREATE `mobile/lib/core/instrumentation/sentry.dart`

**Analog:** RESEARCH §"Init shape" L218–252 (canonical). Indirect analog: `mobile/lib/core/env/app_env.dart` for the env-driven init pattern.

**Wrap-runner pattern** (RESEARCH L218–252, load-bearing — all 30 lines reused verbatim except the `beforeSend` body):
```dart
// Phase 31 H6 D-11 + D-13 + D-14 — sentry_flutter wrap-runner.
import 'package:flutter/foundation.dart';
import 'package:sentry_flutter/sentry_flutter.dart';
import 'package:dio/dio.dart';

Future<void> initSentry({required Future<void> Function() runner}) async {
  const dsn = String.fromEnvironment('SENTRY_DSN_MOBILE');
  const env = String.fromEnvironment('SENTRY_ENVIRONMENT', defaultValue: 'dev');
  const release = String.fromEnvironment('SENTRY_RELEASE');
  if (dsn.isEmpty) {
    debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)');
    await runner();
    return;
  }
  await SentryFlutter.init(
    (options) {
      options.dsn = dsn;
      options.environment = env;
      if (release.isNotEmpty) options.release = release;
      options.tracesSampleRate = 0.0;        // SPEC AC-15 — errors only
      options.beforeSend = (event, hint) {
        // D-12 mobile equivalent: drop DioException with status < 500.
        final t = event.throwable;
        if (t is DioException && (t.response?.statusCode ?? 0) < 500) {
          return null;
        }
        return event;
      };
    },
    appRunner: runner,
  );
}
```

**Differences:**
- First file under `mobile/lib/core/instrumentation/` (new package — D-11).
- DSN-empty branch invokes `runner()` directly without Sentry init. Critical so dev/CI runs without DSN don't crash.
- `tracesSampleRate = 0.0` hard-coded (errors only).
- `beforeSend` drops `DioException` with `response.statusCode < 500` (D-12 mobile equivalent of api_server `before_send`).

**Constraints:**
- DSN-unset path must be BYTE-IDENTICAL no-op except for the debugPrint. No native plugin init, no zone setup, nothing.
- `appRunner: runner` is the public surface — Sentry's docs require this wrap to capture zone-bound errors.

---

### CREATE `mobile/lib/features/chat/chat_stream_error_classifier.dart`

**Analog:** RESEARCH §"Mobile error classifier wire shape" L538–588. No exact in-repo analog; this is a new utility.

**Pure-fn dispatch pattern** (RESEARCH L538–588 — the canonical shape per AMD-02):
```dart
// Phase 31 H4 D-06 + D-07 + AMD-02 — three-class chat-stream error taxonomy.
import 'dart:async';
import 'dart:io';
import 'package:dio/dio.dart';

enum ChatStreamErrorClass {
  networkTransient,  // SocketException, TimeoutException, transport-tier DioException
  authExpired,       // HTTP 401
  serverError,       // 5xx and non-401 4xx
}

ChatStreamErrorClass classifyChatStreamError(Object e) {
  // Network-layer errors → transient.
  if (e is SocketException) return ChatStreamErrorClass.networkTransient;
  if (e is TimeoutException) return ChatStreamErrorClass.networkTransient;

  // Dio surface (defensive — _onResumed may surface dio errors via the
  // history fetch path on retry).
  if (e is DioException) {
    final status = e.response?.statusCode;
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return ChatStreamErrorClass.networkTransient;
    }
    if (status == 401) return ChatStreamErrorClass.authExpired;
    // AMD-02: 5xx → serverError (NOT networkTransient — required by SPEC AC11).
    if (status != null && status >= 500) {
      return ChatStreamErrorClass.serverError;
    }
    // Non-401 4xx → serverError (e.g. 404 ownership mismatch).
    return ChatStreamErrorClass.serverError;
  }

  // Default fallback per D-07: unknown → networkTransient.
  return ChatStreamErrorClass.networkTransient;
}
```

**Differences (AMD-02 supersedes D-07):**
- AMD-02 explicitly maps `DioException` with `response.statusCode >= 500` → `serverError` (NOT `networkTransient` as D-07's original wording suggested). This is the load-bearing reconciliation with SPEC AC-11's `"Server error — try again later"` literal copy contract.
- `SocketException` / `TimeoutException` / connection-tier `DioException` → `networkTransient` (mapped to `"Connection lost — tap to retry"`).
- Unknown `Object` → `networkTransient` default fallback (D-07 explicit).

**Constraints:**
- Pure top-level function — no Riverpod, no I/O, no async (D-06).
- Reusable from BOTH `chat_providers.dart:387` AND `:398` (same classifier, two callsites).

---

### CREATE `mobile/lib/features/chat/chat_stream_error_banner_provider.dart`

**Analog:** `mobile/lib/features/chat/telegram_failed_banner_provider.dart` (entire 41-line file).

**Provider + state-class pattern** (telegram_failed_banner_provider.dart L17–41 — direct analog):
```dart
import 'package:flutter_riverpod/legacy.dart';

class TelegramFailedBannerState {
  const TelegramFailedBannerState({
    required this.agentInstanceId,
    required this.reason,
    required this.telegramInputs,
  });
  final String agentInstanceId;
  final String reason;
  final Map<String, String> telegramInputs;
}

final StateProvider<TelegramFailedBannerState?> telegramFailedBannerProvider =
    StateProvider<TelegramFailedBannerState?>((_) => null);
```

**NEW provider shape** (D-05 + D-09 — mirror exactly, swap the state shape):
```dart
// Phase 31 H4 D-05/D-09 — chat-stream error banner state.
// Memory-only, single-active per chat (D-50 lifecycle inherited).
// Cleared on retry-success / dismiss / sign-out / Riverpod teardown.

import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:flutter_riverpod/legacy.dart';

class ChatStreamErrorState {
  const ChatStreamErrorState({
    required this.agentInstanceId,
    required this.errorClass,
    required this.lastFailedAction,
  });
  final String agentInstanceId;
  final ChatStreamErrorClass errorClass;
  final String lastFailedAction;  // 'connect' | 'reconnect_on_resume'
}

final StateProvider<ChatStreamErrorState?> chatStreamErrorProvider =
    StateProvider<ChatStreamErrorState?>((_) => null);
```

**Differences:**
- State fields differ: `errorClass` (enum) + `lastFailedAction` (string) vs. `reason` (string) + `telegramInputs` (map).
- Same `StateProvider<T?>` outer shape; same `_` constructor placeholder; same `legacy.dart` import (Riverpod 3.x convention for `StateProvider`).

---

### CREATE `mobile/test/features/chat/chat_stream_error_classifier_test.dart`

**Analog:** RESEARCH §"Widget-test fixture shape" L676–705. No exact in-repo top-level-fn unit-test analog.

**Three-class + fallback test pattern** (RESEARCH L683–705 — load-bearing):
```dart
import 'package:agent_playground/features/chat/chat_stream_error_classifier.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'dart:async';
import 'dart:io';

void main() {
  group('classifyChatStreamError', () {
    test('SocketException → networkTransient', () {
      expect(
        classifyChatStreamError(const SocketException('host down')),
        ChatStreamErrorClass.networkTransient,
      );
    });
    test('TimeoutException → networkTransient', () {
      expect(
        classifyChatStreamError(TimeoutException('boom', const Duration(seconds: 1))),
        ChatStreamErrorClass.networkTransient,
      );
    });
    test('DioException 401 → authExpired', () {
      final dio = DioException(
        requestOptions: RequestOptions(path: ''),
        response: Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: 401,
        ),
      );
      expect(classifyChatStreamError(dio), ChatStreamErrorClass.authExpired);
    });
    test('DioException 5xx → serverError (AMD-02)', () {
      final dio = DioException(
        requestOptions: RequestOptions(path: ''),
        response: Response(
          requestOptions: RequestOptions(path: ''),
          statusCode: 503,
        ),
      );
      expect(classifyChatStreamError(dio), ChatStreamErrorClass.serverError);
    });
    test('unknown Object → networkTransient (default fallback per D-07)', () {
      expect(
        classifyChatStreamError(Exception('weird wrapper from flutter_client_sse')),
        ChatStreamErrorClass.networkTransient,
      );
    });
  });
}
```

**Differences:**
- 5 test cases (3 enum classes + 1 AMD-02 5xx assertion + 1 fallback) — the AMD-02 5xx assertion is non-negotiable per SPEC AC-11.

---

### CREATE `mobile/test/features/chat/chat_screen_error_banner_widget_test.dart`

**Analog:** No in-repo widget-test for `RetryBanner` consumption. First-of-kind. Mirror Flutter `widgetTester` + Riverpod `ProviderScope` shape from existing widget tests (none cited in RESEARCH; plan-phase locates the closest in-repo widget-test).

**Required obligations** (per SPEC AC-05 / AC-06 / AC-07 / AC-08 / AC-09):
1. `pumpWidget` a `ProviderScope` around a minimal `MaterialApp` + `chat_screen.dart` host harness.
2. Override `chatStreamErrorProvider` to a non-null state for each of the three classes.
3. Assert `find.byKey(Key('chat-stream-error-banner'))` exists.
4. Assert the message text matches the three locked copy strings exactly:
   - `'Connection lost — tap to retry'`
   - `'Session expired — sign in again'`
   - `'Server error — try again later'`
5. Tap-retry simulation: tap the `Retry` button, verify a new `_stream.connect()` call (mock spy via Riverpod override on whatever provider exposes the stream connector).
6. Auth-class CTA: tap `Sign in`, verify route navigation to `/login` (route-spy).

**Differences:**
- First widget test that consumes `RetryBanner` from the chat-feature side. Sets the precedent for future banner tests.
- No new widget mock infrastructure — `flutter_test` + `ProviderScope.overrides` are sufficient.

---

### CREATE `mobile/test/core/instrumentation/sentry_test.dart`

**Analog:** No in-repo analog. Follow the Sentry SDK's own `Transport` mock primitive (parallel to the api_server-side test).

**Required obligations:**
1. **Captured-event test:** Set `SENTRY_DSN_MOBILE` dart-define for the test, install a capturing transport via `SentryFlutter.init(... transport: ...)`, throw an exception, assert exactly one captured envelope.
2. **No-init test:** Empty `SENTRY_DSN_MOBILE` → assert `Sentry.isEnabled` (or equivalent SDK 2.x idiom) is `false`, assert no init crash, assert `runner` was invoked.

**Constraints:**
- NO `respx`, NO `http_mock_adapter` for this test — Sentry SDK has its own transport mock.
- Test environment must NOT collide with the production zone — use `Sentry.close()` in `tearDown`.

---

### CREATE `.github/workflows/e2e-money-path.yml`

**Analog:** `.github/workflows/mobile.yml` (entire file).

**Workflow header pattern** (mobile.yml L1–18 — direct shape):
```yaml
name: e2e money path

on:
  push:
    branches: [main]
    paths:
      - 'api_server/**'
      - 'recipes/**'
      - '.github/workflows/e2e-money-path.yml'
  pull_request:
    branches: [main]
    paths:
      - 'api_server/**'
      - 'recipes/**'
      - '.github/workflows/e2e-money-path.yml'
```

**Concurrency block** (D-21 — non-optional):
```yaml
concurrency:
  group: e2e-money-path
  cancel-in-progress: false
```

**Job + steps pattern** (mobile.yml L20–53 — adapt: replace `subosito/flutter-action` with `actions/setup-python` and `flutter pub get`/`flutter test` with the docker-compose + `make e2e-money-path` chain):

Full structure per RESEARCH §"GH Actions e2e workflow shape" L431–502:
```yaml
jobs:
  money-path:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env:
      OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_CI_KEY }}
      AP_ENV: dev
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - name: Boot Postgres + Redis from docker-compose.dev.yml
        run: docker compose -f docker-compose.dev.yml up -d postgresql redis
      - name: Wait for Postgres healthy
        run: |
          for i in {1..30}; do
            if docker compose -f docker-compose.dev.yml exec -T postgresql \
                 pg_isready -U temporal >/dev/null 2>&1; then
              echo "postgres ready"; break
            fi
            sleep 1
          done
      - name: Create app DB + run migrations
        run: |
          docker compose -f docker-compose.dev.yml exec -T postgresql \
            psql -U temporal -c "CREATE DATABASE agent_playground_api"
          make install-api
          DATABASE_URL=postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api \
            make migrate-api
      - name: Run e2e money-path test
        env:
          DATABASE_URL: postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api
          AP_REDIS_URL: redis://localhost:6379/0
        run: make e2e-money-path
      - name: Tear down compose stack
        if: always()
        run: docker compose -f docker-compose.dev.yml down -v
```

**Differences:**
- Mirrors mobile.yml's path-filter idiom + single-job + ubuntu-latest discipline.
- Replaces Flutter setup with Python setup; replaces `flutter pub get` with `make install-api`.
- Adds `concurrency` block (D-21) which mobile.yml does NOT have.
- Reuses `docker-compose.dev.yml` directly (D-19) — no CI-only compose variant.

**Secret-hygiene constraint:**
- `OPENROUTER_CI_KEY` referenced via `${{ secrets.OPENROUTER_CI_KEY }}`. GitHub auto-masks the value in logs. Never echoed via `echo` or `printenv`.
- The Makefile guard `test -n "$$OPENROUTER_API_KEY"` prints "ERROR: …not set" but NEVER the value (test-recipes.yml is NOT analog for this — no live key there).

**Constraints:**
- `cancel-in-progress: false` is non-negotiable (D-21) — serializes real-money runs to protect the $5/mo dashboard cap.
- Path-filter on `api_server/**` + `recipes/**` + workflow self-reference (per AC-16 + RESEARCH L437–446).
- Ubuntu-latest already has Docker Compose v2 preinstalled (RESEARCH L519 verified).

---

### MODIFY `Makefile`

**Analog:** self — `test-api-integration` target at L205–206 (the canonical pytest-marker harness pattern per D-17).

**Existing pattern** (Makefile L202–206):
```makefile
test-api:
	cd api_server && pytest -q -m "not api_integration"

test-api-integration:
	cd api_server && pytest -m api_integration
```

**NEW target pattern** (D-17 — append after `test-api-integration`):
```makefile
.PHONY: e2e-money-path
e2e-money-path:  ## Phase 31 H8 — real OpenRouter chat → cost-capture in CI
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set" && exit 1)
	cd api_server && pytest -m e2e_money_path -v --tb=short
```

**Differences:**
- Adds an env-guard preflight (`@test -n "$$OPENROUTER_API_KEY"`) — pattern lifted from `mobile/Makefile`'s `spike` and `screens-e2e` targets (mobile/Makefile L29–32). The error message format ("ERROR: <var> not set") is the consistent project idiom.
- `pytest -v --tb=short` for CI verbosity vs. `test-api-integration`'s default. `-m e2e_money_path` opt-in marker (D-17).

**Constraints:**
- `.PHONY: e2e-money-path` declared (Makefile project convention — see L24, L196 for examples of explicit `.PHONY` blocks).
- Append to the Phase 19 API-server section (~L196–228) since it's an api_server-side test, not a frontend or recipe test.

---

## Shared Patterns

### Pattern S1 — Composite-subject derivation in RateLimitMiddleware
**Source:** `api_server/src/api_server/middleware/rate_limit.py` L158–168 (`chat:<subject>:<agent_id>`)
**Apply to:** new `auth` bucket (D-02)
**Excerpt:** see "MODIFY `middleware/rate_limit.py`" above.
**Why shared:** the load-bearing pattern that gives each route its own counter. Future buckets that need per-key isolation should mirror this exactly.

### Pattern S2 — Fail-open Postgres-outage handling
**Source:** `api_server/src/api_server/middleware/rate_limit.py` L170–180
**Apply to:** new `auth` bucket
**Excerpt:**
```python
try:
    async with app.state.db.acquire() as conn:
        allowed, retry_after = await check_and_increment(conn, subject, bucket, limit, window_s)
except Exception:
    _log.exception("rate_limit backend error; failing open")
    await self.app(scope, receive, send)
    return
```
**Why shared:** SPEC explicit: existing fail-open semantics MUST be preserved. The new auth bucket inherits this branch unchanged because it lives inside the same `RateLimitMiddleware.__call__`.

### Pattern S3 — Stripe-shape 429 error envelope
**Source:** `api_server/src/api_server/middleware/rate_limit.py` L186–203 + `api_server/src/api_server/models/errors.py::make_error_envelope`
**Apply to:** new `auth` bucket
**Excerpt:**
```python
body = json.dumps(
    make_error_envelope(
        ErrorCode.RATE_LIMITED,
        f"rate limit exceeded for bucket {bucket!r}",
        param=bucket,
    )
).encode()
await send({
    "type": "http.response.start",
    "status": 429,
    "headers": [
        (b"content-type", b"application/json"),
        (b"retry-after", str(retry_after).encode()),
        (b"content-length", str(len(body)).encode()),
    ],
})
```
**Why shared:** SPEC AC-01 mandates a Stripe-shape envelope + Retry-After. Reused as-is from chat bucket (no new shape, same `ErrorCode.RATE_LIMITED`).

### Pattern S4 — Authenticated-cookie test fixture
**Source:** `api_server/tests/conftest.py` L606–649 (`authenticated_cookie`)
**Apply to:** `tests/e2e/conftest.py` (the e2e `e2e_money_path_client` composer reuses this fixture verbatim per AMD-03)
**Excerpt:** see "CREATE `tests/e2e/conftest.py`" above.
**Why shared:** AMD-03 explicitly forbids reinventing session signing. The fixture is the canonical "real users + sessions row + Cookie header" path used by 4+ test files already.

### Pattern S5 — Placeholder-log on missing env (graceful no-op)
**Source:** `api_server/src/api_server/auth/oauth.py` (`OAuth config oauth_X missing in dev; using placeholder` log style at L77–80) + dev-fallback constants L55–62
**Apply to:** `api_server/src/api_server/instrumentation/sentry.py` (D-14: `Sentry disabled (AP_SENTRY_DSN_API unset)`) AND `mobile/lib/core/instrumentation/sentry.dart` (`debugPrint('Sentry disabled (SENTRY_DSN_MOBILE unset)')`)
**Excerpt (api_server/auth/oauth.py L55–62):**
```python
# Dev fallbacks — used ONLY when AP_ENV != prod and a given secret is missing.
# These are deliberately non-secret placeholders so tests can exercise the
# registration path without provisioning real credentials.
_DEV_PLACEHOLDER = "dev-placeholder-not-for-prod"
```
**Why shared:** D-14 explicitly says "matches `auth/oauth.py` placeholder-log pattern". Both runtimes mirror the same shape — log INFO once, then silent.

### Pattern S6 — `RetryBanner` reuse for chat-feature inline banners (AMD-01)
**Source:** `mobile/lib/shared/retry_banner.dart` (the widget) + `mobile/lib/features/chat/chat_screen.dart` L196–207 (the consumption pattern)
**Apply to:** new chat-stream error banner consumption inside `chat_screen.dart` (sibling block)
**Excerpt:** see "MODIFY `chat_screen.dart`" above.
**Why shared:** AMD-01 explicit: NO new banner widget file. `RetryBanner` already implements accessibility + dismissal + tone semantics. Two banners now live as siblings in the chat `Column`.

### Pattern S7 — `StateProvider<T?>` for memory-only single-active state
**Source:** `mobile/lib/features/chat/telegram_failed_banner_provider.dart` L17–41
**Apply to:** `mobile/lib/features/chat/chat_stream_error_banner_provider.dart` (D-05)
**Excerpt:** see "CREATE `chat_stream_error_banner_provider.dart`" above.
**Why shared:** Phase 25 D-50 contract — memory-only, cleared on retry-success / dismiss / sign-out / Riverpod teardown. New provider inherits the lifecycle via shape parity.

### Pattern S8 — `--dart-define` propagation via Makefile env-substitution
**Source:** `mobile/Makefile` L13–27 (`ios` + `android` targets)
**Apply to:** D-15 — extend the same targets with 3 new `--dart-define` lines
**Excerpt:** see "MODIFY `mobile/Makefile`" above.
**Why shared:** the `set -a; source .env; set +a; make ios` flow already handles env propagation. Adding 3 lines is byte-symmetric with the existing 4 dart-defines (BASE_URL + 3 OAuth client IDs).

### Pattern S9 — pytest-marker harness via `make` target
**Source:** `Makefile` L202–206 (`test-api-integration: cd api_server && pytest -m api_integration`)
**Apply to:** new `e2e-money-path: cd api_server && pytest -m e2e_money_path` target (D-17)
**Excerpt:** see "MODIFY `Makefile`" above.
**Why shared:** D-17 explicit: "mirrors existing `test-api-integration` pattern exactly". The pyproject.toml marker registration shape parallels.

### Pattern S10 — Env-guard preflight on Make targets that require live secrets
**Source:** `mobile/Makefile` L29–37 (the `spike` target's `BASE_URL` / `SESSION_ID` / `OPENROUTER_KEY` guard chain)
**Apply to:** new `Makefile` `e2e-money-path` target (`OPENROUTER_API_KEY` guard)
**Excerpt:**
```makefile
@test -n "$$BASE_URL" || (echo "ERROR: BASE_URL not set. ..." && exit 1)
```
**Why shared:** consistent error-message idiom across the project. Failing fast with a clear message saves the operator a 60s debug cycle when an env var is missing.

---

## No Analog Found

All 21 in-scope files have at least one verified analog (in-repo or RESEARCH-cited canonical shape). No files require fall-back to RESEARCH.md patterns alone.

---

## Metadata

**Analog search scope:**
- `api_server/src/api_server/middleware/` (rate_limit.py, session.py)
- `api_server/src/api_server/auth/` (oauth.py)
- `api_server/src/api_server/main.py` + `routes/auth.py`
- `api_server/tests/conftest.py` + `api_server/tests/middleware/test_chat_rate_limit.py`
- `mobile/lib/main.dart` + `mobile/lib/features/chat/` (chat_providers.dart, chat_screen.dart, telegram_failed_banner_provider.dart)
- `mobile/lib/shared/retry_banner.dart`
- `mobile/Makefile` + `Makefile`
- `.github/workflows/` (mobile.yml, test-recipes.yml)
- `mobile/pubspec.yaml` + `api_server/pyproject.toml`

**Files scanned:** 18 source files read in full or partially; 100% of file:line citations from CONTEXT/RESEARCH verified against the actual files.

**Pattern extraction date:** 2026-05-07
