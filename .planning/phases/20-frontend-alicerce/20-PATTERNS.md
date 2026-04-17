# Phase 20: Frontend Alicerce — Pattern Map

**Mapped:** 2026-04-17
**Files analyzed:** 7 (5 new/modified, 2 deleted subtrees)
**Analogs found:** 6 / 6 in-scope  (100%)

All analog patterns come from inside `frontend/` — every "new" file has a strong peer already committed. The only truly novel work is the `parseApiError` / `UiError` discriminated union, which has no analog because the app has never had a structured error envelope before.

---

## File Classification

| New / Modified / Deleted File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------------------|------|-----------|----------------|---------------|
| `frontend/lib/api.ts` | utility / fetch wrapper | request-response | (edit-in-place — self-analog) | exact |
| `frontend/lib/api-types.ts` (NEW) | types / error helper | transform (unknown → UiError) | `api_server/src/api_server/models/errors.py` (shape source) + `api_server/src/api_server/models/runs.py` + `api_server/src/api_server/models/recipes.py` (server-side shapes to mirror) | role-match (first TS types file in this repo) |
| `frontend/components/playground-form.tsx` (NEW) | client component / stateful form | request-response (useEffect GET on mount + async POST on click) | `frontend/components/dev-login-form.tsx` — `"use client"` + `useState` + `apiPost` + `ApiError` try/catch + `aria-busy` + `Loader2 animate-spin` + `role="alert"` error surface | **exact** |
| `frontend/components/run-result-card.tsx` (NEW) | pure display component | no I/O — prop-driven render | `frontend/components/ui/alert.tsx` — small display-only component using `data-slot=`, `cva`/`cn` variants, `role="alert"` | role-match (there is no existing verdict-shaped card; closest "prop-driven colored surface" is Alert) |
| `frontend/app/playground/page.tsx` | route entry / page shell | no I/O — composes client tree | (current file — self-analog; mount swap from `<AgentConfigurator>` to `<PlaygroundForm>`) | exact |
| `frontend/components/agent-configurator.tsx` (DELETE) | — | — | — | — |
| `frontend/components/{agent-card,model-selector,a2a-network,task-orchestrator}.tsx` (DELETE) | — | — | — | — |

---

## Pattern Assignments

### 1. `frontend/lib/api.ts`  (utility / fetch wrapper — **EDIT-IN-PLACE**)

**Analog:** self. The file already owns the exact pattern (`request<T>` → `fetch` → `ApiError` on non-OK). Phase 20 adds three surgical edits.

**Existing imports block** (`frontend/lib/api.ts` lines 1-5):
```typescript
// Thin fetch wrapper for the Go API.
// Always sends cookies (session lives in an HttpOnly cookie set by the Go API).
// The Next.js dev server proxies `/api/*` to the Go API via next.config.ts rewrites.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
```
Keep this block verbatim. Note the comment still references "Go API" — that's stale from before the Python pivot; **do not rewrite it in this phase** (scope discipline; not on the Phase 20 success-criteria list).

**Existing ApiError class** (`frontend/lib/api.ts` lines 7-17) — THE thing to extend:
```typescript
export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string, message?: string) {
    super(message ?? `API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}
```

**Existing request<T> core** (`frontend/lib/api.ts` lines 19-43) — THE throw site to extend:
```typescript
async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
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
    throw new ApiError(res.status, text);
  }

  // Empty responses (e.g. 204) are safe to return as null.
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return null as T;
  }
  return (await res.json()) as T;
}
```

**Existing apiPost** (`frontend/lib/api.ts` lines 49-57) — THE function to extend with a third param:
```typescript
export function apiPost<T = unknown>(
  path: string,
  body?: unknown
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}
```

**Three Phase-20 edits (copy verbatim from RESEARCH Pattern 1, lines 216-259):**

| Edit | Location | Change |
|------|----------|--------|
| A | `ApiError` constructor | Add fourth field `headers: Headers` (becomes 4-arg ctor: status, body, headers, message?) |
| B | `request<T>` throw site | Pass `res.headers` as third arg: `throw new ApiError(res.status, text, res.headers);` |
| C | `apiPost` signature | Add third optional param `headers?: HeadersInit` and forward it through `request<T>`'s init.headers |

**Back-compat check (grep-verified):** only one external caller constructs `ApiError` — none (the class is only `throw`n inside `request<T>`). Only one call site uses `apiPost`: `frontend/components/dev-login-form.tsx:38` (`apiPost("/api/dev/login")` — 1 arg, still compatible after adding the optional 2nd and 3rd params). [VERIFIED: Grep result above: 5 matches, all accounted for.]

**DO NOT** rewrite `apiGet` or `apiDelete`. Phase 20 has no auth-bearing GET; `apiGet("/api/v1/recipes")` stays 1-arg.

---

### 2. `frontend/lib/api-types.ts`  (NEW — types + `parseApiError` helper)

**Analog:** no direct TS-types file exists in `frontend/lib/`. The closest-in-spirit reference is the server-side model files (the source of truth the TS must mirror).

**Shape source 1 — `RecipeSummary`** (mirror of `api_server/src/api_server/models/recipes.py` lines 38-50):
```python
class RecipeSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    api_version: str = Field(..., alias="apiVersion")
    source_repo: str | None = None
    source_ref: str | None = None
    provider: str | None = None
    pass_if: str | None = None
    license: str | None = None
    maintainer: str | None = None
```

**TS mirror to write** (Phase 20 executor copies verbatim):
```typescript
export type RecipeSummary = {
  name: string;
  // Server uses alias="apiVersion" — Phase 19 JSON will emit BOTH camelCase
  // and snake_case only if populate_by_name emits the alias. Inspect actual
  // /v1/recipes response during planning to lock this field name.
  apiVersion?: string;
  api_version?: string;
  source_repo?: string | null;
  source_ref?: string | null;
  provider?: string | null;
  pass_if?: string | null;
  license?: string | null;
  maintainer?: string | null;
};
```
**Rule-1 flag for planner:** The Pydantic alias emits `apiVersion` on-the-wire when `populate_by_name=True` is set; this is a lock-it-by-running-the-endpoint concern. See Plan 19-03 SUMMARY referenced in CONTEXT.md for the on-wire shape. Phase 20 planner must confirm with a live `curl /v1/recipes` once, then remove whichever alternate key is not emitted.

**Shape source 2 — `RunRequest` + `RunResponse`** (mirror of `api_server/src/api_server/models/runs.py` lines 49-98):
```python
class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe_name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    prompt: str | None = Field(None, max_length=16384)
    model: str = Field(..., min_length=1, max_length=128)
    no_lint: bool = False
    no_cache: bool = False
    metadata: dict[str, Any] | None = None

class RunResponse(BaseModel):
    run_id: str
    agent_instance_id: str
    recipe: str
    model: str
    prompt: str
    pass_if: str | None = None
    verdict: str
    category: str
    detail: str | None = None
    exit_code: int | None = None
    wall_time_s: float | None = None
    filtered_payload: str | None = None
    stderr_tail: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
```

**TS mirror to write:**
```typescript
export type RunRequest = {
  recipe_name: string;     // /^[a-z0-9][a-z0-9_-]*$/ , max 64
  prompt?: string | null;  // max 16384
  model: string;           // non-empty, max 128
  no_lint?: boolean;
  no_cache?: boolean;
  metadata?: Record<string, unknown> | null;
};

export type RunResponse = {
  run_id: string;
  agent_instance_id: string;
  recipe: string;
  model: string;
  prompt: string;
  pass_if?: string | null;
  verdict: string;
  category: string;
  detail?: string | null;
  exit_code?: number | null;
  wall_time_s?: number | null;
  filtered_payload?: string | null;
  stderr_tail?: string | null;
  created_at?: string | null;  // ISO-8601 string (datetime is JSON-serialized)
  completed_at?: string | null;
};
```

**Shape source 3 — `ErrorResponse`** (mirror of `api_server/src/api_server/models/errors.py` lines 67-78):
```python
class ErrorBody(BaseModel):
    type: str
    code: str
    category: str | None = None
    message: str
    param: str | None = None
    request_id: str

class ErrorEnvelope(BaseModel):
    error: ErrorBody
```

**TS mirror to write (matches RESEARCH Pattern 3 lines 337-346):**
```typescript
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
```

**`UiError` discriminated union + `parseApiError` helper:** copy RESEARCH Pattern 3 lines 348-404 verbatim. No codebase analog — this is net-new. Keep it a **pure function**, no module-level state (RESEARCH Pitfall 2: Turbopack HMR desync).

---

### 3. `frontend/components/playground-form.tsx`  (NEW — client component)

**Analog:** **`frontend/components/dev-login-form.tsx` — exact match.** Same role (client form), same data flow (user action → `apiPost` → success/`ApiError` branches → re-render), same a11y shape (`aria-busy`, `role="alert"`, `animate-spin` spinner). Phase 20 scales this from 1 field + 1 button to 4 fields + 1 button + recipe fetch + verdict render.

**Imports pattern** (copy from `frontend/components/dev-login-form.tsx` lines 1-7, extend):
```typescript
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
```

**Phase 20 extended import block (copy to top of `playground-form.tsx`):**
```typescript
"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { parseApiError, type RecipeSummary, type RunResponse, type UiError } from "@/lib/api-types";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";
import { RunResultCard } from "@/components/run-result-card";
import { cn } from "@/lib/utils";
```

**State-declaration pattern** (adapted from `dev-login-form.tsx` lines 31-32, which has only 2 state vars; Phase 20 needs 8):
```typescript
// dev-login-form.tsx original:
const [isPending, setIsPending] = useState(false);
const [error, setError] = useState<string | null>(null);

// playground-form.tsx (new):
const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
const [recipe, setRecipe] = useState("");
const [model, setModel] = useState("");
const [byok, setByok] = useState("");
const [prompt, setPrompt] = useState("");
const [isRunning, setIsRunning] = useState(false);
const [verdict, setVerdict] = useState<RunResponse | null>(null);
const [uiError, setUiError] = useState<UiError | null>(null);
```

**Async-handler pattern** (the structural analog) — `frontend/components/dev-login-form.tsx` lines 34-51:
```typescript
async function handleLogin() {
  setError(null);
  setIsPending(true);
  try {
    await apiPost("/api/dev/login");
    // Tell the parent to re-check auth state and swap screens.
    await onLoginSuccess();
  } catch (err) {
    // Network errors (TypeError) vs HTTP errors (ApiError).
    if (err instanceof ApiError) {
      setError("Login failed. Check the API server is running and try again.");
    } else {
      setError("Could not reach the server. Check your connection.");
    }
  } finally {
    setIsPending(false);
  }
}
```

**Phase 20 adapted handler** (replaces stringly-typed error branching with the `parseApiError` union; RESEARCH Pattern 2 lines 309-325):
```typescript
async function onDeploy() {
  // Clear prior verdict + error before new run (RESEARCH Pitfall 6)
  setVerdict(null);
  setUiError(null);
  setIsRunning(true);
  try {
    const res = await apiPost<RunResponse>(
      "/api/v1/runs",
      { recipe_name: recipe, model, prompt },
      { Authorization: `Bearer ${byok}` },
    );
    setVerdict(res);
    setByok("");  // BYOK hardening: clear key from state (D-05 + SC-05)
  } catch (e) {
    setUiError(parseApiError(e));
    // On unauthorized specifically, the key is also cleared (RESEARCH Q5):
    // if ((e instanceof ApiError) && (e.status === 401 || e.status === 403)) setByok("");
    // (Optional — up to planner; SC-05 strict reading recommends unconditional clear.)
  } finally {
    setIsRunning(false);
  }
}
```

**Mount-effect pattern** — no direct codebase analog, copy from RESEARCH Example 2 (lines 566-578):
```typescript
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

**Error-surface JSX pattern** — `frontend/components/dev-login-form.tsx` lines 88-94:
```typescript
{error ? (
  <p
    role="alert"
    className="text-sm text-destructive"
  >
    {error}
  </p>
) : null}
```

**Phase 20 has 6 error shapes (see UI-SPEC §Error State Visual Specs E1..E5 + E-fallback).** The `role="alert"` + `text-sm text-destructive` pattern above is the baseline for **E1 inline validation**. E2–E5 use the shadcn `<Alert>` primitive (`frontend/components/ui/alert.tsx`, lines 22-35), which already sets `role="alert"` via `data-slot="alert"` and provides the `variant: "destructive"` styling. E3 (`401/403`) uses `<Alert variant="destructive">`; E2 (`429`) uses `<Alert>` with custom amber classes; E4 (`502 infra_error`) uses custom amber; E5 (`network`) uses default `<Alert>`.

**Spinner-in-button pattern** — `frontend/components/dev-login-form.tsx` lines 78-86:
```typescript
{isPending ? (
  <>
    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
    <span className="sr-only">Signing in…</span>
    <span aria-hidden="true">Signing in…</span>
  </>
) : (
  <span>Dev Login</span>
)}
```

**Phase 20 Deploy button** uses the same in-button spinner pattern, but via the shadcn `<Button>` + `<Spinner>` primitive (UI-SPEC §Deploy button):
```typescript
<Button type="submit" disabled={!canDeploy} aria-busy={isRunning} className="w-full">
  {isRunning ? (
    <><Spinner className="size-4 motion-reduce:animate-none" aria-hidden="true" /> Running…</>
  ) : uiError?.kind === "rate_limited" ? `Retry in ${remaining}s` : "Deploy"}
</Button>
```

**`aria-busy` pattern** — `frontend/components/dev-login-form.tsx` line 61 sets `aria-busy={disabled}` on the `<button>`. Phase 20 extends this to the outer `<form>` (UI-SPEC §A11y checklist bullet 4).

**Focus-on-verdict pattern** — no codebase analog (net-new). Use `useRef<HTMLDivElement>(null)` + `useEffect` watching `verdict`:
```typescript
const cardRef = useRef<HTMLDivElement>(null);
useEffect(() => {
  if (verdict) cardRef.current?.focus();
}, [verdict]);
```
Card gets `tabIndex={-1}` per UI-SPEC §A11y bullet 2. Pattern from RESEARCH Q7 bullet 4.

**Retry countdown hook** — no codebase analog. Use RESEARCH Pattern 4 (`useRetryCountdown`) verbatim, or inline the target-timestamp variant. Keep `onExpire` stable via `useCallback(() => setUiError(null), [])`.

---

### 4. `frontend/components/run-result-card.tsx`  (NEW — pure display)

**Analog:** `frontend/components/ui/alert.tsx` — closest "prop-driven colored surface" primitive in the repo. Same compositional shape (`Card` or `Alert` outer shell + tiny data-slotted subcomponents). But there's no existing "metric grid" analog; that piece is net-new.

**Outer-shell pattern** (from `frontend/components/ui/card.tsx` lines 5-16, adapted with UI-SPEC `role="status"` override):
```typescript
<Card
  role="status"
  aria-live="polite"
  tabIndex={-1}
  ref={cardRef}
  className="p-6"
>
  <CardContent className="flex flex-col gap-4 p-0">
    {/* header row, metadata grid, stderr accordion */}
  </CardContent>
</Card>
```

**Badge pattern** — `frontend/components/ui/badge.tsx` lines 28-44. Phase 20 maps `verdict.verdict` / `verdict.category` to Tailwind classes on the Badge (see UI-SPEC §Header row mapping table). Copy the mapping verbatim from UI-SPEC lines 326-333:

| `verdict.verdict` / `verdict.category` | Tailwind class on Badge |
|----------------------------------------|--------------------------|
| `PASS` | `bg-emerald-600 text-white border-transparent` |
| `FAIL` (ASSERT_FAIL / INVOKE_FAIL / BUILD_FAIL / PULL_FAIL / CLONE_FAIL / TIMEOUT / LINT_FAIL) | `bg-destructive text-destructive-foreground border-transparent` |
| `INFRA_FAIL` | `bg-amber-500 text-white border-transparent` |
| `STOCHASTIC` | `bg-yellow-500 text-black border-transparent` |
| `SKIP` | `bg-slate-400 text-white border-transparent` |

**Source-of-truth for the category enum:** `api_server/src/api_server/models/runs.py` lines 27-46 (`class Category(str, Enum)`). RESEARCH Example 3 lines 585-603 contains the same mapping table — stay consistent with UI-SPEC.

**Accordion pattern** — `frontend/components/ui/accordion.tsx` (all 67 lines). UI-SPEC §stderr tail lines 361-380 gives the exact JSX:
```typescript
<Accordion
  type="single"
  collapsible
  defaultValue={verdict.verdict !== "PASS" ? "stderr" : undefined}
>
  <AccordionItem value="stderr" className="border-t">
    <AccordionTrigger className="text-sm">
      stderr tail ({verdict.stderr_tail?.split("\n").length ?? 0} lines)
    </AccordionTrigger>
    <AccordionContent>
      <pre className="max-h-80 overflow-auto rounded-md bg-muted p-3
                      font-mono text-xs leading-relaxed text-muted-foreground
                      whitespace-pre-wrap break-words">
        {verdict.stderr_tail || "(no output)"}
      </pre>
    </AccordionContent>
  </AccordionItem>
</Accordion>
```

**Metadata grid** — net-new; UI-SPEC §Metadata grid lines 337-353 gives the exact `<dl>`/`<dt>`/`<dd>` pattern. Copy literal.

**Copy-button pattern** — no full codebase analog for the "copy → swap icon for 1.5s" UX, but `<Button variant="ghost" size="icon-sm">` is a stock shadcn combination (defined in `frontend/components/ui/button.tsx` lines 11-30). Use `navigator.clipboard.writeText(verdict.run_id)` + `useState` for the "just copied" flag.

---

### 5. `frontend/app/playground/page.tsx`  (EDIT — swap component mount)

**Analog:** self. This is a 36-line file; only 2 lines change.

**Current imports block** (`frontend/app/playground/page.tsx` lines 1-6):
```typescript
"use client"

import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { AgentConfigurator } from "@/components/agent-configurator"
import { Footer } from "@/components/footer"
```

**Phase 20 edit:** replace line 5 (`import { AgentConfigurator }`) with `import { PlaygroundForm } from "@/components/playground-form"`.

**Current mount-point** (line 30): `<AgentConfigurator />` → replace with UI-SPEC §Form + result container shape:
```typescript
<div className="mx-auto max-w-2xl">
  <PlaygroundForm />
</div>
```

**Everything else stays byte-for-byte** — chrome (`<Navbar>`, `<ParticleBackground>`, `<Footer>`), the outer wrapper `<main className="relative min-h-screen overflow-x-hidden bg-background">`, the orange `<h1>Agent <span className="text-primary">Playground</span></h1>` heading, the `<p className="mt-2 text-sm text-muted-foreground sm:text-base">` subtitle, the existing container classes `mx-auto max-w-7xl px-4 pb-16 pt-24 sm:px-6 sm:pb-20 sm:pt-28 lg:px-8`. CONTEXT D-11 + UI-SPEC §Existing chrome.

**The "Alex Chen" fake user prop** on `<Navbar>` (page.tsx lines 13-17) also stays — CONTEXT D-11 explicitly notes it's wired in and to be removed only when auth lands (Phase 22+).

---

### 6. DELETE files (CONTEXT D-10, SC-07, SC-08, RESEARCH Pitfall 8)

Delete the entire mock subtree:

| File | Why deleted | Grep check after delete |
|------|-------------|--------------------------|
| `frontend/components/agent-configurator.tsx` (1001 lines) | Root mock component | — |
| `frontend/components/agent-card.tsx` | Imports `defaultClones` mock array | `grep -r "defaultClones" frontend/` → 0 matches |
| `frontend/components/model-selector.tsx` | Imports `openRouterModels` mock array | `grep -r "openRouterModels" frontend/` → 0 matches |
| `frontend/components/a2a-network.tsx` | Only imported by `agent-configurator` | `grep -r "A2ANetwork\b" frontend/` → 0 matches |
| `frontend/components/task-orchestrator.tsx` | Only imported by `agent-configurator` | `grep -r "TaskOrchestrator\b" frontend/` → 0 matches |

**One bonus transitive import to handle:** `frontend/components/playground-section.tsx:3` imports `AgentConfigurator`. **Inspect that file**: if it's only used on the `/playground` route (already replaced) it is also dead code and should be removed. If it's used elsewhere (marketing pages) it must either be rewritten to not depend on the configurator or kept as a v0-cosmetic stub. Planner to verify with `grep -r "playground-section\|PlaygroundSection" frontend/`. Not a Phase-20 exit-criterion but a loose-end flag. [Grep result in research: only 1 match, in `playground-section.tsx` itself plus the direct import.]

---

## Shared Patterns

### SP-1. `"use client"` directive as the first line of every client component

**Source:** `frontend/components/dev-login-form.tsx:1`, `frontend/app/playground/page.tsx:1`, `frontend/components/ui/accordion.tsx:1`, `frontend/components/ui/label.tsx:1` — every file that uses hooks or event handlers.

**Apply to:** `frontend/components/playground-form.tsx` (line 1), `frontend/components/run-result-card.tsx` (line 1 — even though it's pure display, it uses `useRef`/`useState` for the copy-button + accordion).

**Excerpt:**
```typescript
"use client";
```

### SP-2. `cn()` utility for conditional Tailwind class merging

**Source:** `frontend/lib/utils.ts` (imported in `frontend/components/dev-login-form.tsx:7`, and every `frontend/components/ui/*.tsx`).

**Apply to:** both new components, every time two class groups need to merge (e.g., Badge class-map + `className` prop, Alert variant + amber override classes).

**Excerpt from** `frontend/components/ui/alert.tsx:31`:
```typescript
className={cn(alertVariants({ variant }), className)}
```

### SP-3. Error → UI surface via `role="alert"` + `text-destructive`

**Source:** `frontend/components/dev-login-form.tsx` lines 88-94.

**Apply to:** Every validation-error site in `<PlaygroundForm>` (E1 inline errors under fields), every non-field error at the form level (fallback path). The `<Alert>` primitive already carries `role="alert"`; use the raw `<p role="alert">` form only for field-specific inline errors (UI-SPEC §E1).

**Excerpt:**
```typescript
{error ? (
  <p role="alert" className="text-sm text-destructive">
    {error}
  </p>
) : null}
```

### SP-4. In-flight `aria-busy` + spinner

**Source:** `frontend/components/dev-login-form.tsx` lines 58-86.

**Apply to:** the Deploy `<Button>` (`aria-busy={isRunning}`) AND the outer `<form>` (UI-SPEC §A11y bullet 4 extension — form level too).

**Excerpt (button-level, dev-login-form.tsx:58-62):**
```typescript
<button
  type="button"
  onClick={handleLogin}
  disabled={disabled}
  aria-busy={disabled}
```

Phase 20 extends to the form:
```typescript
<form aria-busy={isRunning} onSubmit={(e) => { e.preventDefault(); onDeploy(); }}>
```
The `onSubmit + preventDefault` wrapper is mandatory (RESEARCH Pitfall 7 — Enter-in-field otherwise reloads page).

### SP-5. Network vs HTTP error discrimination via `instanceof ApiError`

**Source:** `frontend/components/dev-login-form.tsx` lines 41-48.

**Apply to:** The baseline of `parseApiError`'s first two branches (RESEARCH Pattern 3, lines 358-365). This preserves the idiomatic "TypeError = network fail, ApiError = HTTP fail" split the repo already uses.

**Excerpt:**
```typescript
} catch (err) {
  // Network errors (TypeError) vs HTTP errors (ApiError).
  if (err instanceof ApiError) {
    setError("Login failed. Check the API server is running and try again.");
  } else {
    setError("Could not reach the server. Check your connection.");
  }
}
```

Phase 20 replaces the inner branching with the full `parseApiError` discriminated union — but the outer `try/catch` shape is identical.

### SP-6. Networking path — `next.config.mjs` rewrite + `credentials: "include"`

**Source:** `frontend/next.config.mjs` lines 16-30 (the three rewrite rules) + `frontend/lib/api.ts:25` (`credentials: "include"`).

**Apply to:** every fetch in `<PlaygroundForm>`. All calls use the `/api/v1/*` prefix (dev-time rewrite to `:8000/v1/*`, same-origin in prod behind Caddy). **Never** hit `http://127.0.0.1:8000` from the browser directly — CORS was never configured and won't be in Phase 20.

**Excerpt from** `frontend/next.config.mjs:18-20`:
```javascript
{
  source: "/api/v1/:path*",
  destination: `${API_PROXY_TARGET}/v1/:path*`,
},
```

Call sites in Phase 20:
- `apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes")` — maps to `GET :8000/v1/recipes`
- `apiPost<RunResponse>("/api/v1/runs", body, headers)` — maps to `POST :8000/v1/runs`

---

## No Analog Found

| File / Pattern | Reason | Planner should use |
|----------------|--------|---------------------|
| `parseApiError` discriminated union | Repo has never had a Stripe-shape error envelope before; `dev-login-form.tsx` uses stringly-typed error messages only | RESEARCH Pattern 3 lines 337-404 (verbatim) |
| `useRetryCountdown` 429 timer | No codebase analog | RESEARCH Pattern 4 lines 413-434; prefer target-timestamp variant for tab-background survival |
| Focus-on-verdict `useRef + useEffect` | No existing post-action focus-shift in the repo | UI-SPEC §A11y bullet 2 + RESEARCH Q7 bullet 4 |
| Verdict metadata `<dl>` grid | No existing key/value dataset in the repo | UI-SPEC §Metadata grid lines 337-353 (verbatim) |
| `run_id` copy-to-clipboard with icon swap | No existing clipboard interaction | UI-SPEC §run_id copy (Button ghost icon-sm + `navigator.clipboard.writeText`) |

---

## Metadata

**Analog search scope:**
- `frontend/lib/` (2 files — both read)
- `frontend/components/` (14 non-ui files — key ones read; agent-* and a2a-* read only for delete-confirmation)
- `frontend/components/ui/` (57 shadcn primitives — the 9 relevant ones read exhaustively: label, input, textarea, button, badge, card, alert, accordion, spinner)
- `frontend/app/playground/page.tsx` (full read)
- `frontend/next.config.mjs` (full read)
- `api_server/src/api_server/models/{recipes,runs,errors}.py` (all 3 full read — source of truth for TS mirrors)

**Files scanned:** ~24 code files directly, plus Grep sweeps for `apiGet|apiPost|apiDelete` (5 results, all mapped), `defaultClones|openRouterModels` (3 files, all marked for delete), and analog-confirming import patterns.

**Pattern extraction date:** 2026-04-17

**Confidence:** HIGH on all analogs. `dev-login-form.tsx` is an unusually tight structural analog for `playground-form.tsx` — Phase 20 is `dev-login-form` scaled up 4x with a richer error model and a sibling display component. Executor should be able to type the new files mostly by pattern-match against the analog file plus the RESEARCH excerpts already locked verbatim.
