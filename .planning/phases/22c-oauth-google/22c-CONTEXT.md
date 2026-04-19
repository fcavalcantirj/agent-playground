# Phase 22c: oauth-google — Context

**Gathered:** 2026-04-19
**Amended:** 2026-04-19 (AMD-05/06/07 + D-22c-TEST-03 + D-22c-MIG-05 refinement, post-RESEARCH.md)
**Status:** Ready for planning
**Supersedes:** 22c-SPEC.md scope in seven places — see `<spec_amendments>` below.
**Blocks:** Multi-tenant dashboard (every /dashboard/* page behind real auth), BYOK per-user keys (/dashboard/api-keys), the ACTION-LIST frontend P1 rebuilds.
**Blocked by:** Nothing — SPEC sealed, 8 reqs + 3 locked decisions, creds provisioned.

<domain>
## Phase Boundary

Replace the `setTimeout`-theater login + the `ANONYMOUS_USER_ID` placeholder with a **real multi-provider OAuth flow** (Google + GitHub) that mints a server-side session and resolves a real `user_id` on every API request. Scope covers: backend auth routes + session middleware + `/v1/users/me` + `/v1/auth/logout` + `sessions` table + `users` column expansion, full data purge migration, frontend login rewrite + dashboard layout rewrite + sign-out wire-up + dead-theater cleanup (/signup + /forgot-password redirects).

**Out of scope:** email/password login (UI disabled with copy), refresh-token storage (dropped vs SPEC — see amendments), deep-link preservation after login, magic-link flow, admin session listing, MTProto harness.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**8 requirements locked.** See `22c-SPEC.md` for full text, boundaries, and acceptance criteria. Downstream agents MUST read `22c-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- Google OAuth (login + callback + logout + session middleware + /v1/users/me)
- Server-table session storage (new `sessions` table; opaque cookie carrying `session_id`)
- ANONYMOUS_USER_ID purge migration (alembic 006)
- Frontend: real login button + layout rewrite + sign-out
- CSRF protection via per-request state token

**Out of scope (from SPEC.md):**
- Email/password login (UI present but disabled)
- Multi-account linking
- Magic-link / forgot-password
- Rate-limiting on auth routes (uses existing middleware)
- PKCE (deferred — state-token sufficient for confidential client)
- Refresh-token rotation

</spec_lock>

<spec_amendments>
## SPEC.md Amendments from this discussion

Seven amendments. CONTEXT.md takes precedence over SPEC.md for these items; planner must follow CONTEXT.md.

Four decided on 2026-04-19 (pre-research):

- **AMD-01 — Scope expanded: GitHub OAuth moves from 22c.1 → 22c.** User decision: ship both providers in a single phase. Backend substrate is identical (authlib + `UNIQUE(provider, sub)` covers both), the incremental cost is small, and the login UI needs both buttons wired to avoid dead-theater. SPEC §Boundaries "GitHub OAuth — defer to Phase 22c.1" is overridden.
- **AMD-02 — Refresh-token storage DROPPED.** SPEC R2 says "exchanges code for tokens (access + id + refresh)" + "encrypts refresh_token via age-KEK keyed by user_id". Amended: do NOT request `access_type=offline`; do NOT receive a refresh_token; do NOT reach for `crypto/age_cipher.py`. Justification: 22c only uses the providers for identity (email, sub, name, avatar). We never call Google/GitHub APIs on the user's behalf in this phase. SPEC's refresh-token acceptance criterion ("Refresh token round-trip: encrypt via age-KEK, store in PG, re-fetch + decrypt…") is DROPPED. When a future feature needs Google Calendar / GitHub repos on behalf of the user, add offline scope + refresh-token storage then.
- **AMD-03 — ANONYMOUS users row DELETED in migration 006.** SPEC R8 said "may stay (audit trail) or also delete — operator's call". Decision: DELETE. The `ANONYMOUS_USER_ID` constant is removed from `constants.py`; any reference becomes a build error (the forcing function for complete cleanup).
- **AMD-04 — Migration 006 purge scope WIDENED.** SPEC R8 said `DELETE FROM agent_instances WHERE user_id=ANONYMOUS_USER_ID`. Amended: migration 006 TRUNCATEs ALL data-bearing tables — `agent_instances`, `agent_containers`, `runs`, `agent_events`, `idempotency_keys`, `rate_limit_counters`, and the `users` row for ANONYMOUS. Every row in the live DB is mock dev data from Phase 19/22 execution; no real users exist yet. Clean slate. Schema and `alembic_version` are preserved.

Three added 2026-04-19 (post-research, from RESEARCH.md findings):

- **AMD-05 — Test stub library: `respx` (NOT `responses`).** D-22c-TEST-01 originally prescribed the `responses` library. Research surfaced that authlib's Starlette/FastAPI integration uses **httpx** (not `requests`), so `responses` cannot intercept authlib's outbound calls. Correct tool is **`respx`** (an httpx-native mock library, actively maintained). All integration-test stubbing for Google's `oauth2.googleapis.com/token` + `openidconnect.googleapis.com/v1/userinfo` AND GitHub's `/login/oauth/access_token` + `/user` + `/user/emails` uses `respx`. The "real authlib + network-layer stubs, NOT mocked authlib internals" rule from SPEC §Constraints still applies. Add `respx` to dev deps.
- **AMD-06 — Next.js gate file: `frontend/proxy.ts` (NOT `middleware.ts`).** D-22c-FE-01 originally said "new file `frontend/middleware.ts` runs on every request matching `/dashboard/:path*`". Research surfaced that Next.js 16.2 renamed `middleware.ts` → `proxy.ts` (2025-10-21). Correct file is `frontend/proxy.ts` with the same matcher config and cookie-presence check. Any existing (incorrectly commented) `frontend/middleware.ts` is retired in this phase.
- **AMD-07 — New env var: `AP_OAUTH_STATE_SECRET`.** authlib's OAuth2 flow REQUIRES Starlette's built-in `SessionMiddleware` for CSRF state storage (state lives in `request.session`, not our custom cookie). Our stack gains **two** session middlewares: Starlette's built-in (signed cookie `ap_oauth_state`, 10-minute TTL, holds the state token between authorize-redirect and callback) + our custom `SessionMiddleware` (opaque cookie `ap_session`, 30-day TTL, resolves `request.state.user_id` from PG). `AP_OAUTH_STATE_SECRET` is the Starlette signing key. Pattern mirrors `AP_CHANNEL_MASTER_KEY` / `AP_SYSADMIN_TOKEN`: required in prod (fail-loud at boot per `crypto/age_cipher.py::_master_key`), optional in dev (auto-generated fallback). Add to `config.py` Pydantic settings, to `deploy/.env.prod` (real value), and to `deploy/.env.prod.example` (placeholder + docstring).

</spec_amendments>

<decisions>
## Implementation Decisions

### Migrations & Users Schema

- **D-22c-MIG-01 — `display_name` reused for Google/GitHub `name`.** No new `users.name` column. OAuth callbacks write the provider's name into `display_name`. Frontend `SessionUser.display_name` (already defined in `frontend/lib/api.ts`) stays unchanged. SPEC R4's `/v1/users/me` response uses the `display_name` key semantically (SPEC wording 'name' is the field meaning, not the literal column name).
- **D-22c-MIG-02 — Alembic 005 = sessions table + users column additions in one atomic migration.** Columns added: `users.sub TEXT`, `users.avatar_url TEXT`, `users.last_login_at TIMESTAMPTZ`. Constraint: `UNIQUE (provider, sub)`. Sessions table per SPEC constraint. One file; atomic up+down.
- **D-22c-MIG-03 — Alembic 006 = full-DB data purge.** TRUNCATE TABLE (or DELETE FROM with FK-aware ordering) on: `agent_events`, `runs`, `agent_containers`, `agent_instances`, `idempotency_keys`, `rate_limit_counters`, `sessions`, `users`. Schema + `alembic_version` preserved. Reversible downgrade is impossible (data is gone) — documented as an irreversible migration in the file docstring.
- **D-22c-MIG-04 — Sessions table indexing: PK only + btree on `user_id`.** PK covers the hot-path `SELECT WHERE id=$1` auth lookup. `user_id` btree enables future admin "list my sessions" without a v2 migration. No partial WHERE index — Postgres handles the expiry filter cheaply on PK lookup. Claude's Discretion to add a partial index if profiling proves otherwise.
- **D-22c-MIG-05 — `sessions.last_seen_at` throttled updates (60s granularity, per-worker in-memory dict).** SessionMiddleware uses a per-worker in-memory dict (NOT Redis — Redis isn't in the Python stack; `services/rate_limit.py` uses asyncpg). Shape: `_last_seen_cache: dict[UUID, datetime]` on the middleware instance. On each request: if `(now - cache.get(session_id)) > 60s` OR missing, fire the PG UPDATE + refresh the cache entry. Under Nx workers there is up to Nx write-amplification per 60s window — acceptable at current scale (single-worker dev, low-concurrency prod). Swappable for Redis if + when Redis lands in the stack. Reduces write rate ~60x per worker. Good enough for "recently active" queries; sub-second forensics deferred. Cache eviction: soft-bound at 10k entries via LRU (session expiry handles long-term growth).
- **D-22c-MIG-06 — `ANONYMOUS_USER_ID` constant deleted from `constants.py` after migration 006.** `AP_SYSADMIN_TOKEN_ENV` stays (22b dependency). Any lingering reference = build failure = forced cleanup.

### Auth Middleware & Routes

- **D-22c-AUTH-01 — SessionMiddleware placement.** Middleware order (request-in): `CorrelationId → AccessLog → Session → RateLimit → Idempotency → routers`. Session resolves `user_id` BEFORE rate_limit + idempotency so both key on the real user (not anonymous IP / global bucket).
- **D-22c-AUTH-02 — `request.state.user_id: UUID | None`.** Starlette-idiomatic. `None` = anonymous (no cookie OR invalid session). Mirrors the `request.state.correlation_id` pattern in `middleware/correlation_id.py`. Zero new abstractions.
- **D-22c-AUTH-03 — `require_user` returns `JSONResponse | UUID` (inline, matching codebase `_err()` pattern).** NOT an `HTTPException`-raising dependency (decided post-research on 2026-04-19). Route handlers call `require_user(request)` at the top and early-return the JSONResponse if the result isn't a UUID. This preserves the Stripe-shape error envelope (`make_error_envelope("unauthorized", ...)`) consistently with every existing handler in `routes/agent_events.py`, `routes/runs.py`, `routes/agent_lifecycle.py`. No global exception_handler wrapper needed — zero new plumbing.
  ```python
  # api_server/src/api_server/auth/deps.py
  def require_user(request: Request) -> JSONResponse | UUID:
      user_id = getattr(request.state, "user_id", None)
      if user_id is None:
          return JSONResponse(
              status_code=401,
              content=make_error_envelope("unauthorized", "Authentication required"),
          )
      return user_id

  # usage in a route
  @router.get("/v1/agents")
  async def list_agents(request: Request):
      result = require_user(request)
      if isinstance(result, JSONResponse):
          return result
      user_id: UUID = result
      ...
  ```
  Per-route explicit opt-in. Applied to: `/v1/runs`, `/v1/agents`, `/v1/agents/:id/*`, `/v1/users/me`, `/v1/auth/logout`. Public: `/healthz`, `/readyz`, `/v1/recipes`, `/v1/schemas`, `/v1/lint`, `/v1/auth/{google,github}`, `/v1/auth/{google,github}/callback`.
- **D-22c-AUTH-04 — Complete ANONYMOUS_USER_ID cleanup across 5 files.** Routes `runs.py`, `agents.py`, `agent_lifecycle.py`, `agent_events.py` + `middleware/idempotency.py` all migrate to `request.state.user_id` (via `require_user` for protected routes; via direct attribute read for idempotency middleware). The `ANONYMOUS_USER_ID` import is removed from every file. Constant deletion from `constants.py` is the forcing function.

### Frontend Auth Gating & Error UX

- **D-22c-FE-01 — Next.js `proxy.ts` gates `/dashboard/:path*`.** New file `frontend/proxy.ts` (NOT `middleware.ts` — superseded by AMD-06; Next 16.2 renamed the file 2025-10-21) runs on every request matching `/dashboard/:path*`. Reads `ap_session` cookie PRESENCE (not validity — validation stays server-side). Absent → 307 redirect to `/login` BEFORE React renders. Zero auth-flash. Expired/revoked cookies get a 401 from the subsequent `/v1/users/me` fetch and the layout redirects. Any pre-existing `frontend/middleware.ts` (including stale comments asserting the rename didn't happen) is retired in this phase.
- **D-22c-FE-02 — Eager dashboard render; navbar skeleton until userinfo resolves.** Dashboard layout renders immediately with full content. Navbar user slot shows a name/avatar skeleton until `apiGet<SessionUser>('/api/v1/users/me')` returns. 401 on the fetch → client-side `router.push('/login')`. No Suspense boundary; no full-page spinner. Matches Phase 20 alicerce's eager-render discipline.
- **D-22c-FE-03 — OAuth error paths → `/login?error=<code>` + toast.** Backend callback handler catches `?error=access_denied` (Google denies consent), state-mismatch (400), token-exchange 5xx, and redirects to `/login?error=access_denied | state_mismatch | oauth_failed`. Frontend `/login` reads `?error=` param on mount and displays a toast. Error code enum is Claude's Discretion (suggested: `access_denied`, `state_mismatch`, `oauth_failed`).
- **D-22c-FE-04 — Callback always redirects to `/dashboard`.** No `?next=` deep-link preservation in v1. Matches SPEC R2. User re-navigates from dashboard home.

### OAuth Flow Specifics (Both Providers)

- **D-22c-OAUTH-01 — Both Google AND GitHub ship in 22c.** Two provider-pairs of routes: `GET /v1/auth/google` + `GET /v1/auth/google/callback` + `GET /v1/auth/github` + `GET /v1/auth/github/callback`. One shared `/v1/auth/logout`. One shared session minting logic. `users.UNIQUE(provider, sub)` covers both. Login page shows both buttons enabled.
- **D-22c-OAUTH-02 — Google scope: `openid email profile`. No `access_type=offline`.** Identity-only. No refresh_token stored. Dropped SPEC refresh-token requirement (see AMD-02).
- **D-22c-OAUTH-03 — GitHub scope: `read:user user:email`.** GitHub isn't OIDC — callback fetches `/user` + `/user/emails` (second call needed when primary email is private). authlib's `userinfo_endpoint` + a manual `/user/emails` follow-up. Callback stores `(provider='github', sub=<github_id>, email=<primary_verified_email>, display_name=<name_or_login>, avatar_url=<avatar_url>)`.
- **D-22c-OAUTH-04 — Cookie policy: `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` always. `Secure` only when `AP_ENV=prod`.** Dev runs `http://localhost:8000` + `:3000` — `Secure=true` would block cookies entirely. `AP_ENV` check at cookie-set time; one-line conditional. Matches existing `AP_CHANNEL_MASTER_KEY` env-gating pattern.
- **D-22c-OAUTH-05 — State token: per-request random nonce in short-lived signed cookie.** Set-Cookie: `ap_oauth_state=<nonce>; HttpOnly; SameSite=Lax; Max-Age=600` on the authorize redirect. Callback verifies cookie value == `?state=` param → 400 mismatch otherwise. authlib's built-in state management. Deleted after first successful callback.

### Dead-Theater Cleanup

- **D-22c-UI-01 — `/login` keeps BOTH Google + GitHub buttons enabled.** Email/password form retained but disabled with copy "Use Google or GitHub for now". Tooltip text Claude's Discretion.
- **D-22c-UI-02 — `/signup` server-side redirects to `/login`.** Uses `next.config.ts` `redirects()` entry. One line. Zero theater. Navbar `/signup` link keeps working but lands on `/login`. Resolves SPEC §Boundaries "pending decision" in the audit ACTION-LIST.
- **D-22c-UI-03 — `/forgot-password` server-side redirects to `/login`.** Same `redirects()` mechanism. The "Forgot password?" link on `/login` (next to disabled password field) is removed to avoid the dead-end loop.
- **D-22c-UI-04 — Navbar "Log out" becomes a real button.** Replaces `<Link href="/login">` with `<button onClick={async () => { await apiPost('/api/v1/auth/logout', {}); router.push('/login'); }}>`. Uses the existing `apiPost` wrapper from `frontend/lib/api.ts`.

### CI Test Strategy

- **D-22c-TEST-01 — Integration tests via real authlib + `respx` library stubs for provider endpoints.** Test stack: real FastAPI + real asyncpg + testcontainers PG + real authlib. **`respx`** (NOT `responses` — superseded by AMD-05) intercepts httpx calls to Google's `oauth2.googleapis.com/token` + `openidconnect.googleapis.com/v1/userinfo` AND GitHub's `github.com/login/oauth/access_token` + `api.github.com/user` + `api.github.com/user/emails` — returning canned payloads. Real authlib flows end-to-end; only the provider HTTPs are replayed. Matches SPEC constraint: "real authlib + a stubbed token endpoint at the network layer, NOT mocked authlib internals."
- **D-22c-TEST-02 — One manual smoke per release.** Developer clicks real Google button + real GitHub button on `http://localhost:3000/login` and verifies `/dashboard` shows the real email. Single checkbox in the SPEC acceptance criteria; not a per-commit gate.
- **D-22c-TEST-03 — Wave 0 spikes MANDATORY before PLAN is sealed (golden rule 5).** Two spikes, both must pass before downstream waves execute. Evidence captured as a committed spike artifact under `.planning/phases/22c-oauth-google/spike-evidence/`.
  - **Spike A: respx × authlib 1.6.11 interop.** ~10-line pytest that registers an authlib `StarletteOAuth2App`, calls its token-exchange path, and uses `respx` to intercept Google's `oauth2.googleapis.com/token`. Pass = the stub fires and authlib parses the canned payload successfully (no network call escapes).
  - **Spike B: TRUNCATE CASCADE on 8-table FK graph.** Against testcontainers PG with schema from alembic 001..005: seed each data table with one row, run `TRUNCATE TABLE agent_events, runs, agent_containers, agent_instances, idempotency_keys, rate_limit_counters, sessions, users CASCADE`, then assert all 8 tables have COUNT=0 AND `alembic_version` table still holds the expected revision. Pass = clean truncate, FK order not a problem, `alembic_version` preserved.
  - If either spike fails, the phase returns to discuss — do NOT execute downstream plans against a red spike.

### Claude's Discretion

Decisions the planner can make freely:
- Sessions table partial-index shape if profiling demands (default: PK + btree(user_id) only)
- Error code enum values for `/login?error=` (suggested: `access_denied`, `state_mismatch`, `oauth_failed`; decide authoritatively during planning)
- Tooltip copy for disabled password form
- Toast library choice if not already present in `frontend/` (check before adding a new dep)
- Whether `/signup` and `/forgot-password` redirects use `next.config.ts::redirects()` or per-page client-side `useEffect(router.replace)` — prefer config-level
- Exact shape of the `ap_oauth_state` cookie (JSON vs. bare nonce; authlib's default is fine)
- alembic 006 purge mechanism: `TRUNCATE … CASCADE` (fast) vs sequential `DELETE FROM` (auditable) — TRUNCATE with CASCADE preferred for speed
- Exception handling inside the GitHub userinfo fetcher when `/user/emails` returns no verified primary (defensive fallback: use `/user.email` if present, else 400 with `oauth_failed`)
- authlib's `StarletteOAuth2App` config pattern — follow authlib's FastAPI-Starlette docs literally

### Folded Todos

None — no todos surfaced as relevant to 22c at discussion time.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 22c anchors

- `.planning/phases/22c-oauth-google/22c-SPEC.md` — **8 locked requirements + 3 locked decisions. MUST read.** CONTEXT.md amendments (AMD-01..AMD-04) override SPEC in four places.
- `.planning/audit/ACTION-LIST.md` — B2 (ANONYMOUS hardcode is the multi-tenancy anchor); /signup open-decision resolved here.

### Backend substrate

- `api_server/src/api_server/main.py` — middleware stack (lines 208–211) + lifespan hook (22b re-attach pattern)
- `api_server/src/api_server/middleware/idempotency.py:36,43,159` — `ANONYMOUS_USER_ID` hardcode; the canonical seam the session middleware replaces
- `api_server/src/api_server/middleware/correlation_id.py` — pattern template for SessionMiddleware (`request.state.*`)
- `api_server/src/api_server/middleware/rate_limit.py` — downstream of Session; keys on user_id now
- `api_server/src/api_server/constants.py` — `ANONYMOUS_USER_ID` constant (to be deleted); `AP_SYSADMIN_TOKEN_ENV` (stays)
- `api_server/src/api_server/routes/agent_events.py` — 22b-shipped auth pattern (Bearer + `AP_SYSADMIN_TOKEN` bypass at line 76, 190); keep the bypass, switch the Bearer path to `require_user`
- `api_server/src/api_server/routes/agent_lifecycle.py` — 4 `ANONYMOUS_USER_ID` references (242, 245, 320, 338) to migrate
- `api_server/src/api_server/routes/agents.py` + `routes/runs.py` — remaining ANONYMOUS_USER_ID importers
- `api_server/src/api_server/crypto/age_cipher.py` — **DELIBERATELY NOT USED** in 22c (AMD-02 dropped the refresh-token path)
- `api_server/src/api_server/models/errors.py` — `make_error_envelope` + Stripe-shape errors; new `unauthorized` code

### Database migrations

- `api_server/alembic/versions/001_baseline.py` — current `users` table (email Text nullable, display_name Text not null, provider Text nullable, created_at). Anchor for 005's additive columns.
- `api_server/alembic/versions/003_agent_containers.py` — migration style, partial unique indexes, CHECK constraints; 005 mirrors the idiom
- `api_server/alembic/versions/004_agent_events.py` — 22b style for `CREATE TABLE` + partial unique indexes

### Frontend substrate

- `frontend/app/login/page.tsx` — the setTimeout theater (line 24) to replace; existing Google + GitHub buttons at 54–66 become the real flow
- `frontend/app/dashboard/layout.tsx` — "Alex Chen" hardcode (line 42) to replace with live `useUser()` hook call to `/api/v1/users/me`
- `frontend/components/navbar.tsx` — `<Link href="/login">` Log out at line 232 to replace with a real button
- `frontend/lib/api.ts` — `apiGet / apiPost / apiDelete + SessionUser` type already correctly shaped (display_name + avatar_url + provider)
- `frontend/app/signup/page.tsx` — setTimeout theater, becomes redirect target
- `frontend/app/forgot-password/page.tsx` — setTimeout theater, becomes redirect target
- `frontend/next.config.ts` — where `redirects()` for /signup and /forgot-password land
- (new) `frontend/middleware.ts` — the cookie-presence gate for /dashboard/:path*

### Config & env

- `deploy/.env.prod` — **gitignored.** Holds real Google + GitHub client_id + client_secret + redirect_uri. GitHub secret leaked in chat 2026-04-19 and MUST be rotated before any prod deploy. Google secret similarly leaked 2026-04-19 per SPEC §Background.
- `deploy/.env.prod.example` — committed template; updated in this phase to list all OAuth env vars + AP_SYSADMIN_TOKEN
- `api_server/src/api_server/config.py` — add Pydantic settings for OAuth vars (AP_OAUTH_{GOOGLE,GITHUB}_{CLIENT_ID,CLIENT_SECRET,REDIRECT_URI})

### Golden rules + reference memories

- `CLAUDE.md` §Golden rules 1 (no mocks), 2 (dumb client), 3 (ship e2e), 5 (spike before plan)
- `memory/feedback_no_mocks_no_stubs.md` — substrate-level rule; why responses-stub is OK (network boundary) but mocked authlib is not
- `memory/feedback_dumb_client_no_mocks.md` — frontend fetches /v1/users/me, never hardcodes user state
- `memory/feedback_check_msv_when_stuck.md` — MSV's `api/pkg/auth/` likely has authlib-equivalent Go patterns; grep there for session cookie + middleware shapes

### External specs & docs (read-as-needed)

- authlib docs: https://docs.authlib.org/en/latest/client/fastapi.html — FastAPI + Starlette integration (the canonical pattern)
- Google OAuth 2.0 for web server apps: https://developers.google.com/identity/protocols/oauth2/web-server — scope + userinfo shape
- GitHub OAuth: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps — scope semantics, `/user/emails` fallback
- `responses` library (for test-layer stubs): https://github.com/getsentry/responses — route matchers + method chaining for authlib's httpx calls

### MSV references (patterns to steal)

- `/Users/fcavalcanti/dev/meusecretariovirtual/api/pkg/auth/` — if it exists; grep before planning. Session-cookie + middleware pattern is language-agnostic.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`request.state.correlation_id` pattern** (`middleware/correlation_id.py`) — template for how SessionMiddleware exposes `request.state.user_id`
- **Stripe-shape error envelope** (`models/errors.py::make_error_envelope`) — new error code: `unauthorized` (401)
- **`config.py` Pydantic settings pattern** — add `oauth_google_{client_id,client_secret,redirect_uri}` + `oauth_github_{…}` as required fields in prod, optional in dev
- **`agent_events.py` Bearer + AP_SYSADMIN_TOKEN bypass** — keep the sysadmin bypass path for the test harness; migrate the Bearer-as-user-id path to real session resolution
- **`frontend/lib/api.ts::SessionUser`** — already shaped `{id, email?, display_name, avatar_url?, provider?}` — zero type changes needed on the frontend side
- **`frontend/lib/api.ts::apiPost` + `apiDelete`** — already support cookies via `credentials: "include"` — /v1/auth/logout wire-up is one line
- **22b lifespan re-attach pattern** (`main.py` lines 93–160) — template for future "revoke all sessions for user" sweeps; NOT used in 22c

### Established Patterns

- **asyncpg + connection-per-scope** (Pitfall 4) — SessionMiddleware's PG lookup acquires+releases the pool conn inline per request; never held across a long await
- **Redaction-everywhere** (`middleware/log_redact.py::_redact_creds`) — widen to include the `ap_session` and `ap_oauth_state` cookie VALUES in any log-line that includes request headers
- **Partial unique index discipline** — sessions table uses PK; no partial index in v1 per D-22c-MIG-04
- **env-gated fail-loud** — `crypto/age_cipher.py::_master_key` fails at boot when AP_ENV=prod + master key missing; replicate for AP_OAUTH_{GOOGLE,GITHUB}_* in prod
- **Alembic additive discipline** — 003 (agent_containers) and 004 (agent_events) both additive. 005 is additive too; 006 is the FIRST destructive migration in the repo — DOCSTRING MUST WARN about irreversibility

### Integration Points

- `main.py` middleware stack (lines 208–211) — add `app.add_middleware(SessionMiddleware)` between `AccessLog` and `RateLimit`
- `main.py` app.include_router (line 213+) — add `app.include_router(auth_route.router, prefix="/v1", tags=["auth"])` for the 4 OAuth routes + logout
- `main.py` lifespan — NO additional re-attach logic (sessions don't need re-attach; they're PG rows looked up per-request)
- `middleware/idempotency.py` line 159 — replace `user_id = ANONYMOUS_USER_ID` with `user_id = request.state.user_id` (guaranteed non-None by `require_user` dep on protected routes; but idempotency applies even without auth, so the check needs to handle `None` by keying on anonymous-IP fallback OR forcing auth on the whole POST /v1/runs path — planner decides)
- `frontend/next.config.ts` — add `redirects()` entries for `/signup` → `/login` and `/forgot-password` → `/login`
- `frontend/middleware.ts` — NEW file; matches `/dashboard/:path*`; checks `ap_session` cookie presence; 307 to `/login` if absent

</code_context>

<specifics>
## Specific Ideas

- **Two secrets leaked in chat on 2026-04-19.** Google client secret (SPEC L20) and GitHub client secret (this discussion). Both live in `deploy/.env.prod` (gitignored). BOTH MUST BE ROTATED before any prod deploy. Add a `DEPLOY-ROTATE.md` checklist item OR a startup-time assertion that cross-checks the client secret against a known-leaked-hash deny-list (planner call).
- **All current DB data is mock dev data from Phase 19/22 execution.** No real users, no real agents. Migration 006 can be ruthless; there is zero risk of losing real customer data.
- **GitHub Client ID is public-safe.** It appears on the consent screen GitHub shows users; it's not a secret. Only the client secret requires rotation.
- **authlib is already the right tool** even without refresh-token storage. It handles state tokens, PKCE (unused here), OIDC id_token validation (Google), userinfo fetching, and works cleanly inside FastAPI. Don't reinvent.
- **GitHub's non-OIDC nature means an extra round-trip.** Every GitHub login: `/login/oauth/access_token` → `/user` → (if email is null) `/user/emails` → store primary+verified. Latency ~400ms vs Google's single `/userinfo` call. Acceptable for login flow.
- **deploy/.env.prod.example is committed** — this phase must keep it in sync. Any new env var added post-22c must append to the template too.
- **Cookie name `ap_session` matches the namespace of existing cookies** — `ap_oauth_state` is the companion. Both `ap_*`-prefixed, consistent with `AP_CHANNEL_MASTER_KEY` + `AP_SYSADMIN_TOKEN` env naming.
- **The /v1/users/me endpoint is a singleton-per-request hot path.** Every dashboard page fetch hits it. Consider Redis or in-process TTL caching in v2 if it becomes the dashboard's latency tail. Not in v1 scope.

</specifics>

<deferred>
## Deferred Ideas

### Deferred to post-22c

- **Refresh-token storage + rotation** — revisit when 22c+N needs Google Calendar / GitHub repo access on the user's behalf. Pattern: add offline scope + age-KEK-encrypted refresh_token column on `agent_containers` or a new `oauth_tokens` table.
- **Deep-link preservation via `?next=` param** — user hits `/dashboard/billing` logged out, after OAuth returns to `/billing`. Requires passing through 3 hops (Next middleware → login page → OAuth state → callback). Small UX win; not v1.
- **PKCE for OAuth** — Google + GitHub both support it; confidential clients don't need it. Adds rotation cost. Defer unless a real security requirement surfaces.
- **Dev TLS via mkcert / Caddy local** — `Secure` cookies in dev. Friction > value for solo dev.
- **Admin "list my sessions" UI** — users see all active sessions (device, IP, last-seen), can revoke individually. Uses `btree(user_id)` index already provisioned. Future phase.
- **Multi-account linking** — same email via Google AND GitHub creates two separate user rows today. Linking ("you already have an account with this email — link GitHub to it?") is its own phase.
- **Magic-link password reset** — the `/forgot-password` route is dark until this ships. No v1 need.
- **Dedicated /signup onboarding flow** — tier selection, ToS flow, welcome email. Future phase; the current redirect-to-login is the minimal solution.
- **Session expiry UX** — after 30 days, cookie expires. Frontend catches 401 and redirects to `/login`. Add a "your session expired" toast? Cosmetic polish.
- **PGBouncer or pg connection pool tuning** — session middleware doubles DB reads per request. If pool saturates, tune or cache.
- **MTProto user-impersonation harness** — carries over from 22b deferred list; unrelated to 22c but blocks automated SC-03 Gate C.

### Reviewed Todos (not folded)

None — no todos were surfaced as relevant to 22c at discussion time.

### Scope creep rejected

- None this session — user expanded scope (GitHub) deliberately, not accidentally. All other areas stayed inside the "HOW to implement SPEC's WHAT" boundary.

</deferred>

---

*Phase: 22c-oauth-google*
*Context gathered: 2026-04-19*
*Amendments: AMD-01 (GitHub scope), AMD-02 (refresh-token drop), AMD-03 (ANONYMOUS row delete), AMD-04 (full-DB purge)*
*Downstream agents: read 22c-SPEC.md FIRST, then apply this CONTEXT.md's amendments on top.*
