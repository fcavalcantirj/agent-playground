---
phase: 20-frontend-alicerce
plan: 03
subsystem: frontend
tags: [frontend, react, client-component, byok, error-handling, a11y]
requires:
  - frontend/lib/api.ts::apiGet
  - frontend/lib/api.ts::apiPost
  - frontend/lib/api-types.ts::RecipeSummary
  - frontend/lib/api-types.ts::RunResponse
  - frontend/lib/api-types.ts::UiError
  - frontend/lib/api-types.ts::parseApiError
  - frontend/lib/api-types.ts::useRetryCountdown
provides:
  - frontend/components/playground-form.tsx::PlaygroundForm
affects:
  - frontend/app/playground (wired by Plan 20-05, Wave 3)
tech-stack:
  added: []
  patterns:
    - "client-component with useState + useEffect + useCallback"
    - "discriminated-union UiError dispatch (switch on uiError.kind)"
    - "BYOK clearing in finally block (CONTEXT D-05 strictest reading)"
    - "native <select> populated from GET /api/v1/recipes (golden rule #2)"
    - "ref null-union form for cross-plan prop compatibility"
key-files:
  created:
    - frontend/components/playground-form.tsx
  modified: []
decisions:
  - "Wrapped Deploy / Retry-in-Ns button labels in <span> to satisfy the >Deploy< verbatim-CTA acceptance grep while preserving plan's ternary structure"
  - "Narrowed E-fallback requestId access with a uiError.kind === 'not_found' type guard (UiError 'unknown' variant has no requestId field)"
metrics:
  duration_sec: 281
  completed_date: "2026-04-17"
  tasks_completed: 2
  files_created: 1
  files_modified: 0
  lines_added: 420
---

# Phase 20 Plan 03: `<PlaygroundForm>` Client Component Summary

Implemented the load-bearing stateful React component that replaces the 1001-line `agent-configurator.tsx` mock: fetches recipes from `GET /api/v1/recipes` on mount, owns the four form fields (recipe / model / BYOK / prompt), submits `POST /api/v1/runs` with `Authorization: Bearer <byok>`, clears the BYOK key in the `finally` block (SC-05 strict), and renders all six D-07 error states via a `switch`-like dispatch on `uiError.kind`.

## What Was Built

**Output artifact:** `frontend/components/playground-form.tsx` (420 lines)

**Exported component:** `export function PlaygroundForm(): JSX.Element`

**State owned (all local, no module-level):**
- `recipes: RecipeSummary[] | null` — fetched on mount, alphabetized
- `recipe, model, byok, prompt: string` — the four controlled form fields
- `isRunning: boolean` — in-flight flag driving spinner + disabled gate
- `verdict: RunResponse | null` — last successful run result (rendered via `<RunResultCard>`)
- `uiError: UiError | null` — typed error state driving 6 error branches
- `cardRef: useRef<HTMLDivElement | null>(null)` — null-union form for prop-type parity with Plan 20-04's `RefObject<HTMLDivElement | null>`

**Effects:**
- Mount-effect `useEffect([])` fetches `/api/v1/recipes`, guards against unmount via a `cancelled` flag.
- Focus-on-verdict `useEffect([verdict])` moves focus to `cardRef.current` when a verdict renders (UI-SPEC a11y rule).
- `useRetryCountdown(uiError, onRetryExpire)` ticks down the 429 cooldown, clearing the error when the clock hits zero.

**Handlers:**
- `fetchRecipes` (stable `useCallback`) — reusable by empty-state + load-failed Retry buttons.
- `onRetryExpire` (stable `useCallback`) — wraps `setUiError(null)` so `useRetryCountdown`'s effect doesn't churn.
- `onDeploy` — clears `verdict` + `uiError`, sets `isRunning`, POSTs with `Authorization: Bearer <byok>`, `setVerdict` on success, `setUiError(parseApiError(e))` on failure, and in `finally` always clears `byok` and `isRunning`.

## The 30 Locked Copy Strings (all grep-confirmed at build time)

| # | String | Location in JSX |
|---|---|---|
| 1 | `Loading recipes…` | `<option>` while `recipes === null` |
| 2 | `Select a recipe…` | `<option>` when recipes loaded |
| 3 | `Recipe` | Field 1 `<Label>` |
| 4 | `No recipes available` | empty-state `<AlertTitle>` |
| 5 | `The API returned an empty recipe list. Check the server and retry.` | empty-state description |
| 6 | `Could not load recipes` | load-failed `<AlertTitle>` |
| 7 | `Retry` | empty-state / load-failed / network buttons (3 sites) |
| 8 | `Model` | Field 2 `<Label>` |
| 9 | `e.g., openai/gpt-4o-mini` | Model `<Input>` placeholder |
| 10 | `browse models` | link to `https://openrouter.ai/models` |
| 11 | `API key` | Field 3 `<Label>` |
| 12 | `sk-or-v1-...` | BYOK placeholder |
| 13 | `API key (sent as Authorization: Bearer, never stored)` | BYOK `aria-label` |
| 14 | `Sent once with this run. Never stored.` | BYOK helper paragraph |
| 15 | `Prompt` | Field 4 `<Label>` |
| 16 | `What should the agent do?` | Textarea placeholder |
| 17 | `Deploy` | submit button label (ternary else branch) |
| 18 | `Running…` | button + running-placeholder (2 sites) |
| 19 | `Retry in ${remainingSec}s` | 429-cooldown button label |
| 20 | `Rate limited` | 429 `<AlertTitle>` |
| 21 | `Retry in {remainingSec} s. The API is throttling requests.` | 429 description |
| 22 | `Request ID:` | shown in 4 error branches when `requestId` is present |
| 23 | `Invalid or missing API key` | 401/403 `<AlertTitle>` |
| 24 | `Check your OpenRouter / Anthropic / OpenAI key and try again.` | 401/403 description |
| 25 | `Infrastructure error` | 502 `<AlertTitle>` |
| 26 | `Could not reach API` | network `<AlertTitle>` |
| 27 | `Check your connection and try again.` | network description |
| 28 | `Request failed` | fallback `<AlertTitle>` |
| 29 | `— include when reporting.` | 502 requestId trailer |
| 30 | `Request ID:` (with leading space) | fallback requestId trailer |

Ellipsis character (`…`) used verbatim — not three dots — for strings #1, #2, #18.

## The 6 Error-State Branches (D-07 coverage)

| Branch | Guard (on `uiError.kind`) | Rendered element |
|---|---|---|
| E1 — inline 422 | `validation` with `field === 'model'` or `field === 'prompt'` | `<p role="alert">` attached to the failing field via `aria-describedby` |
| E1' — 422 without field | `validation` with `!field` | `<p role="alert">` below the Deploy button |
| E2 — 429 | `rate_limited` | `<Alert role="status" aria-live="polite">` with amber border + Clock icon + countdown |
| E3 — 401/403 | `unauthorized` | `<Alert variant="destructive">` — never echoes the key |
| E4 — 502/503/500 | `infra` | amber `<Alert>` with AlertCircle + request-ID trailer |
| E5 — network | `network` | neutral `<Alert>` with WifiOff + Retry button calling `onDeploy` |
| E-fallback | `unknown \|\| not_found` | `<Alert variant="destructive">` with Request ID for `not_found` only |

Every branch is reachable by a distinct `uiError.kind`; a TS discriminated union forces exhaustiveness at compile time.

## SC-05 BYOK Hardening (grep-confirmed)

- `byok` exists only in React state — no `localStorage`, no `sessionStorage`, no `window.*`.
- `onDeploy`'s `finally` block contains `setByok("")` — clears the key on success OR failure.
- No `console.*` call in the file (no accidental logging surface).
- BYOK `<Input>` uses `autoComplete="new-password"`, `autoCorrect="off"`, `autoCapitalize="off"`, `spellCheck={false}` (Pitfall 4).
- The 401/403 alert copy never references the key value.

## Cross-Plan Ref Type Alignment (W-4 lock)

`cardRef` is declared as `useRef<HTMLDivElement | null>(null)` — the null-union form — so it structurally matches Plan 20-04's `RunResultCard` prop type `cardRef?: React.RefObject<HTMLDivElement | null>`. The shorter form `useRef<HTMLDivElement>(null)` would not assign to that prop on `@types/react` ≥ 19.2.

## Commits

| Task | Commit | Description |
|---|---|---|
| 1 | `d9f7f13` | Scaffold with imports, state, effects, `onDeploy` handler, placeholder `return null` |
| 2 | `880dae1` | Replace placeholder with full JSX (form, Deploy button, 6 error branches, verdict mount) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Narrow `uiError.requestId` access in the E-fallback branch**
- **Found during:** Task 2 tsc verification
- **Issue:** The plan's verbatim template accessed `uiError.requestId` inside a block guarded by `uiError?.kind === "unknown" || uiError?.kind === "not_found"`. The `unknown` variant of `UiError` has no `requestId` field — only `message` and optional `status`. TypeScript raised `TS2339: Property 'requestId' does not exist on type '{ kind: "unknown"; message: string; status?: number | undefined; }'` at two call sites.
- **Fix:** Wrapped the `requestId` trailer in an inner `uiError.kind === "not_found" && uiError.requestId && …` guard. Behavior preserved for the `not_found` case; the `unknown` case now simply renders the message without a request-ID line (which is the correct semantic — `unknown` variants never carry a request ID).
- **Files modified:** `frontend/components/playground-form.tsx` lines 408–413
- **Commit:** `880dae1`

**2. [Rule 3 — Blocking] Wrap Deploy / Retry-in-Ns labels in `<span>`**
- **Found during:** Task 2 acceptance-criteria grep
- **Issue:** The plan template's Deploy button ternary ended with `: ("Deploy")` — a bare string expression — but the acceptance criteria required `grep -cE ">Deploy<" ... returns >= 1` which only matches element-text boundaries. The plan template and its own acceptance criteria were internally inconsistent.
- **Fix:** Wrapped the two non-spinner ternary branches in `<span>…</span>`. The visible button remains identical (React renders string and span text identically in a flex-centered button), but the grep gate now passes.
- **Files modified:** `frontend/components/playground-form.tsx` line 313, 315
- **Commit:** `880dae1`

## Known Planning Artifacts (not bugs)

These are plan-internal grep-count artifacts where the plan's own documentation comments cause spurious matches. The code itself conforms:

- `grep -cE "useRef<HTMLDivElement>\(null\)" … returns 0` — the acceptance check returns 1 in this file because the plan's template includes that exact string inside an explanatory comment (lines 95–96) documenting why the forbidden form is forbidden. The real `useRef` call (line 98) uses the correct null-union form, which the `useRef<HTMLDivElement \| null>\(null\)` grep confirms. No remediation needed — both strings were dictated verbatim by the plan.
- `grep -cE "<RunResultCard" … returns 1` — the acceptance check returns 2 because the plan's own JSDoc comment on line 91 contains the literal `<RunResultCard>` token ("The ref + tabIndex=-1 live on the `<RunResultCard>` element …"). The actual JSX element usage appears exactly once (line 339). No remediation needed.

## Deferred / Expected Cross-Plan Race

**Cross-plan race — Plan 20-04's `RunResultCard` missing module:**
- `pnpm tsc --noEmit` reports one expected error in this file:
  ```
  components/playground-form.tsx(26,31): error TS2307: Cannot find module '@/components/run-result-card' or its corresponding type declarations.
  ```
- This is explicitly anticipated by the plan's W-1 / cross-plan-race precondition note (plan lines 293–294 + 335). Plan 20-04 is the same-wave sibling that creates `frontend/components/run-result-card.tsx` in a separate parallel worktree. After the orchestrator merges both Wave 2 worktrees, the module resolves and this error clears.
- No remediation inside this plan is appropriate (would cross the file-ownership boundary).

**Pre-existing baseline failures (NOT caused by this plan, per `<wave_2_context>` and `deferred-items.md`):**
- 3 TS errors in `app/dashboard/agents/[id]/page.tsx`, `components/footer.tsx`, `components/particle-background.tsx` — all untouched by Phase 20.
- `pnpm lint` fails to execute because ESLint is not installed as a dev dependency (`sh: eslint: command not found`). The lint script exists in `package.json` but `node_modules/.bin/eslint` is absent after `pnpm install`. This is a pre-existing baseline tooling gap; fixing it belongs to a separate task (likely Plan 20-05 Task 4 or a tooling cleanup).

## Authentication Gates

None — this plan is pure client-component work; no API or auth interaction during build.

## Self-Check: PASSED

- `frontend/components/playground-form.tsx`: FOUND (420 lines)
- Commit `d9f7f13`: FOUND in `git log`
- Commit `880dae1`: FOUND in `git log`
- All 30 locked copy strings: grep-verified present
- BYOK `finally` clearing: grep-verified (`setByok("")` on line 130)
- `cardRef` null-union form: grep-verified (line 98)
- 6 D-07 error branches: visually confirmed at lines 342, 358, 374, 390, 402 + inline validations
- Cross-plan tsc race: expected and documented (sibling worktree will resolve on merge)

## TDD Gate Compliance

Not applicable — Plan 20-03 is declared `type: execute` (not `tdd`). No RED/GREEN/REFACTOR cycle required.
