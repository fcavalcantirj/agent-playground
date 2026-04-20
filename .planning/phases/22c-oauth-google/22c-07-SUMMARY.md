---
phase: 22c-oauth-google
plan: 07
subsystem: ui, auth
tags: [nextjs, react, oauth, sonner, dumb-client, useUser-hook, dashboard, navbar, login]

# Dependency graph
requires:
  - phase: 22c-oauth-google (plan 22c-05)
    provides: "Backend OAuth routes (GET /v1/auth/google + /v1/auth/github authorize+callback), GET /v1/users/me returning SessionUser, POST /v1/auth/logout, require_user gate"
  - phase: 22c-oauth-google (plan 22c-06)
    provides: "ANONYMOUS_USER_ID purged — all protected routes now require a real cookie → FE logout + redirect is the only escape hatch"
provides:
  - "frontend/hooks/use-user.ts — client-side useUser() hook: apiGet /api/v1/users/me on mount; ApiError.status===401 → router.push('/login'); non-401 errors keep user=null so UI stays in skeleton"
  - "frontend/app/login/page.tsx — rewritten: setTimeout theater removed; Google/GitHub buttons perform window.location.href top-level nav to /api/v1/auth/{google,github}; ?error=<code> renders sonner toast for access_denied|state_mismatch|oauth_failed; email+password form inputs all disabled; submit button disabled; dead /forgot-password Link removed (D-22c-UI-03)"
  - "frontend/app/dashboard/layout.tsx — 'Alex Chen' + 'alex@example.com' hardcode replaced with useUser() hook; user={undefined} while hook hasn't resolved so Navbar shows avatar-fallback 'U' skeleton (D-22c-FE-02 eager render)"
  - "frontend/components/navbar.tsx — Log out DropdownMenuItem rewritten: onSelect handler calls apiPost('/api/v1/auth/logout', {}) inside try/catch then router.push('/login') so session is invalidated server-side regardless of backend state"
affects: [22c-08, 22c-09, phase-23]

# Tech tracking
tech-stack:
  added: []  # sonner + next/navigation were already present in package.json
  patterns:
    - "useUser() hook pattern: single-owner session fetch; returns null during loading; self-redirects on 401. Future pages that need session context import this hook instead of redoing the fetch."
    - "Eager-render + skeleton-in-slot (D-22c-FE-02): dashboard layout renders immediately; only the per-user navbar slot shows a skeleton (AvatarFallback + 'User') until useUser resolves. No Suspense boundary, no full-page spinner."
    - "Top-level navigation for OAuth entry (window.location.href): fetch() cannot follow the 302 chain into Google/GitHub; MUST be a real page redirect. Documented inline in login/page.tsx so a future editor does not regress to apiPost."
    - "DropdownMenuItem async action pattern: onSelect={async (e) => { e.preventDefault(); await apiPost(...); router.push(...) }} — onSelect (not onClick) respects keyboard nav + fires AFTER the menu closes. e.preventDefault() suppresses the default close-without-action path."
    - "Exact-string error-code toast mapping (T-22c-25): URL ?error=<code> values are matched against a hardcoded switch (access_denied / state_mismatch / oauth_failed); unmapped values are silently ignored. The raw string is NEVER interpolated into React — toast content is always a constant literal."
    - "No client-side catalogs discipline preserved: login page does not ship its own 'provider list' — the two OAuth buttons are the inventory. If a third provider lands, the backend adds a new /v1/auth/<provider> endpoint and a new button is added manually; no dynamic provider catalog on the client."

key-files:
  created:
    - "frontend/hooks/use-user.ts — 47 lines; the session-fetching hook all authenticated pages consume"
  modified:
    - "frontend/app/login/page.tsx — 170 lines (was 150); setTimeout + isLoading + formData state deleted; useEffect error-toast + onGoogle/onGitHub + disabled form added"
    - "frontend/app/dashboard/layout.tsx — 116 lines (was 104); useUser() hooked into Navbar user prop; Alex Chen hardcode gone"
    - "frontend/components/navbar.tsx — 357 lines (was 344); useRouter + apiPost imports; Log out DropdownMenuItem rewrite; useRouter instance inside Navbar()"
    - ".planning/phases/22c-oauth-google/deferred-items.md — added 22c-07 section logging 3 pre-existing TS errors + pre-existing pnpm build prerender failures (both verified to exist on clean main without any 22c-07 changes)"

key-decisions:
  - "D-22c-FE-02 eager render: render the dashboard layout immediately; let the navbar user slot show a skeleton while useUser resolves. NO Suspense, NO full-page spinner. User sees the shell instantly."
  - "D-22c-FE-03 toast error codes: exact-string switch on ?error=<code>; unmapped values silently ignored to avoid reflecting attacker-controlled strings."
  - "D-22c-UI-01 password form visually present but disabled: inputs disabled + submit disabled + inline caption 'Use Google or GitHub above for now.' — user understands email/password is not a v1 feature."
  - "D-22c-UI-03 dead /forgot-password Link removed: no point steering users to a non-existent recovery flow."
  - "D-22c-UI-04 logout is a real server round-trip: apiPost /v1/auth/logout invalidates the sessions.revoked_at row; the client-side router.push is just the visual fallthrough."
  - "DropdownMenuItem onSelect over onClick for Log out: Radix's onSelect is the correct handler for keyboard + mouse; onClick on DropdownMenuItem fires before the menu closes and fights the default dismiss behavior."
  - "useUser returns SessionUser | null directly (not {user, loading, error}): simpler API; the plan explicitly allows this shape; loading state is implicit in user === null and consumers render skeletons based on that."

patterns-established:
  - "Pattern: useUser() hook — single-responsibility session reader. Fetches /v1/users/me once per mount. On 401, redirects to /login inline. Non-401 errors are logged (console.warn) and UI stays in skeleton state. Cancel flag prevents setState-on-unmounted on fast route changes."
  - "Pattern: OAuth entry via window.location.href in onClick — documented inline to prevent future regression to apiPost/fetch which cannot follow 302s."
  - "Pattern: Backend-owned logout — onSelect calls apiPost('/api/v1/auth/logout', {}) BEFORE router.push('/login'). try/catch swallows apiPost errors so a revoked/expired session still lands the user at /login."
  - "Pattern: Visually-present-but-disabled placeholder form — keeps the expected page shape for users scanning the login flow while explicitly communicating that the feature is not wired (caption copy 'Use Google or GitHub above for now.')."

requirements-completed: [R6, R7, D-22c-FE-02, D-22c-FE-03, D-22c-UI-01, D-22c-UI-04]

# Metrics
duration: ~15min
completed: 2026-04-20
---

# Phase 22c Plan 07: Login + Dashboard + Navbar — Real OAuth Wiring Summary

**Frontend ripped out setTimeout theater + 'Alex Chen' hardcode; Google/GitHub buttons now top-level nav to /api/v1/auth/*, dashboard consumes /v1/users/me via useUser hook, navbar Log out calls POST /v1/auth/logout — the frontend half of Phase 22c OAuth loop is in.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-20T00:58Z
- **Completed:** 2026-04-20T01:13Z
- **Tasks:** 3
- **Files modified:** 4 (1 new + 3 rewrites) + 1 deferred-items update

## Accomplishments

- Login page performs real OAuth navigation to backend endpoints — no more fake 1000ms setTimeout success redirect
- Dashboard reads the actual authenticated user from `/v1/users/me` via the new `useUser()` hook — no more `name: "Alex Chen"` hardcode
- Logout is a server-side session-invalidation (POST /v1/auth/logout) followed by client-side /login redirect
- Error-code toasts surface backend OAuth failures (access_denied / state_mismatch / oauth_failed) as sonner toasts without interpolating attacker-controlled strings
- Password form remains visually present (no layout break) but every input + submit button is disabled with an inline caption steering users to OAuth — honors D-22c-UI-01 without introducing a visual cliff

## Task Commits

Each task was committed atomically:

1. **Task 1: New hook frontend/hooks/use-user.ts** — `a541460` (feat)
2. **Task 2: Rewrite frontend/app/login/page.tsx** — `f1e7dd1` (feat)
3. **Task 3: Rewrite dashboard/layout.tsx + navbar.tsx** — `a549056` (feat)

**Plan metadata (this SUMMARY + STATE + ROADMAP):** pending final commit below.

## Files Created/Modified

- `frontend/hooks/use-user.ts` — NEW (47 lines). Exports `useUser(): SessionUser | null`. On mount: `apiGet<SessionUser>('/api/v1/users/me')` → on ApiError.status===401 → `router.push('/login')`; non-401 → `console.warn` + user stays null. `cancelled` flag on cleanup.
- `frontend/app/login/page.tsx` — Rewrite (170 lines). `useEffect` reads `?error=<code>` from `window.location.search` and fires sonner toast. `onGoogle`/`onGitHub` set `window.location.href` to `/api/v1/auth/google` / `/api/v1/auth/github`. `handleSubmit` only calls `e.preventDefault()`. Every form Input + submit Button has `disabled`. Inline caption below password field: "Use Google or GitHub above for now." `<Link href="/forgot-password">` deleted.
- `frontend/app/dashboard/layout.tsx` — Modified (116 lines). Imports `useUser` from `@/hooks/use-user`. Adds `const sessionUser = useUser()`. Navbar `user` prop is now `sessionUser ? { name: sessionUser.display_name, email: sessionUser.email ?? "", avatar: sessionUser.avatar_url } : undefined`. `isLoggedIn={true}` stays unconditional (the proxy.ts gate from 22c-08 is the real barrier).
- `frontend/components/navbar.tsx` — Modified (357 lines). Adds `import { useRouter } from "next/navigation"` + `import { apiPost } from "@/lib/api"`. Adds `const router = useRouter()` inside `Navbar()`. Log out `DropdownMenuItem` no longer uses `asChild` + `<Link href="/login">`; instead uses `onSelect={async (e) => { e.preventDefault(); try { await apiPost('/api/v1/auth/logout', {}) } catch {} router.push('/login') }}`.
- `.planning/phases/22c-oauth-google/deferred-items.md` — Added 22c-07 section documenting pre-existing TS errors + pre-existing pnpm build prerender failures.

## Decisions Made

None - followed plan as specified. All decisions (D-22c-FE-02, D-22c-FE-03, D-22c-UI-01, D-22c-UI-03, D-22c-UI-04) were prescribed in 22c-CONTEXT.md and are listed in `key-decisions` above for index visibility.

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria and grep gates passed on first try. Pre-existing issues discovered during `pnpm build` + `tsc --noEmit` verification were confirmed to exist on clean `main` (by stashing all 22c-07 edits and re-running) and logged to `deferred-items.md` per the scope-boundary rule; none were auto-fixed because none were caused by this plan's changes.

## Issues Encountered

**Pre-existing frontend TS errors (3) surface during `./node_modules/.bin/tsc --noEmit`**

Three errors predate 22c-07:
- `app/dashboard/agents/[id]/page.tsx:90` — TS2322 "running|stopped" vs "running"
- `components/footer.tsx:77` — TS2339 missing `external` on a union arm
- `components/particle-background.tsx:19` — TS2554 canvas getContext() missing arg

Evidence of pre-existence: reproduced on clean main (all three files untouched by this plan) with the same error messages. `next.config.mjs` sets `typescript.ignoreBuildErrors: true`, so not a dev-server blocker either. Logged to `deferred-items.md` 22c-07 section for a later "frontend type-clean" chore.

**Pre-existing `pnpm build` prerender failures (2)**

Two static-export prerender TypeErrors predate 22c-07:
- `/_global-error/page` — `Cannot read properties of null (reading 'useContext')`
- `/docs/config/page` — `Cannot read properties of null (reading 'use')`

Evidence of pre-existence: `git stash` the 22c-07 uncommitted edits → re-run `pnpm build` → identical errors with identical digests (`1666369206`, `2048828324`). Neither page is in the 22c-07 file set. Logged to `deferred-items.md` 22c-07 section. Phase 19 deploy path does NOT rely on `pnpm build` output (it uses `pnpm dev` behind Caddy); 22c-09 manual smoke will use the dev server.

## User Setup Required

None - no external service configuration required for this plan. Google + GitHub OAuth env vars are required to actually complete a login, but those are set up by plans 22c-03 (config) + 22c-09 (manual smoke); 22c-07 is pure frontend wiring.

## Next Phase Readiness

**22c-08 (Wave 4 sibling): Frontend proxy.ts + dead-route redirects.** Unblocked; 22c-07 adds no blockers for 22c-08. The `useUser()` hook already has a client-side 401→/login redirect, but 22c-08 lands the server-side (middleware) gate which is the real trust boundary.

**22c-09 (Wave 5): Cross-user isolation test + manual smoke + STATE close-out.** The login-page visible in the browser now performs real OAuth; 22c-09 can exercise the click → Google consent → /dashboard-with-real-name flow end-to-end.

**No blockers.** Phase 22c is 7/9 complete after this plan.

## Grep Evidence

```
$ cd frontend && grep -c setTimeout app/login/page.tsx
0

$ grep -c "window.location.href.*auth/google" app/login/page.tsx
1

$ grep -c "window.location.href.*auth/github" app/login/page.tsx
1

$ grep -c "Forgot password" app/login/page.tsx
0

$ grep -c "Alex Chen" app/dashboard/layout.tsx components/navbar.tsx
app/dashboard/layout.tsx:0
components/navbar.tsx:0

$ grep -c useUser app/dashboard/layout.tsx
3

$ grep -c "apiPost.*auth/logout" components/navbar.tsx
1

$ ./node_modules/.bin/tsc --noEmit 2>&1 | grep -E "hooks/use-user|app/login|app/dashboard/layout|components/navbar" | wc -l
0   # zero errors in any file this plan touches
```

## Screenshot Opportunity for 22c-09

22c-09 manual smoke should capture:
1. `http://localhost:3000/login` — shell with Google + GitHub buttons enabled, password form visibly disabled, "Use Google or GitHub above for now." caption visible
2. After Google consent round-trip — `http://localhost:3000/dashboard` navbar shows real Gmail display name (e.g. "Felipe Cavalcanti") + avatar_url from Google (not "Alex Chen", not "U" fallback)
3. Click navbar avatar → "Log out" DropdownMenuItem → session revoked server-side → lands at `/login` cleanly
4. `http://localhost:3000/login?error=access_denied` — sonner toast "Sign-in cancelled" appears top-right
5. `http://localhost:3000/login?error=state_mismatch` — sonner toast "Security check failed — try again"

## Self-Check: PASSED

Files verified on disk:
- `frontend/hooks/use-user.ts` FOUND
- `frontend/app/login/page.tsx` FOUND
- `frontend/app/dashboard/layout.tsx` FOUND
- `frontend/components/navbar.tsx` FOUND
- `.planning/phases/22c-oauth-google/22c-07-SUMMARY.md` FOUND
- `.planning/phases/22c-oauth-google/deferred-items.md` FOUND

Commits verified in git log:
- `a541460` FOUND — feat(22c-07): add useUser hook
- `f1e7dd1` FOUND — feat(22c-07): wire real OAuth buttons on login page + error toast
- `a549056` FOUND — feat(22c-07): dashboard uses useUser + navbar logout calls apiPost

---
*Phase: 22c-oauth-google*
*Completed: 2026-04-20*
