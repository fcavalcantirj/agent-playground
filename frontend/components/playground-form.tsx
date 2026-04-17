"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Loader2, Clock, WifiOff, AlertCircle, Copy, Check } from "lucide-react";

import { apiGet, apiPost } from "@/lib/api";
import {
  parseApiError,
  useRetryCountdown,
  type RecipeSummary,
  type RunResponse,
  type UiError,
} from "@/lib/api-types";
import { cn } from "@/lib/utils";

// shadcn primitives
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";

// Sibling component — created in Plan 20-04 (same wave).
import { RunResultCard } from "@/components/run-result-card";

/**
 * /playground main form. Single client component owning:
 *   - Recipe list (fetched from GET /api/v1/recipes on mount)
 *   - Form fields: recipe (native <select>), model (free text),
 *     BYOK (<input type="password">), prompt (<Textarea>)
 *   - In-flight flag, current verdict, current UI error
 *
 * Golden rule #2: no client-side catalog. Recipes come from the API.
 * CONTEXT D-05: BYOK cleared after every submit attempt (success or failure).
 * CONTEXT D-07: every error path renders visibly via parseApiError dispatch.
 */
export function PlaygroundForm() {
  // --- State -----------------------------------------------------------
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [recipe, setRecipe] = useState("");
  const [model, setModel] = useState("");
  const [byok, setByok] = useState("");
  const [prompt, setPrompt] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [verdict, setVerdict] = useState<RunResponse | null>(null);
  const [uiError, setUiError] = useState<UiError | null>(null);

  // Stable expire callback for useRetryCountdown (Pitfall: non-stable cb churns the effect).
  const onRetryExpire = useCallback(() => setUiError(null), []);
  const remainingSec = useRetryCountdown(uiError, onRetryExpire);

  // --- Effects ---------------------------------------------------------
  /** Fetch recipes on mount. Refetchable via the retry button in the empty/failed state. */
  const fetchRecipes = useCallback(async () => {
    try {
      const data = await apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes");
      // Alphabetize for deterministic option order (UI-SPEC §Field 1)
      const sorted = [...data.recipes].sort((a, b) => a.name.localeCompare(b.name));
      setRecipes(sorted);
      // If we previously errored on recipes-load, clear the error now
      setUiError((prev) =>
        prev?.kind === "network" || prev?.kind === "infra" || prev?.kind === "unknown"
          ? null
          : prev,
      );
    } catch (e) {
      setUiError(parseApiError(e));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes");
        if (cancelled) return;
        const sorted = [...data.recipes].sort((a, b) => a.name.localeCompare(b.name));
        setRecipes(sorted);
      } catch (e) {
        if (!cancelled) setUiError(parseApiError(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Focus the verdict card when a verdict renders (UI-SPEC §A11y bullet 2).
  // The ref + tabIndex=-1 live on the <RunResultCard> element; we pass the ref in.
  //
  // NULL-UNION REQUIRED (locked to match Plan 20-04's prop type
  // `cardRef?: RefObject<HTMLDivElement | null>`). On @types/react >= 19,
  // `useRef<HTMLDivElement>(null)` infers `RefObject<HTMLDivElement>` (no null)
  // which is NOT assignable to a `RefObject<HTMLDivElement | null>` prop.
  // Always use the explicit null-union form below so the two plans agree.
  const cardRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (verdict) cardRef.current?.focus();
  }, [verdict]);

  // --- Derived ---------------------------------------------------------
  const canDeploy =
    recipe !== "" &&
    model.trim() !== "" &&
    byok.trim() !== "" &&
    prompt.trim() !== "" &&
    !isRunning &&
    (uiError?.kind !== "rate_limited" || remainingSec === 0);

  // --- Handlers --------------------------------------------------------
  async function onDeploy() {
    // RESEARCH Pitfall 6: clear prior verdict + error before new run.
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
    } catch (e) {
      setUiError(parseApiError(e));
    } finally {
      // SC-05 strictest reading: clear the key from React state on every attempt.
      // User re-types on re-deploy; acceptable trade-off (CONTEXT D-05, RESEARCH Q5 bullet 2).
      setByok("");
      setIsRunning(false);
    }
  }
  // --- JSX --------------------------------------------------------------
  return (
    <div>
      {/* ─── Form Card ──────────────────────────────────────────────── */}
      <Card className="p-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canDeploy) onDeploy();
          }}
          aria-busy={isRunning}
          className="flex flex-col gap-4"
        >
          {/* Field 1 — Recipe (native <select>, UI-SPEC §Field 1) */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="recipe">Recipe</Label>
            <select
              id="recipe"
              name="recipe"
              value={recipe}
              disabled={recipes === null || isRunning}
              onChange={(e) => setRecipe(e.target.value)}
              required
              className={cn(
                "border-input h-9 w-full rounded-md border bg-transparent px-3 text-sm shadow-xs transition-[color,box-shadow] outline-none",
                "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <option value="" disabled>
                {recipes === null ? "Loading recipes…" : "Select a recipe…"}
              </option>
              {recipes?.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name}
                </option>
              ))}
            </select>

            {/* Empty-state: 0 recipes returned */}
            {recipes !== null && recipes.length === 0 && (
              <Alert className="border-amber-500 bg-amber-500/10">
                <AlertTitle>No recipes available</AlertTitle>
                <AlertDescription>
                  The API returned an empty recipe list. Check the server and retry.
                </AlertDescription>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setUiError(null);
                    setRecipes(null);
                    fetchRecipes();
                  }}
                >
                  Retry
                </Button>
              </Alert>
            )}

            {/* Load-failed state: recipes fetch threw — shown when recipes are still null AND we have a non-rate-limited uiError.
                If uiError is rate_limited or validation from a later POST /v1/runs, do NOT show this banner. */}
            {recipes === null &&
              uiError &&
              uiError.kind !== "rate_limited" &&
              uiError.kind !== "validation" && (
                <Alert className="border-amber-500 bg-amber-500/10">
                  <AlertTitle>Could not load recipes</AlertTitle>
                  <AlertDescription>{uiError.message}</AlertDescription>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setUiError(null);
                      fetchRecipes();
                    }}
                  >
                    Retry
                  </Button>
                </Alert>
              )}
          </div>

          {/* Field 2 — Model (UI-SPEC §Field 2) */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="model">Model</Label>
            <Input
              id="model"
              name="model"
              type="text"
              autoComplete="off"
              placeholder="e.g., openai/gpt-4o-mini"
              required
              disabled={isRunning}
              value={model}
              onChange={(e) => setModel(e.target.value)}
              aria-invalid={
                uiError?.kind === "validation" && uiError.field === "model" ? true : undefined
              }
              aria-describedby={
                uiError?.kind === "validation" && uiError.field === "model"
                  ? "model-error"
                  : undefined
              }
            />
            <a
              href="https://openrouter.ai/models"
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1.5 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              browse models
            </a>
            {uiError?.kind === "validation" && uiError.field === "model" && (
              <p id="model-error" role="alert" className="mt-1.5 text-sm text-destructive">
                {uiError.message}
              </p>
            )}
          </div>

          {/* Field 3 — API key (UI-SPEC §Field 3) */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="byok">API key</Label>
            <Input
              id="byok"
              name="byok"
              type="password"
              autoComplete="new-password"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="sk-or-v1-..."
              aria-label="API key (sent as Authorization: Bearer, never stored)"
              required
              disabled={isRunning}
              value={byok}
              onChange={(e) => setByok(e.target.value)}
            />
            <p className="mt-1.5 text-xs text-muted-foreground">
              Sent once with this run. Never stored.
            </p>
          </div>

          {/* Field 4 — Prompt (UI-SPEC §Field 4) */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="prompt">Prompt</Label>
            <Textarea
              id="prompt"
              name="prompt"
              required
              disabled={isRunning}
              placeholder="What should the agent do?"
              className="min-h-32"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              aria-invalid={
                uiError?.kind === "validation" && uiError.field === "prompt" ? true : undefined
              }
              aria-describedby={
                uiError?.kind === "validation" && uiError.field === "prompt"
                  ? "prompt-error"
                  : undefined
              }
            />
            {uiError?.kind === "validation" && uiError.field === "prompt" && (
              <p id="prompt-error" role="alert" className="mt-1.5 text-sm text-destructive">
                {uiError.message}
              </p>
            )}
          </div>

          {/* Deploy button (UI-SPEC §Deploy button) */}
          <Button type="submit" disabled={!canDeploy} aria-busy={isRunning} className="w-full">
            {isRunning ? (
              <>
                <Spinner className="size-4 motion-reduce:animate-none" aria-hidden="true" />
                <span>Running…</span>
              </>
            ) : uiError?.kind === "rate_limited" && remainingSec > 0 ? (
              <span>{`Retry in ${remainingSec}s`}</span>
            ) : (
              <span>Deploy</span>
            )}
          </Button>

          {/* Non-field validation (422 without a param) fallback — inline under Deploy */}
          {uiError?.kind === "validation" && !uiError.field && (
            <p role="alert" className="text-sm text-destructive">
              {uiError.message}
            </p>
          )}
        </form>
      </Card>

      {/* ─── Result Area (below the form, UI-SPEC §State Machine) ────── */}
      <div className="mt-8">
        {/* State C — Running placeholder (aria-live=polite) */}
        {isRunning && (
          <Alert role="status" aria-live="polite">
            <Spinner className="size-4 motion-reduce:animate-none" aria-hidden="true" />
            <AlertTitle>Running…</AlertTitle>
          </Alert>
        )}

        {/* State D — Verdict card (mounted only when a verdict is present) */}
        {!isRunning && verdict && <RunResultCard verdict={verdict} cardRef={cardRef} />}

        {/* State E2 — 429 rate-limit banner (UI-SPEC §E2) */}
        {!isRunning && uiError?.kind === "rate_limited" && (
          <Alert role="status" aria-live="polite" className="border-amber-500 bg-amber-500/10">
            <Clock className="text-amber-500" aria-hidden="true" />
            <AlertTitle className="text-amber-300">Rate limited</AlertTitle>
            <AlertDescription>
              Retry in {remainingSec} s. The API is throttling requests.
              {uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">
                  Request ID: {uiError.requestId}
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* State E3 — 401/403 (UI-SPEC §E3) — never echo the key value */}
        {!isRunning && uiError?.kind === "unauthorized" && (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>Invalid or missing API key</AlertTitle>
            <AlertDescription>
              Check your OpenRouter / Anthropic / OpenAI key and try again.
              {uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">
                  Request ID: {uiError.requestId}
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* State E4 — 502 infra_error (UI-SPEC §E4) */}
        {!isRunning && uiError?.kind === "infra" && (
          <Alert className="border-amber-500 bg-amber-500/10">
            <AlertCircle className="text-amber-500" aria-hidden="true" />
            <AlertTitle className="text-amber-300">Infrastructure error</AlertTitle>
            <AlertDescription>
              {uiError.message}
              {uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">
                  Request ID: {uiError.requestId} — include when reporting.
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* State E5 — network failure (UI-SPEC §E5) */}
        {!isRunning && uiError?.kind === "network" && (
          <Alert>
            <WifiOff aria-hidden="true" />
            <AlertTitle>Could not reach API</AlertTitle>
            <AlertDescription>Check your connection and try again.</AlertDescription>
            <Button variant="outline" size="sm" onClick={onDeploy}>
              Retry
            </Button>
          </Alert>
        )}

        {/* State E-fallback — unknown / 404 / other (UI-SPEC §E-fallback) */}
        {!isRunning && (uiError?.kind === "unknown" || uiError?.kind === "not_found") && (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>Request failed</AlertTitle>
            <AlertDescription>
              {uiError.message}
              {uiError.kind === "not_found" && uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">
                  {" "}
                  Request ID: {uiError.requestId}
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}
      </div>
    </div>
  );
}
