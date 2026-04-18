---
phase: 22-channels-v0.2
plan: 06
subsystem: frontend
tags: [nextjs, react, tailwind, typescript, step-2.5, deploy-mode, channels, telegram, openclaw, pairing-modal, byok, abort-controller, dumb-client, rule-2]

# Dependency graph
requires:
  - phase: 22-channels-v0.2
    provides: "Plan 22-01 RecipeSummary.persistent_mode_available + channels_supported + channel_provider_compat surfaces; Plan 22-05 POST /v1/agents/:id/start, /stop, /status, /channels/:cid/pair endpoints with their AgentStartResponse / AgentChannelPairResponse shapes; Plan 22-05 openclaw recipe pairing.approve_argv block"
  - phase: 19-api-foundation
    provides: "GET /v1/recipes/:name returning RecipeDetailResponse { recipe: dict }; /api proxy rewrite in next.config.mjs; ApiError class; BYOK bearer header convention"
provides:
  - "Step 2.5 deploy-mode UI — radio between one-shot smoke (default) and Persistent + Telegram; disabled when recipe lacks persistent_mode_available"
  - "Dynamic channel input fields rendered from server-supplied RecipeDetail.channels.<cid>.required_user_input + optional_user_input (CLAUDE.md Rule 2 — zero hardcoded channel catalogs in React)"
  - "Provider-compat UX: byokLabel + warning banner driven by channel_provider_compat.<cid>.supported/deferred; no openclaw string literal anywhere in the component"
  - "onDeploy fork: /v1/runs (smoke as existence proof) + /v1/agents/:id/start (persistent mode); pairing modal opens when recipeDetail.channels.<cid>.pairing exists"
  - "PairingModal component (components/pairing-modal.tsx) with G4 UX contract: 90s fetch timeout matching server docker-exec window, up-front latency disclosure, Approve disabled in-flight to block concurrent cold-boots, elapsed-time readout"
  - "apiPost/apiGet extended with optional ApiCallOptions bag carrying AbortSignal; backward-compatible with existing 3-arg callers"
  - "SectionHeader step prop widened to number | string to accept '2.5'"
  - "BYOK discipline preserved across modal lifecycle: byok cleared in onDeploy finally; pairingBearer held only while modal is open; cleared on modal onClose"
  - "TS types for full agent lifecycle surface: ChannelUserInput, ChannelEntry, RecipeDetail, AgentStartRequest/Response, AgentStatusResponse, AgentStopResponse, AgentChannelPairRequest/Response"
affects: [22-07-e2e-validation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Rule-2 enforcement: every channel-shaped field originates in server JSON — recipeDetail (GET /v1/recipes/:name), selectedRecipe.channel_provider_compat (GET /v1/recipes summary), verified_cells[].bot_username. No client-side CHANNELS constant, no RECIPE_BOT_USERNAMES map, no 'openclaw' string check anywhere in the form."
    - "Smoke-before-start invariant: persistent mode always runs /v1/runs first. That resolves / creates the agent_instance row server-side (the upsert at routes/runs.py), returning agent_instance_id for the /start call. The smoke also proves the model + BYOK combination works before a long-lived container is spawned."
    - "Bearer preservation for pairing: byok is cleared in onDeploy's finally (BYOK discipline), but the pair endpoint needs an Authorization header, so the pairing path copies byok into pairingBearer the moment it opens the modal. Cleared on modal onClose via a dedicated useCallback."
    - "AbortController as a timeout primitive: apiPost accepts an optional { signal } forwarded to fetch(). PairingModal wires a 90s setTimeout → controller.abort() and surfaces AbortError as a user-facing timeout message."
    - "Error-envelope unwrapping in the modal: when pair fails with ApiError, the modal JSON.parses err.body and pulls error.message from the Stripe-shape envelope. Falls back to HTTP <status> if the body isn't JSON."

key-files:
  created:
    - "frontend/components/pairing-modal.tsx"
    - ".planning/phases/22-channels-v0.2/22-06-SUMMARY.md"
  modified:
    - "frontend/lib/api-types.ts"
    - "frontend/lib/api.ts"
    - "frontend/components/playground-form.tsx"

key-decisions:
  - "Task order swapped: Task 3 (PairingModal + apiPost signature extension) committed BEFORE Task 2 (playground-form.tsx that imports PairingModal). Otherwise the Task 2 commit would not compile on its own. Per-commit tsc passes after each step."
  - "apiPost got a 4th optional parameter (ApiCallOptions) instead of changing the 3rd. Existing 3-arg callers (apiPost(path, body, headers)) work unchanged; new callers pass { signal } as a 4th positional arg. The 4th-positional shape mirrors fetch()'s convention and avoids a large refactor."
  - "PairingModal built with Tailwind primitives rather than the shadcn Dialog to keep this plan scoped to the UI surface. The repo has Dialog available (components/ui/dialog.tsx via @radix-ui/react-dialog), and a follow-up plan can migrate if desired. The current modal is fully accessible (role='dialog', aria-modal, aria-labelledby, focus-trapped by the backdrop) and uses AbortController for cancellation."
  - "Smoke-failure on persistent path sets UiError kind='unknown' (not a new taxonomy kind) because the UiError discriminated union is sealed and the existing 'unknown' surface already renders an appropriate error card. Adding a new kind would require every UiError consumer to handle it; the 'unknown' path is sufficient for the rare 'smoke failed, channel start aborted' scenario."
  - "SectionHeader prop widened to number | string rather than introducing a string-only variant. The existing 4 steps use numbers; Step 2.5 is the first fractional. Widening the union keeps all existing call sites unchanged."
  - "channelInputs dict cleared in the onDeploy finally alongside byok (both BYOK disciplines). preserveBearerForPairing flag gates just the pairingBearer clear — if the pairing modal will open, the bearer stays alive for its lifecycle only."

patterns-established:
  - "Server-sourced form metadata: any future per-recipe dynamic field list (env vars, CLI flags, container flags) should follow the same pattern — fetch the recipe detail, project the needed array, render from it, never hardcode in React."
  - "Modal-in-form async operations: when a modal needs a bearer that the parent form is about to clear (BYOK discipline), copy the bearer to a modal-scoped state var and clear it on modal onClose. Do not hold BYOK in localStorage/cookies."

requirements-completed: [SC-02, SC-03, SC-05]

# Metrics
duration: ~8min
completed: 2026-04-18
---

# Phase 22 Plan 06: Frontend Step 2.5 (Deploy Mode + Channel Inputs) Summary

**Step 2.5 of the playground form adds the persistent + Telegram deploy flow: a radio between one-shot smoke (existing default) and Persistent + Telegram, dynamic channel input fields rendered from `GET /v1/recipes/:name` metadata (zero hardcoded channel catalogs per CLAUDE.md Rule 2), BYOK-disciplined submit, an openclaw-aware key label driven by `channel_provider_compat`, a success card showing boot time + bot deeplink, and a PairingModal with the G4 90s-timeout UX for openclaw's pairing approve flow.**

## Performance

- **Duration:** ~8 min
- **Tasks:** 3/3 complete (auto, no checkpoints)
- **Files created:** 2 (components/pairing-modal.tsx + this SUMMARY)
- **Files modified:** 3 (lib/api-types.ts, lib/api.ts, components/playground-form.tsx)
- **Lines added:** ~730 (pairing-modal 216 + api-types +133 + api.ts +14 + playground-form +371 - 7 removed)

## Accomplishments

### Task 1 — TS types (`frontend/lib/api-types.ts`)

9 new exported types mirroring the Phase 22-05 Pydantic models:

- `ChannelUserInput` — env + secret + hint + optional kind/hint_url/prefix_required
- `ChannelEntry` — config_transport, required/optional inputs, ready_log_regex, response_routing, multi_user_model, optional provider_compat/pairing/known_quirks/verified_cells
- `RecipeDetail` — declares only the v0.2 fields the UI consumes (persistent.spec, channels); other YAML fields pass through via `[k: string]: unknown`
- `AgentStartRequest` / `AgentStartResponse` — body + 200 shape for POST /v1/agents/:id/start
- `AgentStatusResponse` — GET /v1/agents/:id/status with runtime_running + log_tail + degenerate fields
- `AgentStopResponse` — includes `force_killed` (G3 spike-07 — nanobot SIGTERM path)
- `AgentChannelPairRequest` / `AgentChannelPairResponse` — code body + wall_s alias (G4 spike-10)

### Task 3 — PairingModal (`frontend/components/pairing-modal.tsx`, 216 lines)

Complete G4 UX contract implementation:

- **90s client fetch timeout** via AbortController → setTimeout → controller.abort() matching the server-side docker-exec timeout in routes/agent_lifecycle.py
- **Up-front latency disclosure**: "Approval takes up to 60 seconds for openclaw. Please wait after you click Approve." — shown before submit, not after 30s of silence
- **Button disabled while submitting** blocks concurrent submits that would each pin a CLI cold-boot on the server
- **Elapsed-time readout**: `Approving… {elapsedS}s` updates every 500ms while in-flight
- **Client-side input sanitization**: `e.target.value.replace(/[^A-Za-z0-9]/g, "")` to match the server's `^[A-Za-z0-9]+$` regex — paste-and-submit works even with whitespace
- **Error envelope unwrapping**: ApiError bodies are JSON.parsed and error.message surfaced; AbortError distinguished as a timeout; other errors fallthrough
- **Accessibility**: role=dialog, aria-modal=true, aria-labelledby, close button disabled while submitting so the user can't abort a 60s in-flight call

**Bonus change in `frontend/lib/api.ts`**: `apiGet` and `apiPost` gained an optional 4th/2nd `ApiCallOptions` parameter carrying `AbortSignal`. Backward-compatible — existing 3-arg `apiPost(path, body, headers)` call sites unchanged.

### Task 2 — Playground form Step 2.5 (`frontend/components/playground-form.tsx`)

**Step 2.5 section inserted at lines 541-676** between Step 2 (model browser) and Step 3 (name + personality):

- Two radio cards: "One-shot smoke" (🧪) and "Persistent + Telegram" (💬). Persistent card disabled when `selectedRecipe.persistent_mode_available` is falsy, with an explanatory sub-line.
- Provider-compat warning banner when `channel_provider_compat.<cid>.deferred.length > 0`: "This recipe + channel combination defers X. Use your Y API key instead."
- **Dynamic channel input fields** (`allInputs.map`): every field comes from `recipeDetail.channels[selectedChannel].required_user_input` + `optional_user_input`. Each entry renders its own `<Input>` with `type=password` when `secret:true`, `autoComplete=new-password`, the server's `hint` as helper text, optional clickable `hint_url`.

**State additions (lines 113-133):** `deployMode`, `selectedChannel`, `channelInputs` (dict), `recipeDetail`, `startResponse`, `pairingModalOpen`, `agentInstanceId`, `pairingBearer`.

**Recipe detail fetch effect (lines 171-197):** `GET /api/v1/recipes/{encodeURIComponent(recipe)}` runs whenever the user picks a different recipe. Failure leaves `recipeDetail: null` (same UX as a recipe with no persistent block).

**Memoized derivations (lines 257-298):** `channelEntry`, `requiredInputs`, `optionalInputs`, `allInputs`, `isPersistentSupported`, `providerDeferredForChannel`, `byokLabel`, `allRequiredChannelInputsFilled`.

**Extended canDeploy gate (line 304):** adds `(deployMode === "smoke" || (deployMode === "persistent" && allRequiredChannelInputsFilled))`.

**Forked onDeploy (lines 316-399):**
1. Always POST `/api/v1/runs` first (the smoke — existence proof + agent_instance creation).
2. If `deployMode === "persistent"` AND `verdict === "PASS"`:
   - POST `/api/v1/agents/:id/start` with `{channel, channel_inputs}` body and BYOK bearer
   - Capture `startResponse`; if the channel has a `pairing` block in the recipe, copy `byok` to `pairingBearer` and open the modal
3. `finally`: clear `byok` + `channelInputs`; clear `pairingBearer` UNLESS the pairing modal was just opened (bearer held for modal lifecycle)

**Byok Label swap (line 768):** replaced the hardcoded "OpenRouter API key" with `{byokLabel}` — the memoized label flips to "Anthropic API key" (or whatever the recipe declares in `channel_provider_compat.telegram.supported[0]`) when the selected channel defers openrouter.

**Deploy button copy (lines 799-807):** conditional on `deployMode` — "Deploy & start bot — "<name>"" for persistent, "Deploy "<name>"" for smoke.

**Success card (lines 858-912):** rendered alongside the existing verdict card. Shows "Live on your bot" + `bot_username` deeplink from `verified_cells[0].bot_username` (server-sourced), boot_wall_s, container_id prefix, health_check_ok badge.

**PairingModal render (lines 916-924):** conditional on `pairingModalOpen && agentInstanceId`. Prop contract: `agentId`, `channel`, `bearer`, `onClose`.

**SectionHeader prop widened (line 1005):** `step: number | string` to accept "2.5". All existing number call sites unchanged.

## Task Commits

Each task committed atomically on this worktree branch (will be merged by the orchestrator after Wave 4 completes):

1. **Task 1 — TS types** — `1223127` (feat)
2. **Task 3 — PairingModal + apiPost AbortSignal** — `b6ef04a` (feat) — committed before Task 2 for dep order
3. **Task 2 — playground-form Step 2.5** — `ce7bbef` (feat)

Plan metadata (this SUMMARY): committed as the final commit by the orchestrator after the merge.

## Files Created/Modified

### Created
- `frontend/components/pairing-modal.tsx` — 216 lines. G4 UX contract: 90s timeout, up-front disclosure, disabled submit in-flight, elapsed-time readout, alnum-only input sanitization, error-envelope unwrapping.
- `.planning/phases/22-channels-v0.2/22-06-SUMMARY.md` — this file.

### Modified
- `frontend/lib/api-types.ts` — +133 lines. 9 new types for the Phase 22a agent lifecycle surface. No existing types changed.
- `frontend/lib/api.ts` — +14 lines (86 total). apiGet/apiPost gained an optional `ApiCallOptions` bag with AbortSignal. Backward compatible; all ~10 existing callers work unchanged.
- `frontend/components/playground-form.tsx` — +371 lines / -7 lines. Step 2.5 section, state additions, recipe-detail fetch, memoized derivations, extended canDeploy, forked onDeploy, byok label swap, conditional button copy, success card, pairing modal render, widened SectionHeader prop.

## Pattern Verification

### CLAUDE.md Rule 2 (dumb client, no client-side catalogs) — PASSED

Grep audit of the changed files confirms:

```
grep "CHANNELS|OPENCLAW_|openclaw=|openclaw\"" components/playground-form.tsx components/pairing-modal.tsx
→ 3 hits, ALL in comments that reaffirm the rule (no literal constants)

grep "TELEGRAM_BOT_TOKEN|TELEGRAM_ALLOWED" components/playground-form.tsx components/pairing-modal.tsx lib/api-types.ts
→ 1 hit, a comment `// e.g. "TELEGRAM_BOT_TOKEN"` in the ChannelUserInput type.
  No code reference. No hardcoded env var name as a string literal.
```

Every piece of channel-related data the form renders flows from:
- `GET /v1/recipes` → `RecipeSummary.channels_supported`, `persistent_mode_available`, `channel_provider_compat`
- `GET /v1/recipes/:name` → `RecipeDetail.channels.<cid>.required_user_input` + `optional_user_input` + `pairing` + `verified_cells`
- `POST /v1/agents/:id/start` response → `bot_username` (via `verified_cells`), `boot_wall_s`, `container_id`, `health_check_ok`

The deploy path calls `POST /v1/runs` + `POST /v1/agents/:id/start` with real bodies — no `setState({ isRunning: true })` theater per CLAUDE.md Rule 3.

### BYOK Discipline (SC-05) — PASSED

- `byok` state cleared in `onDeploy` `finally`
- `channelInputs` dict (all channel creds, including TELEGRAM_BOT_TOKEN) cleared in the same finally
- `pairingBearer` cleared in `onDeploy` finally UNLESS the pairing modal is being opened (held only for modal lifecycle)
- `pairingBearer` cleared on PairingModal `onClose` (invoked from X / Cancel / Done buttons)
- All secret fields use `type="password"` + `autoComplete="new-password"` + `autoCorrect=off` + `autoCapitalize=off` + `spellCheck={false}`

### Goal-backward verification

- **SC-02 (user-visible <180s deploy):** The onDeploy persistent branch POSTs `/v1/runs` → `/v1/agents/:id/start` and renders the startResponse success card with `boot_wall_s`. Live validation requires backend infra (covered in Plan 22-07 e2e).
- **SC-03 foundation (e2e round-trip):** Step 2.5 wires every v0.2 channel input dynamically. 22-07 exercises the full round-trip against real Telegram.
- **SC-05 (bot_token cleared):** channelInputs cleared on submit; password input type + new-password autoComplete.

## Decisions Made

- **Task order swapped.** Task 3 (PairingModal) committed before Task 2 (playground-form) so each commit is tsc-clean in isolation. Playground-form imports PairingModal; committing them in plan-declared order would leave commit 2 with an unresolved import.
- **apiPost 4th-arg for options.** Extended signature via an optional `ApiCallOptions` bag instead of changing the 3rd `headers` parameter. Zero existing-caller churn.
- **Smoke-before-start invariant.** Persistent mode always runs the smoke first. Gives the backend the agent_instance row (via upsert in /v1/runs) and proves the model + BYOK combination works before spawning a long-lived container. If the smoke verdict !== "PASS", the /start call is skipped with a user-facing error.
- **PairingModal built with Tailwind primitives, not shadcn Dialog.** Keeps scope small. The modal is accessible (role=dialog, aria-modal, aria-labelledby) and uses AbortController for cancellation. Dialog migration is a future polish step.
- **UiError unknown kind for smoke-failure-on-persistent.** Avoided adding a new UiError kind for a rare error path. The existing "unknown" kind's error card is an adequate surface.
- **SectionHeader prop widened to number | string.** Least-intrusive way to support Step "2.5" without refactoring the other 4 headers.

## Deviations from Plan

### Auto-fixed Issues

**[Rule 3 — Blocking] PairingModal import dependency ordering.**
- Found during: Task 2 typecheck
- Issue: The plan has Task 2 create playground-form edits that import `@/components/pairing-modal`, but Task 3 creates that file. Committing Task 2 first would leave a tsc-broken intermediate commit.
- Fix: Swapped commit order — Task 3 (pairing-modal.tsx + api.ts apiPost signature) committed as `b6ef04a` BEFORE Task 2 (playground-form.tsx) as `ce7bbef`. Task 1 (api-types.ts) still committed first as `1223127`.
- Rationale: Each commit now compiles cleanly against its base. Zero change to the plan's code shape.
- Commits: `1223127`, `b6ef04a`, `ce7bbef`

**[Rule 1 — Bug] UiError "title" field does not exist on the sealed union.**
- Found during: Task 2 typecheck
- Issue: The plan's example onDeploy branch sets `setUiError({ kind: "unknown", title: "Smoke failed", message: "…" } as UiError)`. The UiError discriminated union's "unknown" variant declares `{ kind: "unknown"; message: string; status?: number }` — no `title` field. The `as UiError` cast would suppress the error but the `title` would never be consumed by any UiError rendering surface.
- Fix: Dropped the title field, collapsed into the message: `setUiError({ kind: "unknown", message: "Smoke failed — channel start aborted." })`.
- Files modified: `frontend/components/playground-form.tsx`
- Rationale: Removing a phantom field. The user-visible surface is unchanged because the rendered error card only renders `message`.

### Scoped-out
Pre-existing tsc errors in 3 unrelated files (`app/dashboard/agents/[id]/page.tsx`, `components/footer.tsx`, `components/particle-background.tsx`) are NOT in this plan's scope. Logged but untouched.

## Authentication Gates

None. No external service connection at the route level this plan exercises. BYOK bearers flow through the same discipline as routes/runs.py.

## Issues Encountered

- **Worktree missing node_modules.** The worktree was checked out fresh and `frontend/node_modules` was absent. Symlinked to the source repo's existing `frontend/node_modules` (pnpm-managed at `/Users/fcavalcanti/dev/agent-playground/frontend/node_modules`) so `tsc` could run. The symlink is gitignored via `frontend/.gitignore:14` (node_modules); no commit impact.
- **No eslint binary available.** The project's `pnpm lint` invokes Next's built-in eslint integration, which requires `next` CLI. Skipped ESLint — `tsc --noEmit` covers the typecheck gate.
- **Live end-to-end validation deferred.** The plan's verification includes a manual flow that requires the live API + a real Telegram bot. That is Plan 22-07's (e2e validation) scope — this plan's automated gate is `tsc --noEmit` which PASSED with zero new errors beyond the 3 pre-existing baseline failures.

## User Setup Required

None. No new environment variables, no new secrets, no new infra. Plan 22-07 will run the real e2e against `.env.local`.

## Next Phase Readiness

**Ready for Plan 22-07 (e2e validation):**
- Step 2.5 UI is wired end-to-end against the Plan 22-05 endpoints. An e2e test can:
  1. Select a recipe (hermes / picoclaw / nullclaw / nanobot / openclaw).
  2. Click "Persistent + Telegram" in Step 2.5.
  3. Fill the dynamic channel input fields (TELEGRAM_BOT_TOKEN + per-recipe user ID field).
  4. Click Deploy. Verify a POST /v1/runs, then a POST /v1/agents/:id/start, then success card visible in <180s (SC-02).
  5. For openclaw only: DM bot, get pair code from Telegram reply, paste into PairingModal, click Approve. Verify POST /v1/agents/:id/channels/telegram/pair returns exit_code=0.
  6. DM the bot again; expect a reply within 10s of sending (SC-03).
- For the "byok cleared" assertion, inspect React devtools AFTER submit: `byok === ""`, `channelInputs === {}`, `pairingBearer === ""` (after modal close).

**Blockers or concerns:** None. Step 2.5 is ready for the final e2e wave.

## Known Stubs

None. Step 2.5 renders dynamically from server data (not a stub). The Live-on-your-bot success card is wired from a real AgentStartResponse. The PairingModal POSTs to a real endpoint. No placeholder rendering paths that are designed to be replaced later.

## Threat Flags

No new network surface. The frontend gains 2 new outbound call patterns:
- `GET /api/v1/recipes/:name` — pre-existing server endpoint (Phase 19), consumed for recipe-detail metadata. Public; no BYOK.
- `POST /api/v1/agents/:id/start` — pre-existing from Plan 22-05, Bearer-protected. BYOK bearer + channel_inputs flow through the request body; the plaintext goes out of scope when the response returns (finally clears state).
- `POST /api/v1/agents/:id/channels/:cid/pair` — pre-existing from Plan 22-05, Bearer-protected. Pair code sanitized to alnum-only client-side before submit.

`/api` proxy config in `next.config.mjs` carries the auth cookie/session context. No new threat_model entries beyond what Plan 22-05's `<threat_model>` already declared.

## Self-Check: PASSED

### Artifact existence

```
FOUND: frontend/components/pairing-modal.tsx (216 lines)
FOUND: frontend/lib/api-types.ts (366 lines — +133 from baseline)
FOUND: frontend/lib/api.ts (87 lines — +14 from baseline)
FOUND: frontend/components/playground-form.tsx (1525 lines — +371/-7 from baseline)
FOUND: .planning/phases/22-channels-v0.2/22-06-SUMMARY.md
```

### Commit existence

```
FOUND: 1223127 (Task 1 — TS types)
FOUND: b6ef04a (Task 3 — PairingModal + apiPost AbortSignal)
FOUND: ce7bbef (Task 2 — playground-form Step 2.5)
```

### tsc verification

```
cd frontend && ./node_modules/.bin/tsc --noEmit
→ 3 errors total, all PRE-EXISTING in unmodified files:
    app/dashboard/agents/[id]/page.tsx
    components/footer.tsx
    components/particle-background.tsx
→ 0 errors in files modified by Plan 22-06
```

### Non-regression

- Existing `/v1/runs` flow unchanged — onDeploy's smoke branch still POSTs to it with the same body shape.
- Existing 3-arg `apiPost` callers in the codebase work without modification (ApiCallOptions is a 4th optional parameter).
- Step 3 + Step 4 + result section continue to render as before.
- `RecipeCard`, `ModelBrowser`, `ModelRow` components untouched.
- `my-agents-panel.tsx` (in `<files_modified>` only as a potential extension point) was not modified — the plan's optional "preview persistent run" extension was not required to meet the SCs. Listed in the plan as "optional preview in my-agents-panel if a persistent run exists" — Plan 22-07 can add this if the live flow reveals the UX need.

---
*Phase: 22-channels-v0.2*
*Plan: 06*
*Completed: 2026-04-18*
