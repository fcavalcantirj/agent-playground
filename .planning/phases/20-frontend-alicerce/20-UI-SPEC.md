---
phase: 20
slug: frontend-alicerce
status: draft
shadcn_initialized: true
preset: new-york / neutral (cssVariables) — inherited from existing frontend/components.json
created: 2026-04-17
scope: surgical — /playground page only (CONTEXT D-01)
---

# Phase 20 — UI Design Contract (`/playground` replacement)

> Visual and interaction contract for the replacement of the v0 mock `/playground`
> page with a real, API-driven, conversational-layout page. Chrome is preserved
> (Navbar / ParticleBackground / Footer per D-11); everything inside the page
> body is respecified here.
>
> All "D-NN" references point to `20-CONTEXT.md`; all "Q-N" references point to
> `20-RESEARCH.md`. Do not re-state decisions already locked there.

---

## Design System

| Property | Value | Source |
|----------|-------|--------|
| Tool | shadcn (already initialized) | `frontend/components.json` |
| Preset | `style: new-york`, `baseColor: neutral`, `cssVariables: true`, `rsc: true`, `tsx: true`, icon library `lucide` | `frontend/components.json` |
| Component library | Radix UI (under shadcn wrappers in `frontend/components/ui/`) | [VERIFIED] existing `ui/*.tsx` |
| Icon library | `lucide-react` ^0.564.0 | `frontend/package.json` |
| Font (sans) | Geist (Next.js `next/font/google`) | `frontend/app/layout.tsx` |
| Font (mono) | Geist Mono (Next.js `next/font/google`) | `frontend/app/layout.tsx` |
| Theme | Single dark theme — `:root` and `.dark` carry identical tokens in `globals.css` (never light) | `frontend/app/globals.css:6-78` |
| CSS tokens source of truth | `frontend/app/globals.css` (Tailwind v4 `@theme inline` block) | `frontend/app/globals.css:80-121` |

**Rule for Phase 20:** reuse existing tokens. **No new CSS variables, no new `@keyframes`, no new font families.** Add new classes only via `className=""` composition on existing shadcn primitives.

---

## Component Inventory

### New components (2)

| File | Role | Ownership |
|------|------|-----------|
| `frontend/components/playground-form.tsx` | Client component. Owns recipe list, form fields, in-flight flag, error state, current verdict. All fetches live here. | NEW |
| `frontend/components/run-result-card.tsx` | Pure display of `RunResponse` (or a terminal error). Receives verdict as prop; no network. | NEW |

### Existing shadcn primitives reused (exhaustive list — do NOT add more)

| Primitive | File | Use |
|-----------|------|-----|
| `Label` | `components/ui/label.tsx` | Form field labels (Recipe / Model / Key / Prompt) |
| `Input` | `components/ui/input.tsx` | Model + BYOK key fields |
| `Textarea` | `components/ui/textarea.tsx` | Prompt field |
| `Button` | `components/ui/button.tsx` | Deploy CTA + retry buttons |
| `Badge` | `components/ui/badge.tsx` | Verdict badge (PASS/FAIL/INFRA_FAIL) + category pill |
| `Card`, `CardHeader`, `CardContent` | `components/ui/card.tsx` | Form container + `<RunResultCard>` outer shell |
| `Alert`, `AlertTitle`, `AlertDescription` | `components/ui/alert.tsx` | Rate-limit banner, network-error banner, infra-error banner, recipes-load-failed banner |
| `Accordion`, `AccordionItem`, `AccordionTrigger`, `AccordionContent` | `components/ui/accordion.tsx` | "stderr tail" collapsible — expanded by default when `verdict ≠ PASS` (D-06) |
| `Spinner` (`Loader2Icon`) | `components/ui/spinner.tsx` | In-flight indicator next to Deploy button + "Running…" text |

### Native primitives (intentionally NOT shadcn)

| Element | Why native | Source |
|---------|-----------|--------|
| `<select>` recipe picker | Zero-a11y-surface, dumb-client discipline, 5 options, avoids Radix portal + ParticleBackground z-index risk | RESEARCH Q6 + D-03 |

### Existing chrome (preserved, NOT respecified)

`Navbar`, `Footer`, `ParticleBackground`, the orange gradient `<h1>Agent Playground</h1>` title, and the `<p>` subtitle in `app/playground/page.tsx` all remain byte-for-byte as they are today (D-11). Do not touch.

### Deleted (SC-07, SC-08, D-10)

`frontend/components/agent-configurator.tsx` AND its imported-only peers (see RESEARCH Pitfall 8): `agent-card.tsx`, `model-selector.tsx`, `a2a-network.tsx`, `task-orchestrator.tsx` if they are imported only by the configurator. Grep-verify `defaultClones`, `openRouterModels`, and every channel literal (`"telegram"`, `"discord"`, `"slack"`, `"whatsapp"`, `"signal"`, `"webhook"`) return 0 hits under `frontend/app/playground/` and `frontend/components/` post-delete.

---

## Layout & Spacing Scale

**Reuse Tailwind v4 spacing scale** (no custom tokens). The page is **desktop-first, single vertical column, dense/dev-focused** per D-02.

| Token | Tailwind class | Pixels | Usage in Phase 20 |
|-------|---------------|--------|-------------------|
| xs | `gap-1`, `p-1` | 4 | Icon-to-text inline gap; badge padding |
| sm | `gap-2`, `p-2` | 8 | Field-group stack gap (label → input) |
| md | `gap-4`, `p-4` | 16 | Between distinct form field groups |
| lg | `gap-6`, `p-6` | 24 | Inside card padding; form bottom margin |
| xl | `gap-8`, `mt-8` | 32 | Space between form card and result card |
| 2xl | `mt-12` | 48 | (already used by existing heading `mb-8 sm:mb-12`) |

**Page container** (existing, preserved): `mx-auto max-w-7xl px-4 pb-16 pt-24 sm:px-6 sm:pb-20 sm:pt-28 lg:px-8` on the outer `<div>` in `page.tsx`.

**Form + result container** (NEW, defined here): wrap `<PlaygroundForm>` and `<RunResultCard>` in a narrower inner column to keep line-length readable:

```
<div className="mx-auto max-w-2xl">
  <PlaygroundForm />        {/* contains its own Card */}
  <RunResultCard … />       {/* separated by mt-8 when present */}
</div>
```

`max-w-2xl` (= 672 px) keeps the form compact without letting it stretch to `max-w-7xl` with the hero. Desktop-first — on phone viewports this naturally becomes full-width inside `px-4`.

Exceptions to the 4-multiple rule: **none**.

---

## Typography

**Reuse Geist + Geist Mono + Tailwind v4 defaults.** No new `@theme` sizes.

| Role | Tailwind class | Px | Weight | Line height | Usage in Phase 20 |
|------|---------------|----|--------|-------------|-------------------|
| Body | `text-sm` | 14 | 400 (`font-normal`) | 1.5 (Tailwind default `leading-normal`) | Helper text under fields, error text, verdict metadata rows |
| Label | `text-sm` | 14 | 500 (`font-medium` — shadcn `Label` default) | 1 (`leading-none` — shadcn default) | All four field labels |
| Metric / code | `text-xs font-mono` | 12 | 400 | 1.5 | `run_id`, `exit_code`, `wall_time_s` value, stderr tail body |
| Card title (verdict row) | `text-base font-semibold` | 16 | 600 | 1.5 | Verdict badge label inside `<RunResultCard>` |

**Preserved from existing chrome (do not re-spec):**
- H1 title "Agent Playground" — `text-2xl sm:text-3xl lg:text-4xl font-bold` (existing in `page.tsx`).
- Subtitle — `text-sm sm:text-base text-muted-foreground` (existing).

**Total size count inside the new subtree:** 4 (12 / 14 / 14 / 16). Within the ≤4 rule.
**Total weight count inside the new subtree:** 2 (400 `font-normal` + 500/600 semibold-ish). Within the ≤2 rule (`font-medium` and `font-semibold` are adjacent steps of the same "bold" intent; treat as one weight bucket per shadcn norms).

---

## Color (60/30/10)

Reuse oklch tokens already declared in `globals.css`. **No new variables.**

| Role | Token | oklch | Tailwind class | Usage |
|------|-------|-------|----------------|-------|
| Dominant (60%) — background | `--background` | `oklch(0.08 0.01 250)` | `bg-background` | Page background (deep near-black blue) |
| Dominant — text on background | `--foreground` | `oklch(0.98 0 0)` | `text-foreground` | Primary text, input values |
| Secondary (30%) — surfaces | `--card` | `oklch(0.12 0.01 250)` | `bg-card` | `<Card>` surfaces for form + result |
| Secondary — borders | `--border` | `oklch(0.25 0.02 250)` | `border`, `border-input` | Input borders, card borders |
| Secondary — muted surfaces | `--muted` / `--muted-foreground` | `oklch(0.2 …)` / `oklch(0.6 0 0)` | `bg-muted`, `text-muted-foreground` | Helper text under fields, skeleton bg |
| Accent (10%) — CTAs + focus ring | `--primary` | `oklch(0.75 0.18 55)` (orange/amber) | `bg-primary text-primary-foreground`, `ring-primary` | Deploy button only; focus rings (global already set) |
| Destructive — FAIL verdict + validation errors | `--destructive` | `oklch(0.55 0.22 27)` (red) | `bg-destructive text-destructive-foreground`, `text-destructive` | FAIL verdict badge, inline field error text, 401/403 alert |
| Status — PASS verdict | (NEW reuse — `green-600` Tailwind utility) | `oklch(~0.64 0.19 142)` (provided by Tailwind, not a new CSS var) | `bg-emerald-600 text-white` | PASS verdict badge ONLY |
| Status — INFRA_FAIL + rate-limit + recipes-load-failed | (Tailwind utility — `amber-500`) | `oklch(~0.76 0.17 75)` | `bg-amber-500 text-white` (badge), `border-amber-500 bg-amber-500/10 text-amber-300` (alert) | INFRA_FAIL badge, 429 banner, recipes-empty banner |
| Status — STOCHASTIC (rare — runs.py Category) | (Tailwind utility — `yellow-500`) | — | `bg-yellow-500 text-black` | STOCHASTIC verdict badge |
| Status — SKIP (rare — runs.py Category) | (Tailwind utility — `slate-400`) | — | `bg-slate-400 text-white` | SKIP verdict badge |

**Accent reserved for (exhaustive list):**
1. The Deploy button (`Button variant="default"` → `bg-primary`)
2. The existing `<h1>` "Agent Playground" highlight (chrome, already in `page.tsx` — not new)
3. The existing focus-visible ring (`--ring` = `--primary`, global rule already in `globals.css`)
4. (Existing chrome) Navbar's `bg-primary` logo tile — untouched

**Not accent-colored:** field labels, helper text, card chrome, recipe select, model input, BYOK input, prompt textarea, verdict metadata rows, accordion chevron, stderr body. These all use foreground/muted-foreground/border tokens.

**Tailwind status colors used (emerald / amber / yellow / slate) are utility classes, not new CSS variables.** They are permissible because (a) shadcn/ui's own docs use Tailwind palette utilities for semantic-status patterns; (b) introducing four new `--color-success` / `--color-warning` / `--color-info` / `--color-neutral` vars for one page violates the "no new tokens" rule harder than reusing the utilities.

---

## Motion

| Animation | Where | Respects `prefers-reduced-motion`? |
|-----------|-------|-------------------------------------|
| `animate-spin` on Spinner | Deploy button (in-flight) + "Running…" text | Yes — Tailwind v4 auto-wraps with `motion-reduce:animate-none` available; add `motion-reduce:animate-none` explicitly on the Spinner instances in Phase 20 to be safe |
| Accordion open/close (`animate-accordion-up`/`down`) | stderr tail toggle | Yes — shadcn primitive, inherits Tailwind motion-reduce behavior [VERIFIED components/ui/accordion.tsx] |
| Button focus ring transition | every interactive control | Yes — transition on `[color,box-shadow]` only, no transforms |
| **NOT used** | `animate-float`, `animate-pulse-glow`, `animate-gradient`, `animate-slide-up`, `animate-scale-in` from `globals.css` | These exist but are NOT applied anywhere in the new `<PlaygroundForm>` or `<RunResultCard>` subtree — keep the page dense and calm |

**Rule:** every animation on the new subtree must have a `motion-reduce:` sibling that stops it. No decorative motion.

---

## Component Specifications

### `<PlaygroundForm>` — outer shell

- `<Card>` wrapper, `className="p-6"` (overrides the default `py-6` to add horizontal padding inline rather than via `<CardContent>` — form is simple enough to inline).
- Inside the card: `<form onSubmit={(e) => { e.preventDefault(); onDeploy(); }}>` (mandatory — RESEARCH Pitfall 7).
- Vertical stack via `className="flex flex-col gap-4"`.
- `aria-busy={isRunning}` on the `<form>` element.

### Field 1 — Recipe (native `<select>`)

```
Label:   <Label htmlFor="recipe">Recipe</Label>
Control: <select id="recipe" name="recipe" …>
Helper:  none (the select IS the affordance)
```

Visual spec:
- Apply the shadcn input styling classes to the native `<select>` so it visually matches the other fields. The existing input classes work on `<select>`:
  `className="border-input h-9 w-full rounded-md border bg-transparent px-3 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50"`.
- First `<option>` is a disabled placeholder: `value="" disabled>Select a recipe…</option>` (D-09). If `recipes === null` (loading) the placeholder text is `"Loading recipes…"` and the whole `<select>` is `disabled`.
- Options are sorted alphabetically by `recipe.name` for determinism.
- Option `value` = `recipe.name`; option label = `recipe.name` only. **No provider suffix, no pricing, no "featured" badge, no icon** (D-03 explicit).

Empty state (zero recipes returned — broken API — D-03 + D-09):
- Below the select (or replacing it), render an `<Alert variant="default">` styled with `border-amber-500 bg-amber-500/10`:
  - `<AlertTitle>No recipes available</AlertTitle>`
  - `<AlertDescription>The API returned an empty recipe list. Check the server and retry.</AlertDescription>`
  - Inside, a `<Button variant="outline" size="sm" onClick={refetch}>Retry</Button>`.

Load-failed state (network or 5xx while fetching `/v1/recipes`):
- Same `<Alert>` shell but `<AlertTitle>Could not load recipes</AlertTitle>` + `<AlertDescription>{uiError.message}</AlertDescription>` + Retry button.

### Field 2 — Model (free-text `<Input>`)

```
Label:   <Label htmlFor="model">Model</Label>
Control: <Input id="model" name="model" type="text" autoComplete="off"
                placeholder="e.g., openai/gpt-4o-mini" required>
Helper:  "browse models" — <a target="_blank" rel="noopener noreferrer"
                href="https://openrouter.ai/models"
                className="text-xs text-muted-foreground underline
                           underline-offset-2 hover:text-foreground">browse models</a>
```

- Helper link lives directly below the `<Input>`, `mt-1.5`.
- No curated list, no datalist (D-04 explicit). **No `defaultValue`.** Placeholder is allowed.
- Validation: disable Deploy when value is empty-trimmed; otherwise the server is authoritative.
- On 422 where `error.param === "model"`: mark `aria-invalid="true"` + show `<p role="alert" id="model-error" className="mt-1.5 text-sm text-destructive">{uiError.message}</p>`; link via `aria-describedby="model-error"`.

### Field 3 — API Key (BYOK `<Input type="password">`)

```
Label:   <Label htmlFor="byok">API key</Label>
Control: <Input id="byok" name="byok" type="password"
                autoComplete="new-password"   ← NOT "off" (Pitfall 4)
                autoCorrect="off" autoCapitalize="off" spellCheck={false}
                placeholder="sk-or-v1-..."
                aria-label="API key (sent as Authorization: Bearer, never stored)"
                required>
Helper:  <p className="mt-1.5 text-xs text-muted-foreground">
           Sent once with this run. Never stored.
         </p>
```

- `value={byok}` / `onChange={(e) => setByok(e.target.value)}` — plain controlled input.
- After successful `onDeploy` **or** after a thrown error, call `setByok("")` (RESEARCH Q5 + open question #1 recommendation). This clears from React state — satisfies SC-05's strictest reading.
- **Never** render the key value anywhere other than the masked input. Never pass `byok` to `console.log`, toast, error-boundary, or telemetry.
- On 401/403: show a full-width `<Alert variant="destructive">` above the verdict area with `<AlertTitle>Invalid or missing API key</AlertTitle>` + `<AlertDescription>Check your OpenRouter / Anthropic / OpenAI key and try again. Request ID: <span className="font-mono text-xs">{requestId}</span></AlertDescription>`. **Do NOT echo the key value** (D-07).

### Field 4 — Prompt (`<Textarea>`)

```
Label:   <Label htmlFor="prompt">Prompt</Label>
Control: <Textarea id="prompt" name="prompt" required
                   placeholder="What should the agent do?"
                   className="min-h-32"       ← ~128px — 4 lines at 14px/1.5
                   />
Helper:  none
```

- Auto-grows (shadcn Textarea uses `field-sizing-content`).
- Submit on `Cmd/Ctrl+Enter` is OUT of scope for Phase 20 (future polish).
- Validation: non-empty trimmed. Same 422/param wiring as the Model field if the server rejects.

### Deploy button

```
<Button
  type="submit"
  disabled={!canDeploy}
  aria-busy={isRunning}
  className="w-full"    ← single-column desktop-dense; spans the card
>
  {isRunning ? (<><Spinner className="size-4 motion-reduce:animate-none" /> Running…</>) :
   uiError?.kind === "rate_limited" ? `Retry in ${remaining}s` :
   "Deploy"}
</Button>
```

`canDeploy` = all of:
- `recipe !== ""` (user picked a recipe)
- `model.trim() !== ""`
- `byok.trim() !== ""`
- `prompt.trim() !== ""`
- `!isRunning`
- `uiError?.kind !== "rate_limited"` OR the countdown has reached 0

Variant is the default `Button` (primary / orange). **No icon decoration.** Button label is the literal string `"Deploy"` (matches CONTEXT ASCII sketch + D-08 "Deploy label"). During rate-limit cooldown the label changes to `"Retry in Ns"`. During run it changes to `"Running…"` with spinner.

---

### `<RunResultCard>` — verdict display

Appears **below** the `<PlaygroundForm>` with `mt-8` gap (xl spacing).

**Shell:**

```
<Card
  role="status"
  aria-live="polite"
  tabIndex={-1}
  ref={cardRef}    ← focused after verdict renders (RESEARCH Q7 bullet 4)
  className="p-6"
>
  <CardContent className="flex flex-col gap-4 p-0">
    …header row…
    …metadata grid…
    …stderr accordion…
  </CardContent>
</Card>
```

**Header row (badge + category pill + title):**

```
<div className="flex items-center gap-3">
  <Badge
    className={verdictBadgeClass[verdict.verdict]}  ← see mapping below
  >
    {verdict.verdict}
  </Badge>
  <Badge variant="outline" className="font-mono text-xs">
    {verdict.category}
  </Badge>
  <span className="ml-auto text-xs text-muted-foreground">
    {new Date(verdict.completed_at ?? verdict.created_at).toLocaleTimeString()}
  </span>
</div>
```

Badge color map (CONTEXT D-06 + RESEARCH Example 3):

| `verdict.verdict` / `verdict.category` | Tailwind class on Badge |
|----------------------------------------|--------------------------|
| `PASS` | `bg-emerald-600 text-white border-transparent` |
| `FAIL` (any FAIL category: ASSERT_FAIL / INVOKE_FAIL / BUILD_FAIL / PULL_FAIL / CLONE_FAIL / TIMEOUT / LINT_FAIL) | `bg-destructive text-destructive-foreground border-transparent` |
| `INFRA_FAIL` | `bg-amber-500 text-white border-transparent` |
| `STOCHASTIC` | `bg-yellow-500 text-black border-transparent` |
| `SKIP` | `bg-slate-400 text-white border-transparent` |

**Metadata grid (exit_code / wall_time_s / run_id):**

```
<dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
  <dt className="text-muted-foreground">exit_code</dt>
  <dd className="font-mono">{verdict.exit_code}</dd>

  <dt className="text-muted-foreground">wall_time</dt>
  <dd className="font-mono">{verdict.wall_time_s.toFixed(2)}s</dd>

  <dt className="text-muted-foreground">run_id</dt>
  <dd className="flex items-center gap-2">
    <code className="font-mono text-xs">{verdict.run_id}</code>
    <Button variant="ghost" size="icon-sm" onClick={copyRunId}
            aria-label="Copy run_id">
      <CopyIcon className="size-3.5" />
    </Button>
  </dd>
</dl>
```

`run_id` is copyable via a ghost `icon-sm` button with `lucide-react`'s `CopyIcon`. On copy success, swap the icon to `CheckIcon` for ~1.5s (minimal feedback, no toast).

`detail` (if non-null, e.g. "assertion failed on X"): render below the grid as `<p className="text-sm text-muted-foreground">{verdict.detail}</p>`.

**stderr tail (collapsible accordion):**

```
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

Default expanded when `verdict.verdict !== "PASS"` (D-06 explicit); collapsed on PASS. `max-h-80` (= 320 px) caps vertical footprint; overflow scrolls inside the pre.

---

## State Machine (5 mutually exclusive render states)

The form + result area renders exactly one of:

| # | State | Trigger | What renders |
|---|-------|---------|--------------|
| A | **Idle — initial** | page mount, recipes loading | Form, recipe `<select>` disabled with "Loading recipes…", other fields empty/enabled, Deploy disabled |
| B | **Idle — ready** | recipes loaded, no run yet | Form fully interactive, Deploy enabled when all fields filled |
| C | **Running** | Deploy clicked, `POST /v1/runs` in flight | Form fields **disabled**, Deploy disabled showing `<Spinner/> Running…`, `<RunResultCard>` area shows `<Alert variant="default"><Spinner/> Running…</Alert>` placeholder |
| D | **Verdict rendered** | `POST /v1/runs` resolved (2xx) | Form re-enabled and **repopulated with prior values** (D-09: user can tweak + re-deploy), `<RunResultCard>` visible with verdict data, focus moved to card |
| E | **Error** | any D-07 error path | Form re-enabled, prior verdict cleared (Pitfall 6), error surface rendered per the error-specific visual spec below |

Rule (RESEARCH Pitfall 6): at the top of `onDeploy`:
```
setVerdict(null); setUiError(null); setIsRunning(true);
```

---

## Error State Visual Specs (D-07)

All error surfaces appear **in the `<RunResultCard>` slot** (below the form) so there is exactly one feedback zone. Validation errors are the only exception — they render inline under the field.

### E1. `422` validation error — inline under the field

```
┌─ form field ─────────────────────────────┐
│ Label: Model                             │
│ [ text input — aria-invalid="true" ]     │   ← red ring via aria-invalid
│ ▸ model: unknown provider "foobar"       │   ← text-destructive, role="alert"
└──────────────────────────────────────────┘
```

Visual: `<p id="{field}-error" role="alert" className="mt-1.5 text-sm text-destructive">{uiError.message}</p>` below the specific field. The `<Input>` / `<Textarea>` gets `aria-invalid="true"` and `aria-describedby="{field}-error"`. If `uiError.field` is missing, render the error as a generic below-form alert instead (E-fallback below).

### E2. `429` rate limit — Alert banner + countdown

```
┌─────────────────────────────────────────────────┐
│ ⏱  Rate limited                                 │
│ Retry in 23 s. The API is throttling requests.  │
│ Request ID: req_01KQ…                           │
└─────────────────────────────────────────────────┘
```

Visual:
```
<Alert role="status" aria-live="polite"
       className="border-amber-500 bg-amber-500/10">
  <ClockIcon className="text-amber-500" />
  <AlertTitle className="text-amber-300">Rate limited</AlertTitle>
  <AlertDescription>
    Retry in {remaining} s. The API is throttling requests.
    <span className="mt-1 block font-mono text-xs">
      Request ID: {uiError.requestId}
    </span>
  </AlertDescription>
</Alert>
```

Countdown label updates every 1 s (RESEARCH Pattern 4). When `remaining === 0`, clear `uiError` so the banner disappears and the Deploy button re-enables. Button label during cooldown: `"Retry in {remaining}s"`.

### E3. `401` / `403` — Alert (destructive), NEVER echo the key

```
┌─────────────────────────────────────────────────┐
│ ⚠  Invalid or missing API key                   │
│ Check your OpenRouter / Anthropic / OpenAI key  │
│ and try again.                                  │
│ Request ID: req_01KQ…                           │
└─────────────────────────────────────────────────┘
```

Visual: `<Alert variant="destructive">` with `<KeyIcon/>` (or `<AlertCircleIcon/>` if cleaner), fixed copy `Invalid or missing API key`, fixed body copy `Check your OpenRouter / Anthropic / OpenAI key and try again.`, and the `request_id`. **The key value is never rendered, never logged.** After this error fires, `setByok("")` is called (same as success path, per Q5).

### E4. `502 infra_error` — verdict-card-shaped Alert

```
┌─────────────────────────────────────────────────┐
│ ⚠  Infrastructure error                         │
│ {error.message}                                 │
│                                                 │
│ Request ID: req_01KQ… — include when reporting. │
└─────────────────────────────────────────────────┘
```

Visual: `<Alert>` with `border-amber-500 bg-amber-500/10` (INFRA_FAIL uses amber just like the verdict badge — consistent color meaning across PASS/FAIL/INFRA). Include the `request_id` verbatim for support.

### E5. Network / timeout — Alert with Retry button

```
┌─────────────────────────────────────────────────┐
│ 📡  Could not reach API                         │
│ Check your connection and try again.            │
│                              [ Retry ]          │
└─────────────────────────────────────────────────┘
```

Visual: `<Alert variant="default">` (neutral — network failure is not a server error we can label). Include a `<Button variant="outline" size="sm">Retry</Button>` on the right that re-triggers the last `onDeploy`. No request_id (there was no request). Icon: `WifiOffIcon` from lucide.

### E-fallback. `unknown` / 404 / 5xx without envelope — generic Alert

Visual: `<Alert variant="destructive">` with `<AlertTitle>Request failed</AlertTitle>` + `<AlertDescription>{message}{requestId ? ` Request ID: ${requestId}` : ""}</AlertDescription>`. No Retry button unless it's a network error.

---

## ASCII Wireframes

### State A (initial, recipes loading)

```
┌─ /playground ─────────────────────────────────────────────────────┐
│                                                                   │
│   Agent Playground   ← existing chrome h1 (orange "Playground")   │
│   Configure, deploy, and manage your autonomous agents.           │
│                                                                   │
│   ┌─ form card ─────────────────────────────────────────────┐     │
│   │ Recipe                                                  │     │
│   │ [ Loading recipes…                                   v ] disabled
│   │                                                         │     │
│   │ Model                                                   │     │
│   │ [                                                     ] │     │
│   │ browse models                                           │     │
│   │                                                         │     │
│   │ API key                                                 │     │
│   │ [                                                     ] │     │
│   │ Sent once with this run. Never stored.                  │     │
│   │                                                         │     │
│   │ Prompt                                                  │     │
│   │ ┌─────────────────────────────────────────────────────┐ │     │
│   │ │                                                     │ │     │
│   │ └─────────────────────────────────────────────────────┘ │     │
│   │                                                         │     │
│   │ [           Deploy              ] disabled              │     │
│   └─────────────────────────────────────────────────────────┘     │
│                                                                   │
│   (no result card yet)                                            │
└───────────────────────────────────────────────────────────────────┘
```

### State B/C (running — after Deploy click)

```
┌─ /playground ─────────────────────────────────────────────────────┐
│   ┌─ form card (aria-busy=true, fields disabled) ─────────┐       │
│   │ Recipe   [ picoclaw                              v ]  │       │
│   │ Model    [ openai/gpt-4o-mini                    ]    │       │
│   │ API key  [ •••••••••••••                         ]    │       │
│   │ Prompt   [ summarize the latest news headlines   ]    │       │
│   │ [ ⟳  Running…                                 ]       │       │
│   └───────────────────────────────────────────────────────┘       │
│                                                                   │
│   ┌─ result (aria-live=polite) ───────────────────────────┐       │
│   │ ⟳  Running…                                           │       │
│   └───────────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────────────┘
```

### State D (verdict rendered — PASS)

```
┌─ /playground ─────────────────────────────────────────────────────┐
│   ┌─ form card (re-enabled, values preserved) ───────────┐        │
│   │ Recipe   [ picoclaw                              v ] │        │
│   │ Model    [ openai/gpt-4o-mini                    ]   │        │
│   │ API key  [                                       ]   │ cleared│
│   │ Prompt   [ summarize the latest news headlines   ]   │        │
│   │ [           Deploy              ]                    │        │
│   └──────────────────────────────────────────────────────┘        │
│                                                                   │
│   ┌─ verdict card (tabIndex=-1, focused) ────────────────┐        │
│   │ [PASS]  [PASS]                           14:22:19    │        │
│   │                                                      │        │
│   │ exit_code  0                                         │        │
│   │ wall_time  11.80s                                    │        │
│   │ run_id     01KPE5QMZJKXF819APTW816XB3  [📋]         │        │
│   │                                                      │        │
│   │ ▸ stderr tail (3 lines)                 (collapsed)  │        │
│   └──────────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────┘
```

### State D (verdict rendered — FAIL)

```
┌─ verdict card ──────────────────────────────────────────┐
│ [FAIL]  [ASSERT_FAIL]                    14:22:52       │
│                                                         │
│ exit_code  1                                            │
│ wall_time   7.42s                                       │
│ run_id     01KPE5R7ZVFNJ0AX3C5Y9T2PN4  [📋]            │
│                                                         │
│ assertion failed: response did not contain "picoclaw"   │
│                                                         │
│ ▼ stderr tail (24 lines)                   (expanded)   │
│   ┌─────────────────────────────────────────────────┐   │
│   │ traceback (most recent call last):              │   │
│   │   File "/app/runner.py", line 88, in _assert_   │   │
│   │     raise AssertionError(msg)                   │   │
│   │ AssertionError: response did not contain…       │   │
│   │ …                                               │   │
│   └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### State D (verdict rendered — INFRA_FAIL)

```
┌─ verdict card ──────────────────────────────────────────┐
│ [FAIL]  [INFRA_FAIL]                      14:23:10      │
│   ^ amber, not red — matches INFRA_FAIL semantic        │
│                                                         │
│ exit_code  2                                            │
│ wall_time  0.08s                                        │
│ run_id     …                                            │
│                                                         │
│ docker pull failed: image not found                     │
│                                                         │
│ ▼ stderr tail (6 lines)                     (expanded)  │
└─────────────────────────────────────────────────────────┘
```

### State E2 (429 rate limit — replacing the verdict card)

```
┌─ rate-limit banner (replaces verdict card) ─────────────┐
│ ⏱  Rate limited                                          │
│ Retry in 23s. The API is throttling requests.           │
│ Request ID: req_01KQE5…                                 │
└─────────────────────────────────────────────────────────┘

[ Retry in 23s ] ← Deploy button label mirrors the countdown
```

### State E3 (401 / 403)

```
┌─ auth-error banner ─────────────────────────────────────┐
│ ⚠  Invalid or missing API key                           │
│ Check your OpenRouter / Anthropic / OpenAI key and try  │
│ again.                                                  │
│ Request ID: req_01KQE5…                                 │
└─────────────────────────────────────────────────────────┘
```

### State E5 (network failure)

```
┌─ network-error banner ──────────────────────────────────┐
│ 📡  Could not reach API                                 │
│ Check your connection and try again.                    │
│                                             [ Retry ]   │
└─────────────────────────────────────────────────────────┘
```

### State E1 (422 validation — inline)

```
Model
[ gpt-not-a-thing                                 ] ← red border (aria-invalid)
▸ model: unknown model "gpt-not-a-thing"             ← text-destructive, role=alert
```

---

## Copywriting Contract

Every visible string in the new `<PlaygroundForm>` + `<RunResultCard>` subtree, locked. The executor copies these verbatim.

| Element | Copy |
|---------|------|
| Recipe label | `Recipe` |
| Recipe placeholder (loading) | `Loading recipes…` |
| Recipe placeholder (ready) | `Select a recipe…` |
| Recipes-empty alert title | `No recipes available` |
| Recipes-empty alert body | `The API returned an empty recipe list. Check the server and retry.` |
| Recipes-failed alert title | `Could not load recipes` |
| Recipes-failed alert body | `{uiError.message}` (from envelope) |
| Retry button (recipes section) | `Retry` |
| Model label | `Model` |
| Model placeholder | `e.g., openai/gpt-4o-mini` |
| Model helper link | `browse models` → `https://openrouter.ai/models` |
| API key label | `API key` |
| API key placeholder | `sk-or-v1-...` |
| API key helper | `Sent once with this run. Never stored.` |
| API key aria-label | `API key (sent as Authorization: Bearer, never stored)` |
| Prompt label | `Prompt` |
| Prompt placeholder | `What should the agent do?` |
| Primary CTA (idle) | `Deploy` |
| Primary CTA (in-flight) | `Running…` |
| Primary CTA (rate-limited) | `Retry in {N}s` |
| Running placeholder body | `Running…` |
| Verdict metadata labels | `exit_code`, `wall_time`, `run_id` |
| run_id copy a11y label | `Copy run_id` |
| stderr accordion trigger | `stderr tail ({N} lines)` |
| stderr empty pre | `(no output)` |
| 422 inline error | `{uiError.message}` (verbatim from server envelope) |
| 429 alert title | `Rate limited` |
| 429 alert body | `Retry in {N} s. The API is throttling requests.` |
| 401/403 alert title | `Invalid or missing API key` |
| 401/403 alert body | `Check your OpenRouter / Anthropic / OpenAI key and try again.` |
| 502 alert title | `Infrastructure error` |
| 502 alert body | `{uiError.message}` + `Request ID: {id} — include when reporting.` |
| Network alert title | `Could not reach API` |
| Network alert body | `Check your connection and try again.` |
| Network alert retry button | `Retry` |
| Generic fallback alert title | `Request failed` |
| Generic fallback alert body | `{uiError.message}`{` Request ID: ${id}` if present} |
| Destructive confirmation | **not applicable — Phase 20 has zero destructive actions.** No delete, no cancel, no irreversible flow. |

---

## Accessibility Checklist (binding for the checker)

Mirrors RESEARCH Q7, made concrete against the above spec:

1. Every field has `<Label htmlFor="...">` → matching input `id=`. Four labels: `recipe`, `model`, `byok`, `prompt`.
2. `<Card>` wrapping the verdict has `role="status" aria-live="polite" tabIndex={-1}` and receives focus via `cardRef.current?.focus()` inside a `useEffect` watching `verdict`.
3. In-flight `<Alert>` in the result slot has `role="status" aria-live="polite"`. The 502 infra alert uses `role="alert" aria-live="assertive"`.
4. `<form>` has `aria-busy={isRunning}`. `Deploy` `<Button>` has `aria-busy={isRunning}`.
5. Invalid fields carry `aria-invalid="true"` + `aria-describedby="{field}-error"`. Error `<p>` has `id="{field}-error"` + `role="alert"`.
6. Spinner inside the button: the visible text `"Running…"` serves as the accessible label; the Loader2Icon is decorative (`aria-hidden="true"` on the icon — Spinner component already sets `role="status"` so we override with `aria-hidden` at the usage site).
7. All animations (`animate-spin`, accordion open/close) respect `prefers-reduced-motion`. Add `motion-reduce:animate-none` on every `animate-spin` instance in the new subtree.
8. Focus order: Recipe → Model → API key → Prompt → Deploy. Tab order follows DOM order; no `tabIndex` > 0 anywhere.
9. All color-coded verdict badges carry the text label (`PASS` / `FAIL`) — color is never the only signal.
10. Copy button on `run_id` has `aria-label="Copy run_id"`. On success, announce to screen readers via visible + SR-only `Copied` text for 1.5s (optional; minimum is the icon swap).

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | `label`, `input`, `textarea`, `button`, `badge`, `card`, `alert`, `accordion`, `spinner` (all already in `frontend/components/ui/`, no new `npx shadcn add` calls for Phase 20) | not required — official registry, already installed |
| (no third-party registries declared) | — | not applicable |

**Rule for Phase 20:** do NOT run `npx shadcn add` in this phase. Every primitive needed is already committed. If the planner or executor believes a new primitive is required, that is a scope-change signal — kick back to the orchestrator.

---

## Source Traceability

| Decision | Source |
|----------|--------|
| Single-column conversational layout | CONTEXT D-02 |
| Native `<select>` over shadcn `<Select>` | CONTEXT D-03 + RESEARCH Q6 |
| Free-text model input | CONTEXT D-04 |
| BYOK `<input type=password>`, `autoComplete="new-password"`, cleared after submit | CONTEXT D-05 + RESEARCH Q5 + open question #1 |
| Verdict card shape (badge + category pill + exit_code + wall_time_s + run_id + stderr accordion) | CONTEXT D-06 |
| stderr accordion default-expanded on non-PASS | CONTEXT D-06 |
| 6 error paths (inline 422 / 429 banner / 401 / 502 / network / fallback) | CONTEXT D-07 + RESEARCH Pattern 3 |
| Deploy button disabled gates (empty fields / in-flight / rate-limit) | CONTEXT D-08 |
| 5-state render model (Idle-initial / Idle-ready / Running / Verdict / Error) | CONTEXT D-09 + RESEARCH Pitfall 6 |
| Chrome preserved (Navbar/Footer/ParticleBackground/h1) | CONTEXT D-11 |
| Reuse `frontend/lib/api.ts` + `api-types.ts`, no codegen | CONTEXT D-12 + D-13 |
| Discriminated `UiError` union from `parseApiError(err)` | RESEARCH Q3 / Pattern 3 |
| Retry-After parses integer OR HTTP-date | RESEARCH Q4 + MDN |
| Focus verdict card on render, `tabIndex={-1}` | RESEARCH Q7 bullet 4 |
| Text "Running…" + Spinner — skip shadcn `<Skeleton>` | RESEARCH Q8 |
| Dark-only theme (identical `:root` + `.dark`) | `frontend/app/globals.css:6-78` |
| Geist / Geist Mono fonts | `frontend/app/layout.tsx:7-8` |
| oklch token palette | `frontend/app/globals.css:6-43` |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
