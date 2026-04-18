# Action List — Remove Mocks + Real Implementation

**Date:** 2026-04-18  
**Source:** `BACKEND-DESICCATED.md` (33KB, 699 lines) + `FRONTEND-DESSICATED.md` (42KB, 842 lines)  
**Scope:** Every page of frontend + every backend surface. What's mock, what's missing, what needs to be done.

---

## Headline

- **Frontend: 71% real, 29% stubbed/mocked.** Core `/playground` is real. Everything under `/dashboard/*` and `/login`, `/signup`, `/forgot-password` is theater (setTimeout → success, hardcoded data).
- **Backend: production-ready foundation.** 9 real routes, BYOK auth, idempotency, rate limit, structured errors. Gaps are forward-looking (not blocking) — multi-tenancy anchor, `pass_if` field never populated in response, metadata dropped.
- **Architecture violations** (per `CLAUDE.md` golden rules):
  - Rule 1 (no mocks): 29% of frontend violates
  - Rule 2 (dumb client, no catalogs): frontend bakes recipes/personalities/accents as hardcoded arrays
  - Rule 3 (ship e2e): auth is fake → can't actually sign in → dashboard flow untestable

---

## FRONTEND — page-by-page action list

Ordered by user-visible damage, then Rule 1/2 violations.

### 🔴 PRIORITY 1 — Delete or rebuild-from-scratch pages (100% mock)

These pages do NOTHING real. Either remove from nav or rebuild properly.

| Page | File | Current state | Action |
|---|---|---|---|
| `/login` | `frontend/app/login/page.tsx` | hardcoded email/password, setTimeout then redirect | DELETE or wire Google/GitHub OAuth (goth backend) |
| `/signup` | `frontend/app/signup/page.tsx` | form that calls `/* TODO */` | DELETE — OAuth-only per PROJECT.md |
| `/forgot-password` | `frontend/app/forgot-password/page.tsx` | stub | DELETE — OAuth-only means no passwords to forget |
| `/dashboard` | `frontend/app/dashboard/page.tsx` | mockAgents array (4 items hardcoded) | REBUILD: fetch `GET /v1/agents`, show real list |
| `/dashboard/agents` | `frontend/app/dashboard/agents/page.tsx` | mock list + filters | REBUILD: same as above + real filtering |
| `/dashboard/agents/[id]` | `frontend/app/dashboard/agents/[id]/page.tsx` | mock single agent + status: "running" \| "stopped" | REBUILD: fetch `GET /v1/agents/:id` + `GET /v1/runs/:id` history |
| `/dashboard/analytics` | `frontend/app/dashboard/analytics/page.tsx` | static chart data | DELETE or defer to Phase 23 (needs backend metrics endpoint) |
| `/dashboard/api-keys` | `frontend/app/dashboard/api-keys/page.tsx` | generates fake keys with random strings | DELETE — BYOK means no platform-issued keys |
| `/dashboard/billing` | `frontend/app/dashboard/billing/page.tsx` | static balance + fake transactions | DEFER to Phase 24 (Stripe wiring) |
| `/dashboard/notifications` | `frontend/app/dashboard/notifications/page.tsx` | mock notifications array, buttons are `setState` only | DEFER to Phase 23 |
| `/dashboard/profile` | `frontend/app/dashboard/profile/page.tsx` | hardcoded user, Save button is `alert()` | REBUILD: `GET/PUT /v1/users/me` (endpoint MISSING) |
| `/dashboard/settings` | `frontend/app/dashboard/settings/page.tsx` | local state only | REBUILD: `GET/PUT /v1/users/me/settings` (endpoint MISSING) |
| `/pricing` | `frontend/app/pricing/page.tsx` | static marketing page | KEEP as-is (marketing, no backend) |
| `/contact`, `/privacy`, `/terms`, `/docs` | various | static marketing | KEEP |

### 🟡 PRIORITY 2 — Rule 2 violations (client-side catalogs)

Backend must own these, frontend must fetch.

| Catalog | File | Location | Action |
|---|---|---|---|
| `RECIPE_TAGLINES` | `frontend/components/playground-form.tsx` | 5 hardcoded recipe descriptions | Backend: add `tagline` field to `RecipeSummary` (read from recipe YAML `metadata.tagline` or use `description` first line). Frontend: read `recipe.tagline`, remove map. |
| `RECIPE_ACCENTS` | `frontend/components/playground-form.tsx` + `my-agents-panel.tsx` | 5 hardcoded color palettes per recipe name, duplicated | Backend: add `accent` field to `RecipeSummary` (from YAML `display.accent` or auto-derive from recipe.name hash). Frontend: read, remove both maps. |
| `PERSONALITIES` | `frontend/lib/api-types.ts` | 6 personalities + emoji + descriptions hardcoded | Backend: expose `GET /v1/personalities` (already exists as `services/personality.py::PERSONALITY_IDS` — just add route). Frontend: fetch on mount. |
| Default model | various | no hardcoded models in state (verified) | ✅ CLEAN |

### 🟢 PRIORITY 3 — Small cleanup

- `frontend/app/error.tsx`, `not-found.tsx`, `loading.tsx` — standard Next.js scaffolds, leave.
- `frontend/components/navbar.tsx` — links to `/dashboard/*` pages that will be deleted. Prune nav after P1 deletions.
- `frontend/components/footer.tsx` — check dead links.
- `/web` (legacy tree) — if still present, delete.

---

## BACKEND — action list

Ordered by blocking impact.

### 🔴 PRIORITY 1 — Blocking fixes (user-visible bugs or Phase 22 blockers)

| # | Issue | File | Action |
|---|---|---|---|
| B1 | `pass_if` field in `RunResponse` always NULL | `api_server/src/api_server/routes/runs.py` + `tools/run_recipe.py::run_cell` returns tuple missing pass_if string in details dict | Propagate `pass_if_str` into details dict before returning |
| B2 | `ANONYMOUS_USER_ID` hardcoded (Phase 19 single-tenant) | `routes/runs.py`, `routes/agents.py` | When OAuth lands (Phase 22 prereq?): resolve real `user_id` from session cookie, pipe through. Already flagged as the multi-tenancy anchor. |
| B3 | `RunRequest.metadata` accepted but dropped | `routes/runs.py` | Either persist to `runs.metadata` JSONB (new migration) or remove from Pydantic model. Per dumb-client rule: DROP the field if not persisted. |

### 🟡 PRIORITY 2 — New endpoints required for frontend rebuild

Every page we rebuild needs a real backend endpoint.

| Need | New endpoint | Source | Notes |
|---|---|---|---|
| `/v1/personalities` | GET — list personality presets | map from `services/personality.py::_PRESETS` | Kills `PERSONALITIES` frontend catalog |
| `/v1/users/me` | GET — current user profile | new; needs OAuth session | Phase 22 prereq (multi-tenancy) |
| `/v1/users/me` | PUT — update profile | new; plus input validation | For `/dashboard/profile` |
| `/v1/users/me/settings` | GET + PUT — user preferences | new; JSONB column on users | For `/dashboard/settings` |
| `/v1/agents/:id/start` | POST — spawn persistent container | Phase 22a scope per CONTEXT | Channels rollout |
| `/v1/agents/:id/stop` | POST — graceful shutdown | Phase 22a scope | |
| `/v1/agents/:id/status` | GET — container state + health | Phase 22a scope | |
| `/v1/agents/:id/channels/:cid/pair` | POST — proxy `openclaw pairing approve` | Phase 22a scope | Bypass SSH requirement |
| OAuth callback routes | GET `/auth/:provider/callback` | new — wire goth (Go) or equivalent | Blocks anything multi-user |

### 🟢 PRIORITY 3 — Technical debt / forward-looking

- `RecipeSummary.tagline` + `RecipeSummary.accent` fields (per Frontend P2).
- Recipe schema v0.2 formal spec (Phase 22a in progress).
- Metadata field JSONB audit trail (B3 fix + migration `003_runs_metadata.sql`).
- Drop `DEFAULT_MODEL_FALLBACK` constant if unused.
- Tests: there are conftest + some tests; backend coverage claim is "WORKS" but no CI integration yet.

---

## CROSS-CUTTING — what's missing entirely

- **Auth layer (OAuth Google + GitHub).** PROJECT.md + CLAUDE.md demand it. Currently: login page is a stub; backend has `ANONYMOUS_USER_ID` placeholder. This is the SINGLE biggest unblocker — 4 frontend pages + ~8 backend endpoints depend on it.
- **Session management.** Cookie, logout, refresh — none implemented.
- **Observability.** No /metrics endpoint, no Sentry/Rollbar, no structured log shipping. Backend logs to stdout (zerolog-equivalent via `log.py`), frontend has no error reporter.
- **Analytics / metrics.** `/dashboard/analytics` is fake; there's no `GET /v1/metrics/*` endpoint on backend.
- **Billing.** `/dashboard/billing` is fake; no Stripe wiring (PROJECT.md schedules it later).
- **Persistent mode for recipes.** The whole Phase 22a work (runner `--mode persistent` + container lifecycle). Recipe v0.2 blocks are drafted; runner/API/UI not implemented.
- **Webhook/event surface.** No way to notify external systems of run completions.

---

## Recommended execution order

Produces a slim working end-to-end stack:

1. **Delete the 7 mock pages** (PRIORITY 1 frontend rows marked DELETE/DEFER). Remove from navbar. Ship commit. This is the biggest readability/trust win — no more theater.
2. **Backend: `GET /v1/personalities`** + drop `PERSONALITIES` frontend catalog. Smallest Rule 2 fix, cheap win.
3. **Backend: `tagline` + `accent` on `RecipeSummary`.** Frontend: read from API. Kills 3 more catalogs.
4. **Backend fix B1** (`pass_if` NULL). User-facing bug.
5. **OAuth wire-up.** Google + GitHub via goth (or similar). Unblocks multi-tenancy + `/v1/users/me` endpoints + real dashboard rebuild.
6. **Phase 22a (channels v0.2).** Already CONTEXT-locked in `.planning/phases/22-channels-v0.2/22-CONTEXT.md`. Proceeds on top of real auth.
7. **Rebuild `/dashboard` + `/dashboard/agents` + `/dashboard/agents/[id]`** as real pages reading from `/v1/agents` + `/v1/runs/:id`.
8. **Defer analytics, billing, notifications, api-keys** to later phases.

---

## Artifacts

- This file: `.planning/audit/ACTION-LIST.md`
- Detail: `.planning/audit/BACKEND-DESICCATED.md` (33KB, 9 routes + 7 services + 4 middleware + migrations)
- Detail: `.planning/audit/FRONTEND-DESSICATED.md` (42KB, 32 pages + 15 components + API cross-ref)
