# Phase 20: Frontend Alicerce — Research

**Researched:** 2026-04-17
**Domain:** Next.js 16.2 / React 19.2 client component — form-driven, dumb-client, API-round-tripping single page
**Confidence:** HIGH

## Summary

Phase 20 is a **single-page client-component rewrite** with 14 locked decisions. Almost every technical question in `<research_focus>` is narrow and concrete. The research answers fall into three buckets:

1. **Extend `frontend/lib/api.ts` minimally** — add a third `headers?` param to `apiPost` (and optionally a typed `request<T>` export) so the BYOK `Authorization: Bearer <key>` path is a single-line addition. The `ApiError` class already swallows response bodies but **does not expose headers**; for 429 `Retry-After` parsing we must capture them. A two-field extension to `ApiError` (`headers: Headers`) is the smallest change.

2. **Plain client `useState` + `fetch` — NOT `useActionState`/Server Actions.** React 19 Server Actions are server-resident by definition; the BYOK key must never touch the server-rendered tree, and the whole form exists to round-trip to a Python FastAPI server via a Next.js rewrite. `useActionState` works with client-only async functions too, and `isPending` is free — but for this phase the idiomatic choice is `useState` for data + `useTransition` for pending state (or just a boolean), so the form reads top-to-bottom without the mental overhead of the action-payload dance. Sample skeleton below.

3. **Testing: defer Playwright to a follow-up phase; ship Phase 20 without a frontend test runner.** Phase 20 has ZERO existing test harness in `frontend/`. The lowest-ceremony path is a single manual SC-11 smoke pass (already mandated as the Hetzner-deploy gate). Adding Playwright is 3–4 tasks of pure testing scaffolding — right magnitude for its own follow-up phase, wrong fit inside the "unblock Hetzner deploy" minimum-change-set.

**Primary recommendation:** Extend `apiPost` with `headers?: HeadersInit`, extend `ApiError` with `headers: Headers`. Use plain `useState` + `fetch` inside a client component. Render errors through a `parseApiError(err)` discriminated union. Defer automated frontend tests to Phase 20.1.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Scope cut — Playground only (minimal)**
- Rewrite only `frontend/app/playground/page.tsx` and its component subtree.
- Delete `frontend/components/agent-configurator.tsx` entirely (1001 lines of mock). Replace with a new `<PlaygroundForm>` + `<RunResultCard>` pair.
- Leave every other page in `frontend/app/` as-is.

**D-02: UI shape — conversational single-column**
- Single vertical flow: form at top → Deploy button → verdict card appears below.
- No tabs, no 3-column panels, no channel grid, no runtime/sandbox/A2A sub-tabs.
- Keep `<Navbar>`, `<Footer>`, `<ParticleBackground>` as visual chrome.

**D-03: Recipe picker — native HTML `<select>` populated from `GET /v1/recipes`**
- Fetched on component mount via `apiGet<{recipes: RecipeSummary[]}>("/api/v1/recipes")`.
- `<select>` options rendered from the response; value = `recipe.name`.
- Loading state: `<select>` disabled with placeholder "Loading recipes…".
- Empty state: inline error + retry button.

**D-04: Model input — free-text**
- Plain `<input type="text" placeholder="e.g., openai/gpt-4o-mini">`.
- **No client-side model catalog.** No curated dropdown. No hardcoded pricing.
- Helper link to OpenRouter model catalog.
- Validation: non-empty string only.

**D-05: BYOK key — per-run form field**
- `<input type="password">`, autofill disabled, no localStorage, no persistence.
- Sent as `Authorization: Bearer <key>` on `POST /v1/runs`. Never logged.

**D-06: Run feedback — structured verdict card**
- Colored verdict badge (PASS green / FAIL red / INFRA_FAIL orange), category pill, exit_code, wall_time_s, run_id (copyable), collapsible stderr tail.
- Renders from `POST /v1/runs` response JSON. One card per most-recent run.

**D-07: Error handling — surface, never swallow** (6 paths; see full table in CONTEXT)

**D-08: Deploy button lifecycle** (disabled gates + spinner)

**D-09: Empty / loading / initial states** (form with recipes loading, then in-flight skeleton)

**D-10: Mock remnants — delete** (no stubs, no "coming soon"; delete completely)

**D-11: Keep v0 chrome** (Navbar/Footer/ParticleBackground stay)

**D-12: Networking path** — reuse `frontend/next.config.mjs` rewrite + `frontend/lib/api.ts`. Add thin wrapper for `Authorization: Bearer` header support.

**D-13: Types** — mirror API response shapes in new `frontend/lib/api-types.ts` (RecipeSummary, RunResponse, ErrorResponse). **No codegen from `/openapi.json` in Phase 20.**

**D-14: No testing framework in Phase 20 (flag for decision)** — planner decides: defer vs Playwright vs Vitest.

### Claude's Discretion

- Whether to clear BYOK state after submit or keep it for re-deploy (D-05 leaves to planner).
- Exact shape of the `apiPost` extension (third param vs separate `apiPostWithAuth` variant).
- Which UI primitive to use for loading skeleton / spinner.
- D-14 testing decision: defer (recommended), Playwright, or Vitest.
- SC-05 "React DevTools-visible state after submit" — up to planner's discretion how strictly to enforce.

### Deferred Ideas (OUT OF SCOPE)

- Auth, login, dashboard, billing, profile, settings pages
- A2A network / Tasks / Monitor tabs (Phase 22+)
- Channel picker (Telegram, Discord, Slack — Phase 23+)
- Persistent Memory, Scheduling, Max Tokens, Sandbox picker toggles
- SSE / streaming verdicts (Phase 21)
- Multi-agent tabs, agent instances list
- Marketing pages (pricing, docs, contact, terms, privacy)
- Settings page for BYOK persistence (Phase 20.2)
- Run history list / `GET /v1/runs` (no such endpoint yet)
- Mobile optimization — desktop-first is acceptable; Phase 20.1
- TypeScript client generation (Phase 19 SC-13)
</user_constraints>

## Project Constraints (from CLAUDE.md)

The 4 Golden Rules at the top of CLAUDE.md are **non-negotiable invariants** for this phase:

1. **No mocks, no stubs.** Tests hit real infra — no client-side catalogs, no fake state. [VERIFIED: CLAUDE.md §Golden rules]
2. **Dumb client, intelligence in the API.** The frontend fetches lists; no hardcoded `defaultClones`/model arrays. This phase exists BECAUSE rule #2 was violated in Phase 19. [VERIFIED: CLAUDE.md §Golden rules + feedback_dumb_client_no_mocks.md]
3. **Ship when the stack works locally end-to-end.** Never deploy until a real user workflow (click → see verdict, persisted row) completes against the Docker topology. Phase 20's SC-11 is literally this gate. [VERIFIED: CLAUDE.md §Golden rules]
4. **Root cause first, never fix-to-pass.** Investigate before removing code. [VERIFIED: CLAUDE.md §Golden rules]

Additional project-specific rules:
- **Dev workflow:** all work must start through a GSD command (`/gsd-quick`, `/gsd-debug`, `/gsd-execute-phase`). [VERIFIED: CLAUDE.md §GSD Workflow Enforcement]
- **User's global rules:** don't create summary/report markdown unless explicitly asked; don't commit without explicit ask; always kill previous processes before starting new ones. [VERIFIED: user's global ~/.claude/CLAUDE.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Recipe catalog source of truth | API (FastAPI `/v1/recipes`) | — | Golden rule #2 — no client-side catalog |
| Model string validation | API (runner rejects unknown) | Browser (empty-string check only) | Client never knows which models exist; server is authoritative |
| BYOK key collection | Browser (`<input type=password>`) | — | Typed into form, sent on one request, never stored |
| BYOK key transport | Browser → FastAPI (`Authorization: Bearer`) | — | Phase 19 D-02 contract; Phase 19 already redacts on both sides |
| Run verdict rendering | Browser (stateless render from POST response) | — | Dumb display; server computes everything |
| Retry-After countdown | Browser (`useEffect` timer) | API (issues 429 + header) | Pure UI state on top of a server instruction |
| Error classification | Browser (`parseApiError`) | API (Stripe-shape envelope) | Server labels; client switches on label |
| Form state | Browser (`useState`) | — | Local to component; not persisted |
| Request routing | Browser → Next.js rewrite → FastAPI | — | `frontend/next.config.mjs` rewrite already proxies `/api/v1/*` → `:8000/v1/*` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `next` | 16.2.0 | Framework (App Router + Turbopack) | Already pinned in `frontend/package.json` [VERIFIED: frontend/package.json:49] |
| `react` | ^19 (19.2.x resolved) | UI runtime | Already pinned; bundled with Next 16 [VERIFIED: frontend/package.json:51] |
| `react-dom` | ^19 | DOM renderer | Paired with react [VERIFIED: frontend/package.json:53] |
| `typescript` | 5.7.3 | Type safety | Already pinned [VERIFIED: frontend/package.json:70] |
| `tailwindcss` | ^4.2.0 | Styling | Already pinned [VERIFIED: frontend/package.json:68] |
| `@radix-ui/react-*` | various (2.x / 1.x) | Primitive UI components under shadcn wrappers | Already pinned and rendered in `frontend/components/ui/` [VERIFIED: frontend/package.json:14-40] |
| `lucide-react` | ^0.564.0 | Icon set (Loader2Icon, CheckIcon, etc.) | Already pinned [VERIFIED: frontend/package.json:48] |

### Supporting (already installed, use directly)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `sonner` | ^1.7.1 | Toast notifications | Optional — can surface rate-limit / network-error toasts if inline text is insufficient. Has a shadcn wrapper at `components/ui/sonner.tsx` [VERIFIED: frontend/package.json:57] |
| `class-variance-authority` + `clsx` + `tailwind-merge` | 0.7.x / 2.1.x / 3.3.x | `cn()` utility + variant props | Used by every shadcn primitive [VERIFIED: frontend/lib/utils.ts (referenced by all ui/*.tsx)] |

### NOT Needed (Phase 20 scope)
| Don't Install | Why |
|---------------|-----|
| `@tanstack/react-query` / `swr` | Two requests total (`GET /v1/recipes` on mount, `POST /v1/runs` on click). Raw `fetch` in `useEffect` is simpler than bringing in a cache layer for two calls. |
| `zod` (runtime already pinned) | Client-side catalog validation is out of scope; API is authoritative. If a shape check helps for a future type guard, `zod` is already in `package.json` — but Phase 20 does not need it for the two response shapes. |
| `react-hook-form` (already pinned) | Four fields, no multi-step, no field-array. `useState` per field is less machinery. |
| `@playwright/test` / `vitest` / `@testing-library/react` | See §Testing Decision below — defer to Phase 20.1. |
| `openapi-typescript` / client-codegen | D-13 explicitly rules this out for Phase 20 (orthogonal Phase 19 SC-13). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| native `<select>` (D-03) | shadcn `<Select>` | See detailed Q6 below — native wins on dumb-client discipline |
| plain `useState` + `fetch` | React 19 `useActionState` | See Q2 — `useActionState` adds indirection without payoff for this shape |
| plain `useState` + `fetch` | `@tanstack/react-query` mutation | Overkill for two endpoints; adds ~50KB + a QueryClient provider for zero reuse |
| `fetch` directly | `axios` | `axios` is not installed; `fetch` + existing `api.ts` wrapper is idiomatic for this codebase |
| inline error divs | `sonner` toasts | CONTEXT D-07 specifies per-error-path inline renders; toasts can be added later |

**Installation:** NONE. Every dependency Phase 20 needs is already in `frontend/package.json`. [VERIFIED: frontend/package.json lines 11-71]

**Version verification:** Not applicable — no new installs. If planner chooses Playwright per D-14, that would add `@playwright/test` (latest stable 1.50+ as of 2026).

## Architecture Patterns

### System Architecture Diagram

```
┌──────────── Browser ────────────┐        ┌──── Next.js rewrite ────┐        ┌────── FastAPI ──────┐
│ /playground                     │        │ next.config.mjs         │        │ api_server :8000    │
│                                 │        │                         │        │                     │
│ <PlaygroundForm>                │        │ /api/v1/recipes         │        │ GET /v1/recipes     │
│  └─ useEffect on mount          │───────▶│  → :8000/v1/recipes     │───────▶│  (reads app.state   │
│     fetch GET /api/v1/recipes   │        │                         │        │   .recipes dict)    │
│     → setState(recipes)         │◀───────│                         │◀───────│                     │
│                                 │        │                         │        │                     │
│  └─ onClick Deploy              │        │ /api/v1/runs            │        │ POST /v1/runs       │
│     fetch POST /api/v1/runs     │───────▶│  → :8000/v1/runs        │───────▶│  - parse Bearer     │
│     headers: Authorization      │        │                         │        │  - run_cell via     │
│     body: {recipe,model,prompt} │        │                         │        │    Pattern 2        │
│     → setState(verdict|error)   │◀───────│                         │◀───────│  - persist + return │
│                                 │        │                         │        │                     │
│ <RunResultCard verdict={...}/>  │        │                         │        │                     │
│                                 │        │                         │        │ Postgres (runs +    │
└─────────────────────────────────┘        └─────────────────────────┘        │  agent_instances)   │
                                                                              └─────────────────────┘
```

### Component Responsibilities

| File | Responsibility |
|------|----------------|
| `frontend/app/playground/page.tsx` | Route entry. Renders chrome (Navbar/Footer/ParticleBackground) + `<PlaygroundForm>`. No state. |
| `frontend/components/playground-form.tsx` (NEW) | Client component (`"use client"`). Owns recipe list, form fields, in-flight flag, error state, current verdict. All fetches live here. |
| `frontend/components/run-result-card.tsx` (NEW) | Pure display of a `RunResponse`. Receives verdict as prop. |
| `frontend/lib/api.ts` | Extended: third `headers?` param on `apiPost`; `ApiError` gains `headers: Headers`. |
| `frontend/lib/api-types.ts` (NEW) | `RecipeSummary`, `RunRequest`, `RunResponse`, `ErrorResponse` TS types + `UiError` discriminated union + `parseApiError(err)` helper. |

### Recommended File Layout

```
frontend/
├── app/playground/
│   └── page.tsx                    # Route — minimal; hosts PlaygroundForm
├── components/
│   ├── playground-form.tsx         # NEW — owns all state + network calls
│   ├── run-result-card.tsx         # NEW — pure display
│   └── agent-configurator.tsx      # DELETE (and its imports: agent-card, model-selector, a2a-network, task-orchestrator)
└── lib/
    ├── api.ts                      # EXTEND — headers param + ApiError.headers
    └── api-types.ts                # NEW — TS types + error helper
```

### Pattern 1: Extend `apiPost` with optional `headers` (RECOMMENDED)

**What:** Add a third optional `headers?: HeadersInit` parameter. Preserves call-site compatibility with the existing single caller (`dev-login-form.tsx` passes `apiPost("/api/dev/login")`).

**Signature:**
```typescript
// frontend/lib/api.ts (DIFF, not full file)
export class ApiError extends Error {
  status: number;
  body: string;
  headers: Headers;      // NEW — needed for Retry-After parsing

  constructor(status: number, body: string, headers: Headers, message?: string) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.headers = headers;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text, res.headers);   // NEW — pass headers
  }
  // ... unchanged
}

export function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  headers?: HeadersInit,        // NEW — third optional param
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    headers,
  });
}
```

**Call-site invocation (Phase 20):**
```typescript
const result = await apiPost<RunResponse>(
  "/api/v1/runs",
  { recipe_name, model, prompt },
  { Authorization: `Bearer ${byokKey}` },
);
```

**Back-compat:** `dev-login-form.tsx`'s existing call `apiPost("/api/dev/login")` keeps working — third param is optional. `ApiError` construction is internal to `request<T>`; no external code constructs `ApiError`. [VERIFIED: grep of frontend/ for `new ApiError` — only constructed inside api.ts request()]

**Why not `apiPostWithAuth` variant:** Two functions doing near-identical work invites drift. One function with a pass-through headers param is the idiomatic extension.

### Pattern 2: Plain `useState` + `fetch` form (RECOMMENDED over `useActionState`)

**What:** Conventional client-component pattern. Fields in `useState`; submit handler is `async onClick` that calls `apiPost`, sets result state, handles errors.

**Why not `useActionState`:** React 19's `useActionState` is valid in client components too (not only for server actions), but it fits best when:
- You want `<form action={submitAction}>` to handle progressive enhancement (form works without JS).
- You want `useFormStatus` to broadcast `isPending` to nested button components.

Neither matters here: the page is `"use client"` (JS is required; the whole app is client-driven), and the Deploy button lives in the same component as `isPending`. `useActionState`'s `(prevState, payload)` signature adds indirection without payoff. Plain `useState` is the idiomatic shape for this phase. [CITED: https://react.dev/reference/react/useActionState]

**Skeleton (15–20 lines of the core):**
```typescript
"use client";
import { useState, useEffect } from "react";
import { apiGet, apiPost, ApiError } from "@/lib/api";
import type { RecipeSummary, RunResponse } from "@/lib/api-types";
import { parseApiError, type UiError } from "@/lib/api-types";

export function PlaygroundForm() {
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [recipe, setRecipe] = useState("");
  const [model, setModel] = useState("");
  const [byok, setByok] = useState("");
  const [prompt, setPrompt] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [verdict, setVerdict] = useState<RunResponse | null>(null);
  const [uiError, setUiError] = useState<UiError | null>(null);

  useEffect(() => {
    apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes")
      .then((d) => setRecipes(d.recipes))
      .catch((e) => setUiError(parseApiError(e)));
  }, []);

  async function onDeploy() {
    setIsRunning(true); setUiError(null); setVerdict(null);
    try {
      const res = await apiPost<RunResponse>(
        "/api/v1/runs",
        { recipe_name: recipe, model, prompt },
        { Authorization: `Bearer ${byok}` },
      );
      setVerdict(res);
      // SC-05 stricter variant: clear the key from state now that we've sent it
      setByok("");
    } catch (e) {
      setUiError(parseApiError(e));
    } finally {
      setIsRunning(false);
    }
  }
  // ... JSX below
}
```

### Pattern 3: `parseApiError` discriminated union for D-07 error paths

**What:** One function converts `unknown` (thrown by `fetch`/`apiPost`) into a tagged shape the JSX can `switch` on.

```typescript
// frontend/lib/api-types.ts — the consumer-facing helper

export type ErrorResponse = {
  error: {
    type: string;
    code: string;
    category: string | null;
    message: string;
    param: string | null;
    request_id: string;
  };
};

export type UiError =
  | { kind: "validation"; field?: string; message: string; requestId?: string }  // 422
  | { kind: "rate_limited"; retryAfterSec: number; message: string; requestId?: string }  // 429
  | { kind: "unauthorized"; message: string; requestId?: string }  // 401/403
  | { kind: "infra"; message: string; requestId?: string }  // 502/500
  | { kind: "not_found"; message: string; requestId?: string } // 404 (e.g., unknown recipe)
  | { kind: "network"; message: string }  // TypeError (fetch failed)
  | { kind: "unknown"; message: string; status?: number };

export function parseApiError(err: unknown): UiError {
  // Network error (fetch throws TypeError on DNS/connection failure)
  if (err instanceof TypeError) {
    return { kind: "network", message: "Could not reach API — check your connection." };
  }
  if (!(err instanceof ApiError)) {
    return { kind: "unknown", message: err instanceof Error ? err.message : "Unknown error" };
  }

  // Try to parse Stripe envelope from body
  let envelope: ErrorResponse | null = null;
  try { envelope = JSON.parse(err.body) as ErrorResponse; } catch { /* non-JSON body */ }
  const msg = envelope?.error.message ?? err.body ?? `HTTP ${err.status}`;
  const requestId = envelope?.error.request_id;
  const param = envelope?.error.param ?? undefined;

  switch (err.status) {
    case 401: case 403:
      return { kind: "unauthorized", message: "Invalid or missing API key", requestId };
    case 404:
      return { kind: "not_found", message: msg, requestId };
    case 422:
      return { kind: "validation", field: param, message: msg, requestId };
    case 429: {
      const retryAfter = parseRetryAfter(err.headers.get("Retry-After"));
      return { kind: "rate_limited", retryAfterSec: retryAfter, message: msg, requestId };
    }
    case 500: case 502: case 503:
      return { kind: "infra", message: msg, requestId };
    default:
      return { kind: "unknown", message: msg, status: err.status };
  }
}

// Retry-After can be a delta-seconds integer OR an HTTP-date.
// MDN: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After
function parseRetryAfter(v: string | null): number {
  if (!v) return 5; // conservative default
  const asInt = Number.parseInt(v, 10);
  if (!Number.isNaN(asInt) && String(asInt) === v.trim()) return Math.max(0, asInt);
  const asDate = Date.parse(v);
  if (!Number.isNaN(asDate)) {
    const deltaMs = asDate - Date.now();
    return Math.max(0, Math.ceil(deltaMs / 1000));
  }
  return 5;
}
```

**Why this shape:** every JSX consumer becomes `switch (uiError.kind)` — type-narrowing gives compile-time exhaustiveness (TS 5.7 `never`-check pattern), no stringly-typed branches.

### Pattern 4: Retry-After countdown via `useEffect`

**What:** When a 429 fires, store a target timestamp; render "Retry in N s"; `useEffect` ticks every second; auto-clear on zero so Deploy re-enables.

```typescript
function useRetryCountdown(uiError: UiError | null, onExpire: () => void): number {
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    if (uiError?.kind !== "rate_limited") {
      setRemaining(0);
      return;
    }
    setRemaining(uiError.retryAfterSec);
    const t = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(t);
          onExpire();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(t);
  }, [uiError, onExpire]);
  return remaining;
}
```

**Pitfall:** `onExpire` must be stable (`useCallback`) or this will churn. Alternative: track a target timestamp in state and compute `remaining` as `Math.max(0, Math.ceil((target - now) / 1000))` on each tick — no dep on the callback. [CITED: MDN Retry-After header]

### Pattern 5: BYOK input hardening (D-05 + SC-05)

**What:** Minimum 4 practices to keep the key out of attack surfaces:

```typescript
<input
  type="password"
  value={byok}
  onChange={(e) => setByok(e.target.value)}
  autoComplete="new-password"   // modern browsers ignore "off" for credentials;
                                // "new-password" is the standard hint to not offer
                                // to remember/autofill. [CITED: MDN autocomplete guide]
  autoCorrect="off"
  autoCapitalize="off"
  spellCheck={false}
  aria-label="API key (sent as Authorization: Bearer, never stored)"
  placeholder="sk-or-v1-..."
/>
```

**Additional practices:**
1. **Clear state after successful POST** (`setByok("")`). Satisfies SC-05's "not visible in React DevTools after submit" strict reading. Deferred downside: user has to retype on second deploy — acceptable tradeoff per CONTEXT D-05 "cleared after submit (up to the planner)".
2. **Never log it.** No `console.log(byok)`. No `console.log({ body })` containing the header. No `console.error(err)` where `err` might close over the key (the fetch API doesn't leak request headers in its exception, but be explicit).
3. **Never persist to localStorage/sessionStorage.** D-05 explicit.
4. **No intermediate variables in closures visible from DevTools.** The request is built inline in `onDeploy`; the Authorization header is constructed at the call site and the string dies as soon as `apiPost` returns.

### Anti-Patterns to Avoid

- **Fetching recipes in a Server Component.** The form is client-driven (needs `useState` for form fields + BYOK). Making `/playground/page.tsx` a Server Component and passing recipes as props works in theory but splits ownership; keep one client component that owns all state. Marking `page.tsx` with `"use client"` is fine.
- **Storing BYOK in a `ref`.** Refs survive renders but React DevTools still inspects them. Plain state + clearing after submit is cleaner for SC-05.
- **Catching errors with a bare `catch (e) { console.log(e) }`.** Every error path must render (D-07). `catch` must `setUiError(parseApiError(e))`.
- **Hardcoding a default model string.** CONTEXT D-04 — free text, no curated defaults. A placeholder attribute (e.g., `placeholder="openai/gpt-4o-mini"`) is allowed; a `defaultValue` is not.
- **Persisting recipe selection across navigations.** Out of scope; recipe is local form state, refetched on mount.
- **Re-fetching recipes on every render.** `useEffect(() => ..., [])` with empty dep array. Consider re-fetch on manual retry (empty state).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Error envelope parsing | Ad-hoc `JSON.parse(body).error.message` scattered across JSX | Single `parseApiError(err)` → `UiError` discriminated union | Exhaustiveness check, single place to update when envelope shape changes |
| Retry-After parsing | `parseInt(header)` only | Full integer-or-HTTP-date parse (`parseRetryAfter` above) | RFC 7231 allows both; some proxies emit dates. MDN notes this explicitly. |
| Countdown clock | Two `setInterval`s + React state soup | Single `useEffect` with timer cleanup + derive `remaining` from a stored target timestamp | Survives tab backgrounding cleanly; avoids drift from setInterval inaccuracies |
| Recipe dropdown accessibility | Custom `<div role="combobox">` | Native `<select>` (D-03) | Zero a11y work — native `<select>` has keyboard nav, screen-reader support, touch support for free |
| Loading state | Custom spinner component | `Loader2Icon` from `lucide-react` with `className="animate-spin"` | Already used by `dev-login-form.tsx`; matches existing pattern |
| Verdict card accordion | Hand-rolled `<details>` + chevron | `Accordion` from `components/ui/accordion.tsx` | Already a shadcn primitive in repo; handles focus, ARIA, animation [VERIFIED: components/ui/accordion.tsx] |
| Toast notifications (if adopted) | Custom queue + positioning | `sonner` via `components/ui/sonner.tsx` | Already installed [VERIFIED: frontend/package.json:57] |
| Fetch abstraction | Fresh `fetch(...)` per call | Extended `apiGet`/`apiPost` from `lib/api.ts` | Already handles credentials, Content-Type, error throwing, body capture |

**Key insight:** Phase 20 is 90% assembly of components that already exist in the repo + two thin additions (`apiPost` headers, `parseApiError`). Anyone reaching for a new dependency should stop.

## Common Pitfalls

### Pitfall 1: `ApiError` currently drops response headers — 429 countdown can't work without extension
**What goes wrong:** `request<T>` in `api.ts` throws `new ApiError(res.status, text)` — the `Response.headers` object is never captured. Any attempt to read `Retry-After` downstream fails silently (returns undefined, defaults to 5s, UI feels broken).
**Why it happens:** The current `ApiError` was built for auth-flow callers that don't inspect headers.
**How to avoid:** Ship the `ApiError.headers: Headers` extension in the same task as any 429-handling code. Don't split them across tasks — it's one coupled change.
**Warning signs:** a pull request that adds 429 parsing but doesn't touch `api.ts` = broken.

### Pitfall 2: Turbopack HMR + module-level state can desync during dev
**What goes wrong:** If anyone refactors `parseApiError`'s helper tables into module-level mutable state (e.g., a cache keyed by request_id), Turbopack's Fast Refresh can leave stale references in-memory after an edit. Error UIs render with stale classifications.
**Why it happens:** Next 16 defaults to Turbopack; HMR preserves component state but module-level singletons can drift. [CITED: github.com/vercel/next.js/issues/85883 "Could not find the module in the React Client Manifest"]
**How to avoid:** Keep `parseApiError` and helpers pure functions. No module-level mutable state. If a cache is ever needed, put it in a React component's `useRef`.
**Warning signs:** After editing `api-types.ts`, previously-working error paths render wrong shape until a hard refresh.

### Pitfall 3: BYOK key leaking via `console.log(body)` or error-boundary stack trace
**What goes wrong:** A developer adds `console.log("sending run", { recipe, model, prompt, byok })` for debugging and forgets to remove it; the key appears in the browser console and in any error telemetry.
**Why it happens:** During debugging, wide-log patterns are the fastest diagnostic.
**How to avoid:** Make `byok` a local variable inside `onDeploy` — never part of any logged state. Build the Authorization header at the call site; never log the header object. Add an ESLint rule banning `console.*` in `playground-form.tsx` if paranoid.
**Warning signs:** `console.log` in a PR that touches form state; `{byok}` passed to any tracing library.

### Pitfall 4: `autoComplete="off"` doesn't work on password fields in modern browsers
**What goes wrong:** Developer writes `autoComplete="off"` expecting the browser to never offer autofill; Chrome/Safari ignore it and offer to save the "password" anyway. User says yes; the BYOK key lands in the browser password manager.
**Why it happens:** Browsers explicitly ignore `autoComplete="off"` on password inputs to support password managers. [CITED: MDN form autocompletion guide]
**How to avoid:** Use `autoComplete="new-password"` (the standard hint for "this is a fresh password, don't offer stored ones"). MDN still warns this is a hint, not a contract; 100% prevention is impossible. Acceptable trade-off for Phase 20 scope.
**Warning signs:** "autoComplete=off" in the input props.

### Pitfall 5: Fetching recipes on every mount causes visible flicker + wasted calls
**What goes wrong:** User navigates away and back to `/playground`; every mount re-fetches `/v1/recipes`; the `<select>` goes to disabled "Loading recipes…" for 50-500ms each time.
**Why it happens:** Empty dep array refetches per mount, not per URL change.
**How to avoid:** Acceptable for Phase 20 — recipes change rarely and the fetch is cheap (5 items). If annoying in practice, a module-level cache object (Pitfall 2 warning applies) or a follow-up phase adding React Query is the fix. Don't optimize yet.
**Warning signs:** User complaint about slow navigation to `/playground`.

### Pitfall 6: Verdict card showing stale data after a new Deploy
**What goes wrong:** User runs once, gets PASS, edits form, clicks Deploy, error fires; the old PASS card is still rendered.
**Why it happens:** Not clearing `verdict` before a new run.
**How to avoid:** At the top of `onDeploy`, `setVerdict(null); setUiError(null);`. In the JSX, render verdict OR error OR running skeleton OR nothing — four mutually exclusive states.
**Warning signs:** Tests (or manual SC-10) show stale result after error.

### Pitfall 7: Form submit via Enter key triggers form reload
**What goes wrong:** Wrapping fields in a `<form>` without `onSubmit={(e) => e.preventDefault()}` — pressing Enter in the model field does a full page reload.
**Why it happens:** Default HTML form behavior.
**How to avoid:** Either no `<form>` (just inputs + button with `onClick`), or `<form onSubmit={(e) => { e.preventDefault(); onDeploy(); }}>`. The second is better for keyboard UX and a11y (Enter in any field triggers Deploy).
**Warning signs:** Page reloads unexpectedly during testing.

### Pitfall 8: Running agent-configurator.tsx deletion without removing its imported-only peers
**What goes wrong:** `agent-configurator.tsx` imports `agent-card.tsx`, `model-selector.tsx`, `a2a-network.tsx`, `task-orchestrator.tsx`. Deleting only the parent leaves dead code in the repo and the `const defaultClones = ...` / `const openRouterModels = ...` catalogs that SC-07 explicitly grep-tests for.
**Why it happens:** Only the parent is referenced in `app/playground/page.tsx`.
**How to avoid:** Delete the full tree. Verify with `grep -r "defaultClones\|openRouterModels" frontend/` → 0 matches before claiming SC-07.
**Warning signs:** SC-07 grep finds survivors post-delete. [VERIFIED: frontend/components/agent-configurator.tsx head import lines 6-10]

## Code Examples

### Example 1: `apiPost` with Authorization header (recommended)
```typescript
// frontend/lib/api.ts (edited — see Pattern 1 for full diff)
export function apiPost<T = unknown>(
  path: string,
  body?: unknown,
  headers?: HeadersInit,
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
    headers,
  });
}

// Call site:
const res = await apiPost<RunResponse>(
  "/api/v1/runs",
  { recipe_name: "hermes", model: "openai/gpt-4o-mini", prompt: "hi" },
  { Authorization: `Bearer ${byokKey}` },
);
```

### Example 2: `useEffect` + `fetch` to populate recipes
```typescript
// inside PlaygroundForm
useEffect(() => {
  let cancelled = false;
  (async () => {
    try {
      const data = await apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes");
      if (!cancelled) setRecipes(data.recipes);
    } catch (e) {
      if (!cancelled) setUiError(parseApiError(e));
    }
  })();
  return () => { cancelled = true; };
}, []);
```

**Why the `cancelled` flag:** In strict mode (React 19 default in dev), effects double-run. Without the flag, a quick unmount before the fetch resolves will `setState` on an unmounted component (warning in dev).

### Example 3: Verdict card verdict-color mapping
```typescript
const verdictStyles: Record<string, string> = {
  PASS: "bg-green-600 text-white",
  // Every FAIL-ish category from models/runs.py::Category
  ASSERT_FAIL: "bg-red-600 text-white",
  INVOKE_FAIL: "bg-red-600 text-white",
  BUILD_FAIL: "bg-red-600 text-white",
  PULL_FAIL: "bg-red-600 text-white",
  CLONE_FAIL: "bg-red-600 text-white",
  TIMEOUT: "bg-red-600 text-white",
  LINT_FAIL: "bg-red-600 text-white",
  INFRA_FAIL: "bg-orange-500 text-white",
  STOCHASTIC: "bg-yellow-500 text-black",
  SKIP: "bg-slate-400 text-white",
};
// Use in JSX:
<span className={`${verdictStyles[verdict.category] ?? "bg-muted"} rounded-md px-2 py-0.5 text-xs font-semibold`}>
  {verdict.verdict}
</span>
```

**Verdict vs category:** `verdict.verdict` is the short label (e.g. `"PASS"`, `"FAIL"`); `verdict.category` is the fine-grained enum (PASS/ASSERT_FAIL/INFRA_FAIL/etc.). CONTEXT D-06 says both surface in the card — badge on verdict, pill on category. [VERIFIED: api_server/src/api_server/models/runs.py:27-46]

## Phase Requirements

Phase 20 has no REQUIREMENTS.md IDs assigned (CONTEXT.md §Phase Boundary). The effective requirements are Success Criteria SC-01..SC-11 + the 14 locked decisions D-01..D-14.

| ID | Description | Research Support |
|----|-------------|------------------|
| SC-01 | `make dev-api-local` + `make dev-frontend` boot the stack | Out of this phase's implementation scope; established by prior phases |
| SC-02 | `/playground` shows form with 5 real recipes from API | Pattern 2 (useState + fetch) + native `<select>` (Q6 below) |
| SC-03 | Deploy POSTs with `Authorization: Bearer` | Pattern 1 (`apiPost` extension) + Example 1 |
| SC-04 | Verdict card renders within N seconds with all fields | Example 3 (verdict styling) + D-06 spec |
| SC-05 | BYOK key never appears in console/Network body/API logs/DevTools | Pattern 5 (BYOK hardening) + Pitfall 3 |
| SC-06 | Every D-07 error path renders in UI | Pattern 3 (`parseApiError`) + Pattern 4 (Retry-After countdown) |
| SC-07 | Zero hardcoded recipe/model/channel arrays in `/playground` subtree | Pitfall 8 (delete full tree, verify grep) |
| SC-08 | `agent-configurator.tsx` deleted | Pitfall 8 |
| SC-09 | `pnpm build` + `pnpm lint` pass | Turbopack-compatible patterns (see Q9) |
| SC-10 | Multi-run — new verdict replaces old; persists as separate rows | Pitfall 6 (state clearing) |
| SC-11 | All green locally → Hetzner deploy unblocks | Manual smoke pass (see §Testing Decision) |

## Research Focus Answers

### Q1: `apiPost` extension pattern — RECOMMENDATION

**Recommended:** Extend `apiPost` with a third optional `headers?: HeadersInit` parameter AND extend `ApiError` with `headers: Headers`. Full diff in Pattern 1 above.

**Why not a separate `apiPostWithAuth` variant:** Two functions doing near-identical work → drift risk. The third-param pattern is the idiomatic TS extension.

**Why extend `ApiError` too:** `Retry-After` parsing (Q4) requires response headers on the error object. Doing it now as one coupled change prevents half-broken intermediate states.

**React 19/Next 16 idiomatic alternative (considered, NOT recommended):** Expose a typed `request<T>(path, init)` directly from `api.ts`. This gives callers full `RequestInit` control — but it breaks the encapsulation benefit of `apiGet`/`apiPost` (credentials, JSON content-type, error mapping). Planner should NOT do this.

**Invocation example:**
```typescript
const res = await apiPost<RunResponse>(
  "/api/v1/runs",
  { recipe_name, model, prompt },
  { Authorization: `Bearer ${byokKey}` },
);
```

Confidence: HIGH. Based on direct reading of `frontend/lib/api.ts` + the one other call site (`dev-login-form.tsx`) which remains compatible.

### Q2: React 19.2 form state pattern — RECOMMENDATION

**Recommended:** Plain `useState` for form fields + `useState<boolean>` for in-flight flag + `try/catch` in `async onClick` handler.

**Why NOT `useActionState`:**
1. Not a server action — BYOK key must never touch the server-rendered tree. (Even though `useActionState` works with client-only async functions, its archetypal shape is `<form action={serverAction}>`.)
2. `(prevState, payload)` indirection adds mental overhead for a 2-field payload.
3. No progressive-enhancement benefit — `"use client"` already requires JS.
4. `useFormStatus` (its companion) is only useful when the submit button is in a deeply-nested child; our Deploy button is a sibling.

**Why NOT `useTransition` on its own:** `useTransition` is designed for non-blocking React state updates (keeping the UI responsive during heavy renders). Here the blocking wait is network I/O, not React work. A boolean `isRunning` in state is clearer.

**Recommended skeleton:** See Pattern 2 above (already in RESEARCH.md).

Confidence: HIGH. Based on React 19 docs + direct pattern fit analysis. [CITED: https://react.dev/reference/react/useActionState]

### Q3: Error-to-UI mapping helper — RECOMMENDATION

**Recommended:** Discriminated union `UiError` + single `parseApiError(err: unknown): UiError` function. Full implementation in Pattern 3 above.

**Consumer-side:** exhaustive `switch (uiError.kind)` with TS `never`-check for compile-time coverage:
```typescript
function ErrorDisplay({ error }: { error: UiError }) {
  switch (error.kind) {
    case "validation":   return <FieldError field={error.field} msg={error.message} />;
    case "rate_limited": return <RateLimitedBanner seconds={error.retryAfterSec} />;
    case "unauthorized": return <InlineError>Invalid or missing API key</InlineError>;
    case "not_found":    return <InlineError>{error.message}</InlineError>;
    case "infra":        return <InfraErrorCard msg={error.message} requestId={error.requestId} />;
    case "network":      return <NetworkErrorCard onRetry={...} />;
    case "unknown":      return <InlineError>{error.message}</InlineError>;
  }
}
```

The server's Stripe envelope (`api_server/src/api_server/models/errors.py`) always includes `request_id` — include it in every error card so users can report with a grep-able ID. [VERIFIED: api_server/src/api_server/models/errors.py:67-77]

Confidence: HIGH.

### Q4: 429 Retry-After parsing + countdown UX — RECOMMENDATION

**Parsing:** Use the `parseRetryAfter` helper in Pattern 3 above. RFC 7231 allows both delta-seconds and HTTP-date formats; MDN and every production retry library support both. Default to 5 seconds if parsing fails. [CITED: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After]

**Countdown:** Pattern 4's `useRetryCountdown` hook, OR — simpler — store `retryAtMs` as a target timestamp and recompute `remaining = Math.max(0, Math.ceil((retryAtMs - Date.now()) / 1000))` on each `setInterval` tick. The target-timestamp variant survives tab backgrounding (where `setInterval` may throttle).

**UI rendering:**
```tsx
{uiError?.kind === "rate_limited" && (
  <div role="status" aria-live="polite" className="rounded-md border border-amber-500 bg-amber-500/10 p-4">
    Rate limited — retry in {remaining}s
  </div>
)}
<Button disabled={isRunning || !!uiError || remaining > 0} onClick={onDeploy}>
  {remaining > 0 ? `Retry in ${remaining}s` : "Deploy"}
</Button>
```

When `remaining === 0`, clear `uiError` so the Deploy button re-enables and the rate-limit banner disappears.

**`ApiError` extension is mandatory** — without it `err.headers.get("Retry-After")` doesn't exist.

Confidence: HIGH.

### Q5: BYOK input hardening — RECOMMENDATION

Four concrete practices, ranked by impact:

1. **`<input type="password" autoComplete="new-password">`** — masks display + strongest hint that browsers should not offer autofill. `autoComplete="off"` alone is ignored by Chrome/Safari for credential fields. [CITED: MDN autocomplete guide + https://blog.0xbadc0de.be/archives/124]

2. **Clear state after submit** — `setByok("")` on both success and unrecoverable failure. Satisfies SC-05's strict reading ("not visible in React DevTools after submit"). The user re-types on re-deploy; acceptable for Phase 20 (persistence is Phase 20.2).

3. **Never log in any form** — no `console.log(byok)`, no `console.log({ formState })` containing it. Construct the Authorization header at the call site; never destructure into a logged object. Add a PR review checklist entry.

4. **No module-level closure over it** — `byok` is a React state value scoped to `PlaygroundForm`. It must NOT leak into module-level caches, Zustand stores, or window-exposed debug objects. No `localStorage`, no `sessionStorage`, no IndexedDB.

**Practices that do NOT help (avoid ceremony):**
- `type="text"` with CSS text obfuscation — type="password" is more important (prevents screen-record captures).
- Overriding `console` globally — fragile, breaks debugging.
- Custom Service Worker proxy — out of scope for Phase 20.

Confidence: HIGH.

### Q6: shadcn/ui `<Select>` vs native `<select>` — RECOMMENDATION

**Recommended: native `<select>`.** CONTEXT D-03 defaults to native; this research confirms that default for Phase 20.

**Rationale (1 paragraph):** shadcn's `<Select>` (`components/ui/select.tsx`) is a Radix UI wrapper with better keyboard/touch affordances, styled-via-Tailwind appearance, and custom popover content. It's genuinely prettier. BUT: (a) it pulls in Radix portal machinery that could interact poorly with the page's `<ParticleBackground>` z-index stacking; (b) it requires a `"use client"` boundary (which we have) and more import lines (`Select, SelectTrigger, SelectValue, SelectContent, SelectItem`); (c) native `<select>` has zero a11y bugs because screen readers have spoken native selects for 25 years; (d) dumb-client discipline (golden rule #2) favors the minimum-surface-area primitive. The verdict: save shadcn `<Select>` for a future phase where the UX polish matters (mobile sheet experience, searchable option lists, model catalog picker). For a 5-option recipe list rendered once, native is correct. [VERIFIED: frontend/components/ui/select.tsx]

Confidence: HIGH.

### Q7: Accessibility checklist — RECOMMENDATION

Seven concrete bullets for the `<PlaygroundForm>` + `<RunResultCard>`:

1. **Label every field.** Use `<Label htmlFor="recipe">` pointing at each input's `id`. shadcn `components/ui/label.tsx` is already available. [VERIFIED: frontend/components/ui/label.tsx]

2. **`role="status"` + `aria-live="polite"` on the verdict container.** When `<RunResultCard>` appears, screen readers announce it without interrupting whatever else the user is reading. Same for the rate-limit banner. For in-flight state, `aria-live="polite"` on the "Running…" skeleton. Use `aria-live="assertive"` only for errors that demand immediate attention (e.g., 502 infra_error).

3. **`aria-invalid="true"` + `aria-describedby="field-error-id"` on fields with validation errors.** When `uiError.kind === "validation"` and `uiError.field === "model"`, mark the model input. shadcn's `<Input>` already styles `aria-invalid` via Tailwind [VERIFIED: frontend/components/ui/input.tsx:13].

4. **Focus management after Deploy.** On successful verdict render, move focus to the verdict card (`useRef<HTMLDivElement>` + `ref.current?.focus()` in a `useEffect` watching verdict changes) with `tabIndex={-1}` on the card so it's programmatically-focusable but not in the tab order.

5. **Reduced-motion respect.** The `Spinner` component uses `animate-spin`. For users with `prefers-reduced-motion: reduce`, Tailwind v4 respects the media query via `motion-reduce:animate-none`. Verify the skeleton's `animate-pulse` also honors it (shadcn Skeleton does by default since Tailwind v3+). [VERIFIED: frontend/components/ui/skeleton.tsx:7]

6. **`aria-busy={isRunning}` on the Deploy button + `aria-busy` on the form container during in-flight.** Matches the pattern already in `dev-login-form.tsx` [VERIFIED: frontend/components/dev-login-form.tsx:60].

7. **Error announcement for form-level errors.** Non-field errors (network, 502) render inside `<div role="alert">` — screen readers announce immediately. Matches `dev-login-form.tsx` [VERIFIED: frontend/components/dev-login-form.tsx:89].

Confidence: HIGH.

### Q8: Loading skeleton pattern — RECOMMENDATION

**Recommended: text-only "Running…" with a `<Spinner>` icon inline** (the lowest-ceremony option).

```tsx
{isRunning && (
  <div role="status" aria-live="polite" className="flex items-center gap-2 text-muted-foreground">
    <Spinner />
    <span>Running…</span>
  </div>
)}
```

**Why not the shadcn `Skeleton`:** `Skeleton` is for content-shaped placeholders (e.g., a card outline while data loads). A run is a one-shot verdict — nothing to shape. A text label is clearer and smaller. [VERIFIED: frontend/components/ui/skeleton.tsx]

**Use Skeleton instead for:** the recipe `<select>` placeholder during initial load (D-09: first page load with recipes loading). Even there, a disabled `<select>` with `placeholder="Loading recipes…"` text is simpler. **My stronger recommendation:** skip Skeleton entirely in Phase 20; use disabled controls + text placeholders.

Confidence: HIGH.

### Q9: Turbopack/Next 16 pitfalls specific to client components — RECOMMENDATION

Three Phase-20-relevant gotchas:

1. **`"use client"` directive must be the first statement in every client-component file.** `frontend/app/playground/page.tsx` already has it on line 1 [VERIFIED]. New files (`playground-form.tsx`, `run-result-card.tsx`) must follow. If a shadcn primitive with `"use client"` is imported into a server component, the importing component becomes a client boundary — fine for our case since we're all-client.

2. **Turbopack HMR + module-level state can desync.** If we introduce module-level mutable state (caches, singletons) in `api-types.ts` or a new helper, Turbopack's Fast Refresh can leave stale references post-edit, breaking error-rendering until a full reload. [CITED: github.com/vercel/next.js/issues/85883] **Mitigation:** keep all Phase-20 helpers as pure functions. Any cache → `useRef` inside a component.

3. **`fetch` deduplication in server components does NOT apply here.** Next 16 deduplicates equivalent `fetch` calls during a single render pass — but only in server components. Our `useEffect(() => apiGet(...))` runs in the browser and is plain `fetch`. No dedup concerns; also no dedup benefits. Don't rely on Next magic you're not using.

**Unlikely to matter for Phase 20 but worth flagging:**
- React Compiler 1.0 is default-on in Next 16.2. It auto-memoizes; don't hand-roll `useMemo`/`useCallback` unless a profile shows a need. Violating this won't break correctness, just bloats PRs.
- TypeScript strict errors — `frontend/next.config.mjs` sets `typescript.ignoreBuildErrors: true` [VERIFIED: frontend/next.config.mjs:10-12]. **Plan-level decision:** keep this as-is (don't turn it off mid-phase); ensure `pnpm lint` passes for SC-09.

Confidence: HIGH. [CITED: https://nextjs.org/blog/next-16-2, github.com/vercel/next.js/issues/85883]

### Q10: Testing decision (D-14 gray area) — RECOMMENDATION

**Recommended: DEFER all frontend tests to Phase 20.1. Ship Phase 20 with a mandatory manual SC-11 smoke pass.**

**State of the frontend today:**
- `frontend/package.json` has **zero test scripts** (only `dev`, `build`, `start`, `lint`) [VERIFIED: frontend/package.json:5-10].
- **No test harness installed** — no Vitest, no Jest, no Playwright, no Testing Library.
- **No test directories** — `grep` for `__tests__/test/tests/e2e` in frontend/ finds only vendored nodules (no project tests).

**Options evaluated:**

| Option | Cost | Value for Phase 20 | Recommendation |
|--------|------|---------------------|----------------|
| **(a) Defer all tests** | 0 tasks | Manual SC-11 smoke pass is mandated by CONTEXT anyway; adds discipline to planner to specify manual steps | **RECOMMENDED** |
| (b) Playwright single E2E test | +2-3 tasks: install, config, CI wiring, single test; ~400-600 lines of scaffold | E2E against local Docker stack is high-value for SC-11 automation — but Hetzner deploy is gated by a SINGLE manual run, not by CI | Defer to Phase 20.1 |
| (c) Vitest + Testing Library | +2-3 tasks: install, config, mock network; unit tests for `parseApiError`, `parseRetryAfter`, `UiError` branches | Reasonable but focuses on helpers — the real risk (full round-trip) isn't covered | Defer to Phase 20.1 |
| (d) Playwright + Vitest (both) | +4-6 tasks | Nyquist coverage + helper unit tests | Definitely a follow-up phase |

**Why "defer" wins for Phase 20:**
- Phase 20's exit gate (SC-11) is literally "unblock Hetzner deploy" — a single end-to-end manual run vs production-bound code suffices. Automation is a follow-up phase's work.
- Adding a test framework inside the same PR that deletes 1000+ lines of mock code AND introduces a new API-driven page is scope creep. Two unrelated concerns shouldn't land in one phase.
- Phase 20.1 (mobile polish) is the natural place to stand up Vitest+Playwright once the page shape is stable.

**What the planner MUST still include in Phase 20** (without a test runner):
- A documented manual smoke runbook in the phase plan (click-by-click: open `/playground`, assert 5 recipes, type key, deploy, assert verdict card).
- SC-11 listed as a task with explicit acceptance criteria.
- A grep-test acceptance for SC-07 (`grep -R "defaultClones\|openRouterModels" frontend/app/playground/ frontend/components/` returns 0 lines) — this is a shell-runnable assertion, doesn't need a test framework.

**If the planner overrides to option (b):** Playwright, not Vitest. Rationale: the failure mode worth catching is "click Deploy → verdict card renders" (full round-trip). Vitest-level unit tests on `parseApiError` don't catch that. [CITED: https://nextjs.org/docs/pages/guides/testing]

Confidence: MEDIUM-HIGH. (Lower than others because "defer" is a scope call the user may override.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Pages Router | App Router with Server Components + `"use client"` | Next 13 (2022); mature in 16 | This project already uses App Router; all Phase-20 components must be explicit client components |
| `useFormState` | `useActionState` | React 19 (2024) | `useFormState` is alias-deprecated; don't use either — plain `useState` is clearer for this page |
| `xterm` package | `@xterm/xterm` scoped | 2024+ | Not relevant to Phase 20 (deferred to Phase 22+ WebSocket terminal) |
| Webpack dev server | Turbopack stable default | Next 16 (2026) | 10x faster HMR; module-level state can desync (see Pitfall 2) |
| `fetch` without built-in cache in client | `fetch` + React Query | Community standard | We're choosing NOT to adopt React Query — two endpoints don't justify it |

**Deprecated/outdated in this context:**
- `useFormState` (renamed to `useActionState` in React 19; same function).
- `autoComplete="off"` alone as a defense — browsers ignore on credentials (see Pitfall 4).
- `xterm` npm package — use `@xterm/xterm` when terminal lands (Phase 22+). Not Phase 20.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No existing `apiPost` caller passes `credentials: "omit"` via headers (the current signature doesn't expose it) | Q1 / Pattern 1 | Low — only one other caller (`dev-login-form.tsx`), verified [VERIFIED: grep shows 1 call site] |
| A2 | `TypeError` is the thrown shape for network failures in the browser `fetch` API | Q3 / `parseApiError` | Low — this is the spec'd behavior; confirmed in existing `dev-login-form.tsx` error branching |
| A3 | Server emits `Retry-After` as delta-seconds on 429 (not HTTP-date) | Q4 | Low — FastAPI middleware convention; `parseRetryAfter` handles both anyway. Planner should VERIFY against Plan 19-05 implementation when it lands. |
| A4 | BYOK key does not contain control characters that would corrupt a `Bearer <key>` header | Q1 call site | Low — OpenRouter/Anthropic/OpenAI keys are `sk-` prefixed ASCII |
| A5 | `ApiError` is never constructed outside `api.ts` `request<T>()` | Pattern 1 extension safety | Low — verified via grep for `new ApiError`; only internal construction |
| A6 | The 5 recipes loaded into `app.state.recipes` are always all 5 (no subset-by-user in Phase 19) | Q6 + SC-02 | Low — [VERIFIED: .planning/phases/19-api-foundation/19-03-SUMMARY.md confirms load_all_recipes returns 5] |
| A7 | Next 16.2's React Compiler 1.0 default-on will not miscompile `useState` patterns in Pattern 2 | Q9 | Low — documented as stable; our patterns are canonical |

All other claims are [VERIFIED] against the referenced files or [CITED] to MDN/React docs/Next.js release notes. Assumption risks are all LOW-impact and easily unblocked at plan time.

## Open Questions

1. **Should BYOK be cleared from state after successful submit?**
   - What we know: CONTEXT D-05 says "Cleared after submit (or kept in state for the current page load only, up to the planner)."
   - What's unclear: UX trade-off. Clearing forces re-type on re-deploy; keeping trades SC-05 strictness for convenience.
   - Recommendation: **clear on successful submit + on any submit attempt** (even failed ones, because the user likely wants to fix a typo). Forces fresh entry; satisfies SC-05's strictest reading. Re-typing is acceptable for a platform-internal smoke surface.

2. **Should the verdict card persist across recipe changes?**
   - What we know: SC-10 says "pick a different recipe, run again — new verdict replaces the old."
   - What's unclear: between runs, while the user edits the form, does the previous verdict stay visible?
   - Recommendation: **yes, keep it visible** until Deploy is clicked again. Clearing on edit causes flicker. Clearing happens at the top of `onDeploy` (Pitfall 6).

3. **Should there be a `Cancel` button for in-flight runs?**
   - What we know: CONTEXT D-06: "No queueing, no cancelation UI (defer)."
   - What's unclear: nothing — explicitly deferred.
   - Recommendation: honor CONTEXT; no cancel button.

4. **D-14 testing decision — final call.**
   - What we know: Research recommends "defer to Phase 20.1."
   - What's unclear: user may prefer Playwright-now.
   - Recommendation: planner proposes DEFER; if user overrides, planner adds Playwright (option (b)) as +2-3 tasks.

## Environment Availability

> This phase depends only on tools already verified in Phase 19.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js ≥ 20 | Next 16 runtime | ✓ (assumed, prior phase) | 20+ | — |
| `pnpm` | Install + build | ✓ (assumed, prior phase) | Latest | `npm` as fallback |
| FastAPI dev server | `GET /v1/recipes`, `POST /v1/runs` | ✓ Phase 19 shipped | — | — |
| PostgreSQL 17 | Via FastAPI; reads `runs` table | ✓ Phase 19 shipped | 17 | — |
| Docker daemon | FastAPI runs runner subprocesses | ✓ Phase 19 shipped | 27+ | — |
| Browser with JS enabled | Client component | ✓ target | — | — |

**Missing dependencies with no fallback:** none — the phase is pure frontend over existing Phase 19 infrastructure.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None installed in frontend/ |
| Config file | none — **see Wave 0 below** |
| Quick run command | `cd frontend && pnpm lint` (ESLint, no test runner) |
| Full suite command | `cd frontend && pnpm build && pnpm lint` (Turbopack prod build + ESLint) |

**Per D-14, Research recommends deferring test framework adoption to Phase 20.1.** The phase's validation therefore comes from manual SC-11 smoke + grep-based structural assertions:

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC-02 | Form renders with 5 recipes from API | manual-only (E2E browser) | `make dev-api-local && make dev-frontend` → open `http://localhost:3000/playground` → visually confirm 5 options | ✅ (infra) |
| SC-03 | Deploy POSTs with `Authorization: Bearer` | manual-only | Browser DevTools Network tab → inspect request header → confirm `Authorization: Bearer <...>` present | ✅ (browser) |
| SC-04 | Verdict card renders all fields | manual-only | Run once; visually confirm verdict, category, exit_code, wall_time_s, run_id, stderr_tail present | ✅ (browser) |
| SC-05 (partial) | BYOK key absent from API logs | grep | `docker compose -f docker-compose.dev.yml exec api_server sh -c 'grep <your-key-value> /proc/1/fd/1'` → 0 matches | ✅ (infra) |
| SC-05 (partial) | BYOK key absent from Network request body | manual-only | DevTools Network → Preview request body → key only in Authorization header, not body | ✅ (browser) |
| SC-06 | All D-07 error paths render | manual-only | Provoke each (422: empty prompt; 429: spam 11 times; 401: wrong key; 502: kill runner; network: disable network) | ✅ (browser) |
| SC-07 | Zero hardcoded recipe/model/channel arrays | grep | `grep -RE "defaultClones\|openRouterModels\|[\"']telegram[\"']\|[\"']slack[\"']" frontend/app/playground/ frontend/components/playground-form.tsx frontend/components/run-result-card.tsx` → 0 matches | ✅ (grep) |
| SC-08 | `agent-configurator.tsx` deleted | shell | `test ! -f frontend/components/agent-configurator.tsx && echo OK` | ✅ (shell) |
| SC-09 | Build + lint pass | automated | `cd frontend && pnpm build && pnpm lint` | ✅ (package.json scripts) |
| SC-10 | Multi-run — verdict replaces; persists as separate rows | manual + SQL | Run twice, manually confirm second verdict replaces first; `docker compose -f ... exec postgres psql -c "SELECT id, created_at FROM runs ORDER BY created_at DESC LIMIT 2"` → 2 distinct rows | ✅ (browser + infra) |
| SC-11 | Full local E2E unblocks Hetzner deploy | manual only | Complete SC-01..SC-10; document in plan SUMMARY; proceed to Phase 19 Plan 07 Task 3 | ✅ (phase gate) |

### Sampling Rate
- **Per task commit:** `pnpm lint` on any task that touches `frontend/`
- **Per wave merge:** `pnpm build` + `pnpm lint` both green
- **Phase gate:** Full manual SC-11 smoke pass before closing Phase 20

### Wave 0 Gaps
- None — existing (non-)test infrastructure covers all phase requirements per the "defer to Phase 20.1" decision. If the planner overrides D-14 to option (b) Playwright, Wave 0 would need:
  - [ ] `frontend/playwright.config.ts` — framework config
  - [ ] `frontend/tests/playground.spec.ts` — single E2E covering SC-02→SC-04→SC-10
  - [ ] Package-install task (`pnpm add -D @playwright/test && pnpm exec playwright install chromium`)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **no** for Phase 20 | Auth is deferred (Phase 21+). Playground is unauthenticated (`anonymous` seed user). |
| V3 Session Management | no | No sessions in this phase. |
| V4 Access Control | partial | Per-user BYOK is the only credential surface; no server-side session. |
| V5 Input Validation | **yes** | Client: non-empty string checks only (D-04 forbids format policing). Server: Pydantic `extra=forbid` + `recipe_name` regex (Phase 19 Plan 04 — already shipped). [VERIFIED: api_server/src/api_server/models/runs.py:49-72] |
| V6 Cryptography | **yes** (transport) | TLS in prod via Caddy (Phase 19 D-08). BYOK transport = HTTPS only. |
| V7 Error Handling & Logging | **yes** | Never log BYOK key (Pitfall 3). Never echo key in error bodies (CONTEXT D-07 "401/403: does NOT echo the key value"). Redacted on server side by Plan 19-06 + route-handler belt-and-suspenders. [VERIFIED: .planning/phases/19-api-foundation/19-04-SUMMARY.md key-decisions §3] |
| V8 Data Protection | **yes** | BYOK key never persisted client-side (no localStorage / sessionStorage / IndexedDB). Not in DB. Cleared from React state after submit (recommended). |
| V9 Communication | **yes** | HTTPS-only in prod. Next.js rewrite → loopback in dev. No direct cross-origin calls. |
| V10 Malicious Code | no | N/A for this phase |
| V11 Business Logic | no | Minimal business rules in client |
| V12 File Handling | no | No file uploads in Phase 20 |
| V13 API & Web Service | partial | API contract is server-side (Phase 19); client consumes |
| V14 Configuration | minimal | `NEXT_PUBLIC_API_PROXY_TARGET` env var is the only client-side config surface |

### Known Threat Patterns for the stack (Client-side + BYOK flow)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| BYOK key leaking via console/logs | Information Disclosure | Never log; never pass to tracing library; clear state after submit (Pitfall 3) |
| BYOK key leaking via localStorage/sessionStorage | Information Disclosure | No persistence APIs touched (D-05); keep key in React state only |
| BYOK key leaking via browser password manager autofill | Information Disclosure | `autoComplete="new-password"` (Pitfall 4 — imperfect but best available) |
| BYOK key leaking via URL query string | Information Disclosure | Only sent in `Authorization` header — never URL. Verified by API contract (Phase 19 D-02). |
| BYOK key replay via XSS | Spoofing | Frontend is `"use client"` but produces no XSS surface in Phase 20 (no `dangerouslySetInnerHTML`, no user-markdown rendering, no `dangerouslyAllowBrowser` SDK calls). |
| CSRF on POST /v1/runs | Tampering | CORS: no cross-origin since rewrite is same-origin; no session cookie depended on for auth (BYOK header is per-request) — CSRF N/A in this phase |
| SQL injection via recipe_name/model | Tampering | Server-side: Pydantic regex + parameterized asyncpg queries (Phase 19 Plan 04 — already shipped) [VERIFIED: 19-04-SUMMARY.md T-19-04-04] |
| Response body leaking key back to UI | Information Disclosure | Server never echoes key in responses (Phase 19 D-02 contract, Plan 19-06 log redaction, Plan 19-04 exception redaction) [VERIFIED] |
| Unencrypted key over network | Information Disclosure | HTTPS in prod (Caddy + Let's Encrypt — Phase 19 D-08); localhost in dev |
| Third-party script exfiltration | Information Disclosure | Phase 20 adds no third-party scripts; ParticleBackground is in-repo |

**Security posture summary:** Phase 20 is low-surface-area. The BYOK key is the only sensitive data. Server-side is hardened by Phase 19. Client-side discipline (Pitfalls 3 + 4, no persistence, clear after submit) closes the known gaps. No new threat classes introduced by this phase.

## Sources

### Primary (HIGH confidence)
- `frontend/lib/api.ts` — full read; confirms `ApiError` shape + `request<T>` signature [VERIFIED]
- `frontend/next.config.mjs` — full read; confirms rewrite paths [VERIFIED]
- `frontend/app/playground/page.tsx` — full read; confirms current mock entry point [VERIFIED]
- `frontend/package.json` — full read; confirms installed deps + NO test scripts [VERIFIED]
- `frontend/components/ui/*.tsx` — read: select.tsx, skeleton.tsx, spinner.tsx, input.tsx, accordion.tsx, badge.tsx, card.tsx, button.tsx, label.tsx, textarea.tsx [VERIFIED]
- `frontend/components/dev-login-form.tsx` — full read; confirms existing `apiPost` call site [VERIFIED]
- `frontend/components/agent-configurator.tsx` — line count + imports header [VERIFIED]
- `.planning/phases/20-frontend-alicerce/20-CONTEXT.md` — full read [VERIFIED]
- `.planning/phases/19-api-foundation/19-CONTEXT.md` — full read; confirms D-01 idempotency, D-02 BYOK, D-04 health shapes [VERIFIED]
- `.planning/phases/19-api-foundation/19-03-SUMMARY.md` — full read; confirms `GET /v1/recipes` shape [VERIFIED]
- `.planning/phases/19-api-foundation/19-04-SUMMARY.md` — full read; confirms `POST /v1/runs` shape + BYOK redaction invariants [VERIFIED]
- `api_server/src/api_server/models/recipes.py` — full read [VERIFIED]
- `api_server/src/api_server/models/runs.py` — full read; Category enum 9 live + 2 reserved [VERIFIED]
- `api_server/src/api_server/models/errors.py` — full read; Stripe envelope shape [VERIFIED]
- `/Users/fcavalcanti/dev/agent-playground/CLAUDE.md` — Golden rules #1-4 [VERIFIED]
- `memory/feedback_dumb_client_no_mocks.md` — golden rule #2 origin incident [VERIFIED]
- `memory/feedback_no_mocks_no_stubs.md` — infra-side counterpart [VERIFIED]
- [React 19 `useActionState` docs](https://react.dev/reference/react/useActionState) [CITED]
- [MDN Retry-After header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After) [CITED]
- [MDN autocomplete practical guide](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Turning_off_form_autocompletion) [CITED]
- [Next.js 16 release blog](https://nextjs.org/blog/next-16) — Turbopack default [CITED]
- [Next.js 16.2 blog](https://nextjs.org/blog/next-16-2) — React Compiler 1.0 default-on [CITED]

### Secondary (MEDIUM confidence)
- [Next.js testing guide](https://nextjs.org/docs/pages/guides/testing) — Vitest + Playwright recommendations [CITED]
- [Strapi Next.js testing guide](https://strapi.io/blog/nextjs-testing-guide-unit-and-e2e-tests-with-vitest-and-playwright) — reference pattern if Playwright adopted [CITED]
- [Vercel next.js issue #85883 — Turbopack HMR manifest](https://github.com/vercel/next.js/issues/85883) — Pitfall 2 source [CITED]
- [Password field autocomplete context](https://blog.0xbadc0de.be/archives/124) — browser autofill behavior background [CITED]

### Tertiary (LOW confidence)
- None — all material claims are verified or cited to authoritative sources.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — all deps confirmed via direct file read of `frontend/package.json`; no new installs required.
- Architecture (single client component + extended api.ts): **HIGH** — patterns follow existing `dev-login-form.tsx` precedent.
- Q1 (apiPost extension): **HIGH** — direct diff of 10 lines against known call sites.
- Q2 (useState over useActionState): **HIGH** — React 19 docs + pattern-fit analysis.
- Q3 (parseApiError): **HIGH** — Stripe envelope shape verified against Phase 19 code.
- Q4 (Retry-After): **HIGH** — MDN-verified algorithm.
- Q5 (BYOK hardening): **HIGH** — MDN + user-rule alignment.
- Q6 (native select vs shadcn): **HIGH** — direct comparison against existing select.tsx.
- Q7 (a11y): **HIGH** — matches existing dev-login-form.tsx patterns.
- Q8 (loading skeleton): **HIGH** — minimum-ceremony recommendation.
- Q9 (Turbopack pitfalls): **MEDIUM-HIGH** — single issue thread cited; project is on bleeding edge of Next 16.
- Q10 (testing deferral): **MEDIUM-HIGH** — "defer" is a scope call; user may override.
- Pitfalls: **HIGH** — each pitfall cites a specific file or external source.

**Research date:** 2026-04-17
**Valid until:** 2026-05-17 (30 days — stable stack; React 19.2 + Next 16.2 are stable; Phase 19 API contract is frozen)
