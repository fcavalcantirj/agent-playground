---
phase: 22c-oauth-google
plan: 08
subsystem: ui
tags: [nextjs-16, proxy, middleware, oauth, edge-gate, redirects, auth-flash]

# Dependency graph
requires:
  - phase: 22c-oauth-google
    provides: "plan 22c-05 — /api/v1/auth/* routes + /v1/users/me + ap_session cookie issued by SessionMiddleware"
  - phase: 22c-oauth-google
    provides: "plan 22c-07 — /login + /dashboard + useUser hook already consume ap_session; proxy.ts closes the server-side trust boundary in front of them"
provides:
  - "frontend/proxy.ts — Next 16.2 edge gate matching /dashboard/:path*; 307 redirects to /login when ap_session cookie is absent; zero auth-flash"
  - "frontend/next.config.mjs redirects() entries — /signup + /forgot-password both 307 to /login at config layer BEFORE page routes render"
  - "Retirement of frontend/middleware.ts (removed with its incorrect no-rename-happened comment; x-ap-has-session orphan header gone)"
affects: [22c-09, 22c.1-github-oauth, future-dashboard-subpages]

# Tech tracking
tech-stack:
  added: []  # no new deps — pure Next.js built-ins
  patterns:
    - "Next.js 16.2 proxy.ts replaces middleware.ts (file-convention rename effective 2025-10-21 per AMD-06)"
    - "Server-side auth gate via cookie-presence check (NOT validity) — validity lives at the backend /v1/users/me; proxy is defense-in-depth layer 1, useUser hook is layer 2"
    - "Dead-route redirects via next.config.mjs redirects() — permanent: false for 307 temporary so pages can be re-enabled without browser-cache fights"

key-files:
  created:
    - frontend/proxy.ts
  modified:
    - frontend/next.config.mjs
  deleted:
    - frontend/middleware.ts

key-decisions:
  - "proxy.ts checks cookie PRESENCE only, not signature/validity — validation stays server-side at /v1/users/me (defense-in-depth: proxy is layer 1 against obvious-anonymous traffic, useUser is layer 2 against expired/revoked sessions)"
  - "Matcher narrowed from the old middleware's broad '/((?!api|_next/static|_next/image|favicon.ico).*)' to '/dashboard/:path*' only — landing page, /login, API proxy, and static assets pass through untouched"
  - "Signup/forgot-password page files (app/signup/page.tsx + app/forgot-password/page.tsx) stay on disk UNTOUCHED — redirect fires at config layer before route renders; zero-touch avoids import-cascade risk from any still-existing component references"
  - "permanent: false (HTTP 307 temporary) chosen over permanent: true (308) — signup/forgot-password may be reintroduced in 22c.1+ with a real sign-up flow; browser cache poisoning is not a concern"

patterns-established:
  - "Pattern: Next 16.2 proxy.ts as auth trust boundary — named export 'proxy' (NOT 'middleware'); export default; config.matcher narrowed to protected subtree only; cookie-presence check only (never cryptographic verification at the edge)"
  - "Pattern: Dead-route config-layer redirect — next.config.mjs async redirects() returning { source, destination, permanent: false } entries; strictly cheaper than wrapping a page component with redirect() since it fires before route resolution"

requirements-completed: [AMD-06, D-22c-FE-01, D-22c-UI-02, D-22c-UI-03]

# Metrics
duration: 4min
completed: 2026-04-20
---

# Phase 22c-oauth-google Plan 08: proxy.ts Frontend Auth Gate + Dead-Route Redirects Summary

**Next 16.2 proxy.ts file (renamed from middleware.ts per AMD-06) gates /dashboard/:path* with a 307-to-/login redirect when ap_session cookie is absent, while next.config.mjs redirects() 307s /signup + /forgot-password to /login at the config layer — closing the frontend auth boundary before React renders.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-20T01:18:15Z
- **Completed:** 2026-04-20T01:22:22Z
- **Tasks:** 2
- **Files modified:** 3 (1 created, 1 modified, 1 deleted)

## Accomplishments

- **frontend/proxy.ts shipped.** 29-line edge gate: `export default function proxy(request)` checks `request.cookies.get("ap_session")`; absent → `NextResponse.redirect(new URL("/login", request.url), 307)`; present → `NextResponse.next()`. Matcher: `["/dashboard/:path*"]`. Zero auth-flash — the redirect fires before React renders.
- **frontend/middleware.ts retired.** Deleted the 41-line file whose comment at L17-19 incorrectly claimed "The middleware file convention remains middleware.ts in Next.js 16. There is no proxy.ts rename" — factually wrong per nextjs.org/blog/next-16 and AMD-06. The file's broader matcher and orphaned `x-ap-has-session` header (zero downstream readers, verified via `grep -rn` returning no matches outside middleware.ts itself and stale `.next/` build artifacts) died with it.
- **frontend/next.config.mjs redirects() added.** Two entries: `/signup → /login` and `/forgot-password → /login`, both `permanent: false` (HTTP 307 temporary). Fires at config layer BEFORE page routes render; existing app/signup/page.tsx + app/forgot-password/page.tsx stay on disk untouched per the scope-boundary rule.
- **Live verification against pnpm dev confirmed every success criterion.** Below.

## Task Commits

Each task was committed atomically to main:

1. **Task 1: Create frontend/proxy.ts + delete frontend/middleware.ts** — `e71bb73` (feat)
2. **Task 2: Extend frontend/next.config.mjs with redirects() entries** — `e435d30` (feat)

## Live Verification (pnpm dev, localhost:3000)

Captured during execution:

```
/dashboard no-cookie:     HTTP 307  loc:http://localhost:3000/login   # proxy.ts gate
/dashboard with-cookie:   HTTP 200  loc:                              # passes through
/dashboard/x no-cookie:   HTTP 307  loc:http://localhost:3000/login   # subpath matcher
/dashboard/x with-cookie: HTTP 200  loc:                              # subpath passes
/signup:                  HTTP 307  loc:http://localhost:3000/login   # redirects() #1
/forgot-password:         HTTP 307  loc:http://localhost:3000/login   # redirects() #2
/ no-cookie:              HTTP 200                                    # matcher scope (correct)
/login no-cookie:         HTTP 200                                    # matcher scope (correct)
```

All must_haves from the plan frontmatter verified live:
- [x] `proxy.ts` exists and exports default `proxy(request)` matching `/dashboard/:path*`
- [x] `proxy.ts` checks for ap_session cookie presence; absent → 307 to /login; present → NextResponse.next()
- [x] `middleware.ts` DELETED (verify: `test ! -f frontend/middleware.ts` passes)
- [x] `next.config.mjs redirects()` returns entries redirecting /signup → /login and /forgot-password → /login, both temporary (permanent: false → 307)
- [x] Visiting /dashboard without cookie → 307 to /login BEFORE React renders (server-side gate, matches verification output)
- [x] Visiting /signup → server-side 307 to /login (matches verification output)
- [x] Visiting /forgot-password → server-side 307 to /login (matches verification output)

## Build Snippet

`pnpm build` tail (compile step):

```
> next build

▲ Next.js 16.2.0 (Turbopack)

  Creating an optimized production build ...
✓ Compiled successfully in 2.3s
  Skipping validation of types
```

The build then fails at the static-prerender stage on two pre-existing pages unrelated to this plan's file set:

- `/docs/config/page` — `TypeError: Cannot read properties of null (reading 'use')` (digest 2048828324)
- `/_not-found/page` — same React-context-null failure
- `/contact/page` — same cascading symptom

Both are documented as PRE-EXISTING in `.planning/phases/22c-oauth-google/deferred-items.md` (confirmed by the 22c-07 executor via `git stash` against clean `main` at commit `f1e7dd1`; identical digests). None of these pages import proxy, middleware, ap_session, useUser, or use-user (verified via `grep -rn` on /docs and /contact directories — zero matches). They are explicitly OUT OF SCOPE per the executor scope-boundary rule.

The frontend's deployment path is `next dev` behind Caddy per Phase 19 (not `next build`), so the prerender failures do not block 22c-09 or any downstream work. `next.config.mjs` already sets `typescript.ignoreBuildErrors: true` from an earlier phase.

## Files Created/Modified

- **`frontend/proxy.ts`** (NEW, 29 lines) — Next 16.2 edge gate. Imports `NextResponse` + `type NextRequest` from `next/server`. Exports `default function proxy(request)` + `const config = { matcher: ["/dashboard/:path*"] }`. Body matches RESEARCH Pattern 7 verbatim.
- **`frontend/next.config.mjs`** (MODIFIED, +12 lines) — `async redirects()` added as sibling to existing `async rewrites()`; returns two entries with `permanent: false`; explanatory comment references D-22c-UI-02 + D-22c-UI-03 and the browser-cache rationale for 307.
- **`frontend/middleware.ts`** (DELETED, 41 lines removed) — stale file with incorrect L17-19 rename-denial comment; broader matcher; orphaned `x-ap-has-session` header with zero downstream readers.

## Decisions Made

None beyond those pre-locked in CONTEXT.md (AMD-06, D-22c-FE-01, D-22c-UI-02, D-22c-UI-03) and the plan text. Execution followed the plan exactly.

## Deviations from Plan

**None — plan executed exactly as written.**

Zero Rule-1/2/3 auto-fixes. Zero Rule-4 architectural decisions surfaced. Every success criterion was met on first attempt:

- proxy.ts body matches RESEARCH Pattern 7 verbatim (plan Step 1)
- middleware.ts deleted cleanly (plan Step 2)
- `grep -rn "x-ap-has-session" frontend/` returns zero matches in source files (plan Step 3)
- `git diff frontend/app/signup/ frontend/app/forgot-password/` empty (plan Step 4)
- redirects() added as sibling to rewrites() without touching any other config key (Task 2)
- Both redirect entries carry `permanent: false` per D-22c-UI-02/03 (Task 2)

## Issues Encountered

- **None from this plan's changes.** The `pnpm build` prerender stage failures on `/docs/config`, `/_not-found`, and `/contact` are pre-existing and already documented in `deferred-items.md`; confirmed out-of-scope via file-set isolation (none of those pages touch proxy / middleware / ap_session / useUser).
- **`frontend/next-env.d.ts`** showed a modification in `git status` (path swap `.next/dev/types/` ↔ `.next/types/`). This is a Next-generated file regenerated every `pnpm build` / `pnpm dev` invocation; its own comment says "This file should not be edited". Intentionally left unstaged — outside this plan's scope.

## Scope Boundary Compliance

This plan touched exactly the three files listed in `files_modified` (proxy.ts new, next.config.mjs modified, middleware.ts deleted). The following pre-existing concerns were observed during execution and deliberately NOT addressed, per the scope-boundary rule:

- Prerender failures on /docs/config, /_not-found, /contact (documented in deferred-items.md)
- Auto-regenerated next-env.d.ts modification (Next infrastructure file)
- Pre-existing untracked `api_server/uv.lock` and `recon/` directory (unrelated to Phase 22c OAuth track)

## Threat Model Compliance

Plan frontmatter's `<threat_model>` registered three mitigations, all honored:

- **T-22c-26 (Spoofing — bogus ap_session cookie bypasses proxy.ts):** MITIGATED as designed. proxy.ts is the first gate against "obvious anonymous" traffic. A bogus cookie reaches the dashboard layout, whose useUser() hook (shipped in 22c-07) hits /v1/users/me, sees 401, redirects to /login. Defense-in-depth layers 1 + 2 are both wired.
- **T-22c-27 (Information disclosure — presence indicator):** ACCEPTED per plan. Cookie presence is observable via Set-Cookie and CSRF chatter anyway. No new exposure.
- **T-22c-28 (DoS — /signup redirect loop):** MITIGATED. `/login` is a distinct path from `/signup`; Next's redirect engine has loop detection; `permanent: false` is safe.

No threat flags (new security-relevant surface outside the registered threats) identified.

## Next Phase Readiness

- **22c-09 (Wave 5, cross-user isolation test + manual smoke + STATE close-out) is UNBLOCKED.** Wave 4 is now fully complete — 22c-06 (backend ANONYMOUS purge) + 22c-07 (frontend OAuth rewrite) + 22c-08 (this plan — proxy.ts + redirects) have all shipped. 22c-09 depends on all three.
- **Manual smoke test ready.** The 22c-09 smoke script can now exercise the complete OAuth loop end-to-end: unauthenticated visit to /dashboard → server-side 307 to /login (proxy.ts) → Google button → /api/v1/auth/google → Google consent → /api/v1/auth/google/callback → ap_session cookie set → /dashboard → proxy.ts passes through → useUser() hydrates /v1/users/me → Navbar shows real name/avatar → logout → POST /api/v1/auth/logout → router.push('/login').
- **No blockers.** proxy.ts and the redirects entries are verified working against `pnpm dev` (the prod deploy path per Phase 19 + Caddy). The prerender-time build failures on unrelated pages do not gate dev-server operation and are already logged as a future cleanup chore.

## Self-Check: PASSED

**Verified file existence:**
- `[ -f frontend/proxy.ts ]` → FOUND: frontend/proxy.ts
- `[ ! -f frontend/middleware.ts ]` → CONFIRMED ABSENT: frontend/middleware.ts
- `grep -q "async redirects" frontend/next.config.mjs` → FOUND: redirects entry in next.config.mjs

**Verified commits exist on main:**
- `git log --oneline | grep -q "e71bb73"` → FOUND: e71bb73 feat(22c-08): proxy.ts replaces middleware.ts
- `git log --oneline | grep -q "e435d30"` → FOUND: e435d30 feat(22c-08): /signup + /forgot-password 307 redirect

All claims in this SUMMARY are backed by verified file paths and live commit hashes.

---
*Phase: 22c-oauth-google*
*Plan: 08*
*Completed: 2026-04-20*
