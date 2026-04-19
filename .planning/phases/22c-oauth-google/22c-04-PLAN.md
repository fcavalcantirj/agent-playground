---
phase: 22c-oauth-google
plan: 04
type: execute
wave: 2
depends_on: [22c-02, 22c-03]
files_modified:
  - api_server/src/api_server/middleware/session.py
  - api_server/src/api_server/middleware/log_redact.py
  - api_server/tests/middleware/test_session_middleware.py
  - api_server/tests/middleware/test_last_seen_throttle.py
  - api_server/tests/middleware/test_log_redact_cookies.py
autonomous: true
requirements: [R3, D-22c-AUTH-01, D-22c-AUTH-02, D-22c-MIG-05]
must_haves:
  truths:
    - "SessionMiddleware reads ap_session cookie, SELECTs sessions row from PG (filters revoked_at IS NULL + expires_at > NOW()), sets scope['state']['user_id'] = <UUID>"
    - "No cookie OR invalid session → scope['state']['user_id'] = None (anonymous)"
    - "PG outage during session lookup → logs + fails open to anonymous (user_id = None)"
    - "sessions.last_seen_at is UPDATE'd at most once per 60s per session per worker (per-worker in-memory dict per D-22c-MIG-05)"
    - "log_redact.py docstring explicitly documents ap_session + ap_oauth_state cookie names as redacted-by-construction"
    - "A session with valid cookie + valid PG row results in request.state.user_id = the UUID matching sessions.user_id"
  artifacts:
    - path: "api_server/src/api_server/middleware/session.py"
      provides: "ASGI SessionMiddleware resolving request.state.user_id from ap_session cookie"
      contains: "class SessionMiddleware"
    - path: "api_server/tests/middleware/test_session_middleware.py"
      provides: "valid/invalid/expired/no-cookie integration tests"
    - path: "api_server/tests/middleware/test_last_seen_throttle.py"
      provides: "60s throttle test (2 rapid requests then 1 UPDATE)"
    - path: "api_server/tests/middleware/test_log_redact_cookies.py"
      provides: "cookie-value redaction test"
  key_links:
    - from: "middleware/session.py"
      to: "sessions table"
      via: "asyncpg SELECT WHERE id=$1 AND revoked_at IS NULL AND expires_at > NOW()"
      pattern: "SELECT user_id.*FROM sessions.*WHERE id"
    - from: "middleware/session.py"
      to: "scope state user_id"
      via: "scope.setdefault state then user_id assignment"
      pattern: "scope.setdefault"
---

<objective>
Ship the ASGI SessionMiddleware that converts the `ap_session` cookie into `request.state.user_id: UUID | None`. This is the auth boundary — every downstream route (protected or public) sees `request.state.user_id` AFTER this middleware runs. Also extend `log_redact.py` docstring to explicitly call out cookie-value redaction (zero code change; the existing `_LOG_HEADERS` allowlist already blocks raw `Cookie:` / `Set-Cookie:` lines). Three integration tests land with this plan.

Per D-22c-MIG-05 (as amended by CONTEXT — NOT Redis; Redis is not in the Python stack), the throttle uses a per-worker in-memory dict on `app.state.session_last_seen: dict[UUID, datetime]`. Under N workers, write amplification is Nx. Acceptable for v1.

The actual `app.add_middleware()` wiring into the stack happens in plan 22c-05 (alongside the auth routes it serves), per D-22c-AUTH-01. This plan only delivers the middleware class + tests.

Purpose: Close the auth-resolution seam. Every other plan's route handler eventually reads `request.state.user_id`; this plan provides the value.
Output: One new middleware module + one doc-only patch to log_redact + three new integration tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/22c-oauth-google/22c-SPEC.md
@.planning/phases/22c-oauth-google/22c-CONTEXT.md
@.planning/phases/22c-oauth-google/22c-RESEARCH.md
@.planning/phases/22c-oauth-google/22c-PATTERNS.md
@api_server/src/api_server/middleware/correlation_id.py
@api_server/src/api_server/middleware/idempotency.py
@api_server/src/api_server/middleware/rate_limit.py
@api_server/src/api_server/middleware/log_redact.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Write middleware/session.py + extend log_redact.py docstring</name>
  <files>api_server/src/api_server/middleware/session.py, api_server/src/api_server/middleware/log_redact.py</files>
  <read_first>
    - api_server/src/api_server/middleware/correlation_id.py (re-export shape)
    - api_server/src/api_server/middleware/idempotency.py (ASGI class body; app.state.db.acquire; header parsing; fail-open try/except)
    - api_server/src/api_server/middleware/rate_limit.py lines 126 to 136 (fail-open discipline pattern)
    - api_server/src/api_server/middleware/log_redact.py (current _LOG_HEADERS allowlist; preserve code; only extend docstring)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-AUTH-01 + §D-22c-AUTH-02 + §D-22c-MIG-05
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pattern 4 (lines 397-462) + §Pitfall 7
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §middleware/session.py (lines 156-215)
  </read_first>
  <action>
Create a new file `api_server/src/api_server/middleware/session.py` with the body below. Copy it verbatim (only formatting adjustments allowed):

```python
"""Session resolution middleware — Phase 22c.

Converts the opaque ``ap_session`` HTTP cookie into
``request.state.user_id : UUID | None`` for every request. Route handlers
downstream either call ``auth/deps.py::require_user`` (protected paths)
or read ``request.state.user_id`` directly.

Behavior matrix:
  * No ``ap_session`` cookie: request.state.user_id = None
  * Cookie present, session valid (not revoked, not expired): UUID
  * Cookie present, session invalid: None
  * Cookie present, PG outage: None + log.exception (fail-closed)

Additionally performs a throttled ``sessions.last_seen_at`` update per
D-22c-MIG-05. Throttle cache is a per-worker in-memory dict on
``app.state.session_last_seen: dict[UUID, datetime]``. Redis was
considered and deferred — see CONTEXT.md §D-22c-MIG-05 + RESEARCH §Pitfall 7.

Placement (per D-22c-AUTH-01):
    CorrelationId -> AccessLog -> StarletteSession -> OurSession -> RateLimit -> Idempotency
The actual ``app.add_middleware()`` wiring lives in plan 22c-05's main.py patch.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    import asyncpg

_log = logging.getLogger("api_server.session")

SESSION_COOKIE_NAME = "ap_session"
LAST_SEEN_THROTTLE = timedelta(seconds=60)
_LAST_SEEN_CACHE_SOFT_CAP = 10_000  # LRU eviction threshold per D-22c-MIG-05


class SessionMiddleware:
    """Resolves ``request.state.user_id`` from the ``ap_session`` cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_cookie = _extract_cookie(scope, SESSION_COOKIE_NAME)
        session_uuid = _coerce_uuid(raw_cookie) if raw_cookie else None
        user_id: UUID | None = None

        if session_uuid is not None:
            asgi_app = scope["app"]
            try:
                async with asgi_app.state.db.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT user_id, last_seen_at "
                        "FROM sessions "
                        "WHERE id = $1 "
                        "  AND revoked_at IS NULL "
                        "  AND expires_at > NOW()",
                        session_uuid,
                    )
                    if row is not None:
                        user_id = row["user_id"]
                        await _maybe_touch_last_seen(
                            asgi_app, conn,
                            session_id=session_uuid,
                            current_last_seen=row["last_seen_at"],
                        )
            except Exception:
                _log.exception(
                    "session resolution failed; treating as anonymous"
                )
                user_id = None

        scope.setdefault("state", {})["user_id"] = user_id
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_cookie(scope: Scope, name: str) -> str | None:
    """Minimal Cookie header parser — returns the first value matching ``name`` or None."""
    for h_name, h_val in scope.get("headers", []):
        if h_name == b"cookie":
            for piece in h_val.decode("latin-1", errors="ignore").split(";"):
                k, _, v = piece.strip().partition("=")
                if k == name and v:
                    return v
    return None


def _coerce_uuid(value: str) -> UUID | None:
    """Coerce cookie string to UUID; return None for malformed input."""
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


async def _maybe_touch_last_seen(
    asgi_app,
    conn: "asyncpg.Connection",
    *,
    session_id: UUID,
    current_last_seen: datetime,
) -> None:
    """Per-worker 60s throttle on sessions.last_seen_at UPDATE (D-22c-MIG-05)."""
    cache = _get_or_init_cache(asgi_app)
    now = datetime.now(timezone.utc)
    last_updated = cache.get(session_id)
    if last_updated is not None and (now - last_updated) < LAST_SEEN_THROTTLE:
        return  # Throttled — skip the UPDATE

    await conn.execute(
        "UPDATE sessions SET last_seen_at = NOW() WHERE id = $1",
        session_id,
    )
    cache[session_id] = now
    _maybe_evict(cache)


def _get_or_init_cache(asgi_app):
    """Lazy-init the per-worker last_seen dict on app.state."""
    cache = getattr(asgi_app.state, "session_last_seen", None)
    if cache is None:
        cache = {}
        asgi_app.state.session_last_seen = cache
    return cache


def _maybe_evict(cache) -> None:
    """Soft LRU: drop oldest 10% by timestamp when cache exceeds cap."""
    if len(cache) <= _LAST_SEEN_CACHE_SOFT_CAP:
        return
    drop_n = max(1, _LAST_SEEN_CACHE_SOFT_CAP // 10)
    victims = sorted(cache.items(), key=lambda kv: kv[1])[:drop_n]
    for sid, _ts in victims:
        cache.pop(sid, None)
```

Then extend `api_server/src/api_server/middleware/log_redact.py` — **docstring only**. Locate the module-level docstring at the top of the file. Append the following paragraph at the END of it (preserving all existing text above):

```
Cookie redaction (Phase 22c):
    The allowlist pattern already blocks raw Cookie / Set-Cookie headers
    because they are not in ``_LOG_HEADERS``. This prevents the following
    Phase 22c cookies from ever being logged:
    * ``ap_session`` — server-side session id (22c SessionMiddleware)
    * ``ap_oauth_state`` — authlib CSRF state cookie (Starlette SessionMiddleware)
    No positive change required for 22c; this note exists so future grep-auditors
    can verify the path without re-deriving the allowlist semantics.
```

**Do not alter `_LOG_HEADERS` itself.** Do not add any runtime logic to log_redact.py. The docstring extension is the only change.
  </action>
  <verify>
<automated>cd api_server && python -c "from api_server.middleware.session import SessionMiddleware, SESSION_COOKIE_NAME, LAST_SEEN_THROTTLE; from api_server.middleware.log_redact import _LOG_HEADERS; assert SESSION_COOKIE_NAME == 'ap_session'; assert LAST_SEEN_THROTTLE.total_seconds() == 60; assert 'cookie' not in _LOG_HEADERS; print('OK')" && grep -q "ap_session" api_server/src/api_server/middleware/log_redact.py</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/src/api_server/middleware/session.py` exists and `from api_server.middleware.session import SessionMiddleware` succeeds
    - `SESSION_COOKIE_NAME == "ap_session"` and `LAST_SEEN_THROTTLE.total_seconds() == 60`
    - `_LOG_HEADERS` in `log_redact.py` contains neither `"cookie"` nor `"set-cookie"` (runtime behavior unchanged)
    - `grep "ap_session" api_server/src/api_server/middleware/log_redact.py` returns a match (docstring updated)
  </acceptance_criteria>
  <done>SessionMiddleware class ships. Log redaction coverage for session cookies is documented.</done>
</task>

<task type="auto">
  <name>Task 2: Write the three middleware integration tests</name>
  <files>api_server/tests/middleware/test_session_middleware.py, api_server/tests/middleware/test_last_seen_throttle.py, api_server/tests/middleware/test_log_redact_cookies.py</files>
  <read_first>
    - api_server/tests/test_rate_limit.py (fixture harness for middleware-only tests)
    - api_server/tests/test_idempotency.py (ASGI middleware test style)
    - api_server/tests/test_log_redact.py (cookie/header redaction test shape)
    - api_server/tests/conftest.py (migrated_pg session fixture + existing async_client fixture)
    - .planning/phases/22c-oauth-google/22c-VALIDATION.md (test rows for R3 + last_seen + log redact)
  </read_first>
  <action>
Create three new test files.

**File 1: `api_server/tests/middleware/test_session_middleware.py`**

This test exercises the middleware against real PG + real app + real SessionMiddleware. We insert two kinds of sessions (valid + expired + revoked) into PG, then drive an ASGI request through the middleware and read `request.state.user_id`.

Since the middleware expects a downstream app to read `request.state.user_id`, mount a tiny echo route on a test-only FastAPI app to surface the user_id as a JSON response. Pattern to copy: `api_server/tests/test_idempotency.py` (fixture + AsyncClient + ASGIApp handoff).

Test cases:
1. `test_no_cookie_sets_user_id_none` — request without `ap_session` cookie gets user_id = None in a test echo route
2. `test_valid_cookie_resolves_user_id` — insert a user + session row; send `Cookie: ap_session=<uuid>`; assert echo route sees the user's UUID
3. `test_expired_session_returns_none` — insert session with `expires_at = NOW() - 1h`; cookie present → user_id = None
4. `test_revoked_session_returns_none` — insert session with `revoked_at = NOW()`; cookie present → user_id = None
5. `test_malformed_cookie_returns_none` — cookie value is not a UUID (e.g. "not-a-uuid") → user_id = None without PG query crash
6. `test_pg_outage_fails_closed` — monkeypatch `app.state.db.acquire` to raise; cookie present → user_id = None + log message emitted

Each test uses `@pytest.mark.api_integration` + `@pytest.mark.asyncio`. Keep the helper for inserting a session row DRY — one `_seed_session(conn, user_id, *, expires_in=timedelta(days=30), revoked=False)` helper at the top of the file.

**File 2: `api_server/tests/middleware/test_last_seen_throttle.py`**

Test the 60s per-worker throttle.

```python
import asyncio
import pytest

@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_two_requests_in_same_worker_trigger_one_update(<fixtures>):
    # Seed user + session; reset app.state.session_last_seen
    # Record sessions.last_seen_at BEFORE (= session creation time)
    # Issue 2 requests with the same cookie within <1s
    # Assert sessions.last_seen_at was UPDATED exactly once
    #   (first request triggers UPDATE, second hits cache, no UPDATE)
    # Count UPDATEs via a counter on asyncpg.Connection.execute OR by
    # querying sessions.last_seen_at before/after and asserting the
    # post-second-request value matches the post-first-request value
    ...

@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_request_after_60s_triggers_second_update(<fixtures>):
    # Issue request 1; UPDATE fires; cache entry set
    # Rewind cache entry to now - 61s
    # Issue request 2; UPDATE must fire again
    ...
```

For the monkeypatch-counter pattern, copy the shape from `api_server/tests/test_idempotency.py` lines 39-55.

**File 3: `api_server/tests/middleware/test_log_redact_cookies.py`**

Test that `Cookie: ap_session=<value>` and `Set-Cookie: ap_session=<value>; ...` headers never appear in log output.

```python
import logging
import pytest

@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_cookie_headers_not_in_access_log(<fixtures>, caplog):
    caplog.set_level(logging.INFO, logger="api_server.access")
    # Send a request with Cookie: ap_session=deadbeef-...
    # Assert no log record from api_server.access contains the UUID or
    # the literal substring "ap_session="
    ...

@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_state_cookie_not_in_logs(<fixtures>, caplog):
    # Same but for ap_oauth_state
    ...
```

For the test setup (FastAPI app + SessionMiddleware + real PG), build a pytest fixture that creates a minimal FastAPI app in-process with only SessionMiddleware + a `/ping` endpoint returning `request.state.user_id`. This avoids dragging in the full `main.py` dependency stack before plan 22c-05 wires it up.

Fixture sketch (put at the top of each test file or in `api_server/tests/middleware/conftest.py`):

```python
import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport
from api_server.middleware.session import SessionMiddleware

@pytest.fixture
async def session_test_app(migrated_pg):
    import asyncpg
    pool = await asyncpg.create_pool(migrated_pg.get_connection_url(driver="asyncpg"))
    app = FastAPI()
    app.state.db = pool
    app.add_middleware(SessionMiddleware)

    @app.get("/_test/whoami")
    async def whoami(request: Request):
        uid = getattr(request.state, "user_id", None)
        return {"user_id": str(uid) if uid else None}

    try:
        yield app, pool
    finally:
        await pool.close()


@pytest.fixture
async def session_client(session_test_app):
    app, _pool = session_test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
```

Commit the plan:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add api_server/src/api_server/middleware/session.py api_server/src/api_server/middleware/log_redact.py api_server/tests/middleware/
git commit -m "feat(22c-04): SessionMiddleware + cookie-redaction doc + 3 integration tests"
```
  </action>
  <verify>
<automated>cd api_server && pytest tests/middleware/ -x -v -m api_integration</automated>
  </verify>
  <acceptance_criteria>
    - `api_server/tests/middleware/test_session_middleware.py` exists with 6 test functions (no-cookie, valid, expired, revoked, malformed, pg-outage)
    - `api_server/tests/middleware/test_last_seen_throttle.py` exists with 2 test functions (throttle hit + throttle expiry)
    - `api_server/tests/middleware/test_log_redact_cookies.py` exists with 2 test functions (ap_session + ap_oauth_state redaction)
    - `pytest tests/middleware/ -m api_integration` exits 0 (all tests pass)
    - Commit on main: `feat(22c-04): SessionMiddleware + cookie-redaction doc + 3 integration tests`
  </acceptance_criteria>
  <done>SessionMiddleware integration-tested end-to-end against real PG. Last-seen throttle validated. Cookie redaction confirmed by construction. Ready for plan 22c-05 to wire it into the middleware stack.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Cookie -> SessionMiddleware | Client controls the cookie value. Middleware treats it as an opaque UUID; malformed UUIDs are coerced to None (no PG query). |
| SessionMiddleware -> PG | Lookup acquires a pool connection per request, runs one parameterized SELECT with the UUID. No SQL injection vector. |
| log_redact -> stdout | Allowlist blocks Cookie / Set-Cookie lines from being formatted into log records. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-08 | Spoofing | Forged ap_session cookie | mitigate | Cookie is a random UUID (122 bits). Attacker must guess a valid sessions.id that is not revoked and not expired. Effective entropy is the birthday-bound of 122 bits over active-session set. |
| T-22c-09 | Tampering | Malformed cookie value (not a UUID) | mitigate | `_coerce_uuid` returns None on ValueError; middleware treats as anonymous and does not issue a PG query. No injection surface. |
| T-22c-10 | Information disclosure | ap_session value in logs | mitigate | `_LOG_HEADERS` allowlist does not include `cookie` / `set-cookie` — headers never reach log formatters. Explicitly documented in docstring. Test case asserts invariant. |
| T-22c-11 | DoS | cache unbounded growth | mitigate | `_maybe_evict` trims oldest 10% at soft cap 10k entries. Session expiry (30d default) caps steady-state at active-session count anyway. |
| T-22c-12 | Repudiation | last_seen_at throttled | accept | 60s coarse-grained last_seen_at means forensic "last activity" resolution is +/- 60s per worker. Acceptable per D-22c-MIG-05 trade-off. |
</threat_model>

<verification>
```bash
cd api_server && pytest tests/middleware/ -m api_integration
```
All test functions must pass. No new code in `log_redact.py` beyond the docstring.
</verification>

<success_criteria>
- SessionMiddleware class lands; resolves `request.state.user_id` per behavior matrix
- 6 session-resolution tests pass (no-cookie, valid, expired, revoked, malformed, pg-outage)
- 2 last-seen throttle tests pass
- 2 cookie-redaction tests pass
- `log_redact.py` docstring extended; code unchanged
- Commit on main: `feat(22c-04): SessionMiddleware + cookie-redaction doc + 3 integration tests`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-04-SUMMARY.md` with:
- Middleware behavior matrix (6 cases) confirmed
- Throttle validated: 2 rapid requests in one worker triggers exactly 1 UPDATE
- Cookie-redaction allowlist unchanged; documentation added
- Plan 22c-05 prerequisite satisfied: SessionMiddleware class importable at `api_server.middleware.session:SessionMiddleware`
</output>
