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
  // --- JSX (added in Task 2) -------------------------------------------
  return null; // placeholder — replaced in Task 2
}
