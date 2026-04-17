# Phase 20 — Deferred Items

Tracked issues discovered during execution that are **out of scope** for the current plan per the executor scope boundary rule ("Only auto-fix issues DIRECTLY caused by the current task's changes").

## Pre-existing TypeScript errors (discovered during 20-02 execution)

`pnpm tsc --noEmit` reports 3 pre-existing TS errors on the Phase 20 base commit
`db877c9` — confirmed present both with and without Plan 20-02 changes:

1. `app/dashboard/agents/[id]/page.tsx(90,26)` — `error TS2322: Type '"running" | "stopped"' is not assignable to type '"running"'`
2. `components/footer.tsx(77,27)` — `error TS2339: Property 'external' does not exist on type '...'`
3. `components/particle-background.tsx(19,24)` — `error TS2554: Expected 1 arguments, but got 0`

None of these files are touched by Phase 20 plans. They were carried over from the v0-imported tree.

## Pre-existing pnpm build prerender failure (discovered during 20-02 Task 4)

`pnpm build` in `frontend/` **compiles successfully** (`✓ Compiled successfully`) but fails at the static-export prerender phase with:

```
Error occurred prerendering page "/_global-error"
Error occurred prerendering page "/docs/installation"
Error occurred prerendering page "/_not-found"
Error occurred prerendering page "/docs/config"
TypeError: Cannot read properties of null (reading 'useContext')
TypeError: Cannot read properties of null (reading 'use')
```

Confirmed pre-existing on base commit `db877c9` (same failure before Plan 20-02 changes). The failing routes (`/docs/*`, `/_global-error`, `/_not-found`) are:

- Not touched by any Phase 20 plan
- Not in scope per CONTEXT D-01 ("Leave every other page in `frontend/app/` as-is")
- Likely caused by v0-generated client components interacting with Next.js 16.2's stricter RSC context rules during static generation

The plan's "no `Module not found`, `Cannot find module`, or `Type error` in the build output" check passes — the compilation is clean. The prerender failure is an unrelated issue that the final Phase 20 SC-09 gate (Plan 20-05 Task 4) may need to address, potentially by:

- Adding `export const dynamic = "force-dynamic"` to the offending pages
- Adding `"use client"` runtime-only boundaries correctly
- Fixing a stale v0 component's RSC compatibility
- Investigating whether a global error boundary or other runtime client-only hook is being called at the module-level of these routes

**Recommendation for Plan 20-05:** Investigate and resolve the prerender failure before SC-11's human-verify gate, since the Hetzner deploy cannot ship from a broken `pnpm build`.

## Pre-existing ESLint binary not installed (discovered during 20-04 verify)

`pnpm lint` fails with `sh: eslint: command not found` because the `frontend/package.json` `"lint"` script points at `eslint .` but ESLint is not declared as a dependency or devDependency (no `"eslint"` or `"@eslint/*"` entries). No ESLint config file (`.eslintrc*`, `eslint.config.{js,mjs,cjs}`) is present in `frontend/` either — the script was inherited from the v0 export template without ever being wired up.

Impact for Plan 20-04:
- The plan's `pnpm lint` verify step cannot produce lint findings — there is no linter to run.
- The scope-boundary rule says pre-existing tool absence is out of scope for this plan. Plan 20-04 only introduces one pure display component which TypeChecked cleanly (`pnpm tsc --noEmit` shows only the 3 pre-existing unrelated errors from the section above — no new errors from `run-result-card.tsx`).

**Recommendation for Plan 20-05 (the SC-09 gate owner):** either install `eslint` + `eslint-config-next` + create `eslint.config.mjs` with the Next/TypeScript rules, or remove the `"lint"` script entry from `package.json`. Adding ESLint is preferred since SC-09 reads "`pnpm build` passes with the new page (Turbopack production build). `pnpm lint` passes" — the current script cannot pass because it cannot run.

