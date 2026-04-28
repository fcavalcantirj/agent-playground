---
phase: 22c-oauth-google
reviewed: 2026-04-28T00:00:00Z
depth: deep
files_reviewed: 17
files_reviewed_list:
  - api_server/src/api_server/middleware/session.py
  - api_server/src/api_server/auth/oauth.py
  - api_server/src/api_server/auth/deps.py
  - api_server/src/api_server/routes/auth.py
  - api_server/src/api_server/routes/users.py
  - api_server/src/api_server/routes/runs.py
  - api_server/src/api_server/routes/agents.py
  - api_server/src/api_server/routes/agent_lifecycle.py
  - api_server/alembic/versions/005_sessions_and_oauth_users.py
  - api_server/alembic/versions/006_purge_anonymous.py
  - api_server/src/api_server/config.py
  - api_server/src/api_server/main.py
  - api_server/src/api_server/middleware/idempotency.py
  - api_server/src/api_server/middleware/rate_limit.py
  - api_server/src/api_server/middleware/log_redact.py
  - frontend/proxy.ts
  - frontend/app/login/page.tsx
  - frontend/hooks/use-user.ts
  - frontend/components/navbar.tsx
  - frontend/lib/api.ts
  - frontend/app/dashboard/layout.tsx
  - frontend/next.config.mjs
  - tools/Dockerfile.api
  - deploy/docker-compose.prod.yml
  - deploy/.env.prod.example
findings:
  critical: 0
  high: 1
  medium: 4
  low: 3
  info: 2
  total: 10
status: issues_found
---

# Phase 22c (oauth-google): Code Review Report

**Reviewed:** 2026-04-28
**Depth:** deep (cross-file analysis, security-critical surface)
**Files Reviewed:** 25 (17 primary + 8 supporting)
**Status:** issues_found
**Ship recommendation:** **SHIP with HIGH-01 patched in deploy template before next prod deploy.** No CRITICAL findings. No code-level changes required to `main`. The single HIGH finding is an operator-facing template gap, not a code bug — easily fixed by editing `deploy/.env.prod.example`.

## Summary

The Phase 22c OAuth identity foundation is well-engineered. The 9-plan execution chain (`394fd7f..70281cc`) lands a clean OAuth surface with disciplined fail-loud-in-prod, correct CSRF state handling via Starlette SessionMiddleware, careful cookie hygiene (HttpOnly + SameSite=Lax + env-gated Secure), and proper cross-user isolation enforced at the SQL layer in every protected route. The integration tests for OAuth callback, logout, cross-user isolation, and last_seen throttle exercise real Postgres via testcontainers (no mocks for the substrate, per golden rule 1).

Notable strengths:

- **EXACT-match on `mismatching_state`** — D-22c-OAUTH-01 regression trap is correctly implemented and explicitly tested at `test_google_callback.py::test_oauth_failed_on_non_state_error`. Substring-match drift is impossible.
- **Stripe-shape error envelopes** are byte-identical with the rest of the codebase (`make_error_envelope`); `require_user` mirrors the inline `_err()` pattern instead of bolting on `Depends`.
- **Defense-in-depth at the SQL layer:** every `/v1/agents/:id/*` route filters `WHERE user_id = $user_id` via `fetch_agent_instance(agent_id, user_id)`. Even if `require_user` were bypassed by a refactor, the SQL still couldn't return another user's row.
- **Fail-loud OAuth config** in prod (`get_oauth(settings)` raises at `create_app` time, not on first request) so a misconfigured deploy crashes loudly instead of accepting requests in a broken state.
- **Cookie redaction is structural, not subtractive:** `AccessLogMiddleware` allowlists 5 specific headers; `Cookie` and `Set-Cookie` are not in the set, so neither `ap_session` nor `ap_oauth_state` can ever be logged. No string-strip hacks.
- **GitHub email-fallback** is correctly implemented: when primary email is private, calls `/user/emails`, picks first `primary && verified`, refuses account creation if still null. Matches D-22c-OAUTH-03 verbatim.
- **Migration 006 is appropriately irreversible** — `downgrade()` raises `NotImplementedError` rather than silently destroying data or re-seeding ANONYMOUS.

The one HIGH finding is operational, not a code defect: the prod env template is missing `AP_FRONTEND_BASE_URL`, which means a deploy following the documented procedure would 302 OAuth-success users to `http://localhost:3000/dashboard`. Catching this at the template level is a 1-line fix.

The MEDIUM findings are all defensible-in-context and acknowledged in the codebase (mostly via comments or deferred-items.md), but worth tracking for v2.

---

## High

### HIGH-01: `AP_FRONTEND_BASE_URL` missing from `deploy/.env.prod.example`

**File:** `deploy/.env.prod.example` (and by extension, every prod `.env.prod` derived from it)
**Issue:**

The Wave 5 smoke gate (commit `f9a7df9`) introduced `settings.frontend_base_url` (default `"http://localhost:3000"`) to fix the OAuth callback redirecting to the API origin instead of the frontend. Three RedirectResponse call sites in `routes/auth.py` (lines 118, 201, 294) use this:

```python
RedirectResponse(f"{settings.frontend_base_url}{_DASHBOARD_PATH}", status_code=302)
```

`AP_FRONTEND_BASE_URL` was added to `config.py` and `auth.py`, BUT it was never added to `deploy/.env.prod.example`. An operator following the documented procedure (copy `.env.prod.example` → fill in real values → deploy) will end up with the default `http://localhost:3000` baked into prod. The result: a Google/GitHub login that succeeds at the IdP and at the API will then 302 the user's browser to `http://localhost:3000/dashboard` — a dead URL on every machine except the operator's laptop, sometimes pointing at the operator's own dev server. This is a confidentiality issue (the `ap_session` cookie is `Secure` in prod and Path=/ scoped to the API host, so it won't leak to localhost; but the user is stranded post-login) and a credibility issue (login looks broken).

There is no fail-loud guard on `frontend_base_url` — it's a `str` field with a default, so missing-env produces silent localhost behavior rather than `RuntimeError`.

**Fix:**

1. Add to `deploy/.env.prod.example`:
   ```ini
   # Phase 22c-09: frontend origin for post-OAuth 302s. Without this, the API
   # redirects users to http://localhost:3000/dashboard after a successful
   # Google/GitHub login (the in-code default), stranding them.
   # Format: scheme://host[:port] (no trailing slash).
   # Example: https://app.agentplayground.dev
   AP_FRONTEND_BASE_URL=
   ```

2. Optional but recommended: convert `frontend_base_url` to `str | None` and add a fail-loud check in `get_oauth()` (or a sibling validator at `create_app` time) so prod boot raises if it's unset:
   ```python
   if settings.env == "prod" and not settings.frontend_base_url:
       raise RuntimeError(
           "AP_FRONTEND_BASE_URL is required when AP_ENV=prod"
       )
   ```
   This mirrors the existing `_resolve_or_fail` discipline for the other 7 OAuth env vars.

3. Add to `deploy/docker-compose.prod.yml` `api_server.environment` block:
   ```yaml
   AP_FRONTEND_BASE_URL: ${AP_FRONTEND_BASE_URL}
   ```
   (The `env_file: .env.prod` line already pulls it through, so this is belt-and-braces; pick whichever convention the project prefers — but the example file MUST list it.)

---

## Medium

### MED-01: `GET /v1/runs/{id}` is unauthenticated and unscoped to user

**File:** `api_server/src/api_server/routes/runs.py:252-278`
**Issue:**

`get_run` performs no `require_user` check and `fetch_run` performs no `WHERE user_id` filter:

```python
@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    if not is_valid_ulid(run_id):
        return _err(...)
    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await fetch_run(conn, run_id)  # NO user_id filter
    ...
```

Test `test_runs.py:140-163` explicitly documents this as deliberate:
> "GET /v1/runs/{id} is public today (no require_user gate); only the POST side carries the cookie."

Run row exposes `prompt`, `stderr_tail`, `filtered_payload`, `model`, `recipe`, `verdict`, plus the joined `agent_instances.recipe_name` and `model`. ULID is unguessable in the cryptographic sense (130 bits), so this isn't a casual-enumeration risk — but:

1. ULIDs are TIMESTAMP-prefixed (Crockford base32 of millisecond epoch + randomness), making **adjacent-time enumeration** materially easier than UUIDv4. An attacker who knows roughly when a victim ran a recipe can iterate the time window.
2. The platform's stated cross-user isolation guarantee (CONTEXT.md §D-22c-AUTH-03 + the cross-user isolation test for `/v1/agents`) does not cover `/v1/runs/{id}`. This is an inconsistency in the platform's security model that is not immediately obvious.
3. `filtered_payload` and `stderr_tail` can carry user-specific data (Telegram chat IDs, agent output, partial tracebacks) — not credentials (those are redacted server-side), but private content nonetheless.

Phase 22c-CONTEXT D-22c-AUTH-03 lists protected paths explicitly and `/v1/runs/{id}` is not on the list. This is a **deliberate Phase 19 design choice that 22c did not revisit**, not a 22c regression. But it should be revisited because it contradicts the platform-level cross-user isolation guarantee that 22c-09's acceptance test asserts elsewhere.

**Fix (deferred to a v2 ticket — does NOT block 22c ship):**

```python
@router.get("/runs/{run_id}")
async def get_run(request: Request, run_id: str):
    session_result = require_user(request)
    if isinstance(session_result, JSONResponse):
        return session_result
    user_id: UUID = session_result

    if not is_valid_ulid(run_id):
        return _err(400, ...)

    pool = request.app.state.db
    async with pool.acquire() as conn:
        row = await fetch_run(conn, run_id, user_id=user_id)
    if row is None:
        return _err(404, ...)  # row missing OR not owned by user
    return RunGetResponse(**row).model_dump(mode="json")
```

And in `services/run_store.py::fetch_run`, add a `user_id` parameter and:

```sql
JOIN agent_instances a ON a.id = r.agent_instance_id
WHERE r.id = $1 AND a.user_id = $2
```

Returning the same 404 for "not found" and "not owned" avoids leaking existence.

---

### MED-02: `mint_session` records direct peer IP, ignoring `AP_TRUSTED_PROXY`

**File:** `api_server/src/api_server/auth/oauth.py:225-227`
**Issue:**

```python
ip = request.client.host if request.client else None
```

In prod, Caddy is in front (`AP_TRUSTED_PROXY=true` per `docker-compose.prod.yml:41`). `request.client.host` returns Caddy's IP, not the user's actual IP. The `sessions.ip_address` column will therefore record the proxy's IP for every prod session. The docstring acknowledges this:
> "the AP_TRUSTED_PROXY/X-Forwarded-For resolution lives in middleware/rate_limit.py and is intentionally NOT replicated here — we record the direct peer for future admin-UI display only."

The decision is intentional and documented, but:

1. The "future admin-UI display" use case is the use case where you actually want the real client IP. Recording Caddy's IP defeats that purpose.
2. If an admin ever queries `sessions WHERE ip_address = $suspicious_ip`, they will find every prod session, not just the suspicious user's.
3. The XFF resolution helper already exists in `middleware/rate_limit.py::_subject_from_scope` — extracting it into a shared util takes ~20 lines.

**Fix (defer to v2; not security-critical because the column is admin-display-only):**

Extract `_resolve_client_ip(request, trusted_proxy: bool) -> str | None` into `util/net.py` and call it from both `mint_session` and `RateLimitMiddleware`. Document the XFF spoofing risk inline.

---

### MED-03: `request.client` is read after a session is minted but `request.client` may be stale across the long callback path

**File:** `api_server/src/api_server/auth/oauth.py:226` (called from `routes/auth.py:198, 291`)
**Issue:**

The OAuth callback flow performs:
1. `await oauth.{google,github}.authorize_access_token(request)` — network round-trip to provider's token endpoint (1–3s typical)
2. For GitHub: `await oauth.github.get("user", token=token)` + possibly `await oauth.github.get("user/emails", token=token)` — additional round-trips
3. `async with pool.acquire() as conn:` — DB acquire
4. `await upsert_user(...)` and then `await mint_session(conn, user_id=user_id, request=request)`

`request.client` is the same object across all these awaits — that's fine, it's stable. The actual concern is more subtle: if the underlying TCP connection is dropped mid-flow (user closes browser tab during the 5s OAuth round-trip), `request.client` is still populated but the response can never be delivered. The session row gets minted in the DB, but the cookie is never set on the browser. Result: an orphaned `sessions` row with no corresponding cookie. Sessions auto-expire in 30 days, so cleanup happens eventually, but on a high-traffic system this could accumulate.

This is a **pre-existing pattern shared with `agent_lifecycle.py`'s pending-row insert flow** and isn't unique to OAuth — but it is worth noting because OAuth is the entry point and a flaky-network user could leave several orphan rows during sign-in retries.

**Fix (defer to v2; low impact in v1):**

Either (a) accept the orphan-row cost (sessions are TTL'd, blast radius is bounded), or (b) flip mint_session + cookie set into a background task triggered AFTER the response is fully sent. Option (a) is the right call for v1 — this is a minor accumulation issue, not a security one.

---

### MED-04: Mint-session `last_seen_at` cache eviction is O(n log n) on every overflow

**File:** `api_server/src/api_server/middleware/session.py:140-147`
**Issue:**

```python
def _maybe_evict(cache) -> None:
    if len(cache) <= _LAST_SEEN_CACHE_SOFT_CAP:  # 10_000
        return
    drop_n = max(1, _LAST_SEEN_CACHE_SOFT_CAP // 10)  # 1000
    victims = sorted(cache.items(), key=lambda kv: kv[1])[:drop_n]
    for sid, _ts in victims:
        cache.pop(sid, None)
```

On every request over the 10k threshold, this performs `sorted()` on the full dict items (O(n log n) where n = 10001+). At 10k entries the cost is ~140k comparisons — measurable but not catastrophic. However: a sudden surge of unique sessions over the cap (e.g., a marketing campaign drops 50k visitors in 60s onto a 1-worker box) would do this on every request until the surge subsides.

Performance is technically out of v1 review scope per `<review_scope>` Out of Scope clause, but I am calling this out because:

1. It is documented as a "soft LRU" but actually re-sorts the entire dict every time.
2. A simple fix using `heapq.nsmallest(drop_n, cache.items(), key=lambda kv: kv[1])` would be O(n log drop_n) ≈ O(n log 1000) — meaningfully cheaper for n much greater than drop_n.
3. Or even simpler: switch `cache` to `collections.OrderedDict` and use `move_to_end` on the throttle-hit path to maintain LRU order naturally; eviction becomes `popitem(last=False)` in a loop, O(drop_n).

**Fix (defer; pure perf, no correctness issue):** Use `OrderedDict` for proper LRU, OR `heapq.nsmallest` for cheaper eviction.

---

## Low

### LOW-01: Frontend `useUser` hook does not refresh on logout

**File:** `frontend/hooks/use-user.ts` + `frontend/components/navbar.tsx:234-247`
**Issue:**

The logout flow in `navbar.tsx`:

```tsx
onSelect={async (e) => {
  e.preventDefault()
  try { await apiPost("/api/v1/auth/logout", {}) }
  catch { /* fall through */ }
  router.push("/login")
}}
```

calls `router.push("/login")` after the logout POST. The login page is outside `/dashboard/:path*`, so `proxy.ts` doesn't gate it — fine. But if the user navigates Back in their browser to a `/dashboard` page that's still in the SPA cache, `useUser` was previously populated with the now-invalid session; the page renders momentarily with the old user data before the next `apiGet('/v1/users/me')` fires and the 401-redirect happens.

This is a flash bug, not a security bug — the cookie is cleared, the API will reject all requests with the dead cookie, and `proxy.ts` is the real barrier on a fresh hard-load. But the brief flash of "logged in" UI on Back button is a UX rough edge.

**Fix:**

Either (a) call `router.replace("/login")` instead of `push` (no Back history), or (b) explicitly invalidate the user state via a context or SWR mutate before the navigation. Option (a) is the one-line fix:

```tsx
router.replace("/login")
```

`replace` removes the dashboard page from history; Back goes one step further, away from the SPA shell.

---

### LOW-02: Mock `/signup` and `/forgot-password` page.tsx files remain on disk after redirect

**File:** `frontend/app/signup/page.tsx`, `frontend/app/forgot-password/page.tsx`
**Issue:**

`next.config.mjs` adds 307 redirects `/signup -> /login` and `/forgot-password -> /login`, but the original page.tsx files (180 + 119 lines, both fully mock with `setTimeout(1000)` fake submit, the signup page's submit-then-router.push("/dashboard") will be blocked by `proxy.ts`) are still on disk. Commit `e435d30` explicitly states: "existing app/signup/page.tsx and app/forgot-password/page.tsx files stay on disk untouched per the scope-boundary rule."

These files:
- Are **not reachable in the running app** because the Next config redirect fires before the app router renders (verified live in commit message).
- Will appear in IDE search, grep, and code review noise as "implemented signup flow" when in fact it's dead code.
- Contain `await new Promise(resolve => setTimeout(resolve, 1000)); router.push("/dashboard")` which is an exact match for the "mock UI shipped to prod" anti-pattern called out in CLAUDE.md golden rule 2 — even though it cannot execute, a future developer who clicks through and hits `/signup?_next=` or removes the redirect block would suddenly have a fake signup that 302s to dashboard with no auth.

**Fix (defer to a cleanup phase; not security-critical because the redirect prevents reachability):**

Replace the two page.tsx bodies with a 1-line `redirect("/login")` call from `next/navigation` so that even if the next.config redirect were removed, the route still falls through to the login page. Or just delete the files — Next 16 will 404 the route, and the redirect handles user-facing UX.

---

### LOW-03: `auth.py::_clear_session_cookie` does not also expire the cookie via `expires=`

**File:** `api_server/src/api_server/routes/auth.py:101-111`
**Issue:**

```python
def _clear_session_cookie(resp: Response, settings) -> None:
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=(settings.env == "prod"),
        path="/",
    )
```

Modern browsers honor `Max-Age=0` and clear the cookie immediately. RFC 6265 also defines `Expires=Thu, 01 Jan 1970 00:00:00 GMT` as the legacy mechanism. Some old user agents (looking at you, embedded WebViews and ancient mobile browsers) honor `Expires` but not `Max-Age`. Setting both is the belt-and-braces convention.

Practical impact in 2026 is near-zero — every browser users would actually use respects `Max-Age=0`. Flagging only because cookie clearing is the only path for client-side session removal and a 100% reliable clear is worth two extra characters.

**Fix (optional, very low priority):**

```python
from datetime import datetime, timezone
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

resp.set_cookie(
    ...
    max_age=0,
    expires=EPOCH,
    ...
)
```

---

## Info

### INFO-01: `_resolve_or_fail` reads but does not return `oauth_state_secret`

**File:** `api_server/src/api_server/auth/oauth.py:115-117`
**Issue:**

```python
_resolve_or_fail(settings, "oauth_state_secret", _DEV_STATE_SECRET)
```

The return value is discarded. The comment explains: *"the state secret is consumed by Starlette's built-in SessionMiddleware during app construction."* Indeed `main.py:234-236` reads it directly:

```python
secret_key=(
    settings.oauth_state_secret
    or "dev-oauth-state-key-not-for-prod-0000000000000000"
),
```

So the call to `_resolve_or_fail` here serves only one purpose: in prod, raise if the secret is missing. The actual value used by Starlette is fetched separately. This works but is fragile:

1. The dev-fallback string in `main.py:236` is duplicated from `_DEV_STATE_SECRET` in `oauth.py:56`. If one is updated and not the other, the cookie signature won't match across modules in some failure mode.
2. If `_resolve_or_fail` returned the resolved value and `main.py` consumed that single source, the dev fallback would live in one place.

**Fix (drift prevention; not a current bug):**

Have `get_oauth` return a tuple `(OAuth, str)` where the second element is the resolved state secret, OR expose a helper `resolve_state_secret(settings) -> str` that both `get_oauth` and `main.create_app` call.

---

### INFO-02: `_DEV_STATE_SECRET` is 48 chars; `itsdangerous` accepts any length but a short-key warning is normal

**File:** `api_server/src/api_server/auth/oauth.py:56`
**Issue:**

```python
_DEV_STATE_SECRET = "dev-oauth-state-key-not-for-prod-0000000000000000"
```

48 characters, predictable, dev-only. The constant is correctly gated (only used when `AP_ENV != prod`) and the test `test_dev_placeholder_constants_are_non_secret` asserts `"not-for-prod" in _DEV_STATE_SECRET`. No issue. Just noting that running tests against this dev placeholder will produce a low-entropy signing key in `itsdangerous`'s view; if `itsdangerous` ever begins emitting a warning for short keys (it currently does not), that warning would surface in the test logs. Defensive constant, no action needed.

---

## Things explicitly checked and FOUND CLEAN

These are points the prompt asked about that I verified and where no issue was found:

1. **Cookie security (HttpOnly + SameSite=Lax + Secure-when-prod):** `auth.py:90-98` is correct. `_set_session_cookie` and `_clear_session_cookie` both use `secure=(settings.env == "prod")`. Starlette's `SessionMiddleware` for `ap_oauth_state` uses `https_only=(settings.env == "prod")` (`main.py:241`) — same gating.
2. **No cookie leakage to logs:** `AccessLogMiddleware` uses an allowlist (`_LOG_HEADERS = {"user-agent", "content-length", "content-type", "accept", "x-request-id"}`); `Cookie` and `Set-Cookie` are absent by construction. Verified at `log_redact.py:36-42` + the docstring at `log_redact.py:18-24` documents this for 22c.
3. **No cookie leakage to outbound HTTP:** `auth/oauth.py` uses authlib for outbound calls; the Authorization Bearer is passed via `token=token` and authlib doesn't replay request cookies on OAuth provider calls. Verified by reading `authlib.integrations.starlette_client.StarletteOAuth2App.get/.post` — they construct a fresh `httpx.AsyncClient` with `OAuth2Auth` headers, no cookie jar.
4. **CSRF state mismatch handling EXACT match:** `auth.py:167` and `auth.py:241` both use `e.error == "mismatching_state"`. Test `test_oauth_failed_on_non_state_error` is the regression trap.
5. **GitHub email-fallback:** `auth.py:257-278` correctly calls `/user/emails`, picks the first `primary && verified && email`, refuses account creation if still null. Matches D-22c-OAUTH-03 verbatim. The list-comprehension pattern survives any provider that returns extra entries with `primary=false` or `verified=false`.
6. **TOCTOU / session-row race:** The `SELECT ... WHERE id = $1 AND revoked_at IS NULL AND expires_at > NOW()` query in `session.py:62-67` reads with no row lock. A logout (DELETE) racing with a request resolution can have one of two outcomes: (a) request resolves to UUID, then logout deletes — request proceeds with one stale resolution, no harm because the request handler will later look up the user and either succeed (still authenticated for this one in-flight request) or 401 if it re-checks. (b) logout deletes first, then request misses — request resolves to None and is rejected. Both outcomes are safe; there is no window where a request gets data from a fully-revoked session beyond the in-flight call. **Acceptable race.**
7. **Per-worker dict cache for last_seen throttle:** Bounded at 10_000 entries with `_maybe_evict` (see MED-04 for perf concerns); growth is bounded. No unbounded growth.
8. **fail-closed-to-None on PG outage:** `session.py:76-80` logs and falls through to `user_id = None`; the request continues unauthenticated. Confirmed semantically equivalent to a missing cookie, so protected routes 401 cleanly. The "fail-open in security sense" terminology (per Wave 2 SUMMARY) is accurate but the behavior is correct: keeping the marketing page reachable during a PG outage matters more than rejecting browse requests.
9. **Frontend redirect host fix (f9a7df9):** `auth.py:118, 201, 294` interpolate `settings.frontend_base_url` — server-controlled, not user input, no f-string injection vector. The settings default `"http://localhost:3000"` is a dev-friendly fallback that needs the operator-facing fix flagged in HIGH-01.
10. **CORS / origin checks on OAuth callback:** N/A — the callback is invoked by the IdP (Google/GitHub) following the redirect; the browser preserves the OAuth state cookie which is `SameSite=Lax`, which permits the navigation. CORS is not relevant for top-level redirects. `request.session` (Starlette's signed cookie) cryptographically validates the state nonce; that is the actual CSRF defense.
11. **Migration 006 IRREVERSIBLE:** `006_purge_anonymous.py:49-53` raises `NotImplementedError` in `downgrade()`. Confirmed.
12. **Cross-user isolation test:** `test_cross_user_isolation.py` is a thorough end-to-end test (R8 belt-and-suspenders for migration-006 evidence + alice/bob seed + 401 anonymous case). The test directly seeds via asyncpg INSERT instead of running OAuth — fine, since OAuth happy path is covered separately at `test_google_callback.py::test_happy_path_upserts_user_mints_session_sets_cookie`.

---

## Cross-File Trace Notes

**Middleware ordering (`main.py:222-245` → request-in flow):**

CorrelationId → AccessLog → StarletteSession (ap_oauth_state) → ApSession (ap_session) → RateLimit → Idempotency → route

This is correct:
- AccessLog runs before any session resolution, so it can never log session contents.
- StarletteSession populates `request.session` BEFORE OAuth callback handler reads `request.session` (authlib needs the state nonce).
- ApSession populates `scope["state"]["user_id"]` BEFORE RateLimit and Idempotency, both of which now correctly read it from `scope.get("state") or {}` (`rate_limit.py:96`, `idempotency.py:170`) for user-scoped rate-limiting and idempotency keys.

**The `scope.setdefault("state", {})["user_id"] = user_id` pattern in `session.py:82`:** I initially worried this might collide with Starlette's `State` class. After tracing the source, `scope["state"]` is always a plain `dict` at the ASGI layer (Starlette wraps it in a `State` object lazily inside `Request.state`'s property accessor). The pattern is correct.

**Type consistency at module boundaries:** `SessionUserResponse` (`models/users.py`) ↔ `SessionUser` (`frontend/lib/api.ts`): `id`, `email?`, `display_name`, `avatar_url?`, `provider?`. Pydantic shape and TS shape match. The Python model adds `created_at: datetime` which the TS shape doesn't claim — that's fine, extra fields on the wire are ignored by TS.

---

## Summary Gates

- **No CRITICAL findings.** No blockers.
- **HIGH-01** is operator-facing template gap; SHIP if your prod `.env.prod` already has `AP_FRONTEND_BASE_URL` set; FIX TEMPLATE before next operator-driven prod deploy.
- **MED-01** (`/v1/runs/{id}` unauthenticated) is a Phase 19 design choice 22c didn't address — file a v2 ticket; do not block 22c ship on it.
- **MED-02 through MED-04, LOW-01 through LOW-03, INFO-01/02:** all defer to v2 cleanup. None block ship.

**Phase 22c-oauth-google: SHIP.** The OAuth foundation is solid, well-tested, and consistent with the platform's security posture. Patch the deploy template before next prod deploy.

---

_Reviewed: 2026-04-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
