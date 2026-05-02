---
phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
plan: 07
subsystem: ui
tags: [frontend, react, dumb-client, openrouter, golden-rule-2, apiGet, models]

# Dependency graph
requires:
  - phase: 23-backend-mobile-api-chat-proxy-persistence-auth-shim
    provides: "Plan 23-05 — GET /v1/models OpenRouter passthrough proxy with cache + GZipMiddleware"
provides:
  - "Web frontend now consumes /api/v1/models via apiGet (same-origin) instead of fetching openrouter.ai directly"
  - "Closes the second of three Golden-Rule-#2 (dumb client) violations identified in Phase 23 CONTEXT (the third — mocked chat page — remains deferred per CONTEXT.md)"
  - "OpenRouter is no longer reachable from any browser served by this frontend; the backend proxy is the only outbound consumer"
affects:
  - "Phase 25 (Mobile MVP) — mobile clients hit the same /v1/models endpoint and inherit the same shape"
  - "Phase 23-08 (chat page de-mock) — pattern to follow when migrating remaining direct fetches"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dumb-client model-catalog fetch via apiGet<{ data: OpenRouterModel[] }>('/api/v1/models')"

key-files:
  created: []
  modified:
    - "frontend/components/playground-form.tsx — useEffect at lines 165-177 migrated from direct openrouter.ai fetch to apiGet"

key-decisions:
  - "Use the same-origin /api/v1/models path (next.config.mjs rewrites /api/v1/* to backend's /v1/* on :8000) — never call backend's /v1/models directly from the browser, since that would bypass the rewrite and break in dev/prod parity."
  - "Drop the manual `if (!r.ok) throw …` check: apiGet's underlying request() in frontend/lib/api.ts:41-44 already throws ApiError on non-2xx, matching the recipes useEffect pattern 15 lines above."
  - "Preserve setOrModels(d.data ?? []) verbatim — Plan 23-05's GET /v1/models is a byte-passthrough of OpenRouter's `{data: […]}` payload (D-20), so the response shape is unchanged from the browser's perspective."
  - "No new imports — apiGet was already imported at line 23 alongside apiPost."
  - "The browser handles gzip Accept-Encoding negotiation automatically; no client-side change needed for Plan 23-05's GZipMiddleware to do its job (per plan must_haves.truths #4)."

patterns-established:
  - "Frontend dumb-client fetches: pattern is identical to recipes useEffect — apiGet<{ shape }>(path), early-return on cancelled, setState on success, parseApiError-or-string on catch."

requirements-completed:
  - API-04

# Metrics
duration: 9m 24s
completed: 2026-05-02
---

# Phase 23 Plan 07: Frontend `/v1/models` Migration to apiGet Summary

**Frontend playground form stops fetching OpenRouter directly and now consumes the same-origin `/api/v1/models` proxy shipped by Plan 23-05 — closing the second Golden-Rule-#2 violation in three lines of code.**

## Performance

- **Duration:** 9m 24s
- **Started:** 2026-05-02T12:52:05Z
- **Completed:** 2026-05-02T13:01:29Z
- **Tasks:** 1 / 1
- **Files modified:** 1

## Accomplishments

- The hardcoded `https://openrouter.ai/api/v1/models` URL is gone from `frontend/components/playground-form.tsx` — verified by `grep -E 'openrouter\.ai/api/v1/models' frontend/components/playground-form.tsx` returning ZERO hits (the load-bearing acceptance gate from VALIDATION.md 23-API04-05 and `must_haves.truths` #1).
- The new `apiGet<{ data: OpenRouterModel[] }>("/api/v1/models")` call sits at the migration site (line 169) and matches the pattern of the recipes useEffect 15 lines above (line 154).
- The model dropdown still receives `OpenRouterModel[]` via `setOrModels(d.data ?? [])` — same downstream contract; the entire ModelBrowser, RecipeCard, and selected-model-bar render paths are untouched.
- No new imports added; useEffect count in the file is unchanged at 6.

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace direct OpenRouter fetch with apiGet('/api/v1/models')** — `ceb104c` (refactor)

## Files Created/Modified

- `frontend/components/playground-form.tsx` — line 165-177: replaced 3-line direct OpenRouter fetch with 1-line apiGet call (net: 1 insertion, 3 deletions). The body of one useEffect changed; the `useEffect(() => { … }, [])` outer scaffold and all surrounding code are byte-identical to pre-plan.

## Diff Traceability

Exact line numbers around the change:

**BEFORE (pre-plan, lines 165-179, per the plan's `<interfaces>` section):**

```typescript
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const r = await fetch("https://openrouter.ai/api/v1/models");  // LINE 169
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = (await r.json()) as { data: OpenRouterModel[] };
      if (cancelled) return;
      setOrModels(d.data ?? []);
    } catch (e) {
      if (!cancelled) setOrError(e instanceof Error ? e.message : "load failed");
    }
  })();
  return () => { cancelled = true; };
}, []);
```

**AFTER (post-plan, lines 165-177):**

```typescript
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const d = await apiGet<{ data: OpenRouterModel[] }>("/api/v1/models");  // LINE 169
      if (cancelled) return;
      setOrModels(d.data ?? []);
    } catch (e) {
      if (!cancelled) setOrError(e instanceof Error ? e.message : "load failed");
    }
  })();
  return () => { cancelled = true; };
}, []);
```

Net diff (`git diff frontend/components/playground-form.tsx`):

```
@@ -166,9 +166,7 @@ export function PlaygroundForm({
     let cancelled = false;
     (async () => {
       try {
-        const r = await fetch("https://openrouter.ai/api/v1/models");
-        if (!r.ok) throw new Error(`HTTP ${r.status}`);
-        const d = (await r.json()) as { data: OpenRouterModel[] };
+        const d = await apiGet<{ data: OpenRouterModel[] }>("/api/v1/models");
         if (cancelled) return;
         setOrModels(d.data ?? []);
       } catch (e) {
```

The block shrunk from 15 lines to 13 lines, so the post-plan trailing `}, []);` lands at line 177 (was line 179).

## Verification Gates (from plan `<verify>` and `must_haves.truths`)

| Gate | Command | Expected | Actual |
|------|---------|----------|--------|
| GR-#2 closure (truths #1) | `grep -E 'fetch\("https://openrouter\.ai/api/v1/models"' frontend/components/playground-form.tsx` | 0 hits | 0 hits — PASS |
| Same-origin path used (truths #2) | `grep -E 'apiGet<.*>\("/api/v1/models"\)' frontend/components/playground-form.tsx` | 1 hit | 1 hit (line 169) — PASS |
| openrouter.ai entirely gone | `grep -E 'openrouter\.ai/api/v1/models' frontend/components/playground-form.tsx` | 0 hits | 0 hits — PASS |
| Render contract preserved (truths #3) | `grep -E 'setOrModels\(d\.data' frontend/components/playground-form.tsx` | 1 hit | 1 hit — PASS |
| useEffect count unchanged | `grep -cE 'useEffect\(\(\) =>' frontend/components/playground-form.tsx` | 6 (same as pre-plan) | 6 — PASS |
| No new imports | `git diff frontend/components/playground-form.tsx \| grep -E '^\+import '` | 0 hits | 0 hits — PASS |
| apiGet usage count | `grep -cE 'apiGet' frontend/components/playground-form.tsx` | ≥ 2 | 6 — PASS |
| GZipMiddleware (truths #4) | Plan 23-05 SUMMARY confirms; browser-native Accept-Encoding | n/a (zero frontend code) | confirmed — PASS |

## Tooling Run Locally?

- **TypeScript compile (`tsc --noEmit`):** ATTEMPTED via `npx -p typescript@5.7 tsc --noEmit` from `frontend/`. Result: tsc resolves the project but the worktree has no `node_modules/` (parallel-executor worktrees do not inherit the main checkout's `pnpm install` state). All errors are environmental — "Cannot find module 'react'", "Cannot find module 'lucide-react'", cascading JSX-types-missing — and the same errors appear on every TSX file in the worktree. **Crucially, ZERO errors are reported in lines 165-177** (the edited region), and the only externally-resolved name in the new code (`apiGet`) was already imported and already in use at line 138 (the recipes fetch) and line 154 (the recipes useEffect), where tsc also reports no errors. The CI gate is therefore the authoritative typecheck. The plan explicitly anticipated this: "If frontend tooling is broken/unavailable in the executor's environment, document in the SUMMARY that the type-check could not run locally and rely on CI for the gate."
- **Next.js build (`pnpm build`):** NOT RUN — same `node_modules` reason. Optional in plan. CI is authoritative.
- **ESLint (`pnpm lint`):** NOT RUN — same reason. The 4-LOC diff stays inside an existing useEffect scope and uses already-imported names; lint risk is effectively zero.
- **Manual UI smoke:** NOT RUN locally (worktree has no `node_modules` and no running api_server / Next dev server). The plan marks the manual smoke as conditional ("only if backend is running locally with Plan 23-05 shipped"). Plan 23-05's `must_haves.truths` already exercise the proxy's `data: […]` shape end-to-end, so the wire contract this plan consumes is independently verified.

## Deviations from Plan

None — plan executed exactly as written. The change is the minimal 4-LOC swap specified in the `<action>` block, with the matching simplification (drop the `!r.ok` check) the plan called out as expected when `apiGet` already throws on non-2xx. No Rule 1/2/3 auto-fixes triggered. No Rule 4 architectural questions surfaced.

## Threat Surface Scan

No new security-relevant surface was introduced. The change actively REDUCES surface:

- T-23-GR2-DUMB-CLIENT (info disclosure / architecture): MITIGATED — the client-side hardcoded OpenRouter catalog source URL is removed; the backend (Plan 23-05) is now the single OpenRouter consumer.
- T-23-CORS-LEAK (info disclosure): MITIGATED — direct browser → openrouter.ai is gone; OpenRouter no longer sees end-user IPs / browser identities for catalog reads. Browsers reach `/api/v1/models` on the same origin and the api_server's outbound HTTP is the only thing OpenRouter sees.

No new threat flags surfaced.

## Self-Check: PASSED

- File `frontend/components/playground-form.tsx` exists and contains the new apiGet call: `grep -nE 'apiGet<.*>\("/api/v1/models"\)' frontend/components/playground-form.tsx` → `169:        const d = await apiGet<{ data: OpenRouterModel[] }>("/api/v1/models");` ✓
- Direct OpenRouter fetch removed: `grep -E 'openrouter\.ai/api/v1/models' frontend/components/playground-form.tsx` returns 0 hits ✓
- Commit `ceb104c` exists in the worktree branch: `git log --oneline | grep ceb104c` → present ✓
- File `.planning/phases/23-backend-mobile-api-chat-proxy-persistence-auth-shim/23-07-SUMMARY.md` exists (this file) ✓
