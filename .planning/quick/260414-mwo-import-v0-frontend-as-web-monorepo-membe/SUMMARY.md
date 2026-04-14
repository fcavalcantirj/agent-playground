---
quick_id: 260414-mwo
slug: import-v0-frontend-as-web-monorepo-membe
status: completed
started: 2026-04-14
completed: 2026-04-14
---

# Quick Task 260414-mwo: Import v0 Frontend as `frontend/`

## Objective

Monorepo reshape to bring the v0-authored marketing + dashboard + playground
tree from `/Users/fcavalcanti/Downloads/b_BgFAb4674I9` into the repo, and
port the load-bearing auth logic from the legacy `web/` tree so Phase 3 has
a single frontend to extend.

## Outcome

Three atomic commits landed on `main`. New `frontend/` directory is a
standalone-buildable Next.js 16.2 + React 19 + Tailwind v4 + shadcn/ui
project that owns the marketing surface. Legacy `web/` is still on disk and
will be deleted once Phase 3 verifies the new tree renders + authenticates
against the Go backend.

## Commits

1. **Import v0 source** — 1 MB copy of the v0 export into `frontend/`,
   preserving its `app/` + `components/` + `lib/` + `hooks/` + `styles/`
   root layout (not `src/`). Ships the marketing landing, pricing, docs,
   contact, terms, privacy pages; the playground configurator; the
   dashboard sub-routes (agents, analytics, api-keys, billing,
   notifications, profile, settings); and auth-surface placeholders for
   login, signup, forgot-password. Zero `fetch` calls — all data mocked.

2. **Port auth logic from web/** — four Phase 1-03 artifacts brought
   over verbatim:
   - `frontend/lib/api.ts` — typed `fetch` wrapper, `ApiError`, session
     cookie handling, `SessionUser` type
   - `frontend/middleware.ts` — edge cookie inspection, matcher skips
     `/api`, `_next`, `favicon`
   - `frontend/components/dev-login-form.tsx` — client component for
     `POST /api/dev/login` (emerald 44px, Loader2 spinner, error copy)
   - `frontend/next.config.mjs` — rewrote to add `/api/*` proxy
     pointing at `http://localhost:8080` (override via
     `NEXT_PUBLIC_API_PROXY_TARGET`); preserved v0's
     `ignoreBuildErrors` + `images.unoptimized` defaults

3. **Makefile targets** — `install-frontend`, `dev-frontend`,
   `build-frontend`, `lint-frontend` as thin `cd frontend && pnpm …`
   delegations. Placed below the existing backend + smoke-test targets
   so `make` still leads with Phase 2 work.

## Files Changed

- `frontend/` (new, ~1 MB, 85 files from v0)
- `frontend/lib/api.ts` (new, ported)
- `frontend/middleware.ts` (new, ported)
- `frontend/components/dev-login-form.tsx` (new, ported)
- `frontend/next.config.mjs` (modified — rewrites added)
- `Makefile` (modified — 4 frontend targets added)

## Not Done (Explicit Scope Boundaries)

- **No backend wiring.** `frontend/app/login/page.tsx` still uses v0's
  mocked login UI — not yet hooked to `DevLoginForm`. Phase 3 owns that
  contract.
- **No dep install.** `pnpm install` inside `frontend/` has NOT been
  run — no `node_modules`, no lockfile reconciliation. The v0
  `pnpm-lock.yaml` is committed as-is.
- **No dev-server verification.** I did not run `make dev-frontend` to
  confirm the tree boots. Targets are wired but unvalidated — a
  Phase 3 plan task will run `pnpm install` + boot + visual check.
- **`web/` not deleted.** Deletion is deferred until Phase 3 verifies
  `frontend/` can replace it functionally. The redundancy is
  intentional safety margin.
- **v0's hardcoded `ClawClone` catalog not reconciled.** It lists 8
  agents (hermes-agent, openclaw, zeroclaw, moltis, ironclaw, safeclaw,
  nanobot, nullclaw) that don't match our Phase 2 backend catalog
  (picoclaw, hermes only). Phase 02.5 (Recipe Manifest Reshape) will
  reconcile by making the backend source-of-truth and exposing it via
  `GET /api/recipes`.

## Followups Captured

1. Phase 02.5 "Recipe Manifest Reshape" — reshape agents from baked
   Dockerfiles into YAML manifests + install scripts; eliminates the
   5.54 GB Hermes image bloat; exposes `GET /api/recipes` so the
   frontend drops the hardcoded catalog.
2. Phase 3 task — wire `DevLoginForm` into `frontend/app/login/page.tsx`,
   run `pnpm install`, verify `make dev-frontend` + `make build-frontend`
   both succeed, then `git rm -rf web/` once the new tree is proven.
