# Phase 22c: oauth-google — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `22c-CONTEXT.md` — this log preserves alternatives considered.

**Date:** 2026-04-19
**Phase:** 22c-oauth-google
**Areas discussed:** Migrations & users schema; Auth middleware + user_id resolution; Frontend auth gating + error UX; CI tests + dead-theater cleanup; Refresh tokens + last_seen + cookie Secure flag
**Mode:** SPEC-locked (8 reqs + 3 locked decisions) — HOW-only discussion

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Migrations & users schema shape | users table pre-existing columns vs. SPEC's new ones; migration splits | ✓ |
| Auth middleware + user_id resolution | stack placement; request.state; require_user dep | ✓ |
| Frontend auth gating + error UX | Next middleware.ts vs client; OAuth errors; loading states | ✓ |
| CI test strategy + dead-theater scope | real Google + CI stubs; /signup + /forgot-password + GitHub button | ✓ |

**User's choice:** All four areas (user said "everything. all gray areas")

---

## Migrations & Users Schema

### Q1 — `users.name` column strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse display_name | One column; OAuth writes `name` into display_name; SessionUser.display_name stays | ✓ |
| Add new 'name' column, deprecate display_name | Schema churn + frontend type rename | |
| Keep both | Over-engineered for v1 | |

**Notes:** D-22c-MIG-01. /v1/users/me returns display_name; SPEC's 'name' is the field meaning, not literal column.

### Q2 — Migration file breakdown

| Option | Description | Selected |
|--------|-------------|----------|
| 005 = sessions + users cols; 006 = purge | Two files; matches SPEC ordering | ✓ |
| 005/006/007 split (three files) | One concern per migration | |
| One big migration | Conflates schema + data | |

**Notes:** D-22c-MIG-02.

### Q3 — ANONYMOUS users row fate

| Option | Description | Selected |
|--------|-------------|----------|
| Keep row, NULL provider/sub | Audit trail preserved | |
| Delete row in 006 | Clean slate; constant deleted from constants.py | ✓ |
| Keep + rename to tombstone | Cosmetic only | |

**Notes:** D-22c-MIG-03 extended beyond SPEC — user direction "PURGE DB, ALL MOCKED". Migration 006 widened from SPEC's "DELETE FROM agent_instances WHERE user_id=ANONYMOUS" to full-DB TRUNCATE of all data-bearing tables (AMD-04).

### Q4 — Sessions table indexing strategy

| Option | Description | Selected |
|--------|-------------|----------|
| PK + partial WHERE revoked_at IS NULL | SPEC literal | |
| PK only + btree on user_id (Claude's Discretion) | Minimal; future-proofs admin listing | default |
| PK only, nothing extra | YAGNI | |

**User's choice:** Implicit — answer was "PURGE DB, ALL MOCKED, RIGHT" (confirmed Q3 + widened scope). No explicit Q4 selection → fell to Claude's Discretion (D-22c-MIG-04: PK + btree(user_id)).

---

## Auth Middleware & Routes

### Q5 — Middleware stack placement

| Option | Description | Selected |
|--------|-------------|----------|
| CorrelationId → AccessLog → Session → RateLimit → Idempotency | Rate limit + idempotency key on real user | ✓ |
| Session innermost | Keeps rate_limit + idempotency per-anonymous | |
| Middle ground | Partial refactor | |

**Notes:** D-22c-AUTH-01.

### Q6 — How middleware exposes resolved user

| Option | Description | Selected |
|--------|-------------|----------|
| request.state.user_id: UUID \| None | Starlette-idiomatic | ✓ |
| request.state.user: full User object | Extra DB roundtrip | |
| FastAPI Depends(resolve_user) per route | No middleware attr | |

**Notes:** D-22c-AUTH-02.

### Q7 — Route auth opt-in mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| `require_user` FastAPI dependency per route | Explicit in signature | ✓ |
| Middleware-level PUBLIC_PATHS allowlist | Hidden from route code | |
| Mix (middleware for auth, routes for ownership) | Two-layer | |

**Notes:** D-22c-AUTH-03.

### Q8 — ANONYMOUS_USER_ID cleanup aggressiveness

| Option | Description | Selected |
|--------|-------------|----------|
| Replace every usage; delete constant | Build failures force full cleanup | ✓ |
| Keep constant as deprecated alias | Drag debt forward | |
| Route-level only; leave middleware | Breaks SPEC R3 acceptance | |

**Notes:** D-22c-AUTH-04.

---

## Frontend Auth Gating & Error UX

### Q9 — Where does the auth gate live?

| Option | Description | Selected |
|--------|-------------|----------|
| Next.js middleware.ts at /dashboard/:path* | Cookie-presence check; zero flash | ✓ |
| Client-side useEffect in layout | Auth-flash on slow connections | |
| Server Component in layout | Refactor cost for all dashboard pages | |

**Notes:** D-22c-FE-01.

### Q10 — Dashboard loading UX during /v1/users/me fetch

| Option | Description | Selected |
|--------|-------------|----------|
| Skeleton in navbar slot + full dashboard render | Eager; matches Phase 20 | ✓ |
| Block full layout on fetch | Safer but slow-feeling | |
| Suspense boundary around navbar | Adds machinery | |

**Notes:** D-22c-FE-02.

### Q11 — OAuth error path UX

| Option | Description | Selected |
|--------|-------------|----------|
| Backend redirects to /login?error=<code> + toast | One page to customize | ✓ |
| Dedicated /login/error page | Overkill for 3 modes | |
| Inline banner only, no toast | Static; less visible | |

**Notes:** D-22c-FE-03.

### Q12 — Deep-link preservation

| Option | Description | Selected |
|--------|-------------|----------|
| Always /dashboard after callback | SPEC R2 literal; simpler | ✓ |
| Preserve via ?next= through OAuth state | 3-hop param path | |

**Notes:** D-22c-FE-04.

---

## CI Tests + Dead-Theater Cleanup

### Q13 — CI strategy for OAuth round-trip

| Option | Description | Selected |
|--------|-------------|----------|
| Real authlib + `responses` library stubs for provider endpoints only | SPEC constraint-literal | ✓ |
| Playwright + real Google test account | Flaky, rate-limited | |
| Manual smoke only | Weakest | |

**Notes:** D-22c-TEST-01.

### Q14 — /signup fate

| Option | Description | Selected |
|--------|-------------|----------|
| Redirect /signup → /login | Minimal; zero theater | ✓ |
| Keep /signup as own page | Duplicate maintenance | |
| Leave as setTimeout theater | Violates Rule 3 | |

**Notes:** D-22c-UI-02.

### Q15 — /forgot-password + navbar Log out

| Option | Description | Selected |
|--------|-------------|----------|
| /forgot-password → /login; LogOut as real button | Zero theater | ✓ |
| Delete /forgot-password; fix LogOut | 'Forgot password?' link broken | |
| Leave /forgot-password theater; fix LogOut only | Partial | |

**Notes:** D-22c-UI-03 + D-22c-UI-04.

### Q16 — GitHub button + email/password form

| Option | Description | Selected |
|--------|-------------|----------|
| GitHub 'Coming soon' disabled; password form disabled w/ copy | SPEC literal | (SPEC original) |
| Hide GitHub; hide password form | Contradicts SPEC | |
| Keep GitHub theater-active | Violates Rule 3 | |
| **Expanded scope: Keep GitHub, implement fully in 22c** | **User override: AMD-01** | **✓** |

**User's choice:** "keep github, guide me on creating app and get vars". Scope expanded: GitHub OAuth moves from 22c.1 → 22c. Discussion of dead-theater cleanup shifted to email/password form only (disabled with copy). See AMD-01 in CONTEXT.md.

**Follow-up action:** Walkthrough provided for GitHub OAuth App registration at https://github.com/settings/developers. User created the app and pasted the Client ID + Client Secret directly into the answer field.

**Security incident:** Client Secret was leaked in the chat transcript (2026-04-19). Claude flagged the leak, stored only the Client ID (`Ov23liFwpCaeY2Cpv9s4`) in CONTEXT.md (Client IDs are public-safe), redacted the Client Secret to `<REDACTED — leaked 2026-04-19, MUST rotate before prod>` in this log. The burned secret was written to `deploy/.env.prod` (gitignored) per user's explicit direction ("keep ALL the envs updated on .env"), with an inline ROTATE comment. User instructed to rotate on GitHub immediately; the rotation action is outside Claude's scope (user performs it in the GitHub UI).

### Env file updates applied

- `deploy/.env.prod` (gitignored): GitHub vars appended with ROTATE warning comment
- `deploy/.env.prod.example` (committed): template expanded — Google OAuth, GitHub OAuth, AP_SYSADMIN_TOKEN added for future ops reference

---

## Refresh Token + last_seen + Cookie Secure (final batch)

### Q17 — Refresh token scope decision

| Option | Description | Selected |
|--------|-------------|----------|
| Don't request refresh_token; id_token + email/profile only | AMD-02: drops SPEC refresh-token path | ✓ |
| Request + store encrypted, don't use yet | SPEC literal; dead code | |
| Request + use immediately | Overkill | |

**Notes:** D-22c-OAUTH-02 + AMD-02. SPEC's refresh-token acceptance criterion is DROPPED.

### Q18 — sessions.last_seen_at write cadence

| Option | Description | Selected |
|--------|-------------|----------|
| Throttled: update only when (now - last_seen_at) > 60s | ~100x write reduction | ✓ |
| Update every request | Doubles DB write rate | |
| Remove column entirely | YAGNI (but loses 'active sessions' admin view) | |

**Notes:** D-22c-MIG-05.

### Q19 — Cookie Secure flag policy

| Option | Description | Selected |
|--------|-------------|----------|
| Secure only when AP_ENV=prod; SameSite=Lax always | SPEC literal; dev works without TLS | ✓ |
| Secure always | Needs dev TLS setup (mkcert/Caddy) | |

**Notes:** D-22c-OAUTH-04.

---

## Claude's Discretion items

Decisions handed back to planner:
- Sessions table partial-index shape (if profiling demands)
- Error code enum values for `/login?error=`
- Tooltip copy for disabled password form
- Toast library choice (check frontend deps first)
- /signup and /forgot-password redirect mechanism (config-level preferred)
- `ap_oauth_state` cookie shape
- alembic 006 purge mechanism (TRUNCATE vs sequential DELETE)
- GitHub `/user/emails` null-primary fallback shape
- authlib `StarletteOAuth2App` config pattern (follow authlib docs literally)

---

## Deferred Ideas

Captured in `22c-CONTEXT.md::<deferred>`. Highlights:
- Refresh-token storage + rotation (revisit when a feature needs Google/GitHub API calls on user's behalf)
- Deep-link preservation via `?next=` param
- PKCE
- Dev TLS via mkcert/Caddy
- Admin "list my sessions" UI
- Multi-account linking (same email via Google AND GitHub)
- Magic-link password reset
- Dedicated /signup onboarding flow
- Session expiry UX toast
- MTProto user-impersonation harness (carried from 22b deferred)

---

## SPEC Amendments Summary

Four SPEC amendments decided in this discussion (CONTEXT.md `<spec_amendments>` section):

1. **AMD-01:** GitHub OAuth moved 22c.1 → 22c (scope expansion)
2. **AMD-02:** Refresh-token storage + encryption-at-rest DROPPED
3. **AMD-03:** ANONYMOUS users row DELETED (SPEC left as operator's call)
4. **AMD-04:** Migration 006 TRUNCATEs all data-bearing tables, not just agent_instances

Planner must follow CONTEXT.md for these four items; SPEC remains authoritative for the other 7 requirements.
