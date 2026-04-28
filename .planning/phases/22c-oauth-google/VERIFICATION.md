---
phase: 22c-oauth-google
verified: 2026-04-28T21:58:34Z
status: passed
score: 21/21 must-haves verified
overrides_applied: 0
re_verification:
  initial: true
---

# Phase 22c: oauth-google Verification Report

**Phase Goal (SPEC §Goal):** Replace `setTimeout`-theater login + the `ANONYMOUS_USER_ID` placeholder with a real OAuth flow (Google + GitHub per AMD-01) that mints a server-side session and resolves a real `user_id` on every API request, so the dashboard shows the logged-in user's own agents and sign-out actually invalidates the session.

**Verified:** 2026-04-28T21:58:34Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Must-Haves (truth set)

Truths derived from SPEC R1..R8 plus CONTEXT amendments AMD-05/06/07 plus three cross-cutting acceptance criteria (CSRF, cross-user isolation, dead-theater cleanup). All 21 truths verified against the live codebase.

### Observable Truths

| #  | Truth                                                                  | Status      | Evidence (file:line)                                                                                                                                                    |
| -- | ---------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | R1 — `GET /v1/auth/google` 302s to Google with state cookie            | PASS        | `api_server/src/api_server/routes/auth.py:128-144` — calls `oauth.google.authorize_redirect`; authlib + StarletteSessionMiddleware (`main.py:232-243`) sets `ap_oauth_state` cookie. Test: `tests/auth/test_google_authorize.py::test_google_authorize_returns_302_with_state_cookie`. |
| 2  | R1 — `GET /v1/auth/github` 302s to GitHub with state cookie (AMD-01)   | PASS        | `routes/auth.py:212-224`. Test: `tests/auth/test_github_authorize.py::test_github_authorize_returns_302_with_state_cookie`.                                              |
| 3  | R2 — Google callback exchanges code → upserts user → mints session     | PASS        | `routes/auth.py:147-204` — calls `authorize_access_token`, parses `userinfo`, `upsert_user` + `mint_session`, sets cookie via `_set_session_cookie`, redirects to `{frontend_base_url}/dashboard`. Helpers: `auth/oauth.py:159-238`. Tests: `tests/auth/test_google_callback.py::test_happy_path_upserts_user_mints_session_sets_cookie`. |
| 4  | R2 — Callback rejects state mismatch (CSRF) and surfaces error code    | PASS        | `routes/auth.py:162-170` — exact match on `e.error == "mismatching_state"` → `_login_redirect_with_error("state_mismatch")`. Tests: `test_google_callback.py::test_state_mismatch_redirects_to_login_error`, `test_github_callback.py::test_state_mismatch_redirects_to_login_error`. |
| 5  | R2 — GitHub callback handles `/user/emails` fallback (D-22c-OAUTH-03)  | PASS        | `routes/auth.py:258-276` — second call to `oauth.github.get("user/emails")` filters `primary AND verified`. Test: `test_github_callback.py::test_happy_path_falls_back_to_user_emails_when_primary_private`. |
| 6  | R3 — SessionMiddleware resolves `request.state.user_id` from cookie    | PASS        | `middleware/session.py:42-83` — extracts `ap_session`, fetches PG row filtered by `revoked_at IS NULL AND expires_at > NOW()`, sets `scope.state.user_id`. Wired in `main.py:231` between `StarletteSessionMiddleware` and `RateLimitMiddleware`. Tests: `tests/middleware/test_session_middleware.py` (no-cookie, valid, expired, revoked, malformed, PG-outage cases). |
| 7  | R3 — `ANONYMOUS_USER_ID` removed from routes + middleware              | PASS        | `grep -r "ANONYMOUS_USER_ID" api_server/src/api_server/routes/ api_server/src/api_server/middleware/` returns 0 hits. Constant deleted from `constants.py:1-17` (only docstring mention remains; AMD-03 + D-22c-MIG-06 forcing-function discipline). |
| 8  | R3 — Idempotency middleware reads `request.state.user_id`              | PASS        | `middleware/idempotency.py:170-174` reads `scope['state']['user_id']`, skips reservation when None (anonymous fall-through). Test: `tests/middleware/test_idempotency_user_id.py`. |
| 9  | R4 — `GET /v1/users/me` returns the authenticated user                 | PASS        | `routes/users.py:23-65` — `require_user` gate, then `SELECT id, email, display_name, avatar_url, provider, created_at`, returns `SessionUserResponse` (`models/users.py:16-36`). |
| 10 | R4 — `GET /v1/users/me` returns 401 when no session                    | PASS        | `auth/deps.py:37-72` — `require_user` returns 401 `JSONResponse` with Stripe-shape `unauthorized` envelope (`models/errors.py:46`); cross-user isolation test STEP 6 asserts `body.error.code == "UNAUTHORIZED"` + `param == "ap_session"`. |
| 11 | R5 — `POST /v1/auth/logout` deletes sessions row + clears cookie + 204 | PASS        | `routes/auth.py:305-344` — `require_user` gate, `DELETE FROM sessions WHERE id = $1`, `Response(status_code=204)` + `_clear_session_cookie` (`Max-Age=0`). Test: `tests/auth/test_logout.py::test_logout_204_invalidates_session` + `test_logout_without_cookie_returns_401`. |
| 12 | R6 — Login page has zero `setTimeout` (no auth theater)                | PASS        | `grep -c setTimeout frontend/app/login/page.tsx` returns 0. `frontend/app/login/page.tsx:27-32` — `onGoogle` and `onGitHub` set `window.location.href = '/api/v1/auth/{provider}'`. Email/password form preserved but `disabled` (D-22c-UI-01). |
| 13 | R7 — Dashboard layout renders the real user (no "Alex Chen")           | PASS        | `grep -c "Alex Chen"` returns 0 in both `frontend/app/dashboard/layout.tsx` and `frontend/components/navbar.tsx`. Layout uses `useUser()` hook (`hooks/use-user.ts`) → `apiGet<SessionUser>('/api/v1/users/me')`; passes `display_name`, `email`, `avatar_url` to Navbar (`layout.tsx:46-57`). |
| 14 | R7 — Sign-out wires to `apiPost('/api/v1/auth/logout')` then redirects | PASS        | `frontend/components/navbar.tsx:234-250` — DropdownMenuItem `onSelect` calls `await apiPost("/api/v1/auth/logout", {})` then `router.push("/login")`, with try/catch fallthrough so server-side already-revoked session still completes the UX. |
| 15 | R8 — Migration 006 truncates all 8 data-bearing tables (AMD-04)        | PASS        | `alembic/versions/006_purge_anonymous.py:37-46` — `TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users CASCADE`. Belt-and-suspenders pre-assertion in `tests/auth/test_cross_user_isolation.py:50-74` checks COUNT=0 for all 8 tables AND `version_num='006_purge_anonymous'`. |
| 16 | R8 — Migration 006 is irreversible (downgrade raises)                  | PASS        | `006_purge_anonymous.py:49-53` — `def downgrade()` raises `NotImplementedError("…irreversible…")`. |
| 17 | AMD-05 — `respx` (not `responses`) is the dev test stub                | PASS        | `api_server/pyproject.toml` declares `respx>=0.22,<0.24` (with comment justifying upgrade past CONTEXT pin to support httpx 0.28 transitively required by authlib 1.6.11 — empirical SPIKE-A finding). Spike artifact: `.planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md`. |
| 18 | AMD-06 — `frontend/proxy.ts` exists; no stale `frontend/middleware.ts` | PASS        | `frontend/proxy.ts:1-30` — Next.js 16.2 file-convention rename observed; matcher `["/dashboard/:path*"]`; cookie-presence gate (no validation — that's server-side). `ls frontend/middleware.ts` → No such file or directory. |
| 19 | AMD-07 — `AP_OAUTH_STATE_SECRET` wired (Settings + fail-loud + Starlette session) | PASS | `config.py:82-84` Pydantic field; `auth/oauth.py:115-117` calls `_resolve_or_fail` which raises `RuntimeError` in prod when missing; `main.py:232-243` plugs the secret into Starlette's `SessionMiddleware`. Tests: `tests/auth/test_oauth_config.py::test_get_oauth_prod_raises_when_state_secret_missing`. |
| 20 | SPEC-AC-CSRF — Callback with mismatched state returns 4xx              | PASS        | Same evidence as truth #4. authlib raises `OAuthError(error="mismatching_state")`; route emits 302 to `/login?error=state_mismatch` (frontend toasts). Note: SPEC originally specified 400; D-22c-FE-03 amended to 302+toast for UX. The CSRF defense is intact at the canonical-error-code level. |
| 21 | SPEC-AC-Cross-user-isolation — 2 users each see only their own agents  | PASS        | `tests/auth/test_cross_user_isolation.py:37-166` seeds two users + two sessions + two agents via direct asyncpg INSERT, asserts `agent_a` only in alice's `/v1/agents` and `agent_b` only in bob's, plus 401 + Stripe-envelope on anonymous request. Per SUMMARY ran in 4.60s. |

**Score:** 21/21 truths verified (100%)

---

### Required Artifacts (Level 1+2+3+4)

| Artifact                                                          | Expected                                                                | Exists | Substantive | Wired | Data Flows | Status     |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------- | ------ | ----------- | ----- | ---------- | ---------- |
| `api_server/alembic/versions/005_sessions_and_oauth_users.py`     | Adds users.sub/avatar_url/last_login_at + `UNIQUE(provider,sub)` partial + sessions table | Yes    | Yes (141 LOC, mirrors 003/004 idiom) | Yes (head migration via conftest) | Yes (rows from upsert_user / mint_session land here) | VERIFIED   |
| `api_server/alembic/versions/006_purge_anonymous.py`              | TRUNCATE ALL 8 data tables CASCADE                                      | Yes    | Yes (TRUNCATE statement enumerates 8 tables) | Yes (down_revision='005' chains correctly) | Yes (confirmed by belt-and-suspenders pre-assertion) | VERIFIED   |
| `api_server/src/api_server/auth/oauth.py`                         | OAuth registry + upsert_user + mint_session                             | Yes    | Yes (239 LOC, dev fallbacks + prod fail-loud + ON CONFLICT upsert) | Yes (imported by main.py:32 + routes/auth.py:53) | Yes (creates real users + sessions rows) | VERIFIED   |
| `api_server/src/api_server/auth/deps.py`                          | `require_user(request) -> JSONResponse | UUID`                          | Yes    | Yes (75 LOC, defensive UUID coerce path) | Yes (imported by 6 route files) | Yes (returns Stripe envelope or real UUID) | VERIFIED   |
| `api_server/src/api_server/middleware/session.py`                 | ASGI middleware + cookie parsing + last_seen throttle                   | Yes    | Yes (147 LOC, in-memory cache + LRU eviction + fail-closed) | Yes (`main.py:231` `app.add_middleware(ApSessionMiddleware)`) | Yes (queries sessions table, populates request.state.user_id) | VERIFIED   |
| `api_server/src/api_server/routes/auth.py`                        | 5 routes — google/github authorize+callback + logout                    | Yes    | Yes (366 LOC, exact-match state-error handling + GitHub email fallback) | Yes (`main.py:288` `app.include_router(auth_route.router, prefix="/v1")`) | Yes (real OAuth round-trip; SUMMARY confirms manual smoke PASS) | VERIFIED   |
| `api_server/src/api_server/routes/users.py`                       | `GET /v1/users/me`                                                      | Yes    | Yes (65 LOC, 401 on missing session + 401 on deleted user) | Yes (`main.py:289` `app.include_router(users_route.router, prefix="/v1")`) | Yes (returns real user data from PG) | VERIFIED   |
| `api_server/src/api_server/models/users.py::SessionUserResponse`  | Pydantic model matching frontend SessionUser type                       | Yes    | Yes (id, email?, display_name, avatar_url?, provider?, created_at) | Yes (used by users.py route response_model) | Yes (round-trip via SessionUserResponse(**dict(row))) | VERIFIED   |
| `api_server/src/api_server/config.py`                             | 7 OAuth env vars + frontend_base_url + state_secret                     | Yes    | Yes (7 fields + frontend_base_url with default) | Yes (read by oauth.py + auth.py) | Yes (settings.frontend_base_url consumed at runtime) | VERIFIED   |
| `frontend/proxy.ts`                                               | Next 16 edge gate on /dashboard/:path*                                  | Yes    | Yes (30 LOC, 307 redirect when cookie absent) | Yes (matcher config → Next runtime picks it up) | Yes (gate fires per request, blocks pre-render flash) | VERIFIED   |
| `frontend/app/login/page.tsx`                                     | Real OAuth buttons + error toasts + no setTimeout                       | Yes    | Yes (170 LOC, sonner toasts on ?error=) | Yes (Next router serves at /login) | Yes (handlers execute window.location.href to API) | VERIFIED   |
| `frontend/hooks/use-user.ts`                                      | Hook fetches /api/v1/users/me + 401 redirect                            | Yes    | Yes (47 LOC, cancellable effect + 401 push to /login) | Yes (imported by dashboard/layout.tsx) | Yes (returns real SessionUser to consumers) | VERIFIED   |
| `frontend/app/dashboard/layout.tsx`                               | Layout passes real user to Navbar (no "Alex Chen")                      | Yes    | Yes (117 LOC, eager render with skeleton fallback) | Yes (Next router shell for /dashboard/*) | Yes (sessionUser flows from useUser → Navbar prop) | VERIFIED   |
| `frontend/components/navbar.tsx`                                  | Real Log out button calling apiPost                                     | Yes    | Yes (line 234-250 onSelect, try/catch + redirect) | Yes (imported by layout) | Yes (apiPost hits backend logout) | VERIFIED   |
| `frontend/next.config.mjs::redirects()`                           | /signup + /forgot-password → /login                                     | Yes    | Yes (lines 38-43, permanent: false → 307) | Yes (Next config consumed at build) | N/A (config-level, no data flow) | VERIFIED   |
| `tools/Dockerfile.api`                                            | Runtime deps include authlib + itsdangerous + httpx                     | Yes    | Yes (line 26 — three deps in one pip install) | Yes (image build + container run) | Yes (manual smoke confirmed container boots) | VERIFIED   |
| `api_server/tests/auth/test_cross_user_isolation.py`              | 2-user isolation + R8 belt-and-suspenders + anon 401                    | Yes    | Yes (166 LOC, 6-step test) | Yes (pytest discovers via tests/auth/) | Yes (per SUMMARY: passes in 4.60s against testcontainers PG) | VERIFIED   |
| `test/22c-manual-smoke.md`                                        | 6-scenario human checklist                                              | Yes    | Yes (file present) | N/A (human-action artifact) | N/A | VERIFIED   |
| `.planning/phases/22c-oauth-google/spike-evidence/spike-a-respx-authlib.md` | Wave 0 SPIKE-A artifact                                       | Yes    | Yes | N/A (evidence document) | N/A | VERIFIED   |
| `.planning/phases/22c-oauth-google/spike-evidence/spike-b-truncate-cascade.md` | Wave 0 SPIKE-B artifact                                    | Yes    | Yes | N/A (evidence document) | N/A | VERIFIED   |

---

### Key Link Verification

| From                                | To                                       | Via                                     | Status | Detail                                                                       |
| ----------------------------------- | ---------------------------------------- | --------------------------------------- | ------ | ---------------------------------------------------------------------------- |
| `main.py::create_app`               | `SessionMiddleware`                      | `app.add_middleware(ApSessionMiddleware)` (line 231) | WIRED  | Order verified: `CorrelationId → AccessLog → StarletteSession → ApSession → RateLimit → Idempotency` (D-22c-AUTH-01). |
| `main.py::create_app`               | `auth_route.router`                      | `app.include_router(..., prefix="/v1")` (line 288) | WIRED  | All 5 OAuth routes registered with `/v1` prefix. |
| `main.py::create_app`               | `users_route.router`                     | `app.include_router(..., prefix="/v1")` (line 289) | WIRED  | `/v1/users/me` registered. |
| `routes/auth.py`                    | `auth/oauth.py::get_oauth`               | imported on line 53                     | WIRED  | Both google + github providers registered through this registry. |
| `routes/auth.py`                    | `auth/oauth.py::upsert_user/mint_session`| imported on line 53                     | WIRED  | Used in google_callback + github_callback. |
| Routes (`agents`, `runs`, `users`, etc.) | `auth/deps.py::require_user`        | imported across 6 files                 | WIRED  | Verified 9 distinct call sites via grep `require_user\(request\)`. |
| `middleware/session.py`             | `app.state.db` pool                      | `asgi_app.state.db.acquire()` (line 60) | WIRED  | Connection-per-scope discipline — never held across long await. |
| `middleware/idempotency.py`         | `request.state.user_id`                  | `scope.state.user_id` (line 171)        | WIRED  | Anonymous → skip reservation; authenticated → key cache by user_id. |
| `frontend/hooks/use-user.ts`        | `/api/v1/users/me`                       | `apiGet<SessionUser>('/api/v1/users/me')` (line 26) | WIRED  | Round-trip → 401 redirect or hydrated user object. |
| `frontend/app/dashboard/layout.tsx` | `Navbar.user` prop                       | `sessionUser ? { name, email, avatar }` (line 49-55) | WIRED  | display_name → name (D-22c-MIG-01 mapping). |
| `frontend/components/navbar.tsx`    | `/api/v1/auth/logout`                    | `apiPost("/api/v1/auth/logout", {})` (line 239) | WIRED  | Real button onSelect, not Link theater. |
| `frontend/app/login/page.tsx`       | `/api/v1/auth/{provider}`                | `window.location.href = '/api/v1/auth/google'` (line 28) and `…/github` (line 31) | WIRED  | Top-level navigation required for OAuth — fetch() can't follow 302 chain. |
| `routes/auth.py`                    | `settings.frontend_base_url`             | line 117, 200, 293                      | WIRED  | F-string concatenation produces absolute redirect URL — fixes the 22c-09 plan-gap (`localhost:8000/dashboard` 404). |
| `auth/oauth.py::upsert_user`        | `users.UNIQUE(provider, sub) WHERE sub IS NOT NULL` | `ON CONFLICT (provider, sub) WHERE sub IS NOT NULL DO UPDATE` (line 185) | WIRED  | Cross-plan invariant — partial unique index in 005 mirrored byte-for-byte. |
| `frontend/proxy.ts::matcher`        | `/dashboard/:path*` route gate           | `config = { matcher: ["/dashboard/:path*"] }` (line 25-29) | WIRED  | Edge-runtime check, fires before React renders. |

All 15 key links verified.

---

### Data-Flow Trace (Level 4)

| Artifact                          | Data Variable        | Source                                    | Real Data | Status     |
| --------------------------------- | -------------------- | ----------------------------------------- | --------- | ---------- |
| `routes/users.py`                 | `row` (asyncpg Record) | `SELECT users WHERE id = user_id`       | Yes       | FLOWING    |
| `routes/agents.py`                | `rows`               | `services/run_store.py::list_agents` filters by `user_id` | Yes       | FLOWING    |
| `middleware/session.py`           | `user_id`            | `SELECT user_id FROM sessions WHERE id=...` | Yes       | FLOWING    |
| `routes/auth.py::google_callback` | `userinfo`           | `oauth.google.userinfo()` via authlib + httpx | Yes       | FLOWING    |
| `routes/auth.py::github_callback` | `profile`, `emails`  | `oauth.github.get("user")` + `get("user/emails")` | Yes       | FLOWING    |
| `frontend/hooks/use-user.ts`      | `user`               | `apiGet<SessionUser>('/api/v1/users/me')` | Yes       | FLOWING    |
| `frontend/app/dashboard/layout.tsx` | `sessionUser` → Navbar `user` prop | `useUser()` hook | Yes       | FLOWING    |

No hollow props. No hardcoded fallbacks at call sites. Manual smoke (per SUMMARY) confirmed display_name + avatar render the real Gmail account name end-to-end.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| ANONYMOUS_USER_ID purge from routes/middleware | `grep -r ANONYMOUS_USER_ID api_server/src/api_server/routes/ middleware/` | 0 hits | PASS |
| ANONYMOUS_USER_ID constant deleted | `grep ANONYMOUS_USER_ID api_server/src/api_server/constants.py` | only docstring mention; no export | PASS |
| `setTimeout` removed from login page | `grep -c setTimeout frontend/app/login/page.tsx` | 0 | PASS |
| "Alex Chen" removed from layout + navbar | `grep -c "Alex Chen" frontend/app/dashboard/layout.tsx frontend/components/navbar.tsx` | 0 / 0 | PASS |
| `proxy.ts` exists, `middleware.ts` retired | `test -f frontend/proxy.ts && ! test -f frontend/middleware.ts` | both gates true | PASS |
| Migration files chain 005 → 006 | `head -50 alembic/versions/006*.py` | `down_revision = "005_sessions_and_oauth_users"` confirmed | PASS |
| Manual smoke (4 OAuth scenarios + 2 curl) | reported by human operator (per 22c-09-SUMMARY) | all 6 PASS | PASS |
| Cross-user isolation integration test | per SUMMARY: 4.60s green | PASS | PASS |
| Spike artifacts present | `ls .planning/phases/22c-oauth-google/spike-evidence/` | spike-a + spike-b both committed | PASS |

All 9 spot-checks PASS. Live container boot, manual browser flows, and integration-test evidence collected during the smoke gate (per 22c-09-SUMMARY) are captured in commit `f9a7df9` (the OAuth callback host fix that unblocked Scenarios 1+2).

---

### Requirements Coverage

| REQ | Description (SPEC) | Source Plan | Status | Evidence |
| --- | ------------------ | ----------- | ------ | -------- |
| R1  | Google authorize endpoint 302s with state cookie | 22c-04 | SATISFIED | Truth #1 + #2 |
| R2  | Google callback exchanges code → user → session | 22c-04 | SATISFIED | Truth #3 + #4 + #5 |
| R3  | Session middleware resolves user_id from cookie | 22c-05, 22c-06 | SATISFIED | Truth #6 + #7 + #8 |
| R4  | `GET /v1/users/me` returns authenticated user | 22c-05 | SATISFIED | Truth #9 + #10 |
| R5  | `POST /v1/auth/logout` invalidates session | 22c-05 | SATISFIED | Truth #11 |
| R6  | Frontend login button starts real OAuth flow | 22c-07 | SATISFIED | Truth #12 |
| R7  | Frontend layout shows real user (not "Alex Chen") | 22c-07 | SATISFIED | Truth #13 + #14 |
| R8  | ANONYMOUS-keyed agents purged via migration 006 | 22c-02, 22c-06 | SATISFIED | Truth #15 + #16 |
| AMD-01 | Both Google + GitHub ship in 22c | 22c-04 | SATISFIED | Truth #2 + #5 |
| AMD-02 | Refresh-token storage DROPPED | 22c-04 | SATISFIED | `auth/oauth.py` registers Google scope `"openid email profile"` only (line 127) — no `access_type=offline`; no refresh-token column; `crypto/age_cipher.py` deliberately not imported by 22c code paths. |
| AMD-03 | ANONYMOUS user row deleted | 22c-06 | SATISFIED | Truth #15 (TRUNCATE includes `users`) |
| AMD-04 | Migration 006 purges ALL data tables | 22c-06 | SATISFIED | Truth #15 |
| AMD-05 | `respx` is the dev test stub | 22c-01 | SATISFIED | Truth #17 |
| AMD-06 | `proxy.ts` (not `middleware.ts`) | 22c-08 | SATISFIED | Truth #18 |
| AMD-07 | `AP_OAUTH_STATE_SECRET` wired (config + fail-loud + Starlette session) | 22c-03 | SATISFIED | Truth #19 |

Total: **8 SPEC requirements + 7 amendments = 15/15 SATISFIED**. Plus 6 acceptance-criterion truths (CSRF defense, cross-user isolation, dead-theater redirects, Dockerfile drift fix, frontend host redirect fix, manual smoke gate).

No orphaned requirements detected. The verifier's 21 truths fully cover SPEC R1-R8, AMD-01..07, and the 12 SPEC acceptance criteria.

---

### Anti-Patterns Scan

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| (none) | - | TODO/FIXME/PLACEHOLDER in 22c-touched files | - | No blockers found |

Targeted scan ran on the 10 files modified by 22c-09 plus the 6 new modules from 22c-04..08. Only documentation comments mention ANONYMOUS_USER_ID; no hardcoded `[]`/`{}`/`null` returns; no `setTimeout` theater; no `console.log`-only handlers. The codebase is genuinely substantive.

---

### Human Verification

**Already complete.** The user reports the manual smoke gate PASSED for all 4 browser scenarios:
1. Google happy path → `/dashboard` with real Gmail name in navbar
2. GitHub happy path → `/dashboard` with real GitHub display name
3. `?error=access_denied` → `/login?error=access_denied` with toast
4. Logout invalidation: cookie replay after logout returns 401

Plus the 2 curl-automatable scenarios (dashboard 307 gate + dead-route redirects).

No further human verification needed for goal acceptance.

---

### Out-of-Scope Findings (NOT counted as gaps — per task instructions)

These were explicitly logged as 22c.1 candidates by the executor and confirmed out-of-scope by the user:

1. `/playground` page hardcoded "Alex Chen" — pre-existing mock leftover, not in 22c file ownership
2. `/#playground` fragment bug on Launch CTA — UX polish, not OAuth identity
3. Persistent+Telegram default UX in agent-deploy step 2.5 — UX polish
4. Long-term: Dockerfile reads from pyproject.toml — drift-prevention, not 22c scope

Plus per `deferred-items.md`, 9 test failures + 3 errors in the broader regression run are pre-existing (Phase 19 baseline `name`-NOT-NULL chore, BusyBox tail flake, recipe v0.1→v0.2 in flight, test_anonymous_user_seeded obsoleted by migration 006).

---

## Goal Achievement Summary

**Phase goal:** "Replace setTimeout-theater login + ANONYMOUS_USER_ID placeholder with real OAuth identity..."

The phase delivered exactly that, plus the AMD-01 expansion to two providers:

- **setTimeout theater is gone** (R6 — verified at the grep level + login page rewrite). 
- **ANONYMOUS_USER_ID is gone** (R3 + AMD-03 + D-22c-MIG-06 — verified across routes, middleware, AND constants.py. The forcing-function discipline worked: deleting the constant turned every residual import into a build error, which was then fixed plan-by-plan).
- **Real OAuth identity flows end-to-end** for both Google and GitHub (R1 + R2 + AMD-01 — verified by both the integration-test layer using respx-stubbed provider endpoints AND the human-driven manual smoke gate which exercised the real Google + GitHub consent screens).
- **Dashboard shows the logged-in user, not "Alex Chen"** (R7 — verified by grep + by manual smoke confirmation that the real Gmail name renders).
- **Sign-out actually invalidates** (R5 + manual smoke scenario 4 — verified by both the `tests/auth/test_logout.py::test_logout_204_invalidates_session` integration test AND the human cookie-replay test).
- **Cross-user isolation proven** (SPEC AC-11 — `test_cross_user_isolation.py` seeds two distinct OAuth users + sessions, verifies each `/v1/agents` view contains only that user's agents, plus 401 + Stripe-shape envelope on anonymous).
- **Migration 006 purged all dev data** (R8 + AMD-04 — TRUNCATE CASCADE on 8 tables; belt-and-suspenders pre-assertion in cross-user test catches any silent skip).

The three plan-gap fixes that surfaced during the manual smoke gate (Dockerfile authlib+itsdangerous, runtime httpx, OAuth callback frontend host) were caught and fixed in-scope under the 22c-09 plan number — exactly the surface-don't-hide doctrine the gate was designed to enforce. They are now part of the phase's atomic git history (commits `4f7d8b0`, `fdf3924`, `f9a7df9`).

**Phase 22c is the OAuth identity foundation that unblocks every dashboard sub-page in the milestone.** It ships clean.

---

## Overall Verdict

**PASS — Phase 22c verified end-to-end against the live codebase.**

- **Truths:** 21/21 PASS
- **Artifacts:** 20/20 verified at all four levels (exists, substantive, wired, data-flowing)
- **Key links:** 15/15 wired
- **Spot-checks:** 9/9 PASS
- **Requirements:** 15/15 SATISFIED (8 SPEC R + 7 AMD)
- **Anti-patterns:** 0 blockers
- **Human verification:** complete (manual smoke gate PASS)
- **Pre-existing test failures:** correctly deferred per `deferred-items.md`; not counted as gaps

The single minor documentation-comment issue (cross-user isolation test references `tests/test_migration_005_sessions_and_users_columns.py` which doesn't exist as a standalone file) is a stylistic nit — the migration is implicitly verified by the conftest's `alembic upgrade head` cycle, the SPIKE-B artifact, and the cross-user test's own belt-and-suspenders pre-assertion. No remediation required.

The milestone close-out gate is green. Phase 22c is ready for the parent milestone to advance.

---

_Verified: 2026-04-28T21:58:34Z_
_Verifier: Claude (gsd-verifier, Opus 4.7 1M)_
