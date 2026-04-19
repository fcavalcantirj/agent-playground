# Phase 22c: oauth-google — Specification

**Created:** 2026-04-19
**Ambiguity score:** 0.16 (gate: ≤ 0.20)
**Requirements:** 8 locked

## Goal

Replace the `setTimeout`-theater login + the `ANONYMOUS_USER_ID` placeholder with a real Google OAuth flow that mints a server-side session and resolves a real `user_id` on every API request, so the dashboard shows the logged-in user's own agents and sign-out actually invalidates the session.

## Background

**Current state (2026-04-19, post-Phase 22b):**
- `frontend/app/login/page.tsx` calls `setTimeout(..., 1000)` then `router.push('/dashboard')` unconditionally — no credential validation, no API call, no session minted
- `api_server/src/api_server/middleware/idempotency.py:36` hardcodes `user_id = ANONYMOUS_USER_ID` ("Phase 19 — Phase 21+ resolves real user")
- `frontend/app/dashboard/layout.tsx` renders hardcoded `"Alex Chen"` as the user name
- 59 agents currently exist in the DB, all keyed to `ANONYMOUS_USER_ID = 00000000-0000-0000-0000-000000000001`
- ZERO OAuth scaffolding exists in `api_server/src/` (no authlib, no fastapi-users, no oauth2 routes)
- Phase 22a's age-KEK encryption pattern (`pyrage` + per-user KEK derived from `AP_CHANNEL_MASTER_KEY` + user_id via HKDF) is in place at `api_server/src/api_server/services/crypto.py` — reusable for refresh-token encryption-at-rest
- Google OAuth credentials provisioned and stashed in `deploy/.env.prod` as `AP_OAUTH_GOOGLE_CLIENT_ID` / `AP_OAUTH_GOOGLE_CLIENT_SECRET` / `AP_OAUTH_GOOGLE_REDIRECT_URI=http://localhost:8000/v1/auth/google/callback` (test users mode; client secret leaked in chat 2026-04-19, must be rotated before any prod deploy)

**Trigger:** Phase 22b shipped Gate A 15/15 + Gate B 5/5 making SC-03 green for the single-tenant ANONYMOUS user. The next milestone milestone needs real user isolation: dashboard shows "your" agents, not the shared bucket. Per `.planning/audit/ACTION-LIST.md`, OAuth is the single biggest unblocker — gates 4 frontend pages + ~8 backend endpoints.

## Requirements

1. **Google OAuth authorize endpoint exists and redirects to Google.**
   - Current: `GET /v1/auth/google` returns 404 (no route registered)
   - Target: `GET /v1/auth/google` issues a 302 redirect to `https://accounts.google.com/o/oauth2/v2/auth` with the configured `client_id`, scopes (`openid email profile`), `redirect_uri`, and a per-request `state` token (CSRF defense) stored in a short-lived signed cookie
   - Acceptance: `curl -sI http://localhost:8000/v1/auth/google` returns `302` with `Location:` starting with `https://accounts.google.com/` AND containing `client_id=303159181051-...` AND `state=` non-empty parameter; `Set-Cookie: ap_oauth_state=...; HttpOnly; SameSite=Lax; Max-Age=600`

2. **Google OAuth callback endpoint exchanges code → user → session.**
   - Current: `GET /v1/auth/google/callback` returns 404
   - Target: `GET /v1/auth/google/callback?code=X&state=Y` validates state token (rejects 400 BAD_REQUEST if mismatch), exchanges code for tokens (access + id + refresh) at Google's token endpoint, fetches userinfo, upserts a `users` row by `(provider='google', sub=<google_sub>)`, encrypts refresh_token via age-KEK keyed by user_id, mints an opaque `session_id`, INSERTs a `sessions` row, sets `Set-Cookie: ap_session=<session_id>; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (30 days), redirects to `/dashboard`
   - Acceptance: integration test (real Google flow OR mocked Google response with real PG) inserts a row in both `users` and `sessions`; `agent_containers.refresh_token_enc` is non-null + age-decryptable round-trip works; response is 302 to `/dashboard` with the cookie set

3. **Session middleware resolves `user_id` from cookie on every API request.**
   - Current: `api_server/src/api_server/middleware/idempotency.py:36` and every route hardcodes `ANONYMOUS_USER_ID`
   - Target: new middleware reads `ap_session` cookie, looks up `sessions` row in PG (filter by expiry + not-revoked), sets `request.state.user_id = <resolved>`. If cookie missing or session invalid: `request.state.user_id = None` (anonymous; routes that require auth return 401 UNAUTHORIZED). Cookie absent → no DB query
   - Acceptance: `grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/routes/ api_server/src/api_server/middleware/` returns 0 hits in route handlers (the constant may still exist in `constants.py` for migration purposes); a request with a valid cookie produces a non-anonymous `user_id` in route logs; a request without a cookie returns 401 from `/v1/agents`

4. **`GET /v1/users/me` returns the authenticated user.**
   - Current: route does not exist
   - Target: route returns `{id, email, name, avatar_url, created_at}` from the resolved session's user; 401 UNAUTHORIZED if no session
   - Acceptance: with a valid `ap_session` cookie, `curl http://localhost:8000/v1/users/me` returns 200 + JSON with the logged-in user's email; without the cookie, returns 401 with `{error: {code: "unauthorized", ...}}`

5. **`POST /v1/auth/logout` invalidates the session server-side.**
   - Current: no logout route
   - Target: route deletes the `sessions` row matching the cookie, sets `Set-Cookie: ap_session=; Max-Age=0` to clear the browser cookie, returns 204
   - Acceptance: after logout, the same `ap_session` cookie value sent to `/v1/users/me` returns 401; the `sessions` row is no longer in PG

6. **Frontend login button starts the real OAuth flow.**
   - Current: `frontend/app/login/page.tsx` setTimeout theater
   - Target: "Sign in with Google" button does `window.location.href = '/api/v1/auth/google'` (full-page navigation — OAuth requires a top-level redirect). Email/password form retained but disabled with copy "Coming soon — use Google for now". No `setTimeout`. No fake success path.
   - Acceptance: `grep -c setTimeout frontend/app/login/page.tsx` returns 0; clicking the Google button in a browser starts the real Google consent flow

7. **Frontend layout shows the real user (replaces "Alex Chen").**
   - Current: `frontend/app/dashboard/layout.tsx` renders hardcoded `"Alex Chen"` user
   - Target: layout fetches `apiGet<UserProfile>('/api/v1/users/me')` on mount; renders user.name + user.avatar_url; if 401, redirects to `/login`. Sign-out button calls `apiPost('/api/v1/auth/logout', {})` then `router.push('/login')`.
   - Acceptance: `grep -c "Alex Chen" frontend/app/dashboard/layout.tsx` returns 0; the rendered layout shows the logged-in Gmail account's display name

8. **Existing ANONYMOUS_USER_ID-keyed agents are purged.**
   - Current: 59 agents in `agent_instances` keyed to `00000000-0000-0000-0000-000000000001`; child rows in `agent_containers` and `runs` cascade
   - Target: alembic migration `005_purge_anonymous.py` runs `DELETE FROM agent_instances WHERE user_id = '00000000-0000-0000-0000-000000000001'`; CASCADE FKs delete child agent_containers + runs + agent_events. The `users` row for ANONYMOUS may stay (audit trail) or also delete — operator's call. After migration, dashboard shows "No agents yet" until a real OAuth user deploys their first.
   - Acceptance: post-migration `psql -c "SELECT COUNT(*) FROM agent_instances WHERE user_id='00000000-0000-0000-0000-000000000001'"` returns 0; same for `agent_containers`, `runs`, `agent_events` (via CASCADE); `/v1/agents` for a fresh OAuth user returns `{agents: []}`

## Boundaries

**In scope:**
- Google OAuth (login + callback + logout + session middleware + /v1/users/me)
- Server-table session storage (new `sessions` table; opaque cookie carrying `session_id`)
- Refresh-token encryption-at-rest via age-KEK (reuses Phase 22a pattern)
- ANONYMOUS_USER_ID purge migration (alembic 005)
- Frontend: real login button + layout rewrite + sign-out
- CSRF protection via per-request state token

**Out of scope:**
- **GitHub OAuth** — defer to Phase 22c.1 once Google shape is proven and patterns extracted. Same backend skeleton can host GitHub by adding `/v1/auth/github` + `/v1/auth/github/callback` + a second `oauth_identities`-style row on `users`.
- **Email/password login** — UI present but disabled; full implementation deferred. Not on the critical path.
- **Multi-account linking** — one OAuth identity per user row. If the same Gmail signs in via GitHub later, that becomes a new user row. Linking is a separate feature.
- **Magic-link / forgot-password** — frontend stubs untouched.
- **`/signup` route fate** — pending decision until OAuth flow lands and we see how Google handles first-time vs returning users (per `.planning/audit/ACTION-LIST.md` open decision).
- **Rate-limiting on auth routes** — relies on the existing rate_limit middleware; no auth-specific limits added.
- **PKCE** — Google supports it but for confidential clients (server-side) the state-token defense is sufficient; PKCE adds rotation cost without commensurate benefit. Optional; defer.
- **Refresh-token rotation** — refresh tokens encrypted at rest but not rotated until needed. When access token expires (1h), middleware can re-fetch from Google using the stored refresh token; rotation is a Phase 22c.2 concern.

## Constraints

- **Auth library:** `authlib` (battle-tested OAuth2/OIDC client; integrates with Starlette/FastAPI; handles state token management).
- **Session storage:** server-table in PG. New `sessions(id UUID PK, user_id UUID FK, created_at, expires_at, last_seen_at, revoked_at, user_agent, ip_address)` table; cookie holds opaque `session_id`. Per-request lookup is a single PG SELECT (indexed on `id`, partial WHERE `revoked_at IS NULL AND expires_at > now()`).
- **Cookie:** `ap_session` HttpOnly, SameSite=Lax, Path=/, Max-Age=2592000 (30 days). `Secure` flag set when `AP_ENV=prod`.
- **Refresh token encryption:** reuses `services/crypto.py` (age-KEK keyed by `AP_CHANNEL_MASTER_KEY` HKDF'd by `user_id`); same pattern Phase 22a uses for `agent_containers.channel_config_enc`.
- **Migration ordering:** alembic 005 (sessions table) must land BEFORE 006 (purge anonymous). Do not collapse into one migration.
- **No mocks anywhere in the substrate.** Tests hit real Google (test-user mode) where possible; where Google round-trip is impractical (CI), use real `authlib` + a stubbed token endpoint at the network layer (responses library), NOT mocked authlib internals.
- **CLAUDE.md golden rule 1 (no mocks/no stubs)** applies to all production code paths. Test-only fixtures use real PG via testcontainers.
- **Database column for users.email is unique** — same Gmail can't have two rows. The migration adds `users.provider`, `users.sub`, `users.email`, `users.name`, `users.avatar_url`, `users.created_at`, `users.last_login_at` columns and a `UNIQUE(provider, sub)` constraint.

## Acceptance Criteria

- [ ] `curl -sI http://localhost:8000/v1/auth/google` returns 302 with Google authorize URL + state cookie
- [ ] Manual end-to-end browser flow: visit `/login`, click Google, consent, land on `/dashboard` with cookie set
- [ ] `curl --cookie 'ap_session=<id>' http://localhost:8000/v1/users/me` returns 200 + your real Gmail email
- [ ] `curl http://localhost:8000/v1/users/me` (no cookie) returns 401
- [ ] `curl -X POST --cookie 'ap_session=<id>' http://localhost:8000/v1/auth/logout` returns 204; subsequent `/v1/users/me` with same cookie returns 401
- [ ] `psql -c "SELECT COUNT(*) FROM agent_instances WHERE user_id='00000000-0000-0000-0000-000000000001'"` returns 0 after migration 006
- [ ] `frontend/app/dashboard/layout.tsx` renders the OAuth user's name (NOT "Alex Chen")
- [ ] `grep -rn "ANONYMOUS_USER_ID" api_server/src/api_server/routes/` returns 0 hits in route handlers
- [ ] `grep -c setTimeout frontend/app/login/page.tsx` returns 0
- [ ] Refresh token round-trip: encrypt via age-KEK, store in PG, re-fetch + decrypt produces the original token bytes
- [ ] Integration test: 2 different Google users sign in → each `GET /v1/agents` returns ONLY their own agents (zero cross-user leakage)
- [ ] CSRF state token: callback with mismatched state returns 400 BAD_REQUEST

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                              |
|--------------------|-------|------|--------|------------------------------------|
| Goal Clarity       | 0.85  | 0.75 | ✓      | Single sentence; specific mechanism (cookie + middleware + /v1/users/me) |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | GitHub explicitly deferred; multi-link, magic-link, /signup all listed out-of-scope with reasons |
| Constraint Clarity | 0.80  | 0.65 | ✓      | Library = authlib; storage = server-table; cookie attrs spec'd; encryption pattern named (age-KEK) |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 12 falsifiable checkbox criteria; each is curl/psql/grep/browser-step |
| **Ambiguity**      | 0.16  | ≤0.20| ✓ PASS | Below gate threshold |

## Locked Decisions (from spec-phase Q&A 2026-04-19)

- **D-22c-01 — Session storage:** server-table in PG. `sessions(id, user_id, created_at, expires_at, last_seen_at, revoked_at, user_agent, ip_address)`. Cookie carries opaque session_id. Per-request PG lookup is the auth boundary.
- **D-22c-02 — ANONYMOUS migration:** purge. Alembic 006 deletes ALL `agent_instances` keyed to ANONYMOUS_USER_ID; CASCADE removes child agent_containers + runs + agent_events. Clean slate.
- **D-22c-03 — OAuth library:** `authlib`. Use the StarletteOAuth2App integration with FastAPI's `Request`. Handles state token + token exchange + userinfo fetch.

## Downstream Notes

- `discuss-phase` should treat all 8 requirements + 3 locked decisions + boundaries as locked; focus its session on HOW (file structure, alembic ordering, frontend session-restore on hard refresh, error UX when Google consent is denied).
- `gsd-planner` should produce ~5-7 plans across 2-3 waves: (a) DB migrations (sessions + users columns + purge), (b) backend auth routes + middleware + /v1/users/me + /logout, (c) frontend login button + layout rewrite + sign-out wire-up, (d) live e2e test with real Google flow.
- `gsd-verifier` checks: every acceptance criterion passes (curl/psql/grep/browser); refresh-token round-trip; cross-user isolation test; CSRF state mismatch returns 400.
