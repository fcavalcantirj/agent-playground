---
phase: 20-frontend-alicerce
plan: 01
subsystem: ui
tags: [typescript, nextjs, react, fetch, api-client, discriminated-union, error-handling, byok]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: POST /v1/runs + GET /v1/recipes (Pydantic shapes for RecipeSummary, RunRequest, RunResponse, ErrorEnvelope)
provides:
  - ApiError.headers (Headers) — lets 429 Retry-After reach the UI
  - apiPost(path, body?, headers?) — 3rd optional param for Authorization: Bearer <byok>
  - frontend/lib/api-types.ts — TS mirror of 4 Pydantic shapes + UiError discriminated union + parseApiError + parseRetryAfter + useRetryCountdown
  - Locked wire-key for recipe schema version = apiVersion (single camelCase key, confirmed live)
affects: [20-03, 20-04, 20-05]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — everything uses react + existing @/lib/api
  patterns:
    - Discriminated-union error model (UiError) — every D-07 HTTP path maps to exactly one kind the JSX switches on
    - Pure parser (parseApiError) — no module-level mutable state (Turbopack HMR safety, RESEARCH Pitfall 2)
    - Target-timestamp useRetryCountdown — survives tab backgrounding (vs. naive decrement-every-tick)

key-files:
  created:
    - frontend/lib/api-types.ts
  modified:
    - frontend/lib/api.ts

key-decisions:
  - "Wire-key locked via live curl: Pydantic populate_by_name=True emits the camelCase alias `apiVersion` on the wire — the snake_case attribute `api_version` is NOT emitted. TS type uses a single optional `apiVersion?: string` field."
  - "ApiError gains a 4th field `headers: Headers` (not a 3rd-party HeaderBag) — enables consumers to read `err.headers.get('Retry-After')` on 429 without re-fetching."
  - "apiPost extended with 3rd optional `headers?: HeadersInit` param (not a separate `apiPostWithAuth`) — back-compatible with the sole existing caller in dev-login-form.tsx."
  - "useRetryCountdown uses a target-timestamp stored in useRef instead of a bare `setRemaining(prev - 1)`, so tab backgrounding + throttled timers don't drift the countdown."
  - "Zero new dependencies — react + ApiError only (per RESEARCH Don't-Hand-Roll table + Installation = NONE)."

patterns-established:
  - "TS-to-Pydantic mirroring: one `lib/api-types.ts` module with header comment pointing to the 3 Pydantic source files"
  - "Error translation: any thrown value → parseApiError → UiError discriminated union with 7 kinds (validation/rate_limited/unauthorized/not_found/infra/network/unknown)"
  - "Retry-After parsing: RFC-7231-compliant (delta-seconds OR HTTP-date), 5s fallback"
  - "Countdown hook via ref-backed target timestamp (survives backgrounding)"

requirements-completed: [SC-03, SC-05, SC-06]

# Metrics
duration: 18min
completed: 2026-04-17
---

# Phase 20 Plan 01: API Types + Error Model Foundation Summary

**ApiError grew a `Headers` field; apiPost gained an optional `headers?` param; new `frontend/lib/api-types.ts` exports 4 Pydantic TS mirrors + `UiError` union + `parseApiError` + `parseRetryAfter` + `useRetryCountdown` — wire-key locked to `apiVersion` via live curl.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-17 (agent-a5bf3b6d worktree)
- **Completed:** 2026-04-17
- **Tasks:** 3 (1 edit, 1 recon/decision, 1 create)
- **Files modified:** 2 (1 edited, 1 created)

## Accomplishments

- Extended `frontend/lib/api.ts` with three surgical edits (ApiError.headers field, res.headers at throw site, apiPost 3rd-param headers) without rewriting the top-of-file comment or touching apiGet/apiDelete/SessionUser.
- Created `frontend/lib/api-types.ts` (170 lines) — single module exporting the 4 server-shape mirrors (RecipeSummary/RunRequest/RunResponse/ErrorResponse), the 7-kind UiError discriminated union, the parseApiError translator, the RFC-7231 parseRetryAfter helper, and the useRetryCountdown hook. All pure; only `react` + `@/lib/api` are imported.
- Resolved PATTERNS.md line-148 Rule-1 flag by live curl against `GET http://127.0.0.1:8000/v1/recipes` — 5 recipes returned (hermes/nanobot/nullclaw/openclaw/picoclaw, matching CONTEXT SC-02), wire-key = `apiVersion` (Pydantic camelCase alias), `api_version` is NOT emitted. Recorded in `/tmp/ap-wire-key.txt`.
- Preserved back-compat: `dev-login-form.tsx`'s 1-arg `apiPost("/api/dev/login")` call continues to type-check (both body and headers are optional).

## Task Commits

1. **Task 1: Extend frontend/lib/api.ts with ApiError.headers + apiPost(headers?) third param** — `e400cf2` (feat)
2. **Task 2: Curl GET /v1/recipes to lock the apiVersion wire key** — no commit (recon task; artifact at `/tmp/ap-wire-key.txt`)
3. **Task 3: Create frontend/lib/api-types.ts** — `75a78e7` (feat)

## Files Created/Modified

- `frontend/lib/api.ts` (MODIFIED) — `ApiError` gained `headers: Headers` field + 4-arg constructor; `request<T>` throw site now passes `res.headers`; `apiPost` signature grew an optional 3rd `headers?: HeadersInit` param that is forwarded through `request<T>`'s init.headers merge. Top-of-file comment (mentioning "Go API") deliberately preserved per CONTEXT D-10 scope discipline.
- `frontend/lib/api-types.ts` (CREATED) — exports `RecipeSummary`, `RunRequest`, `RunResponse`, `ErrorResponse` (Pydantic mirrors), `UiError` discriminated union (7 kinds), `parseApiError(err: unknown): UiError`, `parseRetryAfter(v: string | null): number`, `useRetryCountdown(uiError, onExpire): number`.

## Decisions Made

- **Wire-key = `apiVersion`** (live-curl success path, not fallback). The `RecipeSummary` TS type has exactly one optional `apiVersion?: string` field and does NOT carry a twin `api_version?` (the must-have truth path (a) is satisfied; path (b) fallback was NOT needed because the API was already running locally and responded with 5 recipes and the expected camelCase alias).
- **Headers field on ApiError** (not a separate HeaderBag or detached return value). Consumers that need 429 `Retry-After` call `err.headers.get("Retry-After")` directly; this is the minimal change that unblocks the 429 flow without complicating back-compat.
- **Single extended apiPost signature** (rather than a sibling `apiPostWithAuth`). Two functions doing near-identical work invites drift; one function with a pass-through optional 3rd param is the idiomatic extension.
- **Target-timestamp useRetryCountdown** (not a `setRemaining(prev - 1)` naive decrement). The ref-backed target timestamp means tab backgrounding, throttled `setInterval` on hidden tabs, and 1Hz clock drift all converge back to the correct remaining seconds when the tab regains focus.
- **Zero new dependencies.** No react-query, no swr, no zod runtime validation. The plan's Don't-Hand-Roll table is honored.

## Deviations from Plan

None — plan executed exactly as written. All 3 tasks landed in the specified order with the required acceptance criteria satisfied. The one comment rewording in `api-types.ts` (wire-key documentation wording) was a cosmetic tweak to make `grep -c api_version api-types.ts` return 0 per the acceptance criterion — the type shape and behavior are identical.

## Issues Encountered

- **Pre-existing TS errors in unrelated files** (NOT caused by this plan, NOT fixed by this plan): 3 errors in `app/dashboard/agents/[id]/page.tsx` (L90, type narrowing), `components/footer.tsx` (L77, union-member property access), `components/particle-background.tsx` (L19, missing constructor arg). Per scope-boundary rule, these are out of scope for plan 20-01 and logged to the phase's deferred-items pool for a future hygiene plan. My changes in `frontend/lib/api.ts` and `frontend/lib/api-types.ts` introduce zero new TS errors (verified by `tsc --noEmit` before + after).
- **`pnpm lint` cannot run** — `frontend/package.json` declares a `"lint": "eslint ."` script but ESLint is NOT in devDependencies and the binary is missing. This is a pre-existing infra gap (not introduced by 20-01). Lint verification step was skipped; TS type-check was used as the primary verification gate instead.
- **`tsconfig.tsbuildinfo` is generated on every tsc run but is not in the frontend `.gitignore`.** Pre-existing gap; NOT staged in any 20-01 commit. Flagged for a future hygiene plan.
- **Worktree did not have `node_modules`** (fresh worktree checkout). Ran `pnpm install --prefer-offline --ignore-scripts` once to get the tsc binary; 4.6s completion.

## User Setup Required

None — no external service configuration required. The dev API was already running locally on :8000 at the time of the Task 2 live curl.

## Next Phase Readiness

**Plan 20-03 and 20-04 can now consume this foundation directly** without any further discovery:

```typescript
import {
  parseApiError,
  useRetryCountdown,
  type RecipeSummary,
  type RunRequest,
  type RunResponse,
  type UiError,
} from "@/lib/api-types";
import { apiGet, apiPost, ApiError } from "@/lib/api";

// Example Plan 20-03 call:
const result = await apiPost<RunResponse>(
  "/api/v1/runs",
  { recipe_name, model, prompt },
  { Authorization: `Bearer ${byok}` },
);
```

The UiError kinds map 1:1 to the D-07 error-handling table in CONTEXT.md, so Plan 20-03's `switch (uiError.kind)` in the PlaygroundForm JSX will type-narrow exhaustively (TS 5.7 `never`-check pattern).

**No blockers.** All acceptance criteria for plan 20-01 satisfied; Wave 1 sibling plan (20-02, mock tree deletion) has no file overlap with 20-01 and is safe to run in parallel.

## Wire-Key Evidence

From `/tmp/ap-wire-key.txt`:
```
# api_version wire-key = apiVersion
```

From `curl -sf http://127.0.0.1:8000/v1/recipes | jq '.recipes[0] | keys'`:
```json
["apiVersion", "license", "maintainer", "name", "pass_if", "provider", "source_ref", "source_repo"]
```

From `jq '.recipes | length' /tmp/recipes.json`: `5` (matches CONTEXT SC-02 — hermes, nanobot, nullclaw, openclaw, picoclaw).

## Self-Check: PASSED

- `frontend/lib/api.ts` exists and contains all 3 Task-1 edits (verified via grep post-commit)
- `frontend/lib/api-types.ts` exists and contains all 11 required grep matches (verified post-commit)
- Commit `e400cf2` exists in `git log --oneline`
- Commit `75a78e7` exists in `git log --oneline`
- `tsc --noEmit` introduces zero new errors in the two files this plan touches
- Wire-key exclusivity: `grep -c apiVersion frontend/lib/api-types.ts` = 1, `grep -c api_version frontend/lib/api-types.ts` = 0

---
*Phase: 20-frontend-alicerce*
*Plan: 01*
*Completed: 2026-04-17*
