---
phase: 20-frontend-alicerce
status: ready_for_research
gathered: 2026-04-17
source: /gsd-discuss-phase interactive session after golden-rule violation caught in Phase 19
---

# Phase 20: Frontend Alicerce — Context

## Phase Boundary

Replace the v0 mock `/playground` page with a real, API-driven, conversational-layout page that round-trips a run end-to-end: user types recipe + model + BYOK key + prompt, clicks Deploy, the page POSTs `/v1/runs`, and the verdict card renders from the server's response. **No client-side catalogs** of recipes, models, or channels — anything the API owns must come from the API.

**IN scope:** `frontend/app/playground/page.tsx`, a new `<PlaygroundForm>` component, error/loading/empty states, reuse of existing `frontend/lib/api.ts` + shadcn/ui primitives.

**OUT of scope (explicit, reusable as deferred ideas):**
- Auth, login, dashboard, billing, profile, settings pages (depend on a later auth phase)
- A2A network / Tasks / Monitor tabs (Phase 22+)
- Channel picker (Telegram, Discord, Slack, etc. — each is its own future phase)
- Persistent Memory, Scheduling, Max Tokens, Sandbox picker toggles (no API support yet)
- SSE / streaming verdicts (Phase 21 explicitly)
- Multi-agent tabs, agent instances list, "N agents per user" UX (requires auth)
- Marketing pages (pricing, docs, contact, terms, privacy) — stay as v0 cosmetic
- Settings page for BYOK persistence (Phase 20 uses per-run keys)
- Run history list / list endpoint (`GET /v1/runs`) — no such API endpoint exists yet
- Mobile optimization — acceptable to be desktop-first in Phase 20; mobile-first is FND-04 but scoped to a later UI phase
- TypeScript client generation (SC-13 in Phase 19; orthogonal to this phase)

## Why This Phase Exists (load-bearing context)

On 2026-04-17 we shipped Phase 19's API end-to-end: live Postgres, prod-shaped Docker stack, `POST /v1/runs` persists real runs, BYOK keys never leak, 5 prod-blocking deploy bugs fixed locally before they could bite on Hetzner.

Then the user opened `localhost:3000/playground`, configured a Hermes/Gemini agent in the v0-generated UI, clicked **"Deploy All Agents"** — nothing happened. The entire `/playground` page is a v0 mock: hardcoded `defaultClones` array of 8 clones (only 5 are real recipes), hardcoded model catalog with 4 models and fake prices, channel picker (Telegram/Discord/Slack/WhatsApp/Signal/Email/CLI/Webhook) with no backend, and a `deployAllAgents()` function that only flips `isRunning: true` in React state. Zero network calls from any UI action.

**Golden rule violation #2 (dumb client, intelligence in the API) and #3 (ship when stack works locally end-to-end).** See `CLAUDE.md` top banner and `memory/feedback_dumb_client_no_mocks.md`.

Hetzner deploy of Phase 19 was queued; deploy is now **BLOCKED** pending Phase 20 completion. Shipping a deployed API with a mock UI = shipping a mock to prod.

## Implementation Decisions (locked)

### D-01: Scope cut — Playground only (minimal)
- Rewrite only `frontend/app/playground/page.tsx` and its component subtree.
- Delete `frontend/components/agent-configurator.tsx` entirely (it is 1001 lines of mock). Replace with a new `<PlaygroundForm>` + `<RunResultCard>` pair.
- Leave every other page in `frontend/app/` as-is. Pricing, docs, dashboard, login, signup, forgot-password — all remain v0 cosmetic. They do not wire to any API in this phase.
- Rationale: unblock Hetzner deploy in the smallest possible change-set. Future phases own auth, dashboard, mobile polish, etc.

### D-02: UI shape — conversational single-column
- Single vertical flow: form at top → Deploy button → verdict card appears below.
- No tabs (no Config/A2A/Tasks/Monitor), no 3-column panels, no channel grid, no runtime/sandbox/A2A sub-tabs.
- Dense, dev-focused, zero decoration beyond what Navbar/Footer/ParticleBackground already provide (keep those for visual chrome consistency across pages).
- User-approved ASCII preview (see final section).

### D-03: Recipe picker — native HTML `<select>` populated from `GET /v1/recipes`
- Fetched on component mount via `apiGet<{recipes: RecipeSummary[]}>("/api/v1/recipes")` (Next.js rewrite proxies to `:8000`).
- `<select>` options rendered from the response; each option value = `recipe.name` (e.g., `"picoclaw"`), label = `recipe.name` (no aesthetic cards, no featured/hot badges — those were client-owned mock fields).
- Loading state while fetching: the `<select>` is disabled with placeholder "Loading recipes…".
- Empty state (zero recipes returned, e.g., broken API): inline error message + retry button. Do NOT silently fail.
- Default decision (user can override in planning): picked native `<select>` over card grid / datalist because it's the least-surface-area dumb-client shape.

### D-04: Model input — free-text
- Plain `<input type="text" placeholder="e.g., openai/gpt-4o-mini">`.
- **No client-side model catalog.** No curated dropdown. No hardcoded pricing. The server accepts any model string and forwards it to the runner.
- Helper tooltip/link: small `<a>` to OpenRouter's model catalog (`https://openrouter.ai/models`) labeled "browse models".
- Validation: non-empty string. No format policing on the client — server returns an error if the model doesn't exist; we display it.

### D-05: BYOK key — per-run form field
- `<input type="password">` (masks the key; browser autofill disabled).
- Typed or pasted fresh for each Deploy. No localStorage. No session-only React state that survives across Deploys. Cleared after submit (or kept in state for the current page load only, up to the planner).
- Sent as `Authorization: Bearer <key>` header on the `POST /v1/runs` call. Never written to any other storage, never logged, never added to any log context.
- Rationale: smallest scope, zero storage surface area, zero XSS key-exfiltration risk. Persistent BYOK via settings page is a future phase when auth exists.

### D-06: Run feedback — structured verdict card
- Shape: colored verdict badge (PASS green / FAIL red / INFRA_FAIL orange), category pill, exit_code, wall_time_s, run_id (copyable), and a collapsible "stderr tail" accordion (expanded by default if verdict ≠ PASS).
- Renders directly from the `POST /v1/runs` response JSON — no second fetch needed.
- One card per most-recent run. No history list in Phase 20.
- If a user deploys again while a run is in flight: disable the Deploy button + show loading state. No queueing, no cancelation UI (defer).

### D-07: Error handling — surface, never swallow
Every error path must render visibly in the UI. Specific shapes:

| HTTP / condition | UI behavior |
|------------------|-------------|
| `2xx` with `verdict: FAIL/INFRA_FAIL` | Verdict card with colored FAIL/INFRA_FAIL badge, full verdict + stderr tail visible |
| `422` validation error | Inline red text under the field that errored (pydantic error array → map `loc` to field name) |
| `429` rate limit | Verdict card replaced by "Rate limited — retry in Ns" box; parse `Retry-After` header for N; auto-enable Deploy button after N seconds |
| `401 / 403` | "Invalid or missing API key" box — does NOT echo the key value |
| `502 infra_error` | Verdict-card-shaped error with `error.message` + `request_id` shown for support |
| Network / timeout | "Could not reach API — check your connection" box with a retry button |

### D-08: Deploy button lifecycle
- Disabled when: any required field is empty (recipe, model, BYOK, prompt), or a previous run is in flight, or a rate-limit cooldown is active.
- When active: "Deploy" label. Pressing: `POST /v1/runs`, show inline spinner next to the button.
- Completion: re-enable, render the verdict card below.
- No Idempotency-Key header in Phase 20 (optional; server allows). A future phase can add a "prevent duplicate submits" behavior using idempotency.

### D-09: Empty / loading / initial states
- First page load: form with recipes loading (disabled), rest of fields empty. No verdict card yet.
- First deploy in progress: form fields disabled, Deploy button shows spinner, verdict area shows "Running…" skeleton.
- Post-deploy: verdict card visible; form stays populated so the user can tweak + re-deploy.
- Zero recipes (bad API state): explicit empty state with retry.

### D-10: Mock remnants — delete
- The `<AgentConfigurator>` component, the A2A tab, the Tasks tab, the Monitor tab, the channel grid, the sandbox picker, the runtime/sandbox/A2A sub-tabs, the Persistent Memory / Scheduling / Max Tokens toggles, the Agent Instances panel, and every piece of `defaultClones` / `openRouterModels` mock data — all deleted. Not disabled. Not "coming soon". Deleted.
- Reason: the "disabled coming soon" option (my original question #4 proposal) assumed we were preserving the v0 3-column skeleton. D-02 rebuilds the layout, so there is no skeleton to disable.
- Placeholder tabs/pages for future work can be created in their respective phases; this phase does not ship stubs.

### D-11: Keep v0 chrome
- `<Navbar>`, `<Footer>`, `<ParticleBackground>` stay on the page. They are visual chrome that appears across all pages; removing just from `/playground` would look inconsistent.
- Navbar's "Alex Chen" fake user stays for now (that's wired to a hardcoded prop in `playground/page.tsx` — remove when auth lands).
- The orange gradient "Agent Playground" heading + subtitle stays.

### D-12: Networking path
- All API calls go through the existing `frontend/next.config.mjs` rewrite:
  - `GET /api/v1/recipes` → `http://127.0.0.1:8000/v1/recipes` (dev) or same-origin (prod behind Caddy)
  - `POST /api/v1/runs` → `http://127.0.0.1:8000/v1/runs`
- Reuse `frontend/lib/api.ts::apiGet`, `apiPost`. Add a thin wrapper (or parameter) for the `Authorization: Bearer <key>` header since the existing `apiPost` doesn't accept auth headers today.
- `credentials: "include"` stays on fetch (future-proofs for when auth cookies arrive).

### D-13: Types
- Mirror the API's response shapes in a new `frontend/lib/api-types.ts`:
  - `RecipeSummary` — matches the Pydantic model in `api_server/src/api_server/models/recipes.py` (name, apiVersion, source_repo, source_ref, provider, pass_if, license, maintainer).
  - `RunResponse` — matches `api_server/src/api_server/models/runs.py` (run_id, agent_instance_id, recipe, model, prompt, pass_if, verdict, category, detail, exit_code, wall_time_s, filtered_payload, stderr_tail, created_at, completed_at).
  - `ErrorResponse` — matches the Stripe-shape envelope (`{error: {type, code, category, message, param, request_id}}`).
- **No codegen from `/openapi.json` in Phase 20.** That's Phase 19's SC-13 TS client generation, orthogonal.

### D-14: No testing framework in Phase 20 (flag for decision)
- `frontend/` currently has no test runner. Adding one is a non-trivial scope decision (Vitest vs Jest vs Playwright vs pure Next E2E). **Decision deferred to planning**: either (a) defer all frontend tests to a later phase, (b) add Playwright for the single E2E "click Deploy, see verdict" test, (c) add Vitest for the types/fetch-shape unit tests.
- Gray area for `/gsd-plan-phase 20` to resolve.

## Success Criteria (the exit gate)

SC-01. `make dev-api-local` brings up the containerized Phase 19 API; `make dev-frontend` boots Next at `:3000`.

SC-02. User opens `http://localhost:3000/playground` in a browser and sees: the new conversational form with recipe selector populated with 5 real recipes (hermes, nanobot, nullclaw, openclaw, picoclaw) fetched from the API — NOT from a hardcoded array.

SC-03. User types a model (free-text), a BYOK key, a prompt, and clicks Deploy. `POST /v1/runs` is issued from the browser with `Authorization: Bearer <key>` header.

SC-04. User sees a verdict card render within N seconds containing: verdict badge, category pill, exit_code, wall_time_s, run_id, and stderr tail. The run is persisted in postgres (confirmable via `docker compose ... exec postgres psql -c 'SELECT * FROM runs ORDER BY created_at DESC LIMIT 1;'`).

SC-05. BYOK key never appears in: browser console logs, Network tab request body, api_server container logs (grep test the actual bearer token value against the log stream), or any React DevTools-visible state after submit (up to the planner's discretion).

SC-06. Every error path in D-07 is rendered in the UI (tested manually or via E2E if D-14 adds Playwright): 422, 429 with Retry-After countdown, 401, 502 infra_error, network failure.

SC-07. Zero hardcoded arrays of recipes, models, or channels remain in the `/playground` subtree. Grep for `defaultClones`, `openRouterModels`, channel literals like `"telegram"` / `"slack"` — all gone from `app/playground/` and its components.

SC-08. `agent-configurator.tsx` is deleted from the repo.

SC-09. `pnpm build` passes with the new page (Turbopack production build). `pnpm lint` passes.

SC-10. Re-open the playground, pick a different recipe, run again — the new verdict replaces the old. Multiple runs persist as separate rows in `runs`.

SC-11. After SC-01..SC-10 are green locally, the Phase 19 Hetzner deploy (`bash deploy/deploy.sh`) is unblocked.

## Canonical Refs (downstream agents must read these)

- `CLAUDE.md` (top banner — golden rules #1 #2 #3 #4 are load-bearing for this phase)
- `memory/feedback_dumb_client_no_mocks.md` (the principle + the incident that created this phase)
- `memory/feedback_no_mocks_no_stubs.md` (infra-side counterpart)
- `.planning/phases/19-api-foundation/19-CONTEXT.md` — D-01 (idempotency), D-02 (BYOK delivery), D-04 (/healthz + /readyz), D-06 (DB schema), SC-01..SC-13
- `.planning/phases/19-api-foundation/19-04-SUMMARY.md` — POST /v1/runs implementation details; `RunResponse` shape
- `.planning/phases/19-api-foundation/19-03-SUMMARY.md` — GET /v1/recipes implementation; `RecipeSummary` shape
- `frontend/lib/api.ts` — existing `apiGet`/`apiPost`/`apiDelete`/`ApiError` contract to extend
- `frontend/next.config.mjs` — rewrite rules already wire `/api/v1/*` → `:8000/v1/*`
- `frontend/components/agent-configurator.tsx` — the 1001-line mock that must be deleted (read it once for `AgentInstance`-shaped types we are NOT carrying forward)
- `frontend/app/playground/page.tsx` — the page that hosts `<AgentConfigurator>` today; will host `<PlaygroundForm>` + `<RunResultCard>` after Phase 20
- `frontend/components/ui/` — shadcn/ui primitives (Button, Input, Textarea, Select, Card, Badge) available to reuse
- `api_server/src/api_server/models/recipes.py` — Pydantic shape for recipe response
- `api_server/src/api_server/models/runs.py` — Pydantic shape for run request + response
- `api_server/src/api_server/models/errors.py` — Stripe-envelope error shape

## Reference UI (user-approved ASCII sketch)

```
┌─ /playground ──────────────────────────────┐
│ Recipe:  [ picoclaw           v ]          │
│ Model:   [ openai/gpt-4o-mini     ]        │
│ Key:     [ ********************   ]        │
│                                            │
│ Prompt:                                    │
│ ┌──────────────────────────────────────┐   │
│ │                                      │   │
│ │                                      │   │
│ └──────────────────────────────────────┘   │
│             [  Deploy  ]                   │
│                                            │
│ ┌─ PASS ── 12s ─ exit 0 ───────────────┐   │
│ │ run_id: 01KPE5QMZJKXF819APTW816XB3   │   │
│ │ > stderr tail...                     │   │
│ └──────────────────────────────────────┘   │
└────────────────────────────────────────────┘
```

## Deferred Ideas (seed for later phases)

- **Phase 20.1 / polish:** mobile-first refinement of the playground (FND-04). Desktop-first is acceptable in Phase 20.
- **Phase 20.2 / settings:** BYOK persistence via localStorage + settings page, once auth exists.
- **Phase 21 (already in roadmap):** SSE streaming — `GET /v1/runs/{id}/events` + progressive render in the UI. Replaces the blocking Deploy click with streaming tokens.
- **Phase 22+:** Auth + multi-agent tabs + dashboard + profile + billing. "N agents per user" UX. Persistent agent instances.
- **Phase 23+:** Real channel wiring (Telegram, Discord, Slack, etc.) — each is its own phase.
- **Later:** A2A network graph (the v0 mock had this), Tasks tab, Monitor tab, TypeScript client generated from `/openapi.json`, run history list endpoint (`GET /v1/runs`), idempotency-key generation in the client.

## What This Phase Explicitly Does NOT Fix

- The `api_server/tests/test_migration.py` PATH issue (carryover from Phase 19, noted in `memory/project_phase_19_deploy_handoff.md`).
- Any other v0 page's mock state (pricing cards, docs nav, dashboard tiles, login form's `/api/dev/login` call to the abandoned Go endpoint). Those are out of scope for Phase 20.
- The Phase 19 Hetzner deploy itself — Phase 20 unblocks it, but the actual deploy runs as Phase 19 Plan 07 Task 3 AFTER Phase 20's SC-11 passes.
