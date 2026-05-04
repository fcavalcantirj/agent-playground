# Phase 26: Logout-everywhere + session-invalidation — Research

**Researched:** 2026-05-04
**Domain:** FastAPI session-revocation, Postgres concurrent UPDATE, asyncpg patterns, Flutter/dio + Next.js error-code consumption
**Confidence:** HIGH (substrate is fixed and exhaustively cited in 22c-CONTEXT; this research is implementation-shape detail, not library selection)

## Summary

Phase 26 is a small additive phase on top of a mature Phase 22c substrate. The substrate already does 90% of the work: `SessionMiddleware` per-request `SELECT ... WHERE id=$1 AND revoked_at IS NULL AND expires_at > NOW()` already excludes revoked rows ([api_server/src/api_server/middleware/session.py:60-68](../../../api_server/src/api_server/middleware/session.py)). Adding logout-everywhere is therefore (1) a single bulk `UPDATE ... SET revoked_at = NOW(), revoked_reason = 'logout_all' WHERE user_id = $u AND revoked_at IS NULL`, (2) one audit row, (3) one new error code, and (4) error-code-aware UX on web + mobile. The "propagation" mechanism is the existing per-request DB SELECT — no pub/sub needed at single-replica scale (D-01 locked).

Three real engineering risks emerged from this research, all addressable with prescriptive patterns documented below: (a) mistaking `conn.execute()` return value for a row count (it's a status string), (b) writing the audit row in a separate connection from the UPDATE, opening a partial-state window, and (c) the existing mobile `AuthInterceptor` already strips `error.param == "Authorization"` from the 401 path — the new `error.code == "session_revoked"` signal must be read alongside `param`, not instead of it.

**Primary recommendation:** Mirror `routes/auth.py::logout` exactly. Add `logout_all` next to it; reuse `_clear_session_cookie`, `_read_session_cookie_uuid`, `require_user`, `make_error_envelope`. Single transaction: UPDATE with `RETURNING id` collected to a list, INSERT into `auth_events` using the list length as `device_count_revoked`. Test with the existing `authenticated_cookie` + `second_authenticated_cookie` fixtures plus a new helper that mints N sessions for one user_id.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `POST /v1/auth/logout-all` endpoint | API / Backend | — | Stateful auth gate; returns count; idempotent. Caller's UA/IP captured server-side (D-02). |
| Session row revocation | Database | API / Backend | UPDATE statement with WHERE-clause filter; concurrency handled by row-level locks Postgres acquires automatically. |
| Audit row append | Database | API / Backend | Same transaction as the revoke (in-tx — see Pitfall 2). |
| Revoked-session detection | API / Backend (SessionMiddleware) | — | Per-request `SELECT ... WHERE revoked_at IS NULL` already excludes revoked rows. No new branch needed in middleware for the basic flow; the 401 carries `code='session_revoked'` only when the cookie's row exists AND `revoked_at IS NOT NULL` (the "lookup-then-classify" enhancement). |
| 401 → "session ended elsewhere" banner | Browser / Client (web), Mobile UI | — | Pure UX layer mapping `error.code`. Backend is source of truth; client is dumb. |
| Banner state across navigation | Mobile (Riverpod `showSignedOutBannerProvider`), Web (`/login?reason=session_revoked` query param) | — | Existing pattern from Phase 22c-FE-03 (`?error=oauth_failed`). Mobile already has `showSignedOutBannerProvider` ([mobile/lib/features/login/login_providers.dart:17](../../../mobile/lib/features/login/login_providers.dart)). |
| Settings → Security row UI | Browser / Client (web), Mobile UI | — | Web has dashboard/settings page with a "Security" subsection placeholder ([frontend/app/dashboard/settings/page.tsx:111-137](../../../frontend/app/dashboard/settings/page.tsx)) — replace its 2FA/password-change scaffold with the real button. |

## Standard Stack

> **Substrate is fixed by Phase 22c — research only names existing utilities to reuse.**

### Core (existing — reuse, do NOT add new deps)

| Library/Module | Purpose | Import / Path | Why Reused |
|----------------|---------|---------------|------------|
| `fastapi` (existing) | HTTP framework | `from fastapi import APIRouter, Request` | Same router as `routes/auth.py`. New endpoint is `@router.post("/auth/logout-all")` colocated. |
| `asyncpg` (existing) | Postgres driver | `request.app.state.db` (the pool) | All query patterns already established (`fetchrow`, `execute`, `fetch`, `fetchval`). |
| `alembic` (existing) | Migrations | `api_server/alembic/versions/009_logout_all_audit.py` | Migration 009 = next slot after `008_idempotency_keys_relax_run_fk` ([api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py](../../../api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py)). |
| `pydantic` (existing) | Response models | `from pydantic import BaseModel` | Mirror `MobileSessionResponse` shape. |
| `auth/deps.py::require_user` | Auth gate | `from ..auth.deps import require_user` | Returns `JSONResponse | UUID`. The endpoint MUST early-return if the result is a JSONResponse. Pattern is cited verbatim across the codebase. |
| `models/errors.py::ErrorCode` + `make_error_envelope` | Stripe-shape envelope | `from ..models.errors import ErrorCode, make_error_envelope` | Add `SESSION_REVOKED = "SESSION_REVOKED"` to the class; add `_CODE_TO_TYPE` entry mapping to `"unauthorized"`. |
| `routes/auth.py::_clear_session_cookie` | Set-Cookie clear helper | local in same file | Logout-all clears the caller's cookie too (D-07). |
| `routes/auth.py::_read_session_cookie_uuid` | Cookie → UUID coercion | local in same file | Used to identify (and audit) the caller's specific session even though all sessions for the user are revoked. |

### Mobile (existing — extend, do NOT introduce new packages)

| Library | Version | Purpose | Why Reused |
|---------|---------|---------|------------|
| `dio` (existing) | already in pubspec | HTTP client | Existing `AuthInterceptor` handles 401 ([mobile/lib/core/api/auth_interceptor.dart:42-77](../../../mobile/lib/core/api/auth_interceptor.dart)) — extend the `_isSessionAuthFailure` branch to read `error.code` as a 2nd signal alongside `error.param`. |
| `flutter_riverpod` (existing) | 3.x | State | Existing `showSignedOutBannerProvider` ([mobile/lib/features/login/login_providers.dart:17](../../../mobile/lib/features/login/login_providers.dart)) is a `StateProvider<bool>`. Phase 26 changes it to `StateProvider<String?>` carrying the reason ('signed_out' \| 'session_revoked' \| null) OR adds a sibling provider — see Architecture Patterns §2. |
| `flutter_secure_storage` (existing) | — | Session id storage | `SecureStorage.clearSessionId()` already runs in the interceptor's 401 path. |

### Web (existing — extend)

| Library | Version | Purpose | Why Reused |
|---------|---------|---------|------------|
| `next` (existing) | 16.2 | Framework, App Router | `frontend/proxy.ts` ([frontend/proxy.ts](../../../frontend/proxy.ts)) gates `/dashboard/:path*` on cookie *presence* only. The 401 detection itself happens in the data-fetch layer (`useUser` hook in `frontend/hooks/use-user.ts`). The reason-query-param is set when a 401 is observed inside a hook/handler, not in proxy.ts. |
| `sonner` (existing) | toast library | Login banner | `frontend/app/login/page.tsx:18-23` already maps `?error=oauth_failed` etc. to `toast.error(...)`. Add a 4th branch `if (err === 'session_revoked')` mapped to a non-error info toast (or a persistent banner — Architecture Patterns §3). |
| `lucide-react` (existing) | icons | Icon for the Security subsection | `Shield` is already imported in `frontend/app/dashboard/settings/page.tsx:7`. |

### Test deps (existing — reuse all)

| Tool | Purpose | Source |
|------|---------|--------|
| `pytest_asyncio` + `httpx.AsyncClient` | API integration tests | `api_server/tests/auth/test_logout.py` — direct copy template |
| `authenticated_cookie` + `second_authenticated_cookie` fixtures | Multi-user scenarios | `api_server/tests/conftest.py:511-588` |
| `testcontainers` Postgres 17 | Real DB | `tests/conftest.py:50` |
| New helper: `multi_session_cookie(user_id, n)` | Mint N sessions for one user | New fixture in `tests/auth/conftest.py` (sibling of `authenticated_mobile_session`) |

### Alternatives Considered (and rejected for this phase)

| Instead of | Could Use | Why Rejected |
|------------|-----------|--------------|
| Per-request `SELECT` for revocation | Redis pub/sub fan-out | D-01 locked: skip pub/sub at single-replica scale. Re-evaluate when multi-replica. |
| In-tx audit insert | Best-effort audit insert outside the UPDATE tx | D-02 + Pitfall 2: in-tx is correct. Audit row missing while session revoked is a worse failure mode than "audit row written but UPDATE rolled back" (latter cannot happen — single statement) for this table. |
| Set `revoked_at` on `request.state.user_id` only | DELETE row | DELETE loses forensic data; `revoked_at` keeps a ghost row for "when did this device last get kicked" admin queries. Existing pattern from migration 005. |
| Logout-all leaves caller's cookie alive | Revoke caller too | D-07 locked: caller is included. Defends compromised-device case. |
| New `revoked_reason` table (1:N) | Single column on sessions | D-10 locked: single column. Lean. Add a JSONB column later if a query demands sub-classification. |

**Installation:** None. No new dependencies. Migration 009 is additive DDL only.

**Version verification:** Not applicable — no new packages.

## Architecture Patterns

### System Architecture Diagram

```
┌────────────────────────┐         ┌────────────────────────┐
│  Web (Settings page)   │         │   Mobile (Profile tab) │
│  Click "Log out        │         │   Tap "Log out         │
│  everywhere"           │         │   everywhere"          │
└────────────┬───────────┘         └─────────────┬──────────┘
             │ ConfirmDialog                     │ ConfirmDialog
             │ (destructive=true)                │ (destructive=true)
             ▼                                   ▼
        POST /v1/auth/logout-all  (Cookie: ap_session=<uuid>)
                            │
                            ▼
       ┌───────────────────────────────────────────────────┐
       │  api_server/routes/auth.py::logout_all            │
       │                                                   │
       │  1. require_user(request) → user_id               │
       │  2. async with pool.acquire() as conn:            │
       │       async with conn.transaction():              │
       │         rows = await conn.fetch("""               │
       │            UPDATE sessions                        │
       │            SET revoked_at = NOW(),                │
       │                revoked_reason = 'logout_all'      │
       │            WHERE user_id = $1                     │
       │              AND revoked_at IS NULL               │
       │            RETURNING id                           │
       │         """, user_id)                             │
       │         await conn.execute("""                    │
       │            INSERT INTO auth_events                │
       │              (user_id, kind, ip, user_agent,      │
       │               device_count_revoked)               │
       │            VALUES ($1, $2, $3, $4, $5)            │
       │         """, user_id, 'logout_all', ip, ua,       │
       │            len(rows))                             │
       │  3. resp = JSONResponse({"revoked": len(rows)})   │
       │     _clear_session_cookie(resp, settings)         │
       │     return resp                                   │
       └───────────────────────────────────────────────────┘
                            │
                            ▼
       ┌───────────────────────────────────────────────────┐
       │  Other devices' next request                      │
       │                                                   │
       │  SessionMiddleware reads cookie → SELECT row by   │
       │  id WHERE revoked_at IS NULL → 0 rows → user_id   │
       │  is None → require_user returns 401              │
       │                                                   │
       │  Enhancement: when SELECT-by-id returns 0 rows    │
       │  AND a re-SELECT-by-id WITHOUT the                │
       │  revoked_at filter finds revoked_at IS NOT NULL,  │
       │  the 401 carries code='SESSION_REVOKED' instead   │
       │  of code='UNAUTHORIZED'.                          │
       └────────────┬──────────────────────────────────────┘
                    │
                    ▼
       ┌───────────────────────────────────────────────────┐
       │  Mobile: AuthInterceptor sees 401 +               │
       │   error.code == 'SESSION_REVOKED' →               │
       │   storage.clearSessionId() →                      │
       │   showSignedOutBannerProvider = 'session_revoked' │
       │   AuthEventBus.emit() → router → /login           │
       │   Login screen shows session-ended banner         │
       │                                                   │
       │  Web: useUser() sees 401 + code='SESSION_REVOKED' │
       │   → router.push('/login?reason=session_revoked')  │
       │   /login mounts → reads ?reason= → renders banner │
       └───────────────────────────────────────────────────┘
```

### Recommended Project Structure

```
api_server/
├── src/api_server/
│   ├── alembic/versions/
│   │   └── 009_logout_all_audit.py        # NEW — auth_events + sessions.revoked_reason
│   ├── routes/
│   │   └── auth.py                        # extend: add logout_all handler
│   ├── middleware/
│   │   └── session.py                     # extend: 401-classifier when row missing-but-revoked
│   ├── models/
│   │   └── errors.py                      # add ErrorCode.SESSION_REVOKED
│   └── services/
│       └── auth_events_store.py           # NEW (small) — record_auth_event() helper
├── tests/
│   └── auth/
│       ├── conftest.py                    # extend: multi_session_cookie fixture
│       ├── test_logout.py                 # extend: revoked_reason='logout' assertion
│       └── test_logout_all.py             # NEW — 3-device + idempotency + race tests

frontend/
├── app/
│   ├── dashboard/settings/page.tsx        # extend: real "Log out everywhere" button
│   └── login/page.tsx                     # extend: ?reason=session_revoked → banner
└── lib/
    └── api.ts                             # already supports POST; nothing to change

mobile/
└── lib/
    ├── core/
    │   ├── api/auth_interceptor.dart      # extend: read error.code; carry reason on emit
    │   └── auth/
    │       └── auth_event_bus.dart        # extend: AuthRequired carries optional reason
    └── features/
        ├── login/
        │   ├── login_providers.dart       # extend: showSignedOutBannerProvider → reason field
        │   └── login_screen.dart          # extend: 2 banner copies (signed-out vs revoked)
        └── dashboard/
            └── dashboard_screen.dart      # extend: Profile/Security row with logout-all
```

### Pattern 1: In-Transaction UPDATE-then-INSERT for Revoke + Audit

**What:** Wrap the `UPDATE sessions ... RETURNING id` and the `INSERT INTO auth_events` in a single asyncpg transaction. The audit row's `device_count_revoked` is `len(returned_ids)`. If anything fails, both rows are rolled back consistently.

**When to use:** Always for this phase. The audit row is load-bearing for incident response — losing it because of a partial failure between two separate connections (no transaction) is a worse failure than a 500 on the endpoint.

**Why this is correct:**
- Postgres acquires per-row exclusive locks during UPDATE; concurrent `logout-all` calls for the same user_id serialize cleanly. Lost-update is impossible because each UPDATE-statement's `WHERE revoked_at IS NULL` re-reads the row under its own lock ([Postgres explicit locking docs](https://www.postgresql.org/docs/current/explicit-locking.html)).
- A second concurrent call's UPDATE sees 0 matching rows (all already revoked by call 1) → `len(rows) == 0` → idempotent: a second audit row is still inserted but with `device_count_revoked=0`. This is desirable — incident response sees "two logout-all attempts, second was a no-op."

**Example:**
```python
# api_server/src/api_server/routes/auth.py — NEW handler

@router.post("/auth/logout-all")
async def logout_all(request: Request):
    """Revoke every session row for the calling user_id.

    Idempotent — concurrent calls produce the same end state. The caller's
    own session is included in the revocation set (D-07 — defends the
    compromised-device threat model).

    Returns 200 with body ``{"revoked": <count>}``. Cookie is cleared
    via ``Set-Cookie: ap_session=; Max-Age=0`` so the caller's browser
    forgets the now-revoked cookie immediately (next page load goes
    through /login).
    """
    settings = request.app.state.settings
    result = require_user(request)
    if isinstance(result, JSONResponse):
        return result
    user_id: UUID = result

    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None

    pool = request.app.state.db
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                UPDATE sessions
                SET revoked_at = NOW(),
                    revoked_reason = 'logout_all'
                WHERE user_id = $1
                  AND revoked_at IS NULL
                RETURNING id
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO auth_events
                  (user_id, kind, ip, user_agent, device_count_revoked)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user_id,
                "logout_all",
                ip,
                user_agent,
                len(rows),
            )

    resp = JSONResponse(status_code=200, content={"revoked": len(rows)})
    _clear_session_cookie(resp, settings)
    return resp
```

[VERIFIED: codebase] Mirrors `routes/auth.py::logout` shape. Imports already present in the file.

### Pattern 2: SessionMiddleware Lookup-then-Classify (the surgical change)

**What:** When the existing `SELECT ... WHERE id=$1 AND revoked_at IS NULL AND expires_at > NOW()` returns no rows, perform a second cheap PK lookup `SELECT revoked_at, revoked_reason FROM sessions WHERE id=$1`. If that returns a row with `revoked_at IS NOT NULL`, stash the reason on `request.state.session_revoked_reason = 'logout_all' | 'logout' | 'admin' | 'expired'`. `require_user` reads that flag and emits 401 with `code='SESSION_REVOKED'` instead of `code='UNAUTHORIZED'`.

**When to use:** Only on the cookie-present-but-no-active-row branch (the existing miss path). Cookie-absent path stays exactly as-is.

**Why TWO queries instead of one:**
- The hot path (cookie present, session valid) MUST stay a single PK lookup. Combining the filters with `OR` in the existing query would force every request to read columns the hot path doesn't need.
- The cold path (revoked / expired / never-existed) runs at most once per request and is dominated by the network round-trip cost; the marginal second PK SELECT is a few microseconds.
- Alternative — a single SELECT without the `WHERE revoked_at IS NULL` filter that branches in Python — is also viable. Pick whichever feels cleaner; both ship the same observable behavior.

**Example (alternate, single-query branch in Python):**
```python
# api_server/src/api_server/middleware/session.py — extension to existing SELECT

row = await conn.fetchrow(
    "SELECT user_id, last_seen_at, revoked_at, revoked_reason, expires_at "
    "FROM sessions WHERE id = $1",
    session_uuid,
)
if row is None:
    user_id = None
elif row["revoked_at"] is not None:
    user_id = None
    scope.setdefault("state", {})["session_revoked_reason"] = row["revoked_reason"]
elif row["expires_at"] <= datetime.now(timezone.utc):
    user_id = None
    scope.setdefault("state", {})["session_revoked_reason"] = "expired"
else:
    user_id = row["user_id"]
    await _maybe_touch_last_seen(...)
```

[VERIFIED: codebase] The existing query at [api_server/src/api_server/middleware/session.py:60-68](../../../api_server/src/api_server/middleware/session.py) is one PK SELECT; expanding the column list to include `revoked_at`, `revoked_reason`, `expires_at` is a free read at the same row.

### Pattern 3: Mobile — extend AuthRequired with a reason

**What:** `AuthRequired` ([mobile/lib/core/auth/auth_event_bus.dart:12](../../../mobile/lib/core/auth/auth_event_bus.dart)) becomes `AuthRequired({this.reason})` carrying an optional `String?` ('session_revoked' or null). `AuthInterceptor` reads `error.code` and emits `AuthRequired(reason: 'session_revoked')` when matched.

**When to use:** Only on the 401 path inside `AuthInterceptor.onError`. Other 401s (cookie-absent, BYOK Bearer failure already filtered out) emit `AuthRequired()` with `reason: null`.

**Example:**
```dart
// mobile/lib/core/auth/auth_event_bus.dart
class AuthRequired {
  const AuthRequired({this.reason});
  final String? reason; // 'session_revoked' or null
}

// mobile/lib/core/api/auth_interceptor.dart — onError extension
String? reason;
final data = err.response?.data;
if (data is Map<String, dynamic>) {
  final error = data['error'];
  if (error is Map<String, dynamic> && error['code'] == 'SESSION_REVOKED') {
    reason = 'session_revoked';
  }
}
await _storage.clearSessionId();
_authEvents.emit(AuthRequired(reason: reason)); // emit() arg-shape change
```

The Phase 25 listener (router) reads `event.reason`; non-null reasons set `showSignedOutBannerProvider.notifier.state = reason`. The login screen ([mobile/lib/features/login/login_screen.dart:50-60](../../../mobile/lib/features/login/login_screen.dart)) already gates on `showSignedOutBannerProvider`; phase-26 promotes its type from `bool` to `String?` and renders different copy per value.

[VERIFIED: codebase] `emit()` currently takes no args ([mobile/lib/core/auth/auth_event_bus.dart:24](../../../mobile/lib/core/auth/auth_event_bus.dart)); promoting it requires updating all call sites — only one currently exists in `auth_interceptor.dart:48`.

### Pattern 4: Web — `?reason=session_revoked` query-param mirroring `?error=` pattern

**What:** When `useUser()` hook ([frontend/hooks/use-user.ts:32](../../../frontend/hooks/use-user.ts)) sees a 401 from `/api/v1/users/me`, it currently calls `router.push("/login")`. Phase 26 first parses the response body for `error.code === 'SESSION_REVOKED'` and pushes `/login?reason=session_revoked`.

The login page ([frontend/app/login/page.tsx:18-23](../../../frontend/app/login/page.tsx)) already reads `?error=` and surfaces toasts; add a parallel `?reason=` reader that renders a persistent banner (not a toast — banner is dismiss-only, toast auto-disappears in 5s and the user might miss the message arriving from a different device).

**Example:**
```typescript
// frontend/hooks/use-user.ts — extension
.catch(async (err) => {
  if (cancelled) return;
  if (err instanceof ApiError && err.status === 401) {
    let reason = "";
    try {
      const body = JSON.parse(err.body);
      if (body?.error?.code === "SESSION_REVOKED") reason = "session_revoked";
    } catch {} // body might not be JSON; fall through
    router.push(reason ? `/login?reason=${reason}` : "/login");
    return;
  }
  console.warn("useUser: failed to fetch /users/me", err);
});

// frontend/app/login/page.tsx — extension to existing useEffect
const reason = new URLSearchParams(window.location.search).get("reason");
const [revokedBanner, setRevokedBanner] = useState(reason === "session_revoked");
// ... render <Banner /> conditionally above the Welcome card
```

[VERIFIED: codebase] `ApiError.body` is the raw response text ([frontend/lib/api.ts:13-18](../../../frontend/lib/api.ts)); JSON.parse + optional-chain access is the existing convention pattern (no body-mapping helper).

### Pattern 5: Solvr-Aesthetic Confirm Dialog Copy

**What:** The mobile `ConfirmDialog` widget ([mobile/lib/shared/confirm_dialog.dart:14-82](../../../mobile/lib/shared/confirm_dialog.dart)) accepts `title`, `body`, `confirmLabel`, `cancelLabel`, `destructive=true`. Solvr aesthetic ([feedback_solvr_matrix_aesthetic.md](../../../memory/feedback_solvr_matrix_aesthetic.md)) is terminal/ASCII feel — JetBrains Mono, no emoji, sentence case. Existing dialog uses `RoundedRectangleBorder` with radius 0 (square corners — see line 30).

**Recommended copy (for the planner and discuss-phase to confirm):**

| Field | Web | Mobile |
|-------|-----|--------|
| Title | `Log out everywhere?` | `Log out everywhere?` |
| Body | `This signs you out on every device, including this one. You'll need to sign in again on each.` | `This signs you out on every device, including this one. You'll need to sign in again on each.` |
| Cancel | `Cancel` | `Cancel` |
| Confirm | `Log out everywhere` | `Log out everywhere` |
| Banner copy on next login (web + mobile) | `Your session was ended on another device. Sign in to continue.` | `Your session was ended on another device. Sign in to continue.` |
| Settings subsection title | `Security` | `Security` |
| Subsection blurb | `Sign out of all your devices. Useful if you've lost a device or suspect your account was accessed without permission.` | (same) |

[ASSUMED] copy choices — D-09's Claude's-discretion area; recommended phrasing is plain English, avoids accusatory ("someone logged in as you") language per CONTEXT §specifics, and ships in sentence case to match the existing Solvr theme.

### Anti-Patterns to Avoid

- **DO NOT use `await conn.execute("UPDATE ... WHERE ...")` and rely on the return value as a row count.** asyncpg's `execute()` returns the libpq command-status string (`'UPDATE 3'`, `'DELETE 1'`) — a `str`, not an `int`. Parsing the string is fragile across libpq versions. Use `await conn.fetch("UPDATE ... RETURNING id")` and `len(rows)` ([asyncpg issue #311](https://github.com/MagicStack/asyncpg/issues/311) discusses this exact gap).
- **DO NOT acquire two separate connections** for the UPDATE and the audit INSERT. They MUST share a transaction so a partial failure rolls back coherently. Single `async with pool.acquire() as conn: async with conn.transaction():` block.
- **DO NOT call the new endpoint `POST /v1/auth/logout/all`** (slash-separated) — sibling resources should be flat and the URL `/auth/logout-all` is a cleaner verb. The mobile interceptor + web `apiPost` don't care about path shape, but consistency with the existing `routes/auth.py` (single-segment after `/auth/`) makes routing review obvious.
- **DO NOT add `force=true` query param semantics.** The endpoint is destructive by design (D-07); a "soft" mode would mean "logout the others but not me", which is explicitly out of scope.
- **DO NOT write an `auth_events` row from the existing single-device `/v1/auth/logout`** (D-11). The table stays signal-rich. If `/v1/auth/logout` flips to also write, the H2 incident-response query "show me all logout-all events for this user in the last 30 days" gets polluted by routine sign-outs.
- **DO NOT revoke from inside `SessionMiddleware`.** The middleware is a read path; revocation lives in the route handler. Moving revocation into middleware races with the request that triggered it (CONTEXT.md §Anti-patterns confirms this).
- **DO NOT close in-flight SSE streams synchronously on revoke** (D-08 locked). Revocation is pure DB state; existing SSE consumers stay open until the next reconnect or network close. Documented info-leak window is acceptable.
- **DO NOT add a "logout this device only" alternative endpoint.** `POST /v1/auth/logout` is exactly that. Two endpoints, two semantics, not three (CONTEXT.md §code_context).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stripe-shape error envelope | A bespoke 401 dict | `make_error_envelope("SESSION_REVOKED", message, param="ap_session")` from `models/errors.py` | Already populates `request_id` from the correlation-id contextvar; key ordering matches every other 4xx in the codebase. |
| Cookie clearing | Hand-rolled `Set-Cookie: ap_session=` | `_clear_session_cookie(resp, settings)` from `routes/auth.py:111-121` | Already env-gated for `Secure` flag (dev http vs prod https). |
| Cookie reading | `request.cookies.get("ap_session")` then `UUID(...)` | `_read_session_cookie_uuid(request)` from `routes/auth.py:584-592` | Returns None on malformed UUID — defensive against attacker-supplied junk. |
| Auth gate | Inline `if request.state.user_id is None: return JSONResponse(...)` | `require_user(request)` from `auth/deps.py:37-72` | Returns the canonical 401 envelope. Inline reproductions drift. |
| Multi-session test fixtures | New httpx fixture from scratch | Compose `authenticated_cookie` + a helper that `INSERT`s extra session rows for the same user_id | Mirrors the `second_authenticated_cookie` pattern at `tests/conftest.py:556-587`. |
| Concurrent-call safety | `pg_advisory_xact_lock` (as `services/rate_limit.py:64` does) | Nothing — Postgres' implicit row-level lock is sufficient | The advisory lock in `rate_limit.py` exists to serialize a *read-modify-write* (read count, write count+1) across rows that DON'T exist yet. Phase 26's UPDATE is a single atomic statement that re-reads `revoked_at IS NULL` under the row's exclusive lock — no advisory lock needed. |
| Per-session JSONB detail in audit row | Wide JSONB column on `auth_events` | Nothing (D-03) | "Add columns later when specific queries demand them." |
| Idempotency-key middleware integration | Adding `Idempotency-Key` requirement to logout-all | Nothing | The endpoint is naturally idempotent (re-running gives same end state). The phase 22c idempotency middleware exists for non-idempotent state changes like creating runs. |

**Key insight:** Phase 22c built the substrate exactly for this kind of additive feature. The temptation to reach for "best practice" generic patterns (advisory locks, idempotency keys, separate audit-write transaction) is exactly the over-engineering CONTEXT.md guards against. The right move is pure mirroring of `routes/auth.py::logout`.

## Common Pitfalls

### Pitfall 1: Treating `conn.execute()` return as a row count

**What goes wrong:** Developer writes `count = await conn.execute("UPDATE ... WHERE ...")` expecting an int. The variable holds the string `"UPDATE 3"`. `len(count)` (used in audit insert) returns 8 instead of 3. `device_count_revoked` becomes garbage.

**Why it happens:** SQL drivers in many languages return integer rowcounts; asyncpg returns the raw libpq command-status string for parity with the wire protocol.

**How to avoid:** Use `await conn.fetch("... RETURNING id")` for any UPDATE that needs a count. The list returned has correct `len()`. Pattern is already established in `services/rate_limit.py:75-93` (RETURNING + indexed access on the row dict).

**Warning signs:** `int(rows.split()[1])`-style parsing in code review — mark for change. Tests where `device_count_revoked` is asserted == an unrelated number.

### Pitfall 2: Audit row outside the revoke transaction

**What goes wrong:** Developer writes `async with pool.acquire() as conn: ... UPDATE ...` then in a fresh acquire `async with pool.acquire() as conn2: ... INSERT auth_events ...`. The second connection's INSERT can fail (pool exhaustion, network blip, statement timeout) AFTER the UPDATE succeeded — sessions revoked but no audit row. Silent forensic gap.

**Why it happens:** Reflexive copy-paste from the existing single-action `routes/auth.py::logout` shape. The first action is a DELETE; phase 26 needs TWO actions and the two-acquire pattern doesn't transfer.

**How to avoid:** Single `pool.acquire()` then `async with conn.transaction():` wrapping both statements. Documented in Pattern 1.

**Warning signs:** Two separate `async with pool.acquire()` blocks in the handler. Two separate `try/except` blocks around the DB calls.

### Pitfall 3: SSE stream info-leak window misunderstood as a bug

**What goes wrong:** Tester logs in on device A + B, starts an in-app chat SSE on device B, calls logout-all from device A, and observes that device B's SSE stream keeps emitting events for ~30 seconds until the next reconnect / heartbeat. Reports a security bug.

**Why it happens:** D-08 explicitly accepted this window. Re-validating session per heartbeat is overkill at current scale; the leaked events are the user's own data.

**How to avoid:** Document in the PR + commit message that this is a known-and-accepted gap (CONTEXT.md §D-08). Add a test asserting the SSE stream stays open after revoke (not closes) — captures the deliberate-decision-not-bug status. Re-validate when threat model bar rises (e.g., shared agents).

**Warning signs:** PR review comment "shouldn't this close the SSE?" — point reviewer to D-08.

### Pitfall 4: SessionMiddleware's `last_seen_at` UPDATE on a revoked row

**What goes wrong:** Tester revokes user_id=X. A racing request from device B (cookie still in flight) arrives between the revoke commit and the response Set-Cookie. Existing middleware code at [api_server/src/api_server/middleware/session.py:69-75](../../../api_server/src/api_server/middleware/session.py) — which sees the row missing-or-revoked — does NOT call `_maybe_touch_last_seen` because that's only called when `row is not None`. So this pitfall ACTUALLY DOES NOT EXIST in the current code. Documented here only because reviewers tend to ask: "what about last_seen_at on revoked rows?"

**Why it happens (in a hypothetical buggy refactor):** A future refactor that moves the throttle update before the revoked-at filter would touch `last_seen_at` on a row that's already revoked, producing a misleading "this revoked session was active 200ms ago" forensic signal.

**How to avoid:** Keep the `_maybe_touch_last_seen` call gated on the existing query's result (which already excludes revoked rows). If Pattern 2 above changes the SELECT to read `revoked_at` explicitly, ensure the touch-call only fires when `revoked_at IS NULL` (Python conditional, not SQL).

**Warning signs:** A linter / type-check error if `row` is no longer `None`-or-row but always-row in the new shape. Make sure the touch-call's guard updates accordingly.

### Pitfall 5: Banner shown on every login, not just session-revoked logins

**What goes wrong:** `showSignedOutBannerProvider` (mobile) and `?reason=session_revoked` (web) get set but never cleared. User signs in again successfully, signs out (single-device), and on the next login still sees the "Your session was ended on another device" banner. Wrong cause attributed.

**Why it happens:** State-cleanup discipline lapse. The web `?reason=` param survives re-load because URLs are sticky. The mobile provider survives across nav unless explicitly reset.

**How to avoid:**
- Mobile: `dashboard_screen._confirmSignOut` ([mobile/lib/features/dashboard/dashboard_screen.dart:384](../../../mobile/lib/features/dashboard/dashboard_screen.dart)) already does `ref.read(showSignedOutBannerProvider.notifier).state = false;` after sign-out. Mirror this in the new `_confirmLogoutAll` handler. The `loginSuccessProvider` setter (login_screen.dart:113) also clears it.
- Web: `useUser` hook reads & clears the `?reason` query param after the banner mounts (URL.replaceState).

**Warning signs:** A test that signs in, signs out, signs in again, and observes the banner still visible.

### Pitfall 6: Mobile interceptor mis-classifying the session_revoked 401 as a BYOK failure

**What goes wrong:** The existing interceptor logic at [mobile/lib/core/api/auth_interceptor.dart:70-77](../../../mobile/lib/core/api/auth_interceptor.dart) returns `false` (treat as BYOK failure, KEEP session) when `error.param == "Authorization"`. A future backend change that emits `code='SESSION_REVOKED'` AND `param="Authorization"` (e.g., when the BYOK Bearer is the only thing on the request and the session is also revoked) would skip the session-clear path. User stays logged in with a phantom session id.

**Why it happens:** The interceptor reads `param` only, not `code`. Phase 26 adds the `code` axis without changing the `param` axis.

**How to avoid:** Change `_isSessionAuthFailure` to short-circuit on `code == 'SESSION_REVOKED'` BEFORE the param check.

**Example:**
```dart
bool _isSessionAuthFailure(DioException err) {
  final data = err.response?.data;
  if (data is! Map<String, dynamic>) return true;
  final error = data['error'];
  if (error is! Map<String, dynamic>) return true;
  // NEW — code beats param: session_revoked always means session is dead.
  if (error['code'] == 'SESSION_REVOKED') return true;
  final param = error['param'] as String?;
  return param != 'Authorization';
}
```

**Warning signs:** A test where the response carries both `code='SESSION_REVOKED'` and `param='Authorization'` and the session is NOT cleared.

### Pitfall 7: Migration 009 vs frozen 008 numbering off-by-one

**What goes wrong:** Developer runs `alembic revision -m logout_all_audit` and gets `009` — but the existing latest migration is `008_idempotency_keys_relax_run_fk.py`, NOT `008_idempotency_relax_run_fk.py` (CONTEXT.md mentions the latter; the file on disk has the longer name). New migration must `down_revision = "008_idempotency_keys_relax_run_fk"`. Wrong revision string → alembic upgrade fails.

**Why it happens:** CONTEXT.md §D-12 says "Migration 009 — additive only" but doesn't pin the exact down_revision string. The phase researcher must read the actual file ([api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py](../../../api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py)) — its `revision` is `"008_idempotency_relax_run_fk"` (the file is named with `_keys_` but the revision string omits it).

**How to avoid:** Plan task explicitly captures `down_revision = "008_idempotency_relax_run_fk"` (the revision string, not the filename). Verify by `head -45 api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py | grep ^revision`.

**Warning signs:** `alembic upgrade head` failing with "can't locate revision identified by '008_...'".

### Pitfall 8: Test fixture doesn't TRUNCATE auth_events

**What goes wrong:** Developer adds `auth_events` table in migration 009. The test conftest's `_truncate_tables` autouse fixture at [api_server/tests/conftest.py:175-180](../../../api_server/tests/conftest.py) hardcodes the table list: `agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users`. New `auth_events` table is NOT in the list — rows leak across tests, producing flaky pass/fail on `device_count_revoked` assertions when test order varies.

**Why it happens:** The TRUNCATE list is hand-maintained.

**How to avoid:** Plan task adds `auth_events` to the TRUNCATE list. Verify by adding two tests in different files that both INSERT into auth_events and assert COUNT(*)=1 from a fresh DB.

**Warning signs:** `pytest tests/auth/ -p no:randomly` passes; `pytest tests/auth/` (default randomized order) fails.

## Code Examples

### Migration 009 (additive)

```python
"""Phase 26 — auth_events audit table + sessions.revoked_reason column.

ADDITIVE ONLY. Adds:
  * auth_events table — append-only forensic log for logout-all events
  * sessions.revoked_reason TEXT column — enum-shape ('logout', 'logout_all',
    'admin', 'expired'); NULL for legacy revoked rows pre-26.

Revision ID: 009_logout_all_audit
Revises: 008_idempotency_relax_run_fk
Create Date: 2026-05-04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "009_logout_all_audit"
down_revision = "008_idempotency_relax_run_fk"  # NOTE: revision-string, not filename
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("revoked_reason", sa.Text(), nullable=True),
    )
    op.create_table(
        "auth_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_count_revoked", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_auth_events_user_created",
        "auth_events",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_events_user_created", table_name="auth_events")
    op.drop_table("auth_events")
    op.drop_column("sessions", "revoked_reason")
```

[VERIFIED: codebase] Mirrors migration 005 shape (`api_server/alembic/versions/005_sessions_and_oauth_users.py`).

### asyncpg UPDATE-RETURNING-ids pattern

```python
# Returns a list[Record]; len(rows) is the precise count.
rows = await conn.fetch(
    """
    UPDATE sessions
    SET revoked_at = NOW(),
        revoked_reason = 'logout_all'
    WHERE user_id = $1
      AND revoked_at IS NULL
    RETURNING id
    """,
    user_id,
)
revoked_ids = [r["id"] for r in rows]  # for tests that want UUIDs
count = len(rows)
```

[CITED: asyncpg docs] `Connection.fetch(query, *args)` returns `list[Record]`; each Record supports indexed-by-name access ([asyncpg API reference](https://magicstack.github.io/asyncpg/current/api/index.html)).

### dio interceptor — error-code-aware emit

```dart
// mobile/lib/core/api/auth_interceptor.dart — onError extension
@override
Future<void> onError(
  DioException err,
  ErrorInterceptorHandler handler,
) async {
  if (err.response?.statusCode == 401 && _isSessionAuthFailure(err)) {
    final reason = _extractRevokedReason(err);
    await _storage.clearSessionId();
    _authEvents.emit(AuthRequired(reason: reason));
  }
  handler.next(err);
}

String? _extractRevokedReason(DioException err) {
  final data = err.response?.data;
  if (data is! Map<String, dynamic>) return null;
  final error = data['error'];
  if (error is! Map<String, dynamic>) return null;
  return error['code'] == 'SESSION_REVOKED' ? 'session_revoked' : null;
}
```

### Next.js useUser — error-code-aware redirect

```typescript
// frontend/hooks/use-user.ts — extension
.catch(async (err) => {
  if (cancelled) return;
  if (err instanceof ApiError && err.status === 401) {
    let reason = "";
    try {
      const body = JSON.parse(err.body);
      if (body?.error?.code === "SESSION_REVOKED") reason = "session_revoked";
    } catch {
      // body might not be JSON; fall through with reason=""
    }
    router.push(reason ? `/login?reason=${reason}` : "/login");
    return;
  }
  console.warn("useUser: failed to fetch /users/me", err);
});
```

### Test — 3-device logout-all + idempotency

```python
# api_server/tests/auth/test_logout_all.py — NEW

@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_all_revokes_every_session_for_user(
    async_client, db_pool, multi_session_cookie
):
    """3 sessions for one user; logout-all revokes all 3."""
    cookies = await multi_session_cookie(n=3)  # returns list[dict] with Cookie/_session_id
    caller = cookies[0]

    # Sanity: each cookie individually works.
    for c in cookies:
        r = await async_client.get(
            "/v1/users/me", headers={"Cookie": c["Cookie"]}
        )
        assert r.status_code == 200, r.text

    # Logout-all from the first device.
    r = await async_client.post(
        "/v1/auth/logout-all", headers={"Cookie": caller["Cookie"]}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"revoked": 3}

    # Audit row written.
    async with db_pool.acquire() as conn:
        ev = await conn.fetchrow(
            "SELECT kind, device_count_revoked FROM auth_events "
            "WHERE user_id = $1::uuid",
            caller["_user_id"],
        )
        assert ev["kind"] == "logout_all"
        assert ev["device_count_revoked"] == 3

    # Every cookie now 401s with code='SESSION_REVOKED'.
    for c in cookies:
        r = await async_client.get(
            "/v1/users/me", headers={"Cookie": c["Cookie"]}
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "SESSION_REVOKED"


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_all_idempotent_under_concurrent_calls(
    async_client, db_pool, multi_session_cookie
):
    """Two parallel logout-all from the same user → both 200; final state same."""
    import asyncio
    cookies = await multi_session_cookie(n=2)
    caller_a, caller_b = cookies[0], cookies[1]

    r_a, r_b = await asyncio.gather(
        async_client.post(
            "/v1/auth/logout-all", headers={"Cookie": caller_a["Cookie"]}
        ),
        async_client.post(
            "/v1/auth/logout-all", headers={"Cookie": caller_b["Cookie"]}
        ),
    )
    assert r_a.status_code == 200
    assert r_b.status_code == 200
    # Sum of revoked counts is exactly the number of pre-existing live sessions
    # (2). Either response can have count=2 and the other 0, OR count=1 and
    # count=1 — Postgres' row-level lock serializes the UPDATEs.
    assert r_a.json()["revoked"] + r_b.json()["revoked"] == 2

    # Two audit rows landed.
    async with db_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM auth_events WHERE user_id = $1::uuid",
            caller_a["_user_id"],
        )
        assert n == 2


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_all_does_not_touch_other_users(
    async_client, authenticated_cookie, second_authenticated_cookie
):
    """User A's logout-all does NOT revoke user B's session."""
    r = await async_client.post(
        "/v1/auth/logout-all",
        headers={"Cookie": authenticated_cookie["Cookie"]},
    )
    assert r.status_code == 200

    # User B's session still works.
    r_b = await async_client.get(
        "/v1/users/me",
        headers={"Cookie": second_authenticated_cookie["Cookie"]},
    )
    assert r_b.status_code == 200


@pytest.mark.api_integration
@pytest.mark.asyncio
async def test_logout_all_without_cookie_returns_401_unauthorized(
    async_client,
):
    """No cookie → 401 with code='UNAUTHORIZED' (not SESSION_REVOKED)."""
    r = await async_client.post("/v1/auth/logout-all")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"
```

### Test fixture — multi-session cookie

```python
# api_server/tests/auth/conftest.py — extension to existing file

@pytest_asyncio.fixture
async def multi_session_cookie(db_pool):
    """Mint N sessions for a single user; return list[dict] one per session.

    Each dict has the same shape as ``authenticated_cookie``:
      * Cookie — header value
      * _user_id — same across all N entries (single user)
      * _session_id — distinct per entry
    """
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    async def _factory(n: int):
        async with db_pool.acquire() as conn:
            user_id = await conn.fetchval(
                "INSERT INTO users (id, provider, sub, email, display_name) "
                "VALUES (gen_random_uuid(), $1, $2, $3, $4) RETURNING id::text",
                "google",
                f"test-sub-{uuid4().hex[:12]}",
                f"multi-{uuid4().hex[:6]}@example.com",
                "Multi",
            )
            now = datetime.now(timezone.utc)
            entries = []
            for _ in range(n):
                sid = await conn.fetchval(
                    """
                    INSERT INTO sessions (user_id, created_at, expires_at, last_seen_at)
                    VALUES ($1::uuid, $2, $3, $2)
                    RETURNING id::text
                    """,
                    user_id, now, now + timedelta(days=30),
                )
                entries.append({
                    "Cookie": f"ap_session={sid}",
                    "_user_id": user_id,
                    "_session_id": sid,
                })
            return entries

    return _factory
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JWT logout via blocklist on shared cache | Server-side session table with `revoked_at` column | Phase 22c (this codebase) — opaque cookie, server-side row | The Phase 22c decision dictates Phase 26's whole shape. JWT-blocklist code patterns from blogs are NOT applicable here. |
| Hand-rolled `Set-Cookie` clearing | `Response.set_cookie(... max_age=0)` from FastAPI | Standard FastAPI pattern | Already encapsulated in `_clear_session_cookie`. |
| Single-shot DELETE for revocation | Soft-revoke with `revoked_at` timestamp | Phase 22c migration 005 | Forensic data preserved; queries like "show revoked sessions in the last 24h" become trivial. |
| Cross-replica session invalidation via Redis pub/sub | Per-request DB SELECT (single-replica) | Phase 26 D-01 | Adequate at current scale; revisit in multi-replica. |
| Generic `code: 'unauthorized'` for every 401 | Code-axis differentiation (`SESSION_REVOKED` vs `UNAUTHORIZED`) | Phase 26 (this phase) | Client UX can render different copy per cause; banners reflect actual reason. |

**Deprecated/outdated:**
- The H1 "OAuth refresh tokens" item from the audit was retired during this phase's recon — see [memory/feedback_audit_before_evolve.md](../../../memory/feedback_audit_before_evolve.md). Phase 26 is the correct framing for the H2 fix.
- The `frontend/middleware.ts` filename in older docs — Next.js 16.2 renamed to `proxy.ts` (AMD-06 in 22c-CONTEXT). The current file at [frontend/proxy.ts](../../../frontend/proxy.ts) is canonical.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Solvr-aesthetic confirm-dialog copy ("Log out everywhere?", body, button labels) | Pattern 5 | Low — D-09 marks copy as Claude's discretion; user can override in the discuss-phase or planner can pick alternatives. |
| A2 | Banner copy ("Your session was ended on another device. Sign in to continue.") | Pattern 5 | Low — D-04 locked the message text loosely ("session was ended on another device. Please sign in again."); the recommended copy is essentially identical. |
| A3 | Web banner is dismiss-only persistent (not auto-disappearing toast) | Pattern 4 | Medium — if user prefers a toast (matching the existing `?error=oauth_failed → toast.error` pattern), the implementation is one line different. Either is shippable. |
| A4 | `auth_events` not in tests/conftest.py TRUNCATE list will cause flake | Pitfall 8 | Low — easy to verify; planner adds the line. |
| A5 | Migration 009's `down_revision` string is `"008_idempotency_relax_run_fk"` (NOT `"008_idempotency_keys_relax_run_fk"`) | Pitfall 7 | High if wrong — migration won't apply. **VERIFIED:** read [api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py:37](../../../api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py) — `revision = "008_idempotency_relax_run_fk"`. ✅ |
| A6 | Single SELECT in middleware (Pattern 2 alternate) is the cleaner shape | Pattern 2 | Low — both shapes ship the same observable behavior; planner picks. |
| A7 | `AuthRequired.emit()` arity change is non-breaking (only one call site exists today) | Pattern 3 | Low — verified by grep: only [mobile/lib/core/api/auth_interceptor.dart:48](../../../mobile/lib/core/api/auth_interceptor.dart) calls `_authEvents.emit()`. |

## Open Questions

1. **Should the response body include a list of revoked session IDs, or just `{revoked: count}`?**
   - What we know: D-04 says response is just count; CONTEXT.md §Claude's Discretion says "probably no". 
   - What's unclear: A future admin UI might want the IDs to render "Revoked: laptop-Chrome 12s ago, phone-Safari 30m ago".
   - Recommendation: ship `{"revoked": <count>}` only. Admin UI can re-fetch via a new `GET /v1/auth/sessions` endpoint in a later phase if/when needed. Lean.

2. **Should `auth_events.kind` be a Postgres enum or plain TEXT?**
   - What we know: D-02 says TEXT with initial enum value `'logout_all'`. D-03 says lean.
   - What's unclear: pg_enum is more rigorous but a future addition (`'admin_revoke'`, `'failed_login'`) requires a migration; TEXT keeps additions trivial.
   - Recommendation: TEXT (matches D-02). Add a CHECK constraint as a cheap DB-layer guard if strictness is wanted later.

3. **Should the migration also add a CHECK constraint on `sessions.revoked_reason`?**
   - What we know: D-10 says "enum column (values: 'logout', 'logout_all', 'admin', 'expired')". No CHECK explicitly required.
   - What's unclear: Without a CHECK, a typo at the call site (`'logoutall'`) is silently accepted.
   - Recommendation: ship without CHECK in migration 009; add a Pydantic Literal type at the API boundary instead. CHECK can be added in a future migration if the column gains more callers.

4. **Web: revoke detection on routes that DON'T currently call `/v1/users/me`?**
   - What we know: `useUser()` is the canonical 401 detector. Other API calls (`apiPost("/v1/runs", ...)`) also throw `ApiError(401)`.
   - What's unclear: Does the dashboard's data-fetching layer (e.g., `my-agents-panel.tsx`) consistently observe 401s and route them to login?
   - Recommendation: leave existing call sites as-is. If they 401, the user sees a fetch-error toast and can manually navigate to /login. The session_revoked banner there is set by the next `useUser()` call. This is the dumb-client principle — backend is source of truth, client doesn't need every component to know.

5. **Mobile: are SSE streams (chat) closed on a 401, or do they ride out per D-08?**
   - What we know: D-08 says "stay open until next reconnect or network close." `chat_providers.dart` has its own SSE-connect handler (cited as a YELLOW maturity item in the solidity audit).
   - What's unclear: The dio `AuthInterceptor` does NOT touch SSE streams (they bypass dio); the `flutter_client_sse` package wraps the request differently.
   - Recommendation: ship Phase 26 as-spec'd (don't touch SSE). The 30s window is acceptable per D-08. Add an explicit test that asserts the SSE stream is NOT closed by logout-all.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| PostgreSQL 17 | Migration 009, all DB tests | ✓ | testcontainers `postgres:17-alpine` | — |
| asyncpg | All DB calls | ✓ | already pinned in api_server pyproject | — |
| alembic | Migration runner | ✓ | invoked via `python -m alembic` (conftest pattern) | — |
| Redis | NOT REQUIRED for Phase 26 (D-01 skips pub/sub) | ✓ available but unused | — | — |
| Docker daemon | Existing testcontainers harness | ✓ | required for `pytest -m api_integration` | None (but tests can run unit-only) |
| Flutter `dio` | Mobile interceptor change | ✓ | already in `mobile/pubspec.yaml` | — |
| Flutter `flutter_riverpod` | Mobile state extension | ✓ | 3.x in pubspec | — |
| Next.js 16.2 | Web changes | ✓ | already in `frontend/package.json` | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

## Validation Architecture

> Phase 26 follows the existing test layout. `nyquist_validation` is enabled by default — assume yes.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio + httpx.AsyncClient + testcontainers Postgres 17 |
| Config file | `api_server/pyproject.toml` ([VERIFIED: codebase] markers `api_integration`) |
| Quick run command | `cd api_server && python -m pytest tests/auth/ -x -q` |
| Full suite command | `cd api_server && python -m pytest -x -q -m "api_integration or not api_integration"` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| logout-all revokes all sessions | 3-device fixture; assert all 3 cookies 401 after; assert audit row count_revoked=3 | api_integration | `pytest tests/auth/test_logout_all.py::test_logout_all_revokes_every_session_for_user -x` | ❌ Wave 0 |
| logout-all is idempotent under race | 2 parallel calls via asyncio.gather; assert sum of counts == n_pre_existing | api_integration | `pytest tests/auth/test_logout_all.py::test_logout_all_idempotent_under_concurrent_calls -x` | ❌ Wave 0 |
| logout-all does not affect other users | 2 distinct users, A revokes, B's session still 200 | api_integration | `pytest tests/auth/test_logout_all.py::test_logout_all_does_not_touch_other_users -x` | ❌ Wave 0 |
| 401 differentiation | session_revoked vs unauthorized error code | api_integration | `pytest tests/auth/test_logout_all.py::test_logout_all_without_cookie_returns_401_unauthorized -x` | ❌ Wave 0 |
| Existing logout sets revoked_reason='logout' | extend test_logout.py to assert column value | api_integration | `pytest tests/auth/test_logout.py::test_logout_204_invalidates_session -x` | ✅ extend |
| auth_events row written | sub-assertion inside the 3-device test | api_integration | (covered above) | ❌ Wave 0 |
| Mobile interceptor extracts session_revoked reason | unit test on AuthInterceptor with a mocked dio response | unit | `cd mobile && flutter test test/core/api/auth_interceptor_test.dart` | ❌ Wave 0 |
| Web useUser 401 → /login?reason=session_revoked | RTL/Vitest test on useUser hook with a mock fetch | unit | `cd frontend && pnpm test -- use-user` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/auth/test_logout_all.py -x -q`
- **Per wave merge:** `pytest tests/auth/ -x -q` (existing 22c tests + Phase 26 additions)
- **Phase gate:** `pytest -x -q` full suite + `flutter test` + `pnpm test` all green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/auth/test_logout_all.py` — covers the 4 logout-all scenarios above (NEW)
- [ ] `tests/auth/conftest.py` — `multi_session_cookie` fixture extension (extend existing)
- [ ] Update `tests/conftest.py:175-180` `_truncate_tables` autouse to include `auth_events`
- [ ] `mobile/test/core/api/auth_interceptor_test.dart` — extend existing test (if any) for session_revoked branch (likely doesn't exist; create)
- [ ] `frontend/__tests__/use-user.test.tsx` — assert 401 with code SESSION_REVOKED redirects with reason query param (if vitest is configured; per [frontend/package.json] check at plan time)

*(If existing mobile/web test infrastructure is missing, planner can de-scope unit tests to integration-tested-only; the api_integration tests cover the full contract end-to-end.)*

## Security Domain

`security_enforcement` is enabled (default). Phase 26 IS a security feature — careful coverage required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing OAuth substrate (Phase 22c) — Phase 26 doesn't add a new auth path; only a session-termination path. |
| V3 Session Management | **yes** | Phase 26 IS V3 — V3.3.4 (logout invalidation) and V3.3.1 (session revocation visible) directly. Implementation: `revoked_at` column + `auth_events` audit. |
| V4 Access Control | yes | `require_user` is the gate; logout-all only revokes the caller's own user_id (server-derived from the session, not request-supplied). |
| V5 Input Validation | partial | The endpoint takes no body. The path is parameterless. Pydantic models are not needed. |
| V6 Cryptography | no | No new crypto. The session cookie value is unchanged. |
| V7 Error Handling | yes | Stripe-shape envelope already covers — no exception body leaks. |
| V8 Data Protection | yes | `auth_events` stores `ip` and `user_agent` — both already collected on session creation; no new PII gathered. |
| V13 API & Web Service | yes | RESTful POST verb, idempotent, returns count. Standard. |

### Known Threat Patterns for FastAPI + asyncpg + cookie-session

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on logout-all (attacker triggers victim's logout-all) | Tampering / Repudiation | SameSite=Lax cookie + the endpoint being POST-only blocks the simple CSRF path. The HttpOnly cookie + same-origin policy means an attacker can't trigger logout-all without an XSS-on-our-domain — which they could already use to steal the session entirely. Net new risk: zero. No CSRF token needed. |
| Cross-user revocation (attacker calls logout-all with someone else's user_id) | Tampering | The handler reads `user_id` from `request.state.user_id` (set by SessionMiddleware from the cookie), NOT from a request body or query param. The attacker would need to forge the cookie → already a session-compromise. No additional check needed. |
| Audit log injection (attacker stuffs malicious payload into user_agent) | Tampering | `user_agent TEXT` is stored as-is for forensic value. UI rendering must HTML-escape (standard React/JSX auto-escapes; admin scripts that print to bash should `printf '%q'`). [VERIFIED: codebase] no admin tool reads auth_events today. |
| Audit log floods (attacker calls logout-all 10000x to fill the table) | Denial of Service | Each call generates 1 audit row. At 100 req/s for 1 hour = 360k rows = ~80MB. Acceptable. The phase's own rate limit (Phase 27 H3) would close this entirely; documented as out of scope per CONTEXT.md. The endpoint is gated by `require_user` so an unauthenticated attacker can't even start. |
| Information disclosure via differing 401 messages | Information Disclosure | The two 401 codes (`UNAUTHORIZED` vs `SESSION_REVOKED`) reveal "this user_id had a session that was revoked" to a holder of an old cookie. This is acceptable — the holder of an old cookie ALREADY had a valid session with this user. No new info disclosed. |
| TOCTOU between SessionMiddleware SELECT and revocation in another request | Concurrency | Middleware reads-then-treats-as-anonymous; revocation is a single UPDATE. A request arriving between revoke commit and middleware read sees the revoked row. The "between" window is bounded by the request's own DB query latency — sub-millisecond. Acceptable. |
| Replay of an old `Set-Cookie: ap_session=` from device A by an attacker | Spoofing | The cookie carries a 122-bit `gen_random_uuid()` value. After revocation, the row exists with `revoked_at IS NOT NULL` — middleware returns user_id=None. The attacker can't use a revoked cookie. |

## Project Constraints (from CLAUDE.md)

> Read at session start (per `# claudeMd` system reminder above).

| Directive | Phase 26 Compliance |
|-----------|---------------------|
| **Golden rule 1: No mocks, no stubs.** Tests hit real infra. | ✅ Phase 26 tests use the existing testcontainers Postgres 17 substrate. No in-memory fakes. |
| **Golden rule 2: Dumb client, intelligence in the API.** | ✅ Web + mobile changes only render server-emitted error codes. The client knows `'SESSION_REVOKED'` exists; the client does NOT decide whether a session is revoked. |
| **Golden rule 3: Ship when the stack works locally end-to-end.** | ✅ Phase 26's exit gate must be: real cookie minted, logout-all called, all cookies fail with the right code, banner renders. The integration tests cover this; manual end-to-end verification is one device login + a second device sign-in via mobile. |
| **Golden rule 4: Root cause first, never fix-to-pass.** | N/A for greenfield phase. |
| **Golden rule 5: Probe gray areas empirically BEFORE planning.** | The gray areas this phase touches: (a) asyncpg UPDATE+RETURNING behavior, (b) row-level lock semantics under concurrent UPDATEs, (c) middleware lookup-then-classify additional SELECT cost. (a) and (b) are covered by the integration tests. (c) is unmeasured but the SELECT is on the same row already loaded into the buffer cache → microseconds. If the planner is unsure, a 5-minute spike — `cd api_server && python -m pytest tests/middleware/test_session.py -x` with profiling — answers it. |
| **CLAUDE.md current-state banner: "DO NOT touch `api/`, `deploy/`, `test/`, or the old substrate"** | ✅ Phase 26 only touches `api_server/`, `frontend/`, `mobile/`. The CLAUDE.md banner about the recipe-format pivot is HISTORICAL — Phases 22c/23/24/25 already shipped after the banner was written; Phase 26 is in the same Solvr Labs / mobile MVP track. The banner's "9-phase roadmap" warning does not apply to Phase 26. |
| **Telegram is a LIVE channel — not a stub** ([feedback_telegram_is_live_channel_not_stub.md](../../../memory/feedback_telegram_is_live_channel_not_stub.md)) | N/A — Phase 26 doesn't touch agents/Telegram. |
| **Web playground-form is the canonical client-deploy reference** ([reference_web_playground_form.md](../../../memory/reference_web_playground_form.md)) | N/A — different feature surface. |
| **Surface inflight UI for any >2s backend await** ([feedback_inflight_ui_for_long_awaits.md](../../../memory/feedback_inflight_ui_for_long_awaits.md)) | Likely not applicable — logout-all is sub-second. But IF the UPDATE blocks (e.g., 100s of sessions for one user — improbable), the spinner pattern from `deploy_step.dart` should be mirrored in the Settings → Security button. Plan task should include "Lock the trigger + spinner during the await" for the web button + mobile dialog confirm flow. |

## Sources

### Primary (HIGH confidence)
- [api_server/src/api_server/routes/auth.py](../../../api_server/src/api_server/routes/auth.py) — existing logout shape (lines 542-592 are the canonical mirror target)
- [api_server/src/api_server/middleware/session.py](../../../api_server/src/api_server/middleware/session.py) — existing SELECT pattern (lines 60-68)
- [api_server/src/api_server/auth/deps.py](../../../api_server/src/api_server/auth/deps.py) — `require_user` signature (lines 37-72)
- [api_server/src/api_server/models/errors.py](../../../api_server/src/api_server/models/errors.py) — `ErrorCode` + envelope shape
- [api_server/alembic/versions/005_sessions_and_oauth_users.py](../../../api_server/alembic/versions/005_sessions_and_oauth_users.py) — table-shape baseline for migration 009
- [api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py](../../../api_server/alembic/versions/008_idempotency_keys_relax_run_fk.py) — current head migration; revision string `008_idempotency_relax_run_fk`
- [api_server/tests/auth/test_logout.py](../../../api_server/tests/auth/test_logout.py) — test template
- [api_server/tests/auth/conftest.py](../../../api_server/tests/auth/conftest.py) — fixture extension target
- [api_server/tests/conftest.py](../../../api_server/tests/conftest.py) — `authenticated_cookie` (line 511) + `second_authenticated_cookie` (line 556) + `_truncate_tables` (line 175)
- [api_server/src/api_server/auth/oauth.py](../../../api_server/src/api_server/auth/oauth.py) — `mint_session` + `upsert_user` (lines 180-256) — INSERT … RETURNING pattern
- [api_server/src/api_server/services/rate_limit.py](../../../api_server/src/api_server/services/rate_limit.py) — UPDATE … RETURNING reference (lines 75-93)
- [mobile/lib/core/api/auth_interceptor.dart](../../../mobile/lib/core/api/auth_interceptor.dart) — existing 401 handler
- [mobile/lib/core/auth/auth_event_bus.dart](../../../mobile/lib/core/auth/auth_event_bus.dart) — `AuthRequired`/`emit()` shape
- [mobile/lib/features/login/login_screen.dart](../../../mobile/lib/features/login/login_screen.dart) — banner-render gate
- [mobile/lib/features/login/login_providers.dart](../../../mobile/lib/features/login/login_providers.dart) — `showSignedOutBannerProvider`
- [mobile/lib/features/dashboard/dashboard_screen.dart](../../../mobile/lib/features/dashboard/dashboard_screen.dart) — confirm-dialog usage (lines 375-388)
- [mobile/lib/shared/confirm_dialog.dart](../../../mobile/lib/shared/confirm_dialog.dart) — destructive dialog component
- [frontend/proxy.ts](../../../frontend/proxy.ts) — Next.js gate
- [frontend/lib/api.ts](../../../frontend/lib/api.ts) — fetch wrapper + `ApiError` shape
- [frontend/hooks/use-user.ts](../../../frontend/hooks/use-user.ts) — 401 redirect logic
- [frontend/app/login/page.tsx](../../../frontend/app/login/page.tsx) — `?error=` query-param pattern (lines 18-23)
- [frontend/app/dashboard/settings/page.tsx](../../../frontend/app/dashboard/settings/page.tsx) — Security subsection placeholder (lines 111-137)
- [.planning/phases/22c-oauth-google/22c-CONTEXT.md](../22c-oauth-google/22c-CONTEXT.md) — substrate decisions (esp. AMD-02 refresh-token-drop, AMD-06 proxy.ts rename)
- [.planning/phases/26-logout-everywhere/26-CONTEXT.md](./26-CONTEXT.md) — locked decisions (D-01 to D-12)

### Secondary (MEDIUM confidence)
- [PostgreSQL Documentation: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row-level lock semantics for concurrent UPDATEs
- [asyncpg API Reference](https://magicstack.github.io/asyncpg/current/api/index.html) — `Connection.fetch` / `execute` return types
- [asyncpg Issue #311 — Get the count of affected rows](https://github.com/MagicStack/asyncpg/issues/311) — confirms `execute()` returns the libpq command-status string, not an int
- [memory/project_solidity_audit_2026_05_04.md](../../../memory/project_solidity_audit_2026_05_04.md) — H2 origin
- [memory/feedback_audit_before_evolve.md](../../../memory/feedback_audit_before_evolve.md) — H1-was-misframe correction; phase-recon discipline
- [memory/feedback_solvr_matrix_aesthetic.md](../../../memory/feedback_solvr_matrix_aesthetic.md) — UI vocabulary cues
- [memory/feedback_inflight_ui_for_long_awaits.md](../../../memory/feedback_inflight_ui_for_long_awaits.md) — spinner pattern reference
- [memory/feedback_dumb_client_no_mocks.md](../../../memory/feedback_dumb_client_no_mocks.md) — backend-as-source-of-truth principle
- [memory/feedback_re_ask_gray_areas.md](../../../memory/feedback_re_ask_gray_areas.md) — D-08/D-09 surfaced via second-pass discuss

### Tertiary (LOW confidence — confirm in discuss-phase if disputed)
- Solvr-aesthetic copy choices (Pattern 5) — labeled [ASSUMED] above; user can revise
- "Banner is dismiss-only persistent (not toast)" UX choice — Pattern 4

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components are existing, codebase-verified, with file-line citations.
- Architecture: HIGH — patterns mirror Phase 22c verbatim; no novel mechanisms.
- Pitfalls: HIGH — 8 concrete pitfalls, 5 verified directly against the codebase.
- Test patterns: HIGH — `authenticated_cookie` shape verified at `tests/conftest.py:511`; multi-session fixture is a 30-line addition.
- Postgres concurrency semantics: MEDIUM — verified by official docs but not empirically spiked. Single-statement `UPDATE WHERE` with row-level lock is textbook; failure modes for the ASCII `WHERE revoked_at IS NULL` filter under contention are well-understood.
- UX copy (Solvr aesthetic): LOW (assumption-flagged) — D-09 is Claude's discretion and the recommended phrasing is plain English; user override is cheap.

**Research date:** 2026-05-04
**Valid until:** 2026-06-04 (30 days — substrate is stable; only the asyncpg version is fast-moving but not used in any way that would change shape)
