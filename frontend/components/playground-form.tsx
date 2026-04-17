"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Loader2,
  Clock,
  WifiOff,
  AlertCircle,
  Copy,
  Check,
  ChevronsUpDown,
  ExternalLink,
  HardDrive,
  Timer,
  Github,
  Tag,
  Shield,
  User as UserIcon,
} from "lucide-react";

import { apiGet, apiPost } from "@/lib/api";
import {
  parseApiError,
  useRetryCountdown,
  type RecipeSummary,
  type RunResponse,
  type UiError,
  type OpenRouterModel,
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
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

import { RunResultCard } from "@/components/run-result-card";

const PASS_IF_HUMAN: Record<string, string> = {
  response_contains_name: "PASS when the agent's response mentions its own name",
  response_contains_string: "PASS when the response contains an expected string",
  response_regex: "PASS when the response matches a regex",
  response_not_contains: "PASS when the response does NOT contain a forbidden string",
  exit_zero: "PASS when the container exits with code 0",
};

function shortRef(ref: string | null | undefined): string {
  if (!ref) return "—";
  return /^[0-9a-f]{40}$/i.test(ref) ? ref.slice(0, 7) : ref;
}

function formatPricePerMTok(rate: string | undefined): string | null {
  if (!rate) return null;
  const n = Number.parseFloat(rate);
  if (!Number.isFinite(n) || n === 0) return n === 0 ? "free" : null;
  return `$${(n * 1_000_000).toFixed(n < 1e-7 ? 4 : 2)}`;
}

function formatContext(ctx: number | undefined): string | null {
  if (!ctx) return null;
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(0)}M`;
  if (ctx >= 1_000) return `${(ctx / 1_000).toFixed(0)}K`;
  return String(ctx);
}

export function PlaygroundForm() {
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [recipe, setRecipe] = useState("");
  const [model, setModel] = useState("");
  const [byok, setByok] = useState("");
  const [prompt, setPrompt] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [verdict, setVerdict] = useState<RunResponse | null>(null);
  const [uiError, setUiError] = useState<UiError | null>(null);

  const [orModels, setOrModels] = useState<OpenRouterModel[] | null>(null);
  const [orError, setOrError] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);

  const onRetryExpire = useCallback(() => setUiError(null), []);
  const remainingSec = useRetryCountdown(uiError, onRetryExpire);

  const fetchRecipes = useCallback(async () => {
    try {
      const data = await apiGet<{ recipes: RecipeSummary[] }>("/api/v1/recipes");
      const sorted = [...data.recipes].sort((a, b) => a.name.localeCompare(b.name));
      setRecipes(sorted);
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

  // Fetch OpenRouter model catalog (public endpoint, no auth required).
  // Failure degrades gracefully — the model field falls back to free-text input.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("https://openrouter.ai/api/v1/models");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = (await r.json()) as { data: OpenRouterModel[] };
        if (cancelled) return;
        setOrModels(d.data ?? []);
      } catch (e) {
        if (!cancelled) setOrError(e instanceof Error ? e.message : "load failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedRecipe = useMemo(
    () => recipes?.find((r) => r.name === recipe) ?? null,
    [recipes, recipe],
  );

  const selectedModelMeta = useMemo(
    () => orModels?.find((m) => m.id === model) ?? null,
    [orModels, model],
  );

  const cardRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (verdict) cardRef.current?.focus();
  }, [verdict]);

  const canDeploy =
    recipe !== "" &&
    model.trim() !== "" &&
    byok.trim() !== "" &&
    prompt.trim() !== "" &&
    !isRunning &&
    (uiError?.kind !== "rate_limited" || remainingSec === 0);

  async function onDeploy() {
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
      setByok("");
      setIsRunning(false);
    }
  }

  return (
    <div>
      <Card className="p-6 sm:p-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canDeploy) onDeploy();
          }}
          aria-busy={isRunning}
          className="flex flex-col gap-6"
        >
          {/* ─── Field 1: Recipe ──────────────────────────────────────── */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="recipe" className="text-base font-medium">
              Recipe
            </Label>
            <select
              id="recipe"
              name="recipe"
              value={recipe}
              disabled={recipes === null || isRunning}
              onChange={(e) => setRecipe(e.target.value)}
              required
              className={cn(
                "border-input h-11 w-full rounded-md border bg-transparent px-3 text-base shadow-xs transition-[color,box-shadow] outline-none",
                "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
                "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <option value="" disabled>
                {recipes === null ? "Loading recipes…" : "Select a recipe…"}
              </option>
              {recipes?.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.display_name && r.display_name !== r.name
                    ? `${r.display_name} (${r.name})`
                    : r.name}
                </option>
              ))}
            </select>

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

            {selectedRecipe && (
              <RecipePanel recipe={selectedRecipe} />
            )}
          </div>

          {/* ─── Field 2: Model ───────────────────────────────────────── */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="model" className="text-base font-medium">
              Model
            </Label>
            {orError ? (
              <>
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
                  className="h-11 text-base"
                  aria-invalid={
                    uiError?.kind === "validation" && uiError.field === "model" ? true : undefined
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Model catalog unreachable ({orError}) — type the OpenRouter model ID directly.
                </p>
              </>
            ) : (
              <ModelCombobox
                models={orModels}
                value={model}
                onChange={setModel}
                open={modelOpen}
                setOpen={setModelOpen}
                disabled={isRunning}
              />
            )}
            {selectedModelMeta && (
              <ModelMetaLine meta={selectedModelMeta} />
            )}
            {uiError?.kind === "validation" && uiError.field === "model" && (
              <p id="model-error" role="alert" className="text-sm text-destructive">
                {uiError.message}
              </p>
            )}
          </div>

          {/* ─── Field 3: API key ──────────────────────────────────────── */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="byok" className="text-base font-medium">
              API key
            </Label>
            <Input
              id="byok"
              name="byok"
              type="password"
              autoComplete="new-password"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="sk-or-v1-..."
              aria-label="OpenRouter API key (sent as Authorization: Bearer, never stored)"
              required
              disabled={isRunning}
              value={byok}
              onChange={(e) => setByok(e.target.value)}
              className="h-11 text-base font-mono"
            />
            <p className="text-xs text-muted-foreground">
              Sent once with this run as <code className="text-foreground/80">Authorization: Bearer</code>. Never stored, never logged.
            </p>
          </div>

          {/* ─── Field 4: Prompt ──────────────────────────────────────── */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="prompt" className="text-base font-medium">
              Prompt
            </Label>
            <Textarea
              id="prompt"
              name="prompt"
              required
              disabled={isRunning}
              placeholder="What should the agent do?"
              className="min-h-32 text-base"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              aria-invalid={
                uiError?.kind === "validation" && uiError.field === "prompt" ? true : undefined
              }
            />
            {selectedRecipe?.pass_if && (
              <p className="text-xs text-muted-foreground">
                <span className="text-foreground/80">Tip:</span>{" "}
                {PASS_IF_HUMAN[selectedRecipe.pass_if] ?? `pass_if: ${selectedRecipe.pass_if}`}.
              </p>
            )}
            {uiError?.kind === "validation" && uiError.field === "prompt" && (
              <p role="alert" className="text-sm text-destructive">
                {uiError.message}
              </p>
            )}
          </div>

          {/* ─── Deploy button ────────────────────────────────────────── */}
          <Button
            type="submit"
            disabled={!canDeploy}
            aria-busy={isRunning}
            className="h-12 w-full text-base"
          >
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

          {uiError?.kind === "validation" && !uiError.field && (
            <p role="alert" className="text-sm text-destructive">
              {uiError.message}
            </p>
          )}
        </form>
      </Card>

      {/* ─── Result Area ───────────────────────────────────────────── */}
      <div className="mt-8">
        {isRunning && (
          <Alert role="status" aria-live="polite">
            <Spinner className="size-4 motion-reduce:animate-none" aria-hidden="true" />
            <AlertTitle>
              Running {selectedRecipe?.display_name ?? recipe} on {model}…
            </AlertTitle>
            {selectedRecipe?.expected_runtime_seconds && (
              <AlertDescription>
                Cold-start budget for this recipe: ~{Math.round(selectedRecipe.expected_runtime_seconds)}s observed upstream.
              </AlertDescription>
            )}
          </Alert>
        )}

        {!isRunning && verdict && <RunResultCard verdict={verdict} cardRef={cardRef} />}

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

        {!isRunning && (uiError?.kind === "unknown" || uiError?.kind === "not_found") && (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>Request failed</AlertTitle>
            <AlertDescription>
              {uiError.message}
              {uiError.kind === "not_found" && uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">
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

// ─── RecipePanel ──────────────────────────────────────────────────────
function RecipePanel({ recipe }: { recipe: RecipeSummary }) {
  const [copied, setCopied] = useState(false);

  function copyRef() {
    if (!recipe.source_ref) return;
    navigator.clipboard.writeText(recipe.source_ref).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="mt-3 rounded-md border border-border/60 bg-muted/30 p-4 text-sm">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold leading-tight">
          {recipe.display_name ?? recipe.name}
        </h3>
        {recipe.upstream_version && (
          <span className="font-mono text-xs text-muted-foreground">{recipe.upstream_version}</span>
        )}
      </div>

      {recipe.description && (
        <p className="mb-3 whitespace-pre-line text-sm text-muted-foreground">
          {recipe.description}
        </p>
      )}

      <dl className="grid grid-cols-1 gap-x-4 gap-y-2 sm:grid-cols-2">
        {recipe.provider && (
          <div className="flex items-center gap-2">
            <Tag className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="text-muted-foreground">Provider</dt>
            <dd className="font-mono text-foreground">{recipe.provider}</dd>
          </div>
        )}

        {recipe.image_size_gb != null && (
          <div className="flex items-center gap-2">
            <HardDrive className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="text-muted-foreground">Image</dt>
            <dd className="font-mono text-foreground">{recipe.image_size_gb.toFixed(2)} GB</dd>
          </div>
        )}

        {recipe.expected_runtime_seconds != null && (
          <div className="flex items-center gap-2">
            <Timer className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="text-muted-foreground">Cold-start</dt>
            <dd className="font-mono text-foreground">~{Math.round(recipe.expected_runtime_seconds)}s</dd>
          </div>
        )}

        {recipe.license && (
          <div className="flex items-center gap-2">
            <Shield className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="text-muted-foreground">License</dt>
            <dd className="font-mono text-foreground">{recipe.license}</dd>
          </div>
        )}

        {recipe.maintainer && (
          <div className="flex items-center gap-2">
            <UserIcon className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="text-muted-foreground">Maintainer</dt>
            <dd className="text-foreground">{recipe.maintainer}</dd>
          </div>
        )}

        {recipe.source_repo && (
          <div className="col-span-1 flex items-center gap-2 sm:col-span-2">
            <Github className="size-3.5 text-muted-foreground" aria-hidden="true" />
            <dt className="sr-only">Source</dt>
            <dd className="flex min-w-0 flex-1 items-center gap-2">
              <a
                href={recipe.source_repo}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate font-mono text-foreground/90 underline-offset-2 hover:underline"
              >
                {recipe.source_repo.replace(/^https?:\/\//, "")}
              </a>
              {recipe.source_ref && (
                <>
                  <span className="text-muted-foreground">@</span>
                  <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground">
                    {shortRef(recipe.source_ref)}
                  </code>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="size-6 p-0"
                    onClick={copyRef}
                    aria-label="Copy commit SHA"
                  >
                    {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
                  </Button>
                </>
              )}
              <a
                href={recipe.source_repo}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground"
                aria-label="Open repo in new tab"
              >
                <ExternalLink className="size-3.5" />
              </a>
            </dd>
          </div>
        )}

        {recipe.pass_if && (
          <div className="col-span-1 flex items-start gap-2 sm:col-span-2">
            <dt className="sr-only">Pass criterion</dt>
            <dd className="text-xs text-muted-foreground">
              <Badge variant="outline" className="mr-1.5 font-mono text-[10px]">
                pass_if
              </Badge>
              {PASS_IF_HUMAN[recipe.pass_if] ?? recipe.pass_if}
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

// ─── ModelCombobox ────────────────────────────────────────────────────
function ModelCombobox({
  models,
  value,
  onChange,
  open,
  setOpen,
  disabled,
}: {
  models: OpenRouterModel[] | null;
  value: string;
  onChange: (id: string) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  disabled: boolean;
}) {
  const selected = models?.find((m) => m.id === value);
  const loading = models === null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled || loading}
          className="h-11 w-full justify-between text-base font-normal"
        >
          {loading ? (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading {models === null ? "models from OpenRouter" : ""}…
            </span>
          ) : value ? (
            <span className="truncate font-mono">{value}</span>
          ) : (
            <span className="text-muted-foreground">Select a model…</span>
          )}
          <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] p-0"
        align="start"
      >
        <Command
          filter={(value, search) => {
            // Multi-token AND match on id + name (cmdk passes value lowercased).
            const tokens = search.toLowerCase().split(/\s+/).filter(Boolean);
            return tokens.every((t) => value.includes(t)) ? 1 : 0;
          }}
        >
          <CommandInput placeholder="Search 345+ models (try 'claude opus', 'gpt-4o', 'free')…" />
          <CommandList className="max-h-80">
            <CommandEmpty>No model matches.</CommandEmpty>
            <CommandGroup>
              {(models ?? []).map((m) => {
                const promptPrice = formatPricePerMTok(m.pricing?.prompt);
                const ctx = formatContext(m.context_length);
                return (
                  <CommandItem
                    key={m.id}
                    value={`${m.id} ${m.name}`}
                    onSelect={() => {
                      onChange(m.id);
                      setOpen(false);
                    }}
                    className="flex flex-col items-start gap-0.5"
                  >
                    <div className="flex w-full items-center justify-between gap-2">
                      <span className="truncate font-mono text-sm">{m.id}</span>
                      {value === m.id && <Check className="size-4 shrink-0" />}
                    </div>
                    <div className="flex w-full items-center gap-2 text-xs text-muted-foreground">
                      <span className="truncate">{m.name}</span>
                      {ctx && (
                        <Badge variant="outline" className="ml-auto shrink-0 text-[10px]">
                          {ctx} ctx
                        </Badge>
                      )}
                      {promptPrice && (
                        <Badge variant="outline" className="shrink-0 text-[10px]">
                          {promptPrice}/M in
                        </Badge>
                      )}
                    </div>
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

function ModelMetaLine({ meta }: { meta: OpenRouterModel }) {
  const promptPrice = formatPricePerMTok(meta.pricing?.prompt);
  const completionPrice = formatPricePerMTok(meta.pricing?.completion);
  const ctx = formatContext(meta.context_length);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span className="text-foreground/90">{meta.name}</span>
      {ctx && <Badge variant="outline">{ctx} context</Badge>}
      {promptPrice && <Badge variant="outline">{promptPrice}/M prompt</Badge>}
      {completionPrice && <Badge variant="outline">{completionPrice}/M completion</Badge>}
    </div>
  );
}
