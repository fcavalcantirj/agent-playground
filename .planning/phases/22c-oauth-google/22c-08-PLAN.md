---
phase: 22c-oauth-google
plan: 08
type: execute
wave: 4
depends_on: [22c-05]
files_modified:
  - frontend/proxy.ts
  - frontend/middleware.ts
  - frontend/next.config.mjs
autonomous: true
requirements: [AMD-06, D-22c-FE-01, D-22c-UI-02, D-22c-UI-03]
must_haves:
  truths:
    - "frontend/proxy.ts exists and exports default `proxy(request)` matching /dashboard/:path*"
    - "proxy.ts checks for ap_session cookie presence; absent -> 307 redirect to /login; present -> NextResponse.next()"
    - "frontend/middleware.ts is DELETED (Next 16.2 rename per AMD-06 + the stale comment claiming no rename)"
    - "frontend/next.config.mjs async redirects() returns entries redirecting /signup -> /login and /forgot-password -> /login (both temporary 307)"
    - "Visiting /dashboard without cookie returns a 307 redirect to /login before React renders (server-side gate)"
    - "Visiting /signup server-side 307s to /login"
    - "Visiting /forgot-password server-side 307s to /login"
  artifacts:
    - path: "frontend/proxy.ts"
      provides: "Next 16 edge gate for /dashboard"
      contains: "matcher"
      contains: "ap_session"
    - path: "frontend/next.config.mjs"
      contains: "redirects"
  key_links:
    - from: "/dashboard request"
      to: "ap_session cookie presence check"
      via: "NextRequest.cookies.get"
      pattern: "request.cookies.get.*ap_session"
    - from: "/signup + /forgot-password"
      to: "/login"
      via: "next.config.mjs redirects() 307"
      pattern: "source.*signup.*destination.*login"
---

<objective>
Ship the frontend auth-gate + dead-route cleanup:
1. **Rename `frontend/middleware.ts` -> `frontend/proxy.ts`** per AMD-06 (Next.js 16.2 file-convention rename effective 2025-10-21). The existing file has an INCORRECT comment claiming the rename didn't happen; delete that file in the same step. The new `proxy.ts` narrows the matcher to `/dashboard/:path*` only (per D-22c-FE-01) and checks for `ap_session` cookie presence — absent means 307 to `/login` BEFORE React renders (zero auth-flash).
2. **Add `redirects()` to `next.config.mjs`** per D-22c-UI-02 + D-22c-UI-03: `/signup` -> `/login` and `/forgot-password` -> `/login`, both `permanent: false` (307 temporary) so the original pages can be re-enabled in a future phase without breaking browser caches.
3. The existing `frontend/app/signup/page.tsx` + `frontend/app/forgot-password/page.tsx` files STAY on disk UNTOUCHED — the next.config redirect intercepts the request before the page route can render. These files are NOT in `files_modified` because this plan does not read, write, or delete them. (Removing them would cascade into any component imports still referencing them, a risk not worth taking when a zero-touch redirect achieves the same user-visible behavior.)

Purpose: Close the frontend auth boundary and delete the two dead-end theater pages from the user's click paths.
Output: 1 new file (`proxy.ts`), 1 deleted file (`middleware.ts`), 1 modified file (`next.config.mjs`), 0 page-component edits.
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
@frontend/middleware.ts
@frontend/next.config.mjs
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create frontend/proxy.ts + delete frontend/middleware.ts</name>
  <files>frontend/proxy.ts, frontend/middleware.ts</files>
  <read_first>
    - frontend/middleware.ts (whole file — note the incorrect comment at L17-19 claiming no rename happened; this file is being retired)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §AMD-06 + §D-22c-FE-01
    - .planning/phases/22c-oauth-google/22c-RESEARCH.md §Pattern 7 (lines 560-583 — exact body) + §Anti-Patterns (DON'T use responses; DON'T assume middleware.ts-only)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §frontend/proxy.ts (lines 673-720)
  </read_first>
  <action>
**Step 1: Create `frontend/proxy.ts`** with the exact body from RESEARCH Pattern 7:

```typescript
// frontend/proxy.ts — Next.js 16 edge gate (renamed from middleware.ts per Next 16.2).
// Source: nextjs.org/docs/app/api-reference/file-conventions/proxy
//
// Gates /dashboard/:path* on the PRESENCE of the `ap_session` cookie. Does NOT
// validate the cookie server-side — validity checks live on the backend
// (/api/v1/users/me returns 401 if the cookie references an expired or revoked
// session, and the dashboard layout's useUser() hook handles that 401 by
// redirecting to /login).
//
// Purpose: avoid the auth-flash where an unauthenticated visitor briefly sees
// the dashboard shell before a client-side redirect fires.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default function proxy(request: NextRequest) {
  const session = request.cookies.get("ap_session");
  if (!session) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl, 307);
  }
  return NextResponse.next();
}

export const config = {
  // Match ONLY dashboard subroutes. Landing page, /login, /api/*, and all
  // static assets pass through untouched.
  matcher: ["/dashboard/:path*"],
};
```

**Step 2: Delete `frontend/middleware.ts`** entirely. The file contains:
- An incorrect comment (L17-19) claiming "The middleware file convention remains middleware.ts in Next.js 16. There is no proxy.ts rename." — factually wrong per nextjs.org/blog/next-16
- A broader matcher that runs on every non-`api|_next/static|_next/image|favicon.ico` route and sets a `x-ap-has-session` header that has zero downstream readers (verified in RESEARCH §Assumptions Log A9).

Delete it. The `proxy.ts` file is the complete replacement.

```bash
rm frontend/middleware.ts
```

**Step 3: Verify no file besides proxy.ts references `x-ap-has-session`:**
```bash
grep -rn "x-ap-has-session" frontend/ 2>/dev/null
```
Expected: zero matches.

Also verify Next 16's proxy detection picks up the new file:
```bash
cd frontend && pnpm build 2>&1 | tail -20
```
Should complete without "no proxy.ts or middleware.ts found" warning; Next picks up the edge config automatically.

**Step 4: Confirm NO edits to signup/page.tsx or forgot-password/page.tsx.** This plan does not touch those files. The redirect in Task 2 intercepts at the Next config layer before those page routes render. Running:
```bash
git diff --name-only frontend/app/signup/ frontend/app/forgot-password/ 2>/dev/null
```
must return empty.
  </action>
  <verify>
<automated>cd frontend && test -f proxy.ts && ! test -f middleware.ts && grep -q "matcher.*dashboard" proxy.ts && grep -q "ap_session" proxy.ts && pnpm build 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `frontend/proxy.ts` exists with `matcher: ["/dashboard/:path*"]` and `ap_session` cookie check
    - `frontend/middleware.ts` DOES NOT exist
    - `grep -rn "x-ap-has-session" frontend/` returns 0 matches
    - `pnpm build` succeeds (Next auto-detects proxy.ts)
    - `git diff frontend/app/signup/ frontend/app/forgot-password/` is empty (plan does not modify those files)
    - Manual: `curl -sI http://localhost:3000/dashboard` (with frontend server running) returns 307 redirect when no ap_session cookie present (deferred to 22c-09 manual smoke)
  </acceptance_criteria>
  <done>Next 16 edge gate lands. Dashboard is 307-gated before React renders. Stale middleware.ts with incorrect comment retired.</done>
</task>

<task type="auto">
  <name>Task 2: Extend frontend/next.config.mjs with redirects() entries</name>
  <files>frontend/next.config.mjs</files>
  <read_first>
    - frontend/next.config.mjs (whole file; confirm `rewrites()` block exists — the `redirects()` function is a sibling to rewrites)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-UI-02 + §D-22c-UI-03
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §next.config.mjs (lines 850-878) + §RESEARCH Pattern 8 (lines 587-597)
  </read_first>
  <action>
Extend `frontend/next.config.mjs`. Find the existing `async rewrites()` function; add `async redirects()` as a sibling (top-level config member) IMMEDIATELY AFTER rewrites.

If the existing file structure looks like:
```javascript
const nextConfig = {
  // ... other top-level config ...
  async rewrites() {
    return [
      // ... existing rewrite entries ...
    ];
  },
};

export default nextConfig;
```

Modify to:
```javascript
const nextConfig = {
  // ... preserve every other top-level config key unchanged ...
  async rewrites() {
    return [
      // ... preserve every existing rewrite entry unchanged ...
    ];
  },
  async redirects() {
    return [
      { source: "/signup", destination: "/login", permanent: false },
      { source: "/forgot-password", destination: "/login", permanent: false },
    ];
  },
};

export default nextConfig;
```

Key invariants:
- `permanent: false` => Next emits HTTP 307 (temporary). If the product re-introduces a real signup page in 22c.1+, the redirect can be removed without worrying about browser cache poisoning.
- Do NOT touch `rewrites()` entries or any other config key.
- Do NOT touch `frontend/app/signup/page.tsx` or `frontend/app/forgot-password/page.tsx`. The redirect fires at the Next config layer BEFORE the page routes render.
- If Next config file name is `next.config.ts` (not `.mjs`) because of a prior TypeScript migration, check with `ls frontend/next.config.*` before editing. Use the real filename.

Manual smoke (to be verified in 22c-09):
```bash
curl -sI http://localhost:3000/signup | grep -E "^(HTTP|location)"
# -> HTTP/1.1 307 Temporary Redirect
# -> location: /login
```

Commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add frontend/proxy.ts frontend/next.config.mjs && git rm frontend/middleware.ts
git commit -m "feat(22c-08): proxy.ts + signup/forgot-password redirects"
```
  </action>
  <verify>
<automated>cd frontend && grep -q "async redirects" next.config.mjs && grep -q "source.*signup.*destination.*login" next.config.mjs && grep -q "source.*forgot-password.*destination.*login" next.config.mjs && pnpm build 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -q "async redirects" frontend/next.config.mjs` returns 0 exit (match)
    - Two redirect entries present: `/signup` -> `/login` and `/forgot-password` -> `/login`
    - Both entries have `permanent: false` (307 temporary)
    - `pnpm build` succeeds
    - Commit on main: `feat(22c-08): proxy.ts + signup/forgot-password redirects`
    - `git log --oneline --all | head -5` shows the 22c-08 commit ABOVE the 22c-07 commit (or alongside it; parallel W4 plans can commit in either order)
  </acceptance_criteria>
  <done>Dead-route redirects land at the config layer. No theater pages reachable from the navbar.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser -> Next edge proxy | Proxy runs before page components; its decision is pre-render. |
| proxy.ts cookie read | Reads a cookie name only. Does not verify signature (that's the backend's job at /v1/users/me). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-26 | Spoofing | Attacker sets bogus ap_session cookie to bypass proxy.ts | mitigate | proxy.ts only gates against "obvious anonymous" traffic. A bogus cookie reaches the dashboard layout, whose useUser() hook hits /users/me, sees 401, redirects to /login. Defense-in-depth: proxy.ts is the first gate, useUser is the second. |
| T-22c-27 | Information disclosure | proxy.ts leaks session-presence indicator | accept | Cookie presence is already observable (Set-Cookie + CSRF chatter). No new information exposed. |
| T-22c-28 | DoS | /signup stuck in a redirect loop | mitigate | /login is a distinct path (not /signup); Next's redirect engine has loop detection; `permanent: false` is safe. Verified against Next 16 release notes. |
</threat_model>

<verification>
```bash
cd frontend && pnpm build
test -f frontend/proxy.ts
! test -f frontend/middleware.ts
```
Manual (required in 22c-09):
```bash
curl -sI http://localhost:3000/dashboard   # -> 307 with location: /login (no cookie)
curl -sI http://localhost:3000/signup      # -> 307 with location: /login
```
</verification>

<success_criteria>
- `frontend/proxy.ts` exists with correct matcher + cookie check + 307 redirect
- `frontend/middleware.ts` deleted
- `frontend/next.config.mjs` has `async redirects()` returning 2 entries
- `pnpm build` passes
- Commit on main: `feat(22c-08): proxy.ts + signup/forgot-password redirects`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-08-SUMMARY.md` with:
- proxy.ts body confirmed; matcher scope limited to /dashboard/:path*
- middleware.ts deletion confirmed; x-ap-has-session header no longer emitted
- redirects() entries confirmed; /signup + /forgot-password both 307 to /login
- Next.js build output snippet (tail -5 of pnpm build) pasted for verification
</output>
</output>
