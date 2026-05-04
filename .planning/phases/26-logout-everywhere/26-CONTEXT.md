# Phase 26: Logout-everywhere + session-invalidation — Context

**Gathered:** 2026-05-04
**Status:** Ready for research + planning

<domain>
## Phase Boundary

Adds `POST /v1/auth/logout-all` (authenticated) that revokes every session row for the calling user_id, plus a new `auth_events` audit table and a `revoked_reason` enum column on `sessions`. Mobile + web clients learn about revocation via a new `error.code='session_revoked'` shape on the next 401 they receive, and surface a "session ended elsewhere" banner. **Auth-only** — agents (containers) keep running; BYOK keys are not touched.

This closes H2 from `memory/project_solidity_audit_2026_05_04.md`. H1 (OAuth refresh tokens) was retired during this phase's recon as a misframe (see `feedback_audit_before_evolve.md` + the corrected memory file).

**Out of scope:**
- Multi-replica session-invalidation pub/sub (deferred — single-replica DB SELECT is adequate today; revisit when we go multi-replica)
- Stopping running agents on logout-all (different concern; can ship as a separate micro-phase later if a "panic button" is desired)
- Clearing BYOK keys (kept on device per D-25/D-33; logout flow doesn't touch them)
- Logout-others-but-keep-this-device (deferred — logout-all is destructive by design; user re-logs in here)
- Auth-endpoint rate limiting (H3 — separate phase)

</domain>

<decisions>
## Implementation Decisions

### Session-invalidation propagation (D-01)
- **D-01:** Skip Redis pub/sub. Revocation = `UPDATE sessions SET revoked_at = NOW(), revoked_reason = 'logout_all' WHERE user_id = $u AND revoked_at IS NULL`. SessionMiddleware's per-request SELECT already excludes revoked rows (or will after the column is added). Propagation latency = 1 request RTT, sub-second on a single replica. **Add pub/sub WHEN we go multi-replica.** Audit's "pub/sub for multi-replica" stays as a future item, not Phase 26 scope.

### Audit trail (D-02)
- **D-02:** New `auth_events` table (migration 009). Columns: `id UUID PK`, `user_id UUID NOT NULL FK→users`, `kind TEXT NOT NULL` (initial enum: `'logout_all'` only; expand later), `ip INET`, `user_agent TEXT`, `device_count_revoked INT`, `created_at TIMESTAMPTZ DEFAULT NOW()`. Index on `(user_id, created_at DESC)` for incident-response lookups.
- **D-03:** Lean schema — no per-revoked-session JSONB, no geo, no caller_session_id. Add columns later when specific queries demand them.

### Revoked-device UX (D-04)
- **D-04:** API returns 401 with shaped error envelope: `{error: {code: 'session_revoked', message: 'Your session was ended on another device. Please sign in again.', request_id: ...}}`. Mobile + web clients map `code === 'session_revoked'` to a custom SnackBar/banner; generic 401 (cookie not found, expired) keeps the existing "session expired" copy.
- **D-05:** Mobile: existing `AuthInterceptor` handles 401 today (clears `session_id`, fires `AuthRequired`). Phase 26 adds a one-time-use revocation reason carried via the auth-event-bus payload so the login screen can render the right banner.
- **D-06:** Web: same shape. Frontend `proxy.ts` or auth context maps the code to a query-param on the `/login` redirect (`?reason=session_revoked`) so the login page banner renders.

### Logout-all scope (D-07)
- **D-07:** Revokes ALL sessions including the caller's. The endpoint is destructive by design (compromised-device threat: don't leave the attacker holding the cookie). User re-logs in on this device too. Idempotent: rows already `revoked_at IS NOT NULL` are skipped by the WHERE clause; concurrent calls produce the same end state.

### SSE behavior on revocation (D-08)
- **D-08:** SSE streams (in-app chat) stay open until next reconnect or network close. Acceptable info-leak window — the leaked events are the user's own data, not someone else's. Re-validating session per heartbeat is overkill at current scale; revisit if the threat-model bar rises (e.g., shared agents in a future phase).

### UI placement (D-09)
- **D-09:** Web: Settings → new "Security" subsection → destructive-styled "Log out everywhere" button + confirm dialog. Mobile: Profile tab → existing card list grows a "Security" row → same button + dialog. The header-area "Log out" button stays single-device.

### Sessions schema (D-10)
- **D-10:** Sessions table gains `revoked_reason TEXT NULL` enum column (values: `'logout'`, `'logout_all'`, `'admin'`, `'expired'`). Filterable queries like "all sessions revoked by logout-all in the last 7d" become a single WHERE clause. Existing `revoked_at` semantics unchanged; null `revoked_reason` for legacy rows is acceptable.

### Single-device logout endpoint (D-11)
- **D-11:** Existing `POST /v1/auth/logout` is updated to set `revoked_reason = 'logout'` for symmetry but does NOT write an `auth_events` row (high-volume / low-value for incident response — keep the table focused on logout_all).

### Migration order (D-12)
- **D-12:** Migration 009 — additive only. Adds `auth_events` table + `sessions.revoked_reason` column. No data backfill needed (legacy revoked rows leave `revoked_reason = NULL`).

### Claude's Discretion
- Confirm dialog copy, button color/placement details (Solvr aesthetic — terminal/ASCII feel, no emoji-as-identity).
- Exact error envelope key ordering (must match existing Stripe-shape envelope from `models/errors.py`).
- Whether to include `last_seen_at` of the revoked sessions in any response payload (probably no — endpoint returns just `{revoked: <count>}`).

</decisions>

<specifics>
## Specific Ideas

- The endpoint shape mirrors existing `/v1/auth/logout` (just plural). Same auth requirement (require_user), same return shape on success.
- "Session ended elsewhere" banner copy intentionally avoids accusatory language (no "someone logged in as you" — the user might just have clicked the wrong button on another device).
- Audit row writes immediately after the UPDATE (within the same DB transaction if practical, otherwise best-effort like inapp_dispatcher's event-emit pattern).
- Phase 22c shipped 9 plans; Phase 26 is a much smaller ask — 3-4 plans expected.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit + framing
- `memory/project_solidity_audit_2026_05_04.md` — Phase 26 closes H2; H1 retired correction lives here
- `memory/feedback_audit_before_evolve.md` — pattern for the audit-before-architectural-layer move
- `memory/feedback_re_ask_gray_areas.md` — the re-asked SSE/scope question that surfaced D-08 + D-09

### Phase 22c substrate (re-used unchanged)
- `.planning/phases/22c-oauth-google/22c-CONTEXT.md` (AMD-02 explains why refresh tokens were dropped — Phase 26 leaves that decision intact)
- `api_server/src/api_server/routes/auth.py:138-307` — Google + GitHub OAuth handlers; logout endpoint is in this file
- `api_server/src/api_server/auth/oauth.py` — mint_session, upsert_user
- `api_server/src/api_server/auth/deps.py:37-72` — require_user (the gate; logout-all is `Depends(require_user)`)
- `api_server/src/api_server/middleware/session.py:48-83` — SessionMiddleware (where 401-with-session_revoked-code surfaces)
- `api_server/alembic/versions/005_sessions_and_oauth_users.py` — sessions table baseline; 009 extends

### Mobile auth path (consumed by error-code mapper)
- `mobile/lib/core/api/auth_interceptor.dart` — 401 handler (gets the new revocation reason)
- `mobile/lib/core/auth/auth_event_bus.dart` (or wherever AuthRequired is emitted) — payload extension for revocation reason
- `mobile/lib/features/login/login_screen.dart` — banner render

### Web frontend
- `frontend/middleware/proxy.ts` — current 401 handling (where `session_revoked` code → query param on /login redirect)
- `frontend/components/login/*.tsx` — login page banner rendering

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `auth/deps.py::require_user` — exactly the gate logout-all needs; standard `Depends()` pattern
- `models/errors.py::make_error_envelope` — Stripe-shape error envelope; just add `'session_revoked'` to the ErrorCode enum
- `middleware/session.py` SELECT pattern — already excludes revoked rows; only change is reading + adding `revoked_reason` to the response when 401-ing
- `inapp_dispatcher.py` event-emit-after-state-change pattern — auth_events row insertion mirrors this
- `mobile/lib/core/api/auth_interceptor.dart` already maps 401 → AuthRequired event; just enriches the payload

### Patterns to follow
- Phase 22c-05 plan structure (3 plans: handler + middleware + tests). Phase 26 will be similar.
- Migration 005 shape for the new table + column add.
- Phase 22c.3 e2e test fixtures in `api_server/tests/auth/` for multi-session scenarios.

### Anti-patterns to avoid
- Don't revoke from inside SessionMiddleware (race with the request that triggered the revocation). Keep it route-handler-bound.
- Don't add a "logout this device only" alternative endpoint in Phase 26 — `POST /v1/auth/logout` already does that. Two endpoints, two semantics, not three.
- Don't write an `auth_events` row for routine single-device logouts (D-11) — table stays signal-rich.

</code_context>

<scope_boundary>
## Scope Boundary

**In scope:**
- New `POST /v1/auth/logout-all` endpoint
- Migration 009: `auth_events` table + `sessions.revoked_reason` column
- New `ErrorCode.SESSION_REVOKED` mapping
- SessionMiddleware: when no row matches AND a recent revocation exists for cookie's user_id, return 401 with `session_revoked` code
- Existing `/v1/auth/logout` updated to set `revoked_reason = 'logout'` (no auth_events row)
- Web Settings → Security → Log out everywhere button + confirm dialog
- Mobile Profile → Security → Log out everywhere button + confirm dialog
- Login screen banners (web + mobile) consuming `session_revoked` reason
- Tests: 3-device logout-all scenario, idempotency under concurrent calls, generic-401-vs-session-revoked-401 differentiation

**Deferred:**
- Pub/sub for multi-replica
- Stopping agents on logout-all (panic-button mode)
- Clearing BYOK keys
- Logout-others-but-keep-this-device endpoint
- Geo lookup on auth_events
- Per-revoked-session JSONB detail
- Auth-endpoint rate limits (H3)

</scope_boundary>

## Next steps

1. `/gsd-research-phase 26` — research authlib/FastAPI patterns for session revocation, sessions-table indexes for this access pattern, frontend proxy 401 handling shape (the parts not yet locked in CONTEXT)
2. `/gsd-plan-phase 26` — produce 3-4 plans (migration + API + frontend + mobile)
3. `/gsd-execute-phase 26` — build it
4. After Phase 26 ships: open Phase 27 = H3 auth-endpoint rate limiting (~2 days)
