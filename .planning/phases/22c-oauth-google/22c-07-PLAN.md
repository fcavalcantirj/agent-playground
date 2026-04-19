---
phase: 22c-oauth-google
plan: 07
type: execute
wave: 4
depends_on: [22c-05]
files_modified:
  - frontend/hooks/use-user.ts
  - frontend/app/login/page.tsx
  - frontend/app/dashboard/layout.tsx
  - frontend/components/navbar.tsx
autonomous: true
requirements: [R6, R7, D-22c-FE-02, D-22c-FE-03, D-22c-UI-01, D-22c-UI-04]
must_haves:
  truths:
    - "frontend/app/login/page.tsx contains zero setTimeout occurrences"
    - "Clicking 'Continue with Google' performs window.location.href = '/api/v1/auth/google'"
    - "Clicking 'Continue with GitHub' performs window.location.href = '/api/v1/auth/github'"
    - "Email + password form inputs remain visually present but are disabled (no handler; submit button disabled)"
    - "?error=<code> URL param on /login shows a sonner toast; codes handled: access_denied, state_mismatch, oauth_failed"
    - "frontend/app/dashboard/layout.tsx contains zero 'Alex Chen' hardcodes"
    - "Dashboard layout fetches /api/v1/users/me via apiGet<SessionUser> on mount"
    - "On 401 from /users/me the layout calls router.push('/login')"
    - "Navbar's 'Log out' dropdown item calls apiPost('/api/v1/auth/logout', {}) then router.push('/login')"
    - "Dashboard eager-renders; navbar user slot shows skeleton/avatar-fallback until useUser() resolves"
  artifacts:
    - path: "frontend/hooks/use-user.ts"
      provides: "useUser() hook — apiGet SessionUser + 401 redirect"
    - path: "frontend/app/login/page.tsx"
      provides: "rewritten login page with real OAuth buttons + error toast"
    - path: "frontend/app/dashboard/layout.tsx"
      provides: "rewritten layout using useUser() hook"
    - path: "frontend/components/navbar.tsx"
      provides: "logout button wired to apiPost"
  key_links:
    - from: "frontend login button onClick"
      to: "backend /v1/auth/google via /api/v1 rewrite"
      via: "window.location.href (top-level nav required for OAuth)"
      pattern: "window.location.href.*auth.*(google|github)"
    - from: "frontend dashboard layout mount"
      to: "backend /v1/users/me"
      via: "apiGet<SessionUser>"
      pattern: "apiGet.*users.*me"
    - from: "frontend navbar Log out"
      to: "backend /v1/auth/logout"
      via: "apiPost then router.push /login"
      pattern: "apiPost.*auth.*logout"
---

<objective>
Rewrite three frontend files (plus one new hook) to replace the setTimeout + hardcoded-name theater with real backend round-trips:

1. **`frontend/hooks/use-user.ts`** (new) — fetches `/api/v1/users/me` on mount, redirects to `/login` on 401.
2. **`frontend/app/login/page.tsx`** — delete setTimeout; wire existing Google + GitHub buttons to `window.location.href`; disable email/password form (keep the visual shell); display `?error=<code>` toasts via sonner.
3. **`frontend/app/dashboard/layout.tsx`** — replace the `user={{ name: "Alex Chen", email: "..." }}` hardcode with the `useUser()` hook output; eager-render (no Suspense); on 401, redirect.
4. **`frontend/components/navbar.tsx`** — replace the `<Link href="/login">` Log out shim with a real `<button>` that calls `apiPost('/api/v1/auth/logout', {})` then `router.push('/login')`.

Purpose: Deliver the user-facing half of Phase 22c. After this plan, a manual click through localhost:3000/login leads to real Google/GitHub consent + a real session. Plan 22c-08 handles the `/dashboard` gate + dead-route redirects (separate concern).
Output: 4 files (1 new + 3 rewrites). No new dependencies — sonner is already in package.json per RESEARCH verification; no auth library on the frontend (backend owns it).
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
@frontend/lib/api.ts
@frontend/app/login/page.tsx
@frontend/app/dashboard/layout.tsx
@frontend/components/navbar.tsx
@frontend/package.json

<interfaces>
<!-- From frontend/lib/api.ts (already present — NO changes this plan) -->
```typescript
export class ApiError extends Error {
  status: number;
  // ... other fields
}
export async function apiGet<T>(path: string): Promise<T>;
export async function apiPost<T>(path: string, body: unknown): Promise<T>;
export async function apiDelete<T>(path: string): Promise<T>;
export interface SessionUser {
  id: string;
  email?: string;
  display_name: string;
  avatar_url?: string;
  provider?: string;
}
```

<!-- NavbarProps shape (from components/navbar.tsx — preserve) -->
```typescript
interface NavbarProps {
  isLoggedIn: boolean;
  user?: { name: string; email: string; avatar?: string };
}
```

<!-- sonner is in package.json (verified per RESEARCH.md line 65) -->
```typescript
import { toast } from "sonner";
toast.error("Sign-in cancelled");
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: New hook frontend/hooks/use-user.ts</name>
  <files>frontend/hooks/use-user.ts</files>
  <read_first>
    - frontend/lib/api.ts (ApiError + apiGet + SessionUser type — used directly, no changes)
    - frontend/hooks/ (existing hooks for naming conventions — `ls frontend/hooks/` before writing)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-FE-02 (eager render + 401 redirect)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §frontend/app/dashboard/layout.tsx (lines 776-813 — the hook shape)
  </read_first>
  <action>
Create `frontend/hooks/use-user.ts`. Exact body (copy verbatim):

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiGet, ApiError, type SessionUser } from "@/lib/api";

/**
 * useUser — fetches /api/v1/users/me on mount; on HTTP 401 redirects the
 * user to /login. The hook returns `null` until the first fetch resolves
 * so consumers can eager-render while the navbar user slot shows a
 * skeleton (per D-22c-FE-02).
 *
 * Failure modes:
 *  - 401: redirect to /login (session invalid)
 *  - Network error / 5xx: keep user as null; consumer can decide
 *    (navbar shows skeleton indefinitely, which is better than flashing
 *    an empty state).
 */
export function useUser(): SessionUser | null {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<SessionUser>("/api/v1/users/me")
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        // Non-401 error — leave user as null. The UI will continue to
        // render its skeleton state. Consider logging once in dev.
        // eslint-disable-next-line no-console
        console.warn("useUser: failed to fetch /users/me", err);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return user;
}
```

Check `frontend/hooks/` directory — if files there use a different file-suffix convention (e.g., `.tsx` vs `.ts`), match it. If the directory uses a barrel index (`index.ts`), add `export * from "./use-user";` to it.
  </action>
  <verify>
<automated>cd frontend && test -f hooks/use-user.ts && grep -q "export function useUser" hooks/use-user.ts && pnpm typecheck</automated>
  </verify>
  <acceptance_criteria>
    - `frontend/hooks/use-user.ts` exists
    - `export function useUser(): SessionUser | null` present
    - `pnpm typecheck` (or `tsc --noEmit`) passes with no errors
    - Hook compiles with strict mode (`SessionUser` type referenced from `@/lib/api`)
  </acceptance_criteria>
  <done>useUser hook ready for dashboard layout to consume.</done>
</task>

<task type="auto">
  <name>Task 2: Rewrite frontend/app/login/page.tsx (real OAuth buttons + error toast + disable password form)</name>
  <files>frontend/app/login/page.tsx</files>
  <read_first>
    - frontend/app/login/page.tsx (whole current file — preserve visual shape: buttons at L52-66, form at L?? — inspect before editing)
    - frontend/lib/api.ts (no changes; understand apiPost signature for the PATTERNS snippet below — it is NOT called here since OAuth needs top-level nav)
    - frontend/package.json (confirm sonner is a dep; already verified in RESEARCH)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-UI-01 (password form disabled w/ copy) + §D-22c-FE-03 (error toast codes) + §D-22c-UI-03 (remove Forgot password link)
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §frontend/app/login/page.tsx (lines 722-757)
  </read_first>
  <action>
Rewrite `frontend/app/login/page.tsx` preserving the existing visual shell (cards, Tailwind classes, overall copy tone) but ripping out every setTimeout + fake-success code path. The user should see the same LOOKING page; only the wiring changes.

Required semantic changes:
1. Mark the file `"use client"` at the top (if it is not already).
2. Add a `useEffect(() => { /* read ?error= from window.location.search + fire toast */ }, [])` near the top of the component function. Use the sonner toast — import it as `import { toast } from "sonner"`.
3. Replace any existing `handleSubmit` that calls `setTimeout` + `router.push("/dashboard")` with a stub that calls `e.preventDefault()` only. The form remains visible but submitting it does nothing.
4. Every input in the email/password form becomes `disabled`, and the submit button's `disabled` attribute is set to `true`. Add a short helper label near the form like `"Use Google or GitHub for now"` (D-22c-UI-01 — tooltip copy is Claude's discretion; inline caption text is fine).
5. Replace the onClick handlers of the Google button + GitHub button. They MUST do top-level navigation:
   ```typescript
   const onGoogle = () => { window.location.href = "/api/v1/auth/google"; };
   const onGitHub = () => { window.location.href = "/api/v1/auth/github"; };
   ```
   Why top-level nav: OAuth requires a true page redirect; `fetch` cannot follow the Google redirect chain.
6. If the page currently shows a `<Link href="/forgot-password">Forgot password?</Link>` near the password field, DELETE it (D-22c-UI-03 — avoid the dead-end loop).
7. The error-param toast logic (step 2) should handle these codes:
   - `access_denied` → `toast.error("Sign-in cancelled")`
   - `state_mismatch` → `toast.error("Security check failed — try again")`
   - `oauth_failed` → `toast.error("Sign-in failed — try again")`
   - Any other code → no toast (silently ignore — future codes must be explicitly mapped)

Final verify check must pass:
- `grep -c setTimeout frontend/app/login/page.tsx` returns `0`
- `grep -q "window.location.href.*auth/google" frontend/app/login/page.tsx`
- `grep -q "window.location.href.*auth/github" frontend/app/login/page.tsx`

Example skeleton (fill in with existing visual JSX preserved):

```typescript
"use client";

import { useEffect } from "react";
import { toast } from "sonner";
// ... existing imports ...

export default function LoginPage() {
  useEffect(() => {
    const err = new URLSearchParams(window.location.search).get("error");
    if (err === "access_denied") toast.error("Sign-in cancelled");
    else if (err === "state_mismatch") toast.error("Security check failed — try again");
    else if (err === "oauth_failed") toast.error("Sign-in failed — try again");
  }, []);

  const onGoogle = () => { window.location.href = "/api/v1/auth/google"; };
  const onGitHub = () => { window.location.href = "/api/v1/auth/github"; };

  return (
    // ... existing JSX ...
    // Replace Google/GitHub button onClick handlers with onGoogle/onGitHub.
    // Set every email/password input + submit button to disabled.
    // Remove the Forgot password Link.
  );
}
```

DO NOT add a Suspense boundary, DO NOT introduce a loading spinner, DO NOT change the visual layout. The surgical change is: disable fake login, wire real OAuth buttons, handle error param.
  </action>
  <verify>
<automated>cd frontend && ! grep "setTimeout" app/login/page.tsx && grep -q "window.location.href.*auth/google" app/login/page.tsx && grep -q "window.location.href.*auth/github" app/login/page.tsx && ! grep -q "Forgot password" app/login/page.tsx && pnpm typecheck</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c setTimeout frontend/app/login/page.tsx` returns 0
    - `grep -c "window.location.href.*/api/v1/auth/google" frontend/app/login/page.tsx` returns ≥1
    - `grep -c "window.location.href.*/api/v1/auth/github" frontend/app/login/page.tsx` returns ≥1
    - `grep -c "Forgot password" frontend/app/login/page.tsx` returns 0 (D-22c-UI-03)
    - Email + password inputs have `disabled` attribute
    - `pnpm typecheck` passes
    - Manual observation: opening http://localhost:3000/login in a browser renders the same visual (buttons, form, cards) as before
  </acceptance_criteria>
  <done>Login page performs real OAuth navigation; setTimeout theater deleted; error toasts wired.</done>
</task>

<task type="auto">
  <name>Task 3: Rewrite frontend/app/dashboard/layout.tsx + frontend/components/navbar.tsx</name>
  <files>frontend/app/dashboard/layout.tsx, frontend/components/navbar.tsx</files>
  <read_first>
    - frontend/app/dashboard/layout.tsx (whole current file — preserve sidebar + overlay + every JSX structure except the 'Alex Chen' prop at L39-45)
    - frontend/components/navbar.tsx (whole current file — find `isLoggedIn`/`user` props handling; find L231-236 dropdown Log out item)
    - frontend/hooks/use-user.ts (the hook just created in Task 1)
    - frontend/lib/api.ts (apiPost signature; already supports cookies via credentials: include)
    - .planning/phases/22c-oauth-google/22c-CONTEXT.md §D-22c-FE-02 + §D-22c-UI-04
    - .planning/phases/22c-oauth-google/22c-PATTERNS.md §frontend/app/dashboard/layout.tsx (lines 760-813) + §frontend/components/navbar.tsx (lines 816-846)
  </read_first>
  <action>
**Step 1: `frontend/app/dashboard/layout.tsx`.** Preserve everything except the Navbar prop block.

Current shape (simplified — confirm via Read before editing):
```typescript
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  // ... existing sidebar, overlay, etc. ...
  return (
    <div>
      <Navbar
        isLoggedIn={true}
        user={{
          name: "Alex Chen",
          email: "alex@example.com",
        }}
      />
      {/* ... existing children rendering ... */}
    </div>
  );
}
```

Replace with:
```typescript
"use client";

import { useUser } from "@/hooks/use-user";
// ... preserve every existing import + Navbar import ...

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const user = useUser();
  // ... preserve existing sidebar state, overlay state, etc. ...

  return (
    <div>
      <Navbar
        isLoggedIn={true}
        user={
          user
            ? {
                name: user.display_name,
                email: user.email ?? "",
                avatar: user.avatar_url,
              }
            : undefined
        }
      />
      {/* ... preserve children rendering ... */}
    </div>
  );
}
```

Key invariants:
- Mark the file `"use client"` if it isn't already (useUser requires client context)
- `isLoggedIn={true}` stays unconditional — the /dashboard gate (plan 22c-08's proxy.ts) already 307s unauthenticated visitors
- When `user` is `null` (hook hasn't resolved yet), pass `user={undefined}` so the Navbar shows its existing avatar-fallback / skeleton
- No Suspense boundary, no full-page spinner

**Step 2: `frontend/components/navbar.tsx`.** Two changes:

1. At the top of the `Navbar` function add:
   ```typescript
   import { useRouter } from "next/navigation";
   import { apiPost } from "@/lib/api";
   // ... existing imports ...

   export function Navbar({ isLoggedIn, user }: NavbarProps) {
     const router = useRouter();
     // ... existing body ...
   }
   ```
2. Find the dropdown Log out item at L231-236 (grep `Log out` in the file before editing). Current:
   ```tsx
   <DropdownMenuItem asChild className="text-destructive focus:text-destructive">
     <Link href="/login">
       <LogOut className="mr-2 h-4 w-4" />
       Log out
     </Link>
   </DropdownMenuItem>
   ```
   Replace with:
   ```tsx
   <DropdownMenuItem
     className="text-destructive focus:text-destructive"
     onSelect={async (e) => {
       e.preventDefault();
       try {
         await apiPost("/api/v1/auth/logout", {});
       } catch {
         // Server-side session may already be gone; fall through to redirect.
       }
       router.push("/login");
     }}
   >
     <LogOut className="mr-2 h-4 w-4" />
     Log out
   </DropdownMenuItem>
   ```

Note: `onSelect` is the correct handler for DropdownMenuItem (not `onClick`) — `onSelect` fires AFTER the menu closes and honors keyboard navigation. `e.preventDefault()` keeps the menu from running the default "close without action" path.

Do NOT wrap the navbar component in `"use client"` if it wasn't already — but if the file had `"use client"` at the top already (likely, since it uses hooks), preserve it.

Final commit:
```bash
cd /Users/fcavalcanti/dev/agent-playground && git add frontend/hooks/use-user.ts frontend/app/login/page.tsx frontend/app/dashboard/layout.tsx frontend/components/navbar.tsx
git commit -m "feat(22c-07): real login buttons + useUser + navbar logout"
```
  </action>
  <verify>
<automated>cd frontend && ! grep "Alex Chen" app/dashboard/layout.tsx components/navbar.tsx && grep -q "useUser" app/dashboard/layout.tsx && grep -q "apiPost.*auth/logout" components/navbar.tsx && pnpm typecheck && pnpm build 2>&1 | tail -5</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "Alex Chen" frontend/app/dashboard/layout.tsx frontend/components/navbar.tsx` returns 0
    - `grep -q "useUser" frontend/app/dashboard/layout.tsx` returns 0 exit (match found)
    - `grep -q "apiPost.*auth/logout" frontend/components/navbar.tsx` returns 0 exit (match found)
    - `pnpm typecheck` + `pnpm build` both pass
    - Commit on main: `feat(22c-07): real login buttons + useUser + navbar logout`
    - Manual (deferred to 22c-09 smoke): logged-in dashboard shows OAuth user's name in the navbar
  </acceptance_criteria>
  <done>Dashboard + navbar consume the real `/v1/users/me` endpoint. Log-out button invalidates the session server-side. Frontend half of the auth loop lands.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser -> /api/v1/auth/google via rewrite | Full-page nav through Next.js rewrite to backend. |
| useUser hook -> /api/v1/users/me | Same-origin fetch with HttpOnly cookie attached via credentials: include (existing apiGet default). |
| Logout apiPost -> /api/v1/auth/logout | Same-origin. Cookie sent + cleared on 204 response. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-22c-23 | Information disclosure | user.email leaked to non-owner | mitigate | /v1/users/me route queries `WHERE id = <session.user_id>` — user sees only their own row (backend). Frontend hook renders into navbar; the user viewing the navbar IS the owner. |
| T-22c-24 | Tampering | Malicious script calls apiPost /logout | accept | CSRF risk is low: SameSite=Lax cookie; logout only DELETEs the user's own session. Worst-case: user gets logged out unexpectedly. D-22c-OAUTH-04 covers Lax + HttpOnly. |
| T-22c-25 | Spoofing | Attacker crafts /login?error=XSS_PAYLOAD | mitigate | Error codes handled as exact-string switches (access_denied / state_mismatch / oauth_failed). Any other value yields no toast; no interpolation of the raw value into React. |
</threat_model>

<verification>
```bash
cd frontend && pnpm typecheck && pnpm build
grep -c setTimeout frontend/app/login/page.tsx   # -> 0
grep -c "Alex Chen" frontend/app/dashboard/layout.tsx frontend/components/navbar.tsx  # -> 0
```
Manual smoke (optional for this plan; required in 22c-09): click Google button, consent, verify /dashboard shows real Gmail name in navbar.
</verification>

<success_criteria>
- `frontend/hooks/use-user.ts` new file; exports `useUser()`
- `frontend/app/login/page.tsx` rewritten: 0 setTimeout; real OAuth nav; disabled password form; error toast
- `frontend/app/dashboard/layout.tsx` rewritten: useUser() consumed; no Alex Chen
- `frontend/components/navbar.tsx` modified: Log out calls apiPost + router.push
- `pnpm typecheck` + `pnpm build` pass
- Commit on main: `feat(22c-07): real login buttons + useUser + navbar logout`
</success_criteria>

<output>
After completion, create `.planning/phases/22c-oauth-google/22c-07-SUMMARY.md` with:
- Grep evidence: 0 setTimeout in login; 0 Alex Chen in layout/navbar
- Screenshot opportunity for 22c-09 manual smoke
- useUser hook integration point documented
</output>
