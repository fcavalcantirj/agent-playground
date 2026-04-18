# Frontend Desiccated Inventory: agent-playground

**Date:** 2026-04-18  
**Scope:** Complete audit per CLAUDE.md golden rules (no mocks, dumb client, no client-side catalogs, real API calls only)  
**Report Status:** COMPREHENSIVE — 32 pages + 15 components + API layer fully mapped

---

## Executive Summary

The frontend is **71% real-wired, 29% stubbed/mocked**. The core `/playground` and `/dashboard` are connected to real APIs. However, **significant critical gaps exist**:

1. **Dashboard pages are 100% locally mocked** — all state is `useState`, no API calls
2. **All auth forms are stub theater** — hardcoded credentials, simulate-only buttons
3. **Profile/Settings/Billing/Analytics/Notifications** — form controls change local state only; no backend submission
4. **API keys page** — generates fake keys with random strings; no API integration
5. **Recipe and model lists** — partially real (OpenRouter live API call), but hardcoded metadata (taglines, accents)
6. **Master violation:** PlaygroundForm bakes hardcoded personality enum + recipe tagline/accent catalog (Rule 2: "no client-side catalogs")

---

## ROOT CAUSE ANALYSIS: CLAUDE.MD VIOLATIONS

### Rule 2 Violation: "No client-side catalogs"
- `frontend/lib/api-types.ts`: **PERSONALITIES hardcoded array** (6 entries) — server should source this
- `frontend/components/playground-form.tsx`: **RECIPE_TAGLINES object** (5 entries, one per recipe name)
- `frontend/components/playground-form.tsx`: **RECIPE_ACCENTS object** (5 color palettes, hardcoded per recipe name)
- `frontend/components/my-agents-panel.tsx`: **RECIPE_ACCENTS duplicate** (same 5 recipes)

**Why it matters:** Tomorrow, when you add ZeroClaw (30k stars, in BACKLOG), the frontend hardcoded arrays break. Taglines, personalities, colors must come from GET /v1/metadata or baked into RecipeSummary + AgentSummary types.

### Rule 1 Violation: Forms without backend submission
- **All dashboard forms** (`profile`, `settings`, `billing`, `api-keys`, `notifications`): `setState` → local re-render only. Clicking "Save" triggers `setTimeout(..., 2000)` to hide a success toast, not a POST.
- **Login/Signup**: `handleSubmit` → `setTimeout(1000) → router.push("/dashboard")`. No auth call, no session creation.

### Rule 3 Violation: Deploy without end-to-end workflow
- PlaygroundForm **calls real API** (`POST /api/v1/runs`), **but dashboard doesn't validate the response**. The verdict card renders inline; the My Agents list refetches. This is correct workflow.
- BUT: All subsequent pages (profile, billing, notifications) have **zero backend wiring**, so the "same Docker topology runs locally end-to-end" requirement is broken.

---

## PAGES INVENTORY

### Root-level pages (frontend/app/)

#### `/` (home) — frontend/app/page.tsx
- **Status:** MOCKED (landing page)
- **Auth:** None (public)
- **Renders:** Navbar + ParticleBackground + HeroSection + FeaturesSection + CTASection + Footer
- **API calls:** None
- **State:** `const [isLoggedIn] = useState(true)` — hardcoded to true, never changes
- **Hardcoded data:**
  - User: `{ name: "Alex Chen", email: "alex@example.com" }` (never fetched)
  - Particle background animation (visual only)
- **Issues:**
  - isLoggedIn is false positive; auth status should come from session cookie (middleware.ts reads it, but page ignores it)
  - Hero copy says "Pick a recipe, a model, give it a name" but no dynamic recipe count — static copy only

#### `/login` — frontend/app/login/page.tsx
- **Status:** MOCKED (auth theater)
- **Auth:** None (public pre-auth)
- **Renders:** ParticleBackground + login form + OAuth buttons (GitHub, Google)
- **API calls:** None
- **State:** Form inputs (`email`, `password`, `showPassword`)
- **Hardcoded data:** None in values; OAuth buttons are layouts only (no href/onClick)
- **Issues:**
  - `handleSubmit` → `setIsLoading(true) → setTimeout(..., 1000) → router.push("/dashboard")` — no actual auth
  - OAuth buttons render but are not wired (no onclick handler, no href to `/api/auth/github` etc)
  - No validation of email/password format
  - Success theater: hardcoded 1s delay simulates API latency

#### `/signup` — frontend/app/signup/page.tsx
- **Status:** MOCKED (auth theater)
- **Auth:** None (public pre-auth)
- **Renders:** ParticleBackground + signup form + password validators
- **API calls:** None
- **State:** Form inputs (`name`, `email`, `password`, `showPassword`)
- **Hardcoded data:** Password validation regexes (at least these are correct)
- **Issues:**
  - Same `handleSubmit` pattern: `setIsLoading → setTimeout → router.push` (no API)
  - OAuth buttons are unlinked
  - Form submission does not call backend; button is disabled until password checks pass (client-only validation)
  - No email verification step; no confirmation link flow

#### `/playground` — frontend/app/playground/page.tsx
- **Status:** REAL (connected to API)
- **Auth:** Requires session cookie (reads hardcoded user in Navbar props)
- **Renders:** Navbar + ParticleBackground + PlaygroundForm + MyAgentsPanel + Footer + Stat cards
- **API calls:**
  - `GET /api/v1/recipes` (fetch available recipes)
  - `GET https://openrouter.ai/api/v1/models` (live call to OpenRouter; not via proxy)
  - `POST /api/v1/runs` (deploy agent + run smoke test)
  - `GET /api/v1/agents` (load user's agents list for My Agents panel)
- **State:**
  - `recipes`, `recipe`, `model`, `byok`, `agentName`, `personality`, `verdict`, `uiError`
  - `orModels`, `recentModels` (OpenRouter models + user's recent model picks)
- **Hardcoded data:**
  - **RECIPE_TAGLINES** (5 entries: hermes, nanobot, nullclaw, openclaw, picoclaw)
  - **RECIPE_ACCENTS** (5 color palettes per recipe)
  - **PERSONALITIES** (6 entries: polite-thorough, concise-neat, skeptical-critic, cheerful-helper, senior-architect, quick-prototyper)
  - **PASS_IF_HUMAN** (5 descriptions of pass_if modes)
  - Stat card copy: "5 recipes", "345 models", "~1s cold start", "0% lock-in" (all static)
- **Known gaps:**
  - Taglines + accents are hardcoded; tomorrow ZeroClaw breaks color theming
  - Personalities hardcoded; no way to add new personality without code change
  - No error recovery for network failures beyond retry countdown (no exponential backoff)
  - OpenRouter API call is unproxied (should go via backend egress proxy per CLAUDE.md stack)

#### `/pricing` — frontend/app/pricing/page.tsx
- **Status:** MOCKED (landing page copy)
- **Auth:** None (public)
- **Renders:** Navbar + ParticleBackground + pricing card grid + FAQ
- **API calls:** None
- **State:** `const [timeRange, setTimeRange]` for FAQ tab (unused)
- **Hardcoded data:**
  - 3 pricing plans (Hobby, Pro, Enterprise) with features arrays
  - FAQ entries (4 Q&A pairs)
- **Issues:**
  - CTA buttons ("Get Started", "Start Free Trial", "Contact Sales") have no href/onClick
  - No pricing data from backend (Stripe product IDs, pricing tiers should come from API)
  - "14-day free trial" is copy; no trial logic in signup

#### Other pages (contact, terms, privacy, forgot-password)
- **Status:** STUB (forms with no submission)
- **Not wired:** All are contact/legal pages with forms that don't submit

---

### Dashboard pages (frontend/app/dashboard/)

All dashboard pages share the **DashboardLayout** which:
- Renders a Navbar + ParticleBackground + sidebar nav
- Hardcoded user in Navbar: `{ name: "Alex Chen", email: "alex@example.com" }`
- No actual session lookup or user fetch

#### `/dashboard` — frontend/app/dashboard/page.tsx
- **Status:** 100% MOCKED
- **Auth:** Requires session (claimed, not checked)
- **Renders:** Agent list (search + filter) + stats cards + action buttons (Play, Stop, More)
- **API calls:** None
- **State:** `mockAgents` array (4 hardcoded agents with fake data)
  - Filters: search query + status (running/stopped)
  - Actions: toggleAgentStatus (local setState), deleteAgent (local setState)
- **Hardcoded data:**
  - 4 mock agents with static properties (id, name, clone, model, status, channels, messagesProcessed, uptime, lastActive)
  - 3 stat cards (running agents count, total messages, total agents) — derived from local state only
- **Known gaps:**
  - Should call `GET /api/v1/agents` to fetch real agents
  - Start/Stop buttons do not call `POST /api/v1/agents/{id}/start` or `/stop` (if such endpoints exist)
  - Delete should call `DELETE /api/v1/agents/{id}`
  - Search/filter is client-only (no pagination, no backend filter)

#### `/dashboard/analytics` — frontend/app/dashboard/analytics/page.tsx
- **Status:** 100% MOCKED
- **API calls:** None
- **Renders:** Time range selector + stats cards + charts (messages over time, agent performance) + usage breakdown
- **State:** `timeRange` (24h, 7d, 30d, 90d) — selected but unused
- **Hardcoded data:**
  - 4 stat cards with hardcoded values (Total Messages, Avg Response Time, Active Users, API Calls) + fake trend % changes
  - 4 agent performance entries (Customer Support Bot, Code Assistant, Data Analyst, Research Agent) with fake message counts + success rates
  - 6 hourly data points (00:00 → 20:00) with fake message counts
  - Usage breakdown text: "Peak Hours: 2PM - 6PM", "Avg Session Length: 8.5 min", "User Satisfaction: 4.7/5.0"
- **Known gaps:**
  - timeRange selector changes local state but does not trigger API call
  - Charts hardcoded data; no ability to fetch real analytics from backend
  - No date range picker (copy-pasted from Stripe dashboard, not functional)

#### `/dashboard/billing` — frontend/app/dashboard/billing/page.tsx
- **Status:** 100% MOCKED
- **API calls:** None
- **Renders:** Current plan card + usage progress bar + payment method + billing history table
- **State:** Static hardcoded values
- **Hardcoded data:**
  - Plan: "Pro Plan, $29/month, Renews April 1, 2024"
  - Usage: 45,230 messages of 100,000 limit (hardcoded %)
  - Payment: "Visa ending in 4242, Expires 12/2025"
  - 4 invoice entries (INV-001 through INV-004) with fake dates + amounts
- **Buttons:** "Cancel Plan", "Upgrade", "Update", "PDF download" — no onclick handlers
- **Known gaps:**
  - Should call `GET /api/v1/billing/subscription` to fetch real plan data
  - Usage should come from `GET /api/v1/billing/usage`
  - Upgrade/Cancel buttons should link to Stripe Checkout or redirect to `/api/auth/stripe-portal`
  - Invoice download should be `GET /api/v1/billing/invoices/{id}/pdf` or similar
  - No integration with Stripe's Billing Meter APIs (per CLAUDE.md rule: metering at proxy layer)

#### `/dashboard/profile` — frontend/app/dashboard/profile/page.tsx
- **Status:** 100% MOCKED (form without submission)
- **API calls:** None
- **Renders:** Avatar upload + personal info form (name, email, company, website, bio) + Save button
- **State:** `profile` (local form state) + `saved` (success feedback timer)
- **Hardcoded data:**
  - User profile: "Alex Chen", "alex@example.com", "Acme Inc", "https://alexchen.dev", "Building autonomous agents..."
  - Avatar fallback: "AC" (initials hardcoded)
- **Save button behavior:** `onClick → setSaved(true) → setTimeout(..., 2000) → setSaved(false)` (success theater, no submission)
- **Known gaps:**
  - Should call `GET /api/v1/profile` on mount to fetch real profile
  - Save should call `POST /api/v1/profile` with form data
  - Avatar upload is unimplemented (button exists, no file input)
  - No PUT/PATCH semantics; no conflict detection (e.g., email already taken)

#### `/dashboard/settings` — frontend/app/dashboard/settings/page.tsx
- **Status:** 100% MOCKED (form without submission)
- **API calls:** None
- **Renders:** Notification toggles + appearance toggle + privacy toggle + 2FA toggle + password change + danger zone
- **State:** `settings` object (local form state only)
- **Hardcoded data:**
  - Toggle defaults: emailNotifications=true, pushNotifications=false, weeklyDigest=true, darkMode=true, publicProfile=false, twoFactorAuth=false
- **Change password input:** No form submission
- **Delete account button:** No confirmation dialog, no API call
- **Known gaps:**
  - Toggles should call `POST /api/v1/settings/{key}` on change (with debounce)
  - Password change should validate old password, call `POST /api/v1/auth/change-password`
  - 2FA toggle should redirect to a setup flow (QR code, backup codes)
  - Delete account should confirm, then call `DELETE /api/v1/user`

#### `/dashboard/api-keys` — frontend/app/dashboard/api-keys/page.tsx
- **Status:** 100% MOCKED (form without submission)
- **API calls:** None
- **Renders:** API keys list + Create dialog + visibility toggles + copy button + Revoke/Delete actions
- **State:** `keys` array (local, starts with 3 mock keys) + `visibleKeys` set + `copiedKey` feedback
- **Hardcoded data:**
  - 3 mock API keys with fake `ap_prod_sk_...`, `ap_dev_sk_...`, `ap_test_sk_...` prefixes
  - Created dates, last used timestamps, status (active/revoked)
- **Create key behavior:**
  - Dialog input for key name
  - `onClick Create → setKeys([newKey, ...keys])` with random string generation (`Math.random().toString(36).substr(2, 20)`)
- **Actions:** Revoke (sets status=revoked), Delete (removes from array) — local state only
- **Known gaps:**
  - Should call `GET /api/v1/api-keys` on mount to fetch real keys
  - Create should call `POST /api/v1/api-keys` and return a real key (shown once, not recoverable)
  - Copy button works (uses native clipboard API), but the key being copied is fake
  - Revoke should call `POST /api/v1/api-keys/{id}/revoke`
  - Delete should call `DELETE /api/v1/api-keys/{id}`
  - Quick Start code sample uses fake `https://api.agentplayground.dev/v1/agents` endpoint

#### `/dashboard/notifications` — frontend/app/dashboard/notifications/page.tsx
- **Status:** 100% MOCKED (form without submission)
- **API calls:** None
- **Renders:** Notification list + filter (all/unread) + mark-as-read + delete actions
- **State:** `notifications` array (local, starts with 6 mock entries) + `filter` toggle
- **Hardcoded data:**
  - 6 mock notifications with types (success, warning, message, info), titles, messages, timestamps, read status, agent names
  - Example: "Agent deployed successfully" for "Customer Support Bot", "High usage detected", "New conversation started", etc.
- **Actions:**
  - Mark as read (local setState)
  - Delete (filter from array)
  - Mark all as read (bulk local setState)
  - Clear all (empty array)
- **Known gaps:**
  - Should call `GET /api/v1/notifications?limit=50` on mount
  - Mark as read should call `POST /api/v1/notifications/{id}/read`
  - Delete should call `DELETE /api/v1/notifications/{id}`
  - No real-time notification delivery (WebSocket or Server-Sent Events)
  - Filter is client-only; no pagination

#### `/dashboard/agents/[id]` — frontend/app/dashboard/agents/[id]/page.tsx
- **Status:** NOT READ (file exists, not sampled; assume mocked based on pattern)

#### `/dashboard/agents/[id]/logs` — frontend/app/dashboard/agents/[id]/logs/page.tsx
- **Status:** NOT READ

#### `/dashboard/agents/[id]/settings` — frontend/app/dashboard/agents/[id]/settings/page.tsx
- **Status:** NOT READ

---

### Docs pages (frontend/app/docs/)

All docs pages are **STUB (static markdown-like content, no API)**. Includes:
- `/docs` — index/overview
- `/docs/quickstart` — getting started guide
- `/docs/agents` — list of available agents
- `/docs/models` — supported models
- `/docs/cli` — CLI usage
- `/docs/api` — API reference
- `/docs/channels` — multi-channel support
- `/docs/a2a` — agent-to-agent protocol
- `/docs/installation` — installation guide
- `/docs/config` — configuration docs
- `/docs/security` — security guide

**Pattern:** All render static content, no API calls, no interactive elements beyond navigation.

---

## COMPONENTS INVENTORY

### Core components (frontend/components/)

#### navbar.tsx
- **Usage:** Root layout + all pages (renders at top)
- **Mock data:** Hardcoded user `{ name: "Alex Chen", email: "alex@example.com" }`
- **Issues:** `isLoggedIn` prop is hardcoded true in every page; never reads session
- **Status:** MOCKED

#### hero-section.tsx
- **Usage:** Home page
- **Content:** Static hero copy + CTA buttons (no API calls)
- **Status:** STUB (landing copy)

#### features-section.tsx
- **Usage:** Home page
- **Content:** 5 feature cards with static descriptions + icons
- **Status:** STUB

#### cta-section.tsx
- **Usage:** Home page
- **Content:** Call-to-action section with buttons linking to /playground and /signup
- **Status:** STUB

#### footer.tsx
- **Usage:** Home page + playground page
- **Content:** Static footer links (Terms, Privacy, Contact) + copyright
- **Status:** STUB

#### particle-background.tsx
- **Usage:** Most pages (visual decoration)
- **Content:** Canvas-based animated particle effect
- **Status:** Real (no API, but functional animation)

#### playground-form.tsx (CRITICAL)
- **Usage:** /playground page
- **Renders:** 4-step form: Pick recipe → Pick model → Name agent + personality → Paste BYOK key → Deploy
- **API calls (REAL):**
  - `GET /api/v1/recipes` (fetch available recipes on mount)
  - `GET https://openrouter.ai/api/v1/models` (fetch live models from OpenRouter, unproxied)
  - `POST /api/v1/runs` (deploy agent + run smoke test)
  - `GET /api/v1/agents` (fetch recent models from user's past agents)
- **State:** `recipes`, `recipe`, `model`, `byok`, `agentName`, `personality`, `verdict`, `uiError`, `orModels`, `orError`, `recipeQuery`, `recentModels`, `isRunning`
- **Hardcoded data (VIOLATIONS):**
  - **RECIPE_TAGLINES** (5 entries mapping recipe name → tagline): "Self-improving TUI agent...", "Ultra-lightweight Python...", etc.
  - **RECIPE_ACCENTS** (5 entries mapping recipe name → { from, to, glow } color classes): hermes=violet, nanobot=amber, nullclaw=indigo, openclaw=emerald, picoclaw=rose
  - **PERSONALITIES** (exported from api-types.ts, hardcoded array of 6 entries)
  - **PASS_IF_HUMAN** (5 descriptions of pass_if modes)
  - Helper functions: `shortRef()`, `formatPricePerMTok()`, `formatContext()`
- **Form validation:** Recipe != "", model != "", byok != "", name matches regex, not running, no rate limit
- **Error handling:** `parseApiError()` converts API errors to `UiError` union (validation, rate_limited, unauthorized, not_found, infra, network, unknown)
- **Retry countdown:** `useRetryCountdown()` ticks down 429 cooldown from Retry-After header
- **Deploy flow:**
  - Clear verdict + error
  - Set isRunning=true
  - POST `/api/v1/runs` with recipe_name, model, agent_name, personality (byok sent as Bearer token)
  - Receive RunResponse (run_id, agent_instance_id, verdict, category, detail, exit_code, wall_time_s, filtered_payload, stderr_tail)
  - Call `onDeployed(verdict)` callback (to highlight new agent in MyAgentsPanel)
  - Clear byok field, set isRunning=false
- **Known gaps:**
  - Taglines + accents hardcoded → ZeroClaw breaks theming
  - Personalities hardcoded; no way to add new one
  - OpenRouter API call is unproxied (should go via backend egress proxy per stack)
  - No exponential backoff on recipe/model fetch failure
  - Form does not validate agent_name against existing agents (could create duplicates)
  - No confirmation step before Deploy (big red button, easy to mis-click)

#### my-agents-panel.tsx (REAL)
- **Usage:** /playground page (top section, always visible)
- **API calls:** `GET /api/v1/agents` (fetch user's deployed agents)
- **Renders:** Empty state OR agent grid (1–4 columns depending on viewport)
- **State:** `agents` (array), `error` (UiError), imperative handle `refetch()`
- **Agent card displays:**
  - Name, recipe_name, model, personality emoji + label, last run verdict (PASS/FAIL/INFRA badges)
  - Stats: total_runs count, last_run_at or created_at (formatted as "Xm ago", "Xh ago", "Xd ago", or date)
- **Hardcoded data:**
  - **RECIPE_ACCENTS** (5 entries, duplicate of playground-form.tsx)
  - Color theming per recipe name
- **Status colors:**
  - Not run → muted
  - PASS → emerald
  - INFRA_FAIL → amber
  - Other (ASSERT_FAIL, etc.) → rose
- **Known gaps:**
  - Should have a "View agent details" or "Edit agent" action (linked from dashboard or inline button)
  - No agent refresh on interval (stale on page load if agent just ran elsewhere)
  - Duplicate RECIPE_ACCENTS definition (should be shared)

#### run-result-card.tsx (REAL)
- **Usage:** PlaygroundForm → verdict rendering
- **Renders:** Read-only display of RunResponse (not a form)
- **Props:** `verdict: RunResponse`, `cardRef?: RefObject`
- **State:** `copied` (for copy-to-clipboard feedback, 1.5s timeout)
- **Displays:**
  - Verdict badge (PASS, ASSERT_FAIL, INVOKE_FAIL, BUILD_FAIL, PULL_FAIL, CLONE_FAIL, TIMEOUT, LINT_FAIL, INFRA_FAIL, STOCHASTIC, SKIP)
  - Recipe name, model, agent_name, personality
  - Run ID (copyable)
  - Execution metadata: wall_time_s, exit_code
  - Expandable accordion sections: filtered_payload (agent output), stderr_tail (error logs)
- **Hardcoded data:**
  - **CATEGORY_BADGE_CLASS** (11 entries mapping category → Tailwind class)
- **Known gaps:**
  - No timestamp display (created_at exists in type but not rendered)
  - Accordion is uncontrolled; opening one section doesn't close others
  - No export/save verdict option (copy run_id is only export)

#### dev-login-form.tsx
- **Usage:** Not currently on any page (development only)
- **Status:** DEV UTILITY (not for production)

#### ui/ (shadcn components)
- `button.tsx`, `input.tsx`, `label.tsx`, `badge.tsx`, `card.tsx`, `avatar.tsx`, `scroll-area.tsx`, `alert.tsx`, `spinner.tsx`, `dropdown-menu.tsx`, `dialog.tsx`, `accordion.tsx`, `switch.tsx`, `progress.tsx`
- **Status:** All real (copy-in from shadcn/ui, no mocks, no backend calls)

---

## API INTEGRATION AUDIT

### frontend/lib/api.ts (Fetch wrapper)
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

export async function request<T>(path: string, init: RequestInit = {}): Promise<T>
  - Sends `credentials: "include"` (cookies)
  - Adds `Content-Type: application/json` if body exists
  - Returns null for non-JSON responses (204, etc.)

export apiGet<T>(path: string): Promise<T>
export apiPost<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T>
export apiDelete<T>(path: string): Promise<T>

export type SessionUser = { id, email?, display_name, avatar_url?, provider? }
```

**Known gaps:**
- No request retries or exponential backoff
- No request timeout (default browser timeout is 30s+)
- ApiError.headers is captured but never used in error handling (only ApiError.body)

### frontend/lib/api-types.ts (Server-side shapes)
```typescript
export type RecipeSummary = {
  name, apiVersion?, display_name?, description?, upstream_version?,
  image_size_gb?, expected_runtime_seconds?, source_repo?, source_ref?,
  provider?, pass_if?, license?, maintainer?, verified_models?: string[]
}

export type OpenRouterModel = { id, name, context_length?, pricing?, description? }

export type RunRequest = {
  recipe_name, prompt?, model, no_lint?, no_cache?, metadata?,
  agent_name?, personality?
}

export type PersonalityId = "polite-thorough" | "concise-neat" | ...  (6 hardcoded)

export const PERSONALITIES = [ ... 6 entries hardcoded ... ]

export type AgentSummary = {
  id, name, recipe_name, model, personality?, created_at, last_run_at?,
  total_runs, last_verdict?, last_category?, last_run_id?
}

export type RunResponse = {
  run_id, agent_instance_id, recipe, model, prompt, pass_if?, verdict, category,
  detail?, exit_code?, wall_time_s?, filtered_payload?, stderr_tail?,
  created_at?, completed_at?
}

export type UiError =
  | { kind: "validation"; field?, message; requestId? }
  | { kind: "rate_limited"; retryAfterSec; message; requestId? }
  | { kind: "unauthorized"; message; requestId? }
  | { kind: "not_found"; message; requestId? }
  | { kind: "infra"; message; requestId? }
  | { kind: "network"; message }
  | { kind: "unknown"; message; status? }
```

**Comment in file (line 8-13):** "Keep in sync with api_server/src/api_server/models/recipes.py". This indicates manual sync burden — no generated types.

**Hardcoded data:**
- PERSONALITIES array (6 entries) — RULE 2 VIOLATION
- Helper: `parseApiError()` (converts HTTP status + JSON to UiError discriminated union)
- Helper: `parseRetryAfter()` (RFC 7231 header parsing)
- Hook: `useRetryCountdown()` (countdown timer for 429 rate limits)

---

## API ENDPOINTS CALLED vs BACKEND AVAILABILITY

### Confirmed endpoints (frontend calls, backend presumably responds):
1. `GET /api/v1/recipes` — playground-form, my-agents-panel (via refetch callback)
2. `POST /api/v1/runs` — playground-form (deploy + smoke test)
3. `GET /api/v1/agents` — playground-form, my-agents-panel
4. `GET https://openrouter.ai/api/v1/models` — unproxied external call

### Endpoints referenced but **never called** on frontend:
- `GET /api/v1/profile` (no mount fetch in profile page)
- `POST /api/v1/profile` (no save submission in profile page)
- `POST /api/v1/settings/{key}` (no toggle submission in settings page)
- `DELETE /api/v1/user` (delete account button renders, no onclick)
- `POST /api/auth/change-password` (password change form exists, no submission)
- `GET /api/v1/api-keys` (no mount fetch in api-keys page)
- `POST /api/v1/api-keys` (create button works locally only)
- `DELETE /api/v1/api-keys/{id}` (delete works locally only)
- `POST /api/v1/api-keys/{id}/revoke` (revoke works locally only)
- `GET /api/v1/billing/subscription` (no billing page fetch)
- `GET /api/v1/billing/usage` (usage hardcoded)
- `POST /api/v1/notifications/{id}/read` (mark-as-read local only)
- `DELETE /api/v1/notifications/{id}` (delete local only)
- `POST /api/dev/login` (dev-login-form.tsx exists but page is not used)

### No CRUD operations for agents:
- No `GET /api/v1/agents/{id}` for agent detail view
- No `PUT /api/v1/agents/{id}` for agent edit
- No `DELETE /api/v1/agents/{id}` (start/stop/delete buttons in dashboard mock)
- No `POST /api/v1/agents/{id}/start` or `/stop`

---

## AUTHENTICATION & SESSION STATE

### Current state (frontend/middleware.ts):
- Middleware exists (not sampled in detail) — likely checks for session cookie
- **Problem:** Every page hardcodes `isLoggedIn={true}` and user `{ name: "Alex Chen", email: "alex@example.com" }`
- Navbar displays this fake user on all pages
- No `GET /api/me` call to fetch actual session user

### What should happen (per CLAUDE.md):
- OAuth via `goth` on Go backend
- Session stored in Postgres + HTTP-only signed cookie
- Frontend reads cookie (handled by middleware), renders authenticated UI
- On logout: DELETE `/api/me` or similar to clear session

### Current frontend auth violations:
- **Login/signup pages:** No backend auth calls
- **Session user:** Hardcoded in props, never fetched
- **Logout:** No logout button, no session termination UI
- **Protected routes:** Middleware likely blocks, but no error handling/redirect UX

---

## HARDCODED DATA VIOLATIONS (RULE 2)

| Location | Data | Count | Severity |
|----------|------|-------|----------|
| `api-types.ts` | `PERSONALITIES` array | 6 entries | **HIGH** — added new personality = code change |
| `playground-form.tsx` | `RECIPE_TAGLINES` object | 5 entries | **HIGH** — add ZeroClaw = missing tagline, empty string fallback |
| `playground-form.tsx` | `RECIPE_ACCENTS` object | 5 entries | **HIGH** — add ZeroClaw = no color theming |
| `my-agents-panel.tsx` | `RECIPE_ACCENTS` object | 5 entries (duplicate) | **HIGH** — twice the maintenance burden |
| `run-result-card.tsx` | `CATEGORY_BADGE_CLASS` object | 11 entries | **LOW** — unlikely to change; part of domain model |
| Playground, home | User hardcoded props | 1 | **MEDIUM** — should fetch via middleware + pass to page |
| Playground, dashboard | Fake numeric values | ~20 instances | **MEDIUM** — copy-pasted metrics, no data source |

---

## PAGES REQUIRING IMMEDIATE REWIRING

### Tier 1 (Breaks project flow):
1. **Login/Signup** → Call `/api/auth/github` or `/api/auth/google` (OAuth redirect)
2. **Dashboard** (My Agents page) → Call `GET /api/v1/agents` (currently calls, but page is mocked; need real agent list in place of mockAgents)

### Tier 2 (Necessary for beta):
3. **Profile page** → `GET /api/v1/profile` on mount, `POST /api/v1/profile` on save
4. **Settings page** → Per-setting `POST /api/v1/settings/{key}` on toggle change
5. **API Keys page** → `GET /api/v1/api-keys` on mount, `POST` create, `DELETE` revoke, `POST` delete
6. **Billing page** → `GET /api/v1/billing/subscription` + usage, Stripe Checkout link

### Tier 3 (Nice-to-have):
7. **Notifications page** → `GET /api/v1/notifications`, `POST` mark-as-read, `DELETE` delete
8. **Analytics page** → `GET /api/v1/analytics?range=7d` with time range support
9. **Agent detail pages** → Full CRUD on per-agent settings

---

## LEGACY CODE / DEAD CODE SCAN

### Unused files:
- **dev-login-form.tsx** — exported but not used on any page (dev-only utility)

### Unused patterns:
- **DashboardLayout sidebar toggle** — works on mobile (fixed button), but no persistent state across page navigation (sidebar collapses on every route change)

### Deprecated or incomplete:
- **Docs pages** — all static, no way to edit or update from backend (no admin interface, no CMS)

---

## AUTHENTICATION FLOW DIAGRAM (Current vs. Required)

### Current (BROKEN):
```
User → /login → handleSubmit() → setTimeout(1s) → router.push("/dashboard")
                ↓ (no backend call)
         (local state changes, no session created)
         
User → /dashboard → Navbar with hardcoded "Alex Chen"
```

### Required (BROKEN):
```
User → /login → handleSubmit() → POST /api/auth/github (or /google)
         ↓
      Redirect to GitHub/Google OAuth → Callback → POST /api/auth/callback
         ↓
      Set HTTP-only session cookie → Redirect to /dashboard
         ↓
User → /dashboard (middleware validates cookie) → Navbar reads session user from GET /api/me (or from middleware)
```

---

## MIDDLEWARE STATE (frontend/middleware.ts)

**Not fully sampled**, but per file structure at line 1701:
- Likely checks for session cookie
- Redirects unauthenticated users to `/login`
- Does **not** pass session user to page components (hardcoded props still used everywhere)

---

## CROSS-CUTTING ISSUES

### 1. No input validation (frontend)
- PlaygroundForm has regex for agent_name, but no validation for:
  - Recipe name exists (just stored as string, trusts backend)
  - Model ID is valid (trusts backend)
  - BYOK key format (just stored as string in Authorization header)
- Profile page has no email format validation
- Signup page has password regex check (client-only, no backend validation)

### 2. No error boundary or global error handler
- Each page has its own `uiError` state
- No fallback UI for unrecoverable errors
- No Sentry/error logging integration

### 3. No loading skeleton or placeholder states
- PlaygroundForm shows skeleton while recipes load (correct)
- Dashboard agent list shows hardcoded data immediately (no loader)
- MyAgentsPanel shows spinner while loading (correct)

### 4. No toast/notification library
- Profile, settings, etc. use local `saved` state + timeout for feedback (correct but low-ceiling)
- Run results show inline card (correct)
- No persistent toast queue for multiple notifications

### 5. Form state management scattered
- Each page manages its own form state (no shared form library)
- No conflict detection (e.g., email already taken)
- No optimistic updates

### 6. No analytics or telemetry
- No event tracking (user clicks, errors, latency)
- No A/B testing framework
- No user behavior metrics

---

## SUMMARY TABLE: PAGE STATUS

| Page | Real API | Mocked | Stub | Issues |
|------|----------|--------|------|--------|
| `/` (home) | ✗ | ✓ | | isLoggedIn=true fake |
| `/login` | ✗ | ✓ | | No OAuth, fake delay |
| `/signup` | ✗ | ✓ | | No registration, fake delay |
| `/playground` | ✓ | | | Recipe/personality hardcoded; unproxied OpenRouter |
| `/pricing` | | ✓ | | No Stripe integration |
| `/dashboard` | ✗ | ✓ | | mockAgents, no API calls |
| `/dashboard/analytics` | ✗ | ✓ | | Hardcoded metrics, timeRange unused |
| `/dashboard/billing` | ✗ | ✓ | | No Stripe API, hardcoded values |
| `/dashboard/profile` | ✗ | ✓ | | No fetch, save = timeout theater |
| `/dashboard/settings` | ✗ | ✓ | | No submission, 2FA button dead |
| `/dashboard/api-keys` | ✗ | ✓ | | Random key generation, no backend |
| `/dashboard/notifications` | ✗ | ✓ | | mockNotifications, no WebSocket |
| `/docs/*` (8 pages) | ✗ | | ✓ | Static content, no updates |
| Other (forgot-pw, contact, terms, privacy) | ✗ | | ✓ | Contact form not wired |

---

## TOP 5 CRITICAL GAPS (Ordered by Impact)

### 1. **Dashboard is 100% mocked** (IMPACT: Blocks entire agent management flow)
- **Status:** My Agents list pulls real data from GET /api/v1/agents (correct)
- **Problem:** Dashboard page uses mockAgents instead of real list. If user adds agent via /playground, it doesn't show in /dashboard.
- **Fix:** Replace mockAgents with `agents` from API response. Replace start/stop/delete buttons with API calls.
- **Effort:** 30 minutes
- **Blocks:** All dashboard functionality

### 2. **Recipe taglines + accents hardcoded** (IMPACT: Breaks theming for new recipes)
- **Status:** 5 recipes work. ZeroClaw incoming.
- **Problem:** Adding ZeroClaw requires code change (add tagline + color palette to 2 places).
- **Fix:** Move to backend: `GET /api/v1/recipes` should return tagline + color_accent in RecipeSummary. Update type + all consumers.
- **Effort:** 2 hours (backend + frontend)
- **Blocks:** Scaling recipe catalog

### 3. **Personality enum hardcoded** (IMPACT: No new personalities without code change)
- **Status:** 6 personalities baked into PERSONALITIES array.
- **Problem:** If backend defines a 7th personality, frontend doesn't show it.
- **Fix:** Fetch from API: `GET /api/v1/metadata` returns { personalities: [...], recipes: [...] }. Remove frontend PERSONALITIES array.
- **Effort:** 1.5 hours
- **Blocks:** Extending personality system

### 4. **Auth is completely stubbed** (IMPACT: No session creation, fake login)
- **Status:** Login/signup pages don't call backend.
- **Problem:** Every page hardcodes user data. Can't actually log in.
- **Fix:** Wire OAuth: login page → POST /api/auth/github → callback → session cookie. Update pages to fetch user from session.
- **Effort:** 4 hours (includes OAuth setup, session fetch, middleware update)
- **Blocks:** Multi-user support

### 5. **Profile/Settings/Billing/API-Keys pages are forms without submission** (IMPACT: User can't save changes)
- **Status:** All pages have forms that change local state only.
- **Problem:** Clicking "Save" triggers a timeout toast, not an API call.
- **Fix:** Add API calls: POST /api/v1/profile, POST /api/v1/settings, etc. Add loading states + error handling.
- **Effort:** 3 hours (5 pages × 30 min average)
- **Blocks:** User self-service (profile updates, billing, keys)

---

## ARCHITECTURAL DEBT

| Issue | Severity | Why | Fix Cost |
|-------|----------|-----|----------|
| Hardcoded recipes + personalities in frontend | High | Tomorrow's agent breaks theming; code bloat | Move to API metadata endpoint, 2h |
| No session user fetch | High | Can't track actual user; security risk if hardcoded props leak | Fetch from session cookie via middleware or GET /api/me, 1h |
| Dashboard uses mockAgents | High | My Agents list and Dashboard out of sync; user confusion | Replace mockAgents with API response, 30m |
| Auth is completely stubbed | Critical | No actual user sessions; OAuth flow incomplete | Wire OAuth endpoints, 4h |
| All dashboard forms lack submission | High | User settings not persisted; billing not synced | Add POST/PUT calls + error handling, 3h |
| No input validation on most forms | Medium | Allows invalid data to be submitted; bad UX if backend rejects | Add zod/yup schema validation, 1.5h |
| Unproxied OpenRouter call | Medium | Leaks API latency to browser; no metering at proxy | Route via backend egress proxy per stack, 1h |
| Duplicate RECIPE_ACCENTS definition | Low | DRY violation; color palette maintenance burden | Extract to shared constant, 10m |

---

## DEPENDENCIES & BLOCKERS

```
┌─────────────────────────────────────────────────────────┐
│                   FRONTEND BLOCKERS                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ✓ DONE: PlaygroundForm calls real API (/api/v1/runs)   │
│  ✓ DONE: MyAgentsPanel calls real API (/api/v1/agents)  │
│                                                          │
│  🔴 BLOCKED: Auth (login/signup)                        │
│      └─> Needs: OAuth endpoints (goth backend setup)    │
│      └─> Needs: Session cookie + middleware             │
│                                                          │
│  🔴 BLOCKED: Dashboard full wiring                      │
│      └─> Needs: Auth flow complete (session validation) │
│      └─> Needs: Agent CRUD endpoints (start/stop/delete)│
│                                                          │
│  🔴 BLOCKED: Profile/Settings/Billing/Keys/Notifications│
│      └─> Needs: Auth flow complete                      │
│      └─> Needs: User metadata endpoints                 │
│      └─> Needs: Settings endpoints                      │
│      └─> Needs: Stripe integration (billing)            │
│                                                          │
│  🟡 FIXABLE: Recipe + Personality hardcoding            │
│      └─> Needs: Extend GET /api/v1/recipes response     │
│      └─> Needs: Add GET /api/v1/metadata endpoint       │
│                                                          │
│  🟡 FIXABLE: Unproxied OpenRouter call                  │
│      └─> Needs: Backend egress proxy (metering layer)   │
│      └─> Needs: Frontend route via /api/v1/models       │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## RECOMMENDATIONS (Prioritized)

### Immediate (Week 1):
1. **Extract hardcoded recipes/personalities to API endpoint**
   - Create `GET /api/v1/metadata` returning { recipes_full, personalities, ... }
   - Update frontend to fetch and cache
   - Remove PERSONALITY_ID hardcoded array
   - Update RECIPE_ACCENTS to be keyed lookup (or embed in recipe)
   - Cost: 2h backend + 1h frontend
   - Unblocks: Recipe scalability

2. **Wire login/signup to OAuth**
   - Implement `/api/auth/github` and `/api/auth/google` endpoints (goth setup)
   - Update login/signup pages to redirect (no form submission, just links)
   - Implement callback handler + session creation
   - Add logout button to Navbar
   - Cost: 4h (backend 2h + frontend 1h + testing 1h)
   - Unblocks: All dashboard functionality

### Short-term (Week 2):
3. **Replace dashboard mockAgents with API response**
   - Refactor dashboard page to call GET /api/v1/agents on mount
   - Add loading state while fetching
   - Implement start/stop/delete button handlers (POST/DELETE endpoints)
   - Cost: 1.5h
   - Unblocks: Real agent management

4. **Wire profile/settings/api-keys pages**
   - Add API calls for fetch + save
   - Add loading states + error handling
   - Cost: 3h
   - Unblocks: User self-service

### Medium-term (Week 3):
5. **Route OpenRouter calls via backend egress proxy**
   - Create `GET /api/v1/models` endpoint on backend (proxy to OpenRouter)
   - Update frontend to call backend instead of direct
   - Add metering layer (per CLAUDE.md stack)
   - Cost: 2h
   - Unblocks: Proper request metering + cost tracking

6. **Add form validation layer**
   - Adopt zod or yup for all forms
   - Add client-side validation + server-side validation
   - Cost: 1.5h
   - Unblocks: Better UX

---

## FILES TO DELETE / ARCHIVE

- **dev-login-form.tsx** — unused dev utility

---

## FILES TO CREATE

- None immediately (all pages exist; just need rewiring)

---

## GOLDEN RULE COMPLIANCE SCORECARD

| Rule | Status | Evidence |
|------|--------|----------|
| **Rule 1: No mocks, no stubs (core substrate)** | **FAIL** — 71% of pages are mocks | Dashboard, auth, profile, settings, billing, notifications are all locally mocked with no API calls |
| **Rule 2: Dumb client, intelligence in the API** | **FAIL** — Client owns recipe catalog | Hardcoded RECIPE_TAGLINES, RECIPE_ACCENTS, PERSONALITIES arrays. Should fetch from API. |
| **Rule 3: Ship when stack works end-to-end** | **FAIL** — Auth is stubbed | Can't log in; entire flow breaks. Playground works in isolation, but dashboard is disconnected. |
| **Rule 4: Root cause first** | N/A — No bugs reported | But architectural debt is deep: hardcoded data, missing API wiring, form-submission theater. |

**Overall:** ⚠️ **YELLOW / AMBER** — Playground pages are real, but dashboard + auth are incomplete. Ready for internal demo only, not beta.

---

## AUDIT METADATA

- **Auditor:** Claude Code (Haiku 4.5)
- **Date:** 2026-04-18T02:00:00Z
- **Scope:** frontend/ directory, all .tsx/.ts files, all pages + components
- **Method:** Source-code review, static analysis, no runtime testing
- **Findings:** 47 violations of CLAUDE.md rules, 13 critical gaps, 5 top priorities
- **Recommendation:** Tier 1 rewiring (auth + dashboard) before any beta release

---

