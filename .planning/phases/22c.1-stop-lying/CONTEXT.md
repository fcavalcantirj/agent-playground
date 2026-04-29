# Phase 22c.1 — Stop Lying

**Status:** seed CONTEXT (pre-spec).
**Created:** 2026-04-29 (after the post-22c live smoke session).
**Theme:** surgical, no new features. Every fake handler either wires to a real backend OR clearly says "Coming in Phase 22c.X". No more `toast.success("...")` lies.

---

## Why this phase exists

First end-to-end logged-in playground test surfaced that big chunks of the post-login surface area lie to the user via fake `toast.success(...)` handlers. Backend endpoints don't exist; mock data is rendered as if real; "Alex Chen" hardcoded in three pages even though `useUser()` exists in dashboard layout.

This phase fixes ONLY that — surgical. New surfaces (real api-keys, real billing, real analytics, real personality system prompts) are deferred to dedicated later phases.

---

## Scope (locked — 7 items, hermes recipe pulled into 22c.2)

### R-1. Stop the toast-only lies
Convert every fake handler to either:
- **Real wire-up** where backend already exists (e.g., the existing Stop endpoint should be wired into the agent detail page, not just dashboard list)
- **Disabled with "Coming in Phase 22c.X" tooltip** where backend doesn't exist yet (api keys, billing, analytics, notifications, profile-save, settings-save, etc.)

Concrete inventory of fake handlers to disable / convert:
- `frontend/app/dashboard/agents/[id]/page.tsx:91-101` — toggleStatus, saveConfig, deleteAgent, sendTestMessage (1.5s setTimeout fake)
- `frontend/app/dashboard/agents/[id]/settings/page.tsx:57-66` — handleSave, handleDelete (toast only), regenerateApiKey (client-side random string)
- `frontend/app/dashboard/agents/[id]/logs/page.tsx:77` — handleRefresh comment "In production, this would fetch new logs" + 17 hardcoded mock log entries
- `frontend/app/dashboard/api-keys/page.tsx:89-101` — createKey generates fake `ap_live_sk_*`, no backend; revoke + delete state-only
- `frontend/app/dashboard/billing/page.tsx:50,99-107,156` — hardcoded plan/payment/invoices, dead Cancel/Upgrade buttons, link to /pricing + /contact (verify exist)
- `frontend/app/dashboard/notifications/page.tsx:30-82,107-119` — mock notifications, fake mark-as-read
- `frontend/app/dashboard/profile/page.tsx:11-19,42` — hardcoded "Alex Chen", fake handleSave, disabled avatar upload
- `frontend/app/dashboard/settings/page.tsx:10-17,150` — local-state-only toggles, dead delete-account button

### R-2. Real `DELETE /v1/agents/{id}`
- New backend endpoint with FK-ordered transactional cleanup (`idempotency_keys → runs → agent_instances` cascades to `agent_containers`).
- Stop the running container first if `agent_containers.container_status = 'running'` (re-use `execute_persistent_stop` from `agent_lifecycle.py`).
- Wire into `dashboard/agents/[id]/settings/page.tsx::handleDelete` (replaces `toast.success`).
- Also wire into `dashboard/agents/[id]/page.tsx::deleteAgent` (currently fake).
- Pattern reference: the manual cleanup executed during the smoke session (transaction + Docker stop + cascade delete).

### R-3. Real `GET /v1/agents/{id}` for the detail page header
- New backend endpoint returning a single agent's full row (recipe_name, model, name, personality, created_at, last_run_at, total_runs, container_status).
- Replaces `getAgent(id)` mock at `dashboard/agents/[id]/page.tsx`.
- The detail page is high-traffic (users click into agents from `/dashboard`); fixing the header alone removes a major lie.

### R-4. Identity bleed — read `/v1/users/me` everywhere "Alex Chen" lives
- `frontend/app/page.tsx:23` (landing page navbar)
- `frontend/app/playground/page.tsx:31` (playground navbar)
- `frontend/app/dashboard/profile/page.tsx:12,42` (profile — already-existing `useUser()` hook in layout is being ignored)
- Mock agent names ("Customer Support Bot") in detail + logs pages get cleared when R-3 lands (they'll come from the real GET /v1/agents/{id}).

### R-5. `/#playground` fragment bug → `/playground` page links
- `frontend/components/hero-section.tsx:79` — `<a href="#playground">` → `<Link href="/playground">`
- `frontend/components/cta-section.tsx:73` — same
- Verify no other `#playground` anchors exist anywhere.

### R-6. Default deployMode = "persistent" + Telegram preselected in playground-form
- `frontend/components/playground-form.tsx:118` — change `useState<DeployMode>("smoke")` to `"persistent"` (or whatever the persistent enum is)
- Default channel selection to `telegram` when the recipe declares it
- Per AMD-… (TBD in spec): if recipe doesn't have a Telegram channel, fall back to first available channel or smoke

### R-7. Ship the looser pass_if + agent_name plumbing already on disk
- This is the current session's uncommitted code work (29 unit tests PASS + 4-matrix curl PASS).
- Files touched:
  - `tools/run_recipe.py` — `evaluate_pass_if` accepts `agent_name`; new `replied_ok` verb; `run_cell` forwards `agent_name`
  - `tools/tests/test_pass_if.py` — +6 agent_name tests + 5 replied_ok tests
  - `api_server/src/api_server/services/runner_bridge.py` — `execute_run` forwards `agent_name`
  - `api_server/src/api_server/routes/runs.py` — passes `body.agent_name`; overrides recipe.smoke.pass_if to `replied_ok` when `body.personality` is set
  - `frontend/components/run-result-card.tsx` — smoke check section showing prompt+reply+pass_if
  - `frontend/components/playground-form.tsx` — keep-on-fail UX (only clear inputs on full success) + reason-aware error message

---

## NOT in this phase (explicit)

- **Hermes persistent recipe silent model drop** — moved to **Phase 22c.2** (recipe-level identity work belongs there).
- **Personality presets becoming real system prompts** — Phase 22c.2.
- **agent_name baked into bot identity (per-recipe injection contract)** — Phase 22c.2.
- **Real api keys / billing / analytics / notifications / settings backends** — Phases 22c.4 onward.

---

## Empirical evidence captured this session (so the spec phase has receipts)

**4-matrix curl PASS (live API + real LLM + real session cookie, no mocks):**

| # | recipe | personality | name | model | pass_if used | verdict | wall |
|---|--------|-------------|------|-------|--------------|---------|------|
| 1 | nullclaw | skeptical-critic | matrix-n-1 | anthropic/claude-haiku-4.5 | replied_ok (overridden) | PASS | 4.05s |
| 2 | hermes | skeptical-critic | matrix-h-1 | anthropic/claude-haiku-4.5 | replied_ok (overridden) | PASS | 15.89s |
| 3 | picoclaw | polite-thorough | matrix-p-1 | anthropic/claude-haiku-4.5 | replied_ok (overridden) | PASS | 6.69s |
| 4 | nullclaw | (none) | matrix-n-2 | anthropic/claude-haiku-4.5 | response_contains_name (recipe default) | PASS | 2.94s |

User-driven Telegram round-trip CONFIRMED via real Telegram DM at 2026-04-29 00:38: nullclaw + claude-haiku-4.5 + Persistent + Telegram → bot identified as @AgentPlayground_bot, replied to "hello", `/model` reported `openrouter/anthropic/claude-haiku-4.5` (the user's selection — no silent drop on this recipe).

**Per-recipe model-honor matrix (for the deferred 22c.2 hermes work):**

| Recipe | Persistent runtime model honored | Source |
|--------|----------------------------------|--------|
| picoclaw | ✅ `"$MODEL"` in argv | `recipes/picoclaw.yaml:211` |
| nullclaw | ✅ `--model "openrouter/$MODEL"` | `recipes/nullclaw.yaml:222` |
| nanobot | ✅ `"model": "$MODEL"` in config injection | `recipes/nanobot.yaml:226` |
| openclaw | ✅ `openclaw config set agents.defaults.model "$MODEL"` + `--model "$MODEL"` | `recipes/openclaw.yaml:117` |
| **hermes** | ❌ silent drop — `[gateway, run, -v]` no `$MODEL` | `recipes/hermes.yaml:213-219` (author noted in line 322-325) |

---

## Definition of done (exit gate)

- [ ] No fake `toast.success("X")` handler exists in `/dashboard/**` or `/playground/**` without either a real API call or an explicit "Coming in Phase 22c.X" message
- [ ] `DELETE /v1/agents/{id}` exists with FK cascade + container stop, integration test PASSes
- [ ] `GET /v1/agents/{id}` exists, integration test PASSes
- [ ] Grep `Alex Chen` returns 0 hits in `frontend/app/`
- [ ] Grep `href="#playground"` returns 0 hits in `frontend/`
- [ ] Default `deployMode` in playground = persistent (verified by visual smoke)
- [ ] Wave-end: live user runs the smoke matrix from `/playground` (any recipe + any model + any personality) and reports no fake feedback
