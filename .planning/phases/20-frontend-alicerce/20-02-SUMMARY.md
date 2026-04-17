---
phase: 20-frontend-alicerce
plan: 02
subsystem: ui

tags: [nextjs, react, frontend, cleanup, delete-and-verify, sc-07, sc-08, dumb-client]

# Dependency graph
requires:
  - phase: 19-api-foundation
    provides: Live POST /v1/runs + GET /v1/recipes endpoints (enforces golden rule #2 from the API side; this plan removes the client-side catalogs that violated the rule)
provides:
  - Clean frontend/components/ tree with zero hardcoded recipe/model/channel catalogs
  - /playground page that compiles against a placeholder <div className="mx-auto max-w-2xl"> slot (Plan 20-05 fills it with <PlaygroundForm>)
  - Homepage (app/page.tsx) free of mock PlaygroundSection
  - Deferred-items log for Plan 20-05 to address pre-existing build prerender failure
affects:
  - 20-03 (PlaygroundForm build target — now has clean tree)
  - 20-04 (RunResultCard build target — now has clean tree)
  - 20-05 (page.tsx wiring — can drop <PlaygroundForm /> into the placeholder)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Deletion-before-wiring pattern: remove importers first (Task 2), then delete import targets (Task 3), to avoid a moment where the build has dangling imports"
    - "Placeholder slot pattern: leave an empty <div> at the exact final container shape so the follow-up wiring plan is a single-component drop-in"

key-files:
  created:
    - .planning/phases/20-frontend-alicerce/deferred-items.md  # logs out-of-scope pre-existing TS+build errors
    - .planning/phases/20-frontend-alicerce/20-02-SUMMARY.md
  modified:
    - frontend/app/playground/page.tsx  # dropped AgentConfigurator import + mount, left empty max-w-2xl <div>
    - frontend/app/page.tsx  # dropped PlaygroundSection import + usage
    - frontend/.gitignore  # added tsconfig.tsbuildinfo (TS incremental build cache, generated)
  deleted:
    - frontend/components/agent-configurator.tsx  # 1001-line mock root
    - frontend/components/agent-card.tsx  # exported defaultClones catalog
    - frontend/components/model-selector.tsx  # exported openRouterModels catalog
    - frontend/components/a2a-network.tsx  # mock A2A network UI
    - frontend/components/task-orchestrator.tsx  # mock task UI
    - frontend/components/playground-section.tsx  # homepage section that embedded AgentConfigurator

key-decisions:
  - "Deleted 6 files (5 mock components + 1 homepage section wrapper) in a single commit after neutralizing their usage sites — keeps the build green throughout the task sequence"
  - "Added tsconfig.tsbuildinfo to frontend/.gitignore because the TS incremental cache was appearing as untracked after running tsc"
  - "Logged 3 pre-existing TS errors and the pre-existing prerender build failure to deferred-items.md — all confirmed present on the Phase 20 base commit db877c9, out of scope per executor scope boundary rule"

patterns-established:
  - "Two-phase delete: remove import statements from consumers first, then delete the imported files. This prevents 'Module not found' errors from ever appearing in the build log."
  - "Placeholder container shape: when staging a delete that will be re-wired in a later plan, leave the exact final wrapper shape (<div className='mx-auto max-w-2xl'>) with an HTML comment pointing to the plan that fills it in. Makes the wiring plan a single-component swap."

requirements-completed:
  - SC-07
  - SC-08

# Metrics
duration: ~18min
completed: 2026-04-17
---

# Phase 20 Plan 02: Mock Tree Deletion Summary

**Deleted the 6-file mock component tree (2406 lines) that violated golden rule #2, cleaned up homepage + playground page imports, left an empty max-w-2xl placeholder slot that Plan 20-05 will fill with the real PlaygroundForm.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-04-17T19:20:17Z
- **Completed:** 2026-04-17T19:38:17Z
- **Tasks:** 4 (all executed autonomously; no checkpoints)
- **Files modified:** 3 (playground/page.tsx, app/page.tsx, frontend/.gitignore)
- **Files deleted:** 6 (5 mock components + playground-section.tsx)
- **Files created:** 2 (deferred-items.md, this SUMMARY)
- **Lines removed:** 2406

## Accomplishments

- SC-07 achieved: zero hardcoded recipe / model / channel catalog arrays under `frontend/app/playground/` or `frontend/components/`. `defaultClones`, `openRouterModels`, and channel literals (`"telegram"`, `"discord"`, `"slack"`, `"whatsapp"`, `"signal"`, `"webhook"`) all removed from the playground subtree (marketing copy in `features-section.tsx` / `hero-section.tsx` intentionally preserved per CONTEXT D-01).
- SC-08 achieved: `frontend/components/agent-configurator.tsx` deleted from the repo (confirmed via `test ! -f`).
- `/playground` page still compiles with chrome (Navbar, ParticleBackground, Footer, h1 "Agent Playground" heading + subtitle) preserved byte-for-byte per D-11.
- Homepage still compiles with Hero / Features / CTA / Footer sections intact.
- Empty `<div className="mx-auto max-w-2xl">` placeholder in `playground/page.tsx` is the exact final container shape for Plan 20-05's `<PlaygroundForm>` drop-in.
- Wave 2 (Plans 20-03 + 20-04) can now add new components against a clean, known-green baseline.

## Task Commits

Each task was committed atomically (Task 1 was a pure read-only verification with no file changes — findings recorded here instead):

1. **Task 1: Confirm deletion graph** — no commit (verification only). Findings:
   - `agent-configurator` imported by exactly 2 files (`app/playground/page.tsx` + `components/playground-section.tsx`) ✓
   - `agent-card`, `model-selector`, `a2a-network`, `task-orchestrator` each imported by exactly 1 file (`agent-configurator.tsx`) ✓
   - `playground-section` imported by exactly 1 file (`app/page.tsx`) ✓
   - `defaultClones` baseline count: 4 in `agent-configurator.tsx`; `openRouterModels` baseline count: 2 in `model-selector.tsx` (both >= 1) ✓

2. **Task 2: Neutralize mock usage sites** — `540c60d` (refactor)
   - Dropped `AgentConfigurator` import + mount from `playground/page.tsx`, replaced with empty `<div className="mx-auto max-w-2xl">` + HTML comment pointing at Plan 20-05
   - Dropped `PlaygroundSection` import + usage from homepage `app/page.tsx`
   - Added `tsconfig.tsbuildinfo` to `frontend/.gitignore` (TS incremental build cache, generated)

3. **Task 3: Delete mock file tree** — `8c0c05d` (refactor) — 6 files, 2406 lines removed
   - `git rm` on the 5 mock components + `playground-section.tsx`
   - SC-07 grep battery all green: no `defaultClones` / `openRouterModels` / channel literals remain in the playground subtree

4. **Task 4: Verify pnpm build** — `81e3aea` (docs) — deferred-items log only
   - `pnpm build` compiles successfully (`✓ Compiled successfully in 3.3s`)
   - No `Module not found`, `Cannot find module`, or `Type error` in build output
   - Static prerender fails on unrelated pages (`/docs/installation`, `/_global-error`, `/_not-found`, `/docs/config`) — confirmed pre-existing on base commit `db877c9`, not caused by this plan's delete
   - Logged to `.planning/phases/20-frontend-alicerce/deferred-items.md` with a recommendation for Plan 20-05 to resolve before SC-11 gate

## Files Created/Modified/Deleted

**Created:**
- `.planning/phases/20-frontend-alicerce/deferred-items.md` — tracks 3 pre-existing TS errors + pre-existing prerender build failure (all out of scope)
- `.planning/phases/20-frontend-alicerce/20-02-SUMMARY.md` — this document

**Modified:**
- `frontend/app/playground/page.tsx` — removed `AgentConfigurator` import (line 5 of original) and replaced `<AgentConfigurator />` mount (line 30 of original) with empty `<div className="mx-auto max-w-2xl">` placeholder. Navbar / ParticleBackground / Footer / h1 / subtitle / `user={{ name: "Alex Chen" ... }}` prop all preserved byte-for-byte per D-11.
- `frontend/app/page.tsx` — removed `PlaygroundSection` import (line 8 of original) and its `<PlaygroundSection />` usage + surrounding "Interactive Playground" comment (lines 35-37 of original). Hero / Features / CTA / Footer order preserved.
- `frontend/.gitignore` — added `tsconfig.tsbuildinfo` entry.

**Deleted:**
- `frontend/components/agent-configurator.tsx` (1001 lines — the mock root)
- `frontend/components/agent-card.tsx` (exported `defaultClones` + `ClawClone` type)
- `frontend/components/model-selector.tsx` (exported `openRouterModels` + `OpenRouterModel` type)
- `frontend/components/a2a-network.tsx` (mock A2A network graph + shared types)
- `frontend/components/task-orchestrator.tsx` (mock task orchestrator + `A2ATask`/`A2ASubtask`/`A2AArtifact` types)
- `frontend/components/playground-section.tsx` (homepage section wrapper that embedded `AgentConfigurator`)

## Decisions Made

None beyond the plan text — followed the 4-task sequence and deletion graph exactly as specified in `20-02-PLAN.md`. Plan's Task 2 → Task 3 ordering (neutralize usage first, then delete imports) was respected so the build never had dangling imports.

## Deviations from Plan

None of the Rule 1 / Rule 2 / Rule 3 / Rule 4 deviation rules fired. The plan was delete-and-verify, not build-and-fix; there was no opportunity for bug / missing-critical / blocking-fix / architectural decisions.

The only "discovery" was the pre-existing TypeScript errors + pnpm build prerender failures in unrelated files. Per the executor scope-boundary rule ("Only auto-fix issues DIRECTLY caused by the current task's changes. Pre-existing… failures in unrelated files are out of scope"), these were logged to `deferred-items.md` rather than fixed in this plan. Plan 20-05 Task 4 owns the final `pnpm build` SC-09 gate and is the correct owner of that remediation.

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** None — plan executed exactly as written.

## Issues Encountered

- **Pre-existing `pnpm tsc --noEmit` errors in unrelated files** (Task 2 verify step). 3 pre-existing TS errors in `app/dashboard/agents/[id]/page.tsx`, `components/footer.tsx`, `components/particle-background.tsx`. Confirmed present on the Phase 20 base commit `db877c9` both with and without Plan 20-02 changes. Out of scope — logged to `deferred-items.md`.
- **Pre-existing `pnpm build` static-prerender failures** (Task 4). Compile step is green but prerender fails on `/docs/installation`, `/_global-error`, `/_not-found`, `/docs/config` with `TypeError: Cannot read properties of null (reading 'useContext' | 'use')`. Confirmed pre-existing on base commit. Out of scope — logged to `deferred-items.md` with a recommendation for Plan 20-05.
- **`next-env.d.ts` modified by `pnpm build`** — Next.js regenerates the reference to `.next/dev/types/routes.d.ts` vs `.next/types/routes.d.ts` depending on build mode. The file is marked "should not be edited". Reset with `git checkout --` and excluded from commits.

## Threat Flags

None. This plan deletes code only; no new network endpoints, auth paths, file access, or schema changes at trust boundaries were introduced.

## Known Stubs

The empty `<div className="mx-auto max-w-2xl">` in `frontend/app/playground/page.tsx` (line 29) is an intentional, documented stub. Plan 20-05 wires `<PlaygroundForm />` into this slot. The HTML comment `{/* PlaygroundForm is wired in Plan 20-05 */}` marks the site. This is not a golden-rule violation — the page currently renders an empty playground slot, which is honest: the user will see a heading + subtitle + nothing below until 20-05 ships.

## Self-Check: PASSED

Verified claims:

- `frontend/components/agent-configurator.tsx` — MISSING (as intended for SC-08) ✓
- `frontend/components/agent-card.tsx` — MISSING ✓
- `frontend/components/model-selector.tsx` — MISSING ✓
- `frontend/components/a2a-network.tsx` — MISSING ✓
- `frontend/components/task-orchestrator.tsx` — MISSING ✓
- `frontend/components/playground-section.tsx` — MISSING ✓
- `frontend/app/playground/page.tsx` — FOUND, no `AgentConfigurator`, has `mx-auto max-w-2xl` placeholder ✓
- `frontend/app/page.tsx` — FOUND, no `PlaygroundSection` ✓
- `.planning/phases/20-frontend-alicerce/deferred-items.md` — FOUND ✓
- Commit `540c60d` — FOUND in git log ✓
- Commit `8c0c05d` — FOUND in git log ✓
- Commit `81e3aea` — FOUND in git log ✓

## Next Phase Readiness

**Ready:**
- Wave 2 (Plans 20-03 and 20-04) can start. The repo is in a clean state: no mock components under `frontend/components/`, no mock imports from `frontend/app/playground/` or `frontend/app/page.tsx`, and the placeholder slot in `playground/page.tsx` is ready for Plan 20-05's drop-in.
- Plan 20-01 (types + apiPostWithAuth helper) is running in parallel in a sibling worktree. After both Wave 1 plans merge, Plan 20-03 (PlaygroundForm) and Plan 20-04 (RunResultCard) have everything they need.

**Blockers for Plan 20-05:**
- The pre-existing `pnpm build` static-prerender failure must be resolved before Plan 20-05's SC-11 human-verify gate, otherwise the Hetzner deploy cannot ship. See `deferred-items.md` for the recommended investigation path.

---
*Phase: 20-frontend-alicerce*
*Plan: 02*
*Completed: 2026-04-17*
