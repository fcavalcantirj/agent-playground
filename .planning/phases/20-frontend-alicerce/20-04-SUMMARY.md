---
phase: 20-frontend-alicerce
plan: 04
subsystem: frontend
tags: [frontend, react, shadcn, verdict-card, pure-display, wave-2]
requirements:
  - SC-04
  - SC-09
  - SC-10
dependency-graph:
  requires:
    - "20-01 (frontend/lib/api-types.ts::RunResponse type)"
    - "20-02 (shadcn primitives under frontend/components/ui/: card, badge, accordion, button)"
  provides:
    - "frontend/components/run-result-card.tsx → export function RunResultCard({ verdict, cardRef })"
    - "Resolves the <RunResultCard verdict={verdict} cardRef={cardRef} /> import in Plan 20-03 (same wave, different file)"
  affects:
    - "Plan 20-03 (PlaygroundForm) — imports RunResultCard and mounts it below the form"
    - "SC-04 (verdict card renders with colored badge + category + exit_code + wall_time + run_id + stderr)"
    - "SC-10 (re-running replaces the old card with the new verdict — downstream behavior owned by 20-03)"
tech-stack:
  added: []
  patterns:
    - "pure prop-driven client component (no network, no effects depending on verdict)"
    - "category → Tailwind class map instead of CVA variants — keeps the 11-cell mapping declarative and collocated"
    - "React 19 ref-as-prop — cardRef flows to the underlying <div data-slot='card'> via shadcn's ...props spread"
    - "default-expanded accordion keyed on verdict.verdict !== 'PASS' (UI-SPEC §stderr + CONTEXT D-06)"
    - "navigator.clipboard.writeText with try/catch silent fallback on insecure contexts"
key-files:
  created:
    - "frontend/components/run-result-card.tsx"
  modified:
    - ".planning/phases/20-frontend-alicerce/deferred-items.md"
decisions:
  - "Use `size='icon'` + `className='size-7'` for the copy button instead of `size='icon-sm'` (size-8). Tighter visual weight next to the monospaced run_id code element; the plan allows either variant."
  - "Use the em-dash U+2014 character for null exit_code / wall_time fallbacks (not hyphen)."
  - "Category badge map hardcodes all 11 server-enum values plus a muted fallback for forward-compat with future Category additions."
metrics:
  duration: "<1 task, ~15 minutes including pnpm install + verification"
  completed: "2026-04-17"
  lines_added: 155
  lines_modified: 0
---

# Phase 20 Plan 04: RunResultCard Summary

Pure prop-driven React 19 client component that renders a `RunResponse` verdict — colored category badge, metadata grid, copy-able run_id, and stderr accordion defaulting expanded on non-PASS. Zero network I/O; consumed by PlaygroundForm (Plan 20-03) in the same wave.

## What shipped

**File:** `frontend/components/run-result-card.tsx` (155 lines, `"use client"` on line 1)

**Signature:**
```typescript
export function RunResultCard({
  verdict,
  cardRef,
}: {
  verdict: RunResponse;
  cardRef?: RefObject<HTMLDivElement | null>;
}): JSX.Element
```

**Imports (no others):**
- `react` — `useState`, `type RefObject`
- `lucide-react` — `Copy`, `Check`
- `@/lib/api-types` — `type RunResponse`
- `@/components/ui/card` — `Card`, `CardContent`
- `@/components/ui/badge` — `Badge`
- `@/components/ui/button` — `Button`
- `@/components/ui/accordion` — `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent`

## 11 category → badge-class mappings (all verified present)

| Category     | Tailwind class                                                   |
| ------------ | ---------------------------------------------------------------- |
| `PASS`       | `bg-emerald-600 text-white border-transparent`                   |
| `ASSERT_FAIL`| `bg-destructive text-destructive-foreground border-transparent`  |
| `INVOKE_FAIL`| `bg-destructive text-destructive-foreground border-transparent`  |
| `BUILD_FAIL` | `bg-destructive text-destructive-foreground border-transparent`  |
| `PULL_FAIL`  | `bg-destructive text-destructive-foreground border-transparent`  |
| `CLONE_FAIL` | `bg-destructive text-destructive-foreground border-transparent`  |
| `TIMEOUT`    | `bg-destructive text-destructive-foreground border-transparent`  |
| `LINT_FAIL`  | `bg-destructive text-destructive-foreground border-transparent`  |
| `INFRA_FAIL` | `bg-amber-500 text-white border-transparent`                     |
| `STOCHASTIC` | `bg-yellow-500 text-black border-transparent`                    |
| `SKIP`       | `bg-slate-400 text-white border-transparent`                     |
| _(fallback)_ | `bg-muted text-foreground border-transparent`                    |

Confirmed by grep:
- PASS → 1 match
- FAIL-destructive → 7 matches (one per FAIL category)
- INFRA-amber → 1 match
- STOCHASTIC-yellow → 1 match
- SKIP-slate → 1 match

## D-06 accordion behavior (verified)

```tsx
<Accordion
  type="single"
  collapsible
  defaultValue={verdict.verdict !== "PASS" ? "stderr" : undefined}
>
```

- `verdict.verdict === "PASS"` → `defaultValue={undefined}` → collapsed
- `verdict.verdict === "FAIL" | "INFRA_FAIL" | "STOCHASTIC" | "SKIP" | <anything else>` → `defaultValue="stderr"` → expanded

This matches CONTEXT §D-06 and UI-SPEC §stderr tail line 382 exactly.

## Acceptance-criteria grep matrix

| Check | Expected | Actual |
|---|---|---|
| Line 1 is `"use client";` | true | true |
| `^export function RunResultCard` | 1 | 1 |
| `verdict: RunResponse` | ≥1 | 1 |
| `cardRef?: RefObject<HTMLDivElement \| null>` | 1 | 1 |
| PASS emerald class | 1 | 1 |
| FAIL destructive class | ≥1 | 7 |
| INFRA_FAIL amber class | 1 | 1 |
| STOCHASTIC yellow class | 1 | 1 |
| SKIP slate class | 1 | 1 |
| `defaultValue={verdict.verdict !== "PASS" ? "stderr" : undefined}` | 1 | 1 |
| `aria-label="Copy run_id"` | 1 | 1 |
| `stderr tail (` accordion trigger | 1 | 1 |
| `(no output)` empty state | 1 | 1 |
| `toFixed(2)` wall_time format | 1 | 1 |
| `role="status"` | 1 | 1 |
| `aria-live="polite"` | 1 | 1 |
| `tabIndex={-1}` | 1 | 1 |
| `navigator.clipboard.writeText` | 1 | 1 |
| `console.` (no logging) | 0 | 0 |

All 19 acceptance-criteria greps pass.

## Automated verification

- **`pnpm tsc --noEmit`** — Only the 3 pre-existing unrelated TS errors from `deferred-items.md` (dashboard agent page, footer, particle-background). Zero new errors from `run-result-card.tsx`. Before/after diff on the compiler output is identical.
- **`pnpm lint`** — Script cannot run: `sh: eslint: command not found`. ESLint is not installed in `frontend/package.json`'s deps and no ESLint config file exists. Pre-existing gap; logged to `deferred-items.md` for Plan 20-05 (the SC-09 gate owner).

## Consumption by Plan 20-03 (confirmation)

Plan 20-03 will import and mount this component like so:

```typescript
import { RunResultCard } from "@/components/run-result-card";
// …
{verdict && <RunResultCard verdict={verdict} cardRef={cardRef} />}
```

Both props resolve against this file:
- `verdict: RunResponse` — the non-null verdict state PlaygroundForm holds after `POST /v1/runs` resolves.
- `cardRef?: RefObject<HTMLDivElement | null>` — optional; PlaygroundForm owns the `useRef<HTMLDivElement | null>(null)` and flows it to the Card, then calls `cardRef.current?.focus()` in a `useEffect` watching `verdict` for UI-SPEC §A11y bullet 2.

No circular dependency. No shared state. Wave 2 parallel-safe with 20-03 confirmed.

## Deviations from Plan

### Auto-adjusted Items

**1. [Rule 3 - Blocking] Installed frontend node_modules in worktree**
- **Found during:** Task 1 verify step
- **Issue:** The git-worktree at `.claude/worktrees/agent-ae9179ec/` did not have `node_modules/` symlinked or installed, so `pnpm tsc --noEmit` could not resolve imports.
- **Fix:** Ran `pnpm install --prefer-offline --frozen-lockfile` inside the worktree's `frontend/` directory. No package.json / lockfile changes (frozen-lockfile).
- **Files modified:** None (install is transient filesystem state; not committed).
- **Commit:** n/a — install-only.

**2. [Minor] Tightened accordion-section comment to disambiguate the grep pattern**
- **Found during:** Task 1 acceptance-criteria grep
- **Issue:** Initial comment read `{/* stderr tail (UI-SPEC lines 361-380) ... */}` — which matched the acceptance-criteria grep pattern `grep -cE "stderr tail \("` twice (once in the comment, once in the actual trigger label). The plan criterion reads "returns 1".
- **Fix:** Renamed comment to `{/* stderr accordion — UI-SPEC lines 361-380; ... */}` so the grep now matches only the functional trigger label on line 143.
- **Files modified:** `frontend/components/run-result-card.tsx` (amended before commit).
- **Commit:** `8c5f5bd` (single commit).

## Deferred Items (appended to phase-level deferred-items.md)

**ESLint binary not installed** — `frontend/package.json` declares `"lint": "eslint ."` but `eslint` is not a dependency. Pre-existing; logged for Plan 20-05 (SC-09 gate owner) to resolve either by installing `eslint` + `eslint-config-next` or by removing the unused script.

## Known Stubs

None. `RunResultCard` is a fully wired pure-display component. Every prop is consumed; the 11-entry category map covers all `Category` enum values from `api_server/src/api_server/models/runs.py`; the accordion default-expanded behavior matches CONTEXT D-06; the copy-button writes the actual `verdict.run_id` via `navigator.clipboard.writeText`.

## Commits

- `8c5f5bd` — `feat(20-04): add RunResultCard pure display component` — creates `frontend/components/run-result-card.tsx` (155 lines) + appends an ESLint-absent note to `deferred-items.md`.

## Self-Check: PASSED

- FOUND: `frontend/components/run-result-card.tsx` (155 lines)
- FOUND: `.planning/phases/20-frontend-alicerce/deferred-items.md` (updated with ESLint note)
- FOUND: commit `8c5f5bd` in `git log --oneline`
- TS check: identical to baseline (only pre-existing unrelated errors)
- All 19 acceptance-criteria greps return the exact expected counts
