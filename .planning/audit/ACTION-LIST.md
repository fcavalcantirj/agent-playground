# Action List — Remove Mocks + Real Implementation

**Date:** 2026-04-18  
**Status:** FROZEN (sealed 2026-04-18) — this is the authoritative execution list. Further changes only via `/gsd-plan-phase` for individual phases consuming this list as input.  
**Source:** `BACKEND-DESICCATED.md` (33KB, 699 lines) + `FRONTEND-DESSICATED.md` (42KB, 842 lines)  
**Scope:** Every page of frontend + every backend surface. What's mock, what's missing, what needs to be done.  
**Open decisions:** 1 — `/signup` route fate (decided after OAuth flow lands).

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

### 🔴 PRIORITY 1 — Implement every mocked page for real (no deletions)

Directive from user 2026-04-18: "we are not fucking deleting. implement everything."
Every page below gets real backend wiring. Marketing pages stay as-is.

| Page | File | Current state | Real-implementation plan (minimal) |
|---|---|---|---|
| `/login` | `frontend/app/login/page.tsx` | hardcoded email/password, setTimeout | OAuth buttons (Google + GitHub via `goth` in Go, or equivalent in FastAPI); form for password/email kept as a non-default alt (magic link) |
| `/signup` | `frontend/app/signup/page.tsx` | form → `/* TODO */` | OPEN DECISION — with OAuth, "Sign in with Google" handles both signup and signin (account auto-created on first callback). Options: (a) keep `/signup` as an intent-switched redirect to `/login?intent=signup` with copy framing ("Get started"); (b) keep as dedicated first-time flow with ToS + tier selection before OAuth; (c) drop the route entirely — decide after OAuth flow lands. The other 11 pages ARE being implemented regardless. |
| `/forgot-password` | `frontend/app/forgot-password/page.tsx` | stub | Magic-link reset flow: `POST /v1/auth/forgot` → email → `POST /v1/auth/reset?token=...` |
| `/dashboard` | `frontend/app/dashboard/page.tsx` | mockAgents (4 items hardcoded) | Fetch `GET /v1/agents` on mount, render live list with verdict badges + last_run_at |
| `/dashboard/agents` | `frontend/app/dashboard/agents/page.tsx` | mock list + filters | Same `GET /v1/agents` + client-side filtering by recipe/model/status, OR server-side `GET /v1/agents?recipe=...&status=...` |
| `/dashboard/agents/[id]` | `frontend/app/dashboard/agents/[id]/page.tsx` | mock agent, status `running`\|`stopped` | `GET /v1/agents/:id` (metadata) + `GET /v1/agents/:id/runs` (history) + `GET /v1/agents/:id/status` (live container state from Phase 22a endpoint) |
| `/dashboard/analytics` | `frontend/app/dashboard/analytics/page.tsx` | static chart data | Real chart: `GET /v1/users/me/analytics?range=...` (new endpoint aggregating user's runs by day/recipe/verdict). Uses SQL group-by on `runs` table. |
| `/dashboard/api-keys` | `frontend/app/dashboard/api-keys/page.tsx` | generates fake keys | Store per-user BYOK provider keys (OpenRouter, Anthropic, OpenAI) encrypted via age/libsodium keyed by server master + user_id. Endpoints: `GET/POST/DELETE /v1/users/me/api-keys`. Keys decrypt server-side only when spawning a run/agent, never returned to frontend. |
| `/dashboard/billing` | `frontend/app/dashboard/billing/page.tsx` | static balance + fake txs | Stripe wiring: `GET /v1/users/me/billing/balance` (reads credit_balance_cents from users table), `GET /v1/users/me/billing/history` (Stripe-fetched txs + local meter events), `POST /v1/users/me/billing/topup` → Stripe Checkout redirect, webhook `POST /v1/stripe/webhook` populates balance |
| `/dashboard/notifications` | `frontend/app/dashboard/notifications/page.tsx` | mock array, buttons = `setState` | New table `notifications(id, user_id, kind, payload, read_at, created_at)`. Endpoints: `GET /v1/users/me/notifications`, `PATCH /v1/users/me/notifications/:id` (mark read). Kinds: run_complete, agent_crash, channel_ready, credit_low. |
| `/dashboard/profile` | `frontend/app/dashboard/profile/page.tsx` | hardcoded user, Save = `alert()` | `GET /v1/users/me` + `PUT /v1/users/me` (name, avatar_url, timezone, language). `users` table already exists; needs profile columns migration. |
| `/dashboard/settings` | `frontend/app/dashboard/settings/page.tsx` | local state only | `GET /v1/users/me/settings` + `PUT` — JSONB column on users: default model, default personality, default recipe, theme, telegram bot preferences, notification prefs. |
| `/pricing` | `frontend/app/pricing/page.tsx` | static marketing | KEEP — pure marketing, but CTAs must link to real signup flow |
| `/contact`, `/privacy`, `/terms`, `/docs` | various | static marketing | KEEP — legal/docs pages, no backend |

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
