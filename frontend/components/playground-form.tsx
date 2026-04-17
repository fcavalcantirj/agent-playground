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
  Sparkles,
  Rocket,
  KeyRound,
  MessageSquareText,
  Cpu,
  Boxes,
  Search as SearchIcon,
} from "lucide-react";

import { apiGet, apiPost } from "@/lib/api";
import {
  parseApiError,
  useRetryCountdown,
  PERSONALITIES,
  type PersonalityId,
  type RecipeSummary,
  type RunResponse,
  type UiError,
  type OpenRouterModel,
} from "@/lib/api-types";
import { cn } from "@/lib/utils";

import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
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
  response_contains_name: "PASS when the agent's reply mentions its own name",
  response_contains_string: "PASS when the response contains an expected string",
  response_regex: "PASS when the response matches a regex",
  response_not_contains: "PASS when the response does NOT contain a forbidden string",
  exit_zero: "PASS when the container exits with code 0",
};

const RECIPE_TAGLINES: Record<string, string> = {
  hermes: "Self-improving TUI agent with skills system, slash-commands, and full multi-provider support.",
  nanobot: "Ultra-lightweight Python agent — 99% fewer lines than OpenClaw, native OpenAI + Anthropic SDKs.",
  nullclaw: "Zero-overhead Zig agent. 100% Agnostic. Static binary, no runtime, fastest cold start.",
  openclaw: "Open-source coding gateway. TypeScript, Node 24, multi-channel, fully extensible.",
  picoclaw: "Tiny Go CLI agent. Single binary, minimal deps, designed to be embedded anywhere.",
};

const RECIPE_ACCENTS: Record<string, { from: string; to: string; glow: string }> = {
  hermes:   { from: "from-violet-500/30",  to: "to-purple-500/10",  glow: "shadow-violet-500/20" },
  nanobot:  { from: "from-amber-500/30",   to: "to-yellow-500/10",  glow: "shadow-amber-500/20" },
  nullclaw: { from: "from-indigo-500/30",  to: "to-blue-500/10",    glow: "shadow-indigo-500/20" },
  openclaw: { from: "from-emerald-500/30", to: "to-teal-500/10",    glow: "shadow-emerald-500/20" },
  picoclaw: { from: "from-rose-500/30",    to: "to-orange-500/10",  glow: "shadow-rose-500/20" },
};

function shortRef(ref: string | null | undefined): string {
  if (!ref) return "—";
  return /^[0-9a-f]{40}$/i.test(ref) ? ref.slice(0, 7) : ref;
}

function formatPricePerMTok(rate: string | undefined): string | null {
  if (!rate) return null;
  const n = Number.parseFloat(rate);
  if (!Number.isFinite(n)) return null;
  if (n === 0) return "free";
  return `$${(n * 1_000_000).toFixed(n < 1e-7 ? 4 : 2)}`;
}

function formatContext(ctx: number | undefined): string | null {
  if (!ctx) return null;
  if (ctx >= 1_000_000) return `${(ctx / 1_000_000).toFixed(0)}M`;
  if (ctx >= 1_000) return `${(ctx / 1_000).toFixed(0)}K`;
  return String(ctx);
}

export function PlaygroundForm({
  onDeployed,
}: {
  onDeployed?: (verdict: RunResponse) => void;
} = {}) {
  const [recipes, setRecipes] = useState<RecipeSummary[] | null>(null);
  const [recipe, setRecipe] = useState("");
  const [model, setModel] = useState("");
  const [byok, setByok] = useState("");
  const [agentName, setAgentName] = useState("");
  const [personality, setPersonality] = useState<PersonalityId>("polite-thorough");
  const [isRunning, setIsRunning] = useState(false);
  const [verdict, setVerdict] = useState<RunResponse | null>(null);
  const [uiError, setUiError] = useState<UiError | null>(null);

  const [orModels, setOrModels] = useState<OpenRouterModel[] | null>(null);
  const [orError, setOrError] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [recipeQuery, setRecipeQuery] = useState("");

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
    return () => { cancelled = true; };
  }, []);

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
    return () => { cancelled = true; };
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

  const trimmedName = agentName.trim();
  const nameValid = /^[a-zA-Z0-9][a-zA-Z0-9 _-]*$/.test(trimmedName);
  const canDeploy =
    recipe !== "" &&
    model.trim() !== "" &&
    byok.trim() !== "" &&
    nameValid &&
    !isRunning &&
    (uiError?.kind !== "rate_limited" || remainingSec === 0);

  async function onDeploy() {
    setVerdict(null);
    setUiError(null);
    setIsRunning(true);
    try {
      const res = await apiPost<RunResponse>(
        "/api/v1/runs",
        {
          recipe_name: recipe,
          model,
          agent_name: trimmedName,
          personality,
        },
        { Authorization: `Bearer ${byok}` },
      );
      setVerdict(res);
      onDeployed?.(res);
    } catch (e) {
      setUiError(parseApiError(e));
    } finally {
      setByok("");
      setIsRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-12">
      {/* ─── STEP 1 — Recipe cards ──────────────────────────────────── */}
      <section>
        <SectionHeader
          step={1}
          icon={<Boxes className="size-5" />}
          title="Pick an agent recipe"
          subtitle="Each recipe is a fully-pinned dockerized agent. One click runs it in an isolated container."
        />

        {recipes === null && !uiError && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-56 animate-pulse rounded-xl border border-border/50 bg-muted/20"
              />
            ))}
          </div>
        )}

        {recipes && recipes.length > 0 && (() => {
          const q = recipeQuery.trim().toLowerCase();
          const tokens = q.split(/\s+/).filter(Boolean);
          const filtered = tokens.length
            ? recipes.filter((r) => {
                const hay = [
                  r.name,
                  r.display_name ?? "",
                  RECIPE_TAGLINES[r.name] ?? "",
                  r.description ?? "",
                  r.source_repo ?? "",
                  r.upstream_version ?? "",
                ]
                  .join(" ")
                  .toLowerCase();
                return tokens.every((t) => hay.includes(t));
              })
            : recipes;

          return (
            <>
              <div className="mb-5 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="relative w-full sm:max-w-md">
                  <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <input
                    type="search"
                    placeholder={`Search ${recipes.length} recipe${recipes.length === 1 ? "" : "s"} — name, description, repo…`}
                    value={recipeQuery}
                    onChange={(e) => setRecipeQuery(e.target.value)}
                    disabled={isRunning}
                    className={cn(
                      "h-11 w-full rounded-lg border border-border/60 bg-card/40 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground/70",
                      "focus-visible:border-primary focus-visible:bg-card/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                    )}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {filtered.length === recipes.length
                    ? `${recipes.length} recipes available`
                    : `${filtered.length} of ${recipes.length} match`}
                </p>
              </div>

              {filtered.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border/60 bg-card/20 p-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    No recipe matches <span className="font-mono text-foreground">"{recipeQuery}"</span>.
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2"
                    onClick={() => setRecipeQuery("")}
                  >
                    Clear search
                  </Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
                  {filtered.map((r) => (
                    <RecipeCard
                      key={r.name}
                      recipe={r}
                      selected={recipe === r.name}
                      onSelect={() => setRecipe(r.name)}
                      disabled={isRunning}
                    />
                  ))}
                </div>
              )}
            </>
          );
        })()}

        {recipes && recipes.length === 0 && (
          <Alert className="border-amber-500 bg-amber-500/10">
            <AlertTitle>No recipes available</AlertTitle>
            <AlertDescription>The API returned an empty recipe list.</AlertDescription>
            <Button variant="outline" size="sm" onClick={fetchRecipes}>Retry</Button>
          </Alert>
        )}

        {recipes === null && uiError && uiError.kind !== "rate_limited" && uiError.kind !== "validation" && (
          <Alert className="border-amber-500 bg-amber-500/10">
            <AlertTitle>Could not load recipes</AlertTitle>
            <AlertDescription>{uiError.message}</AlertDescription>
            <Button variant="outline" size="sm" onClick={() => { setUiError(null); fetchRecipes(); }}>Retry</Button>
          </Alert>
        )}
      </section>

      {/* ─── STEP 2 — Model picker ──────────────────────────────────── */}
      <section>
        <SectionHeader
          step={2}
          icon={<Cpu className="size-5" />}
          title="Pick a model"
          subtitle={
            orError
              ? `OpenRouter catalog unreachable (${orError}) — type the model id directly.`
              : `${orModels?.length ?? 0} models from OpenRouter, fetched live. Search by provider, family, or tag.`
          }
        />

        {orError ? (
          <Input
            id="model"
            type="text"
            placeholder="e.g., openai/gpt-4o-mini"
            disabled={isRunning}
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="h-14 max-w-2xl text-lg font-mono"
          />
        ) : (
          <ModelCombobox
            models={orModels}
            value={model}
            onChange={setModel}
            open={modelOpen}
            setOpen={setModelOpen}
            disabled={isRunning}
            selected={selectedModelMeta}
          />
        )}
      </section>

      {/* ─── STEP 3 — Name + Personality ────────────────────────────── */}
      <section>
        <SectionHeader
          step={3}
          icon={<Sparkles className="size-5" />}
          title="Name your agent & pick a personality"
          subtitle="The personality shapes how the agent introduces itself in the deploy smoke and steers its tone in later chats."
        />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Name — 1/3 column */}
          <div className="flex flex-col gap-2">
            <Label htmlFor="agent-name" className="flex items-center gap-2 text-base font-medium">
              <Boxes className="size-4 text-muted-foreground" /> Agent name
            </Label>
            <Input
              id="agent-name"
              type="text"
              autoComplete="off"
              placeholder={selectedRecipe ? `e.g., my-${selectedRecipe.name}` : "e.g., my-helper"}
              disabled={isRunning}
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              className="h-14 text-lg"
              maxLength={64}
              aria-invalid={agentName.length > 0 && !nameValid ? true : undefined}
            />
            <p className="text-sm text-muted-foreground">
              Stored in your account. Letters, numbers, spaces, <code className="rounded bg-muted px-1 py-0.5">_</code> and <code className="rounded bg-muted px-1 py-0.5">-</code>. Must be unique among your agents.
            </p>
          </div>

          {/* Personality — 2/3 column */}
          <div className="flex flex-col gap-2 lg:col-span-2">
            <Label className="flex items-center gap-2 text-base font-medium">
              <MessageSquareText className="size-4 text-muted-foreground" /> Personality preset
            </Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {PERSONALITIES.map((p) => {
                const active = personality === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setPersonality(p.id)}
                    disabled={isRunning}
                    aria-pressed={active}
                    className={cn(
                      "group flex h-full items-start gap-3 rounded-xl border p-3 text-left transition-all",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                      active
                        ? "border-primary/60 bg-primary/10 shadow-md shadow-primary/10"
                        : "border-border/50 bg-card/30 hover:border-border/80 hover:bg-card/60",
                      isRunning && "cursor-not-allowed opacity-60",
                    )}
                  >
                    <span className="text-2xl leading-none" aria-hidden>{p.emoji}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-foreground">{p.label}</span>
                        {active && <Check className="size-3.5 text-primary" />}
                      </div>
                      <p className="mt-0.5 text-xs leading-snug text-muted-foreground">{p.description}</p>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* ─── STEP 4 — Deploy ──────────────────────────────────────── */}
      <section>
        <SectionHeader
          step={4}
          icon={<Rocket className="size-5" />}
          title="Deploy"
          subtitle="Your OpenRouter key is sent once with this deploy smoke and is never stored on our side."
        />

        <form
          onSubmit={(e) => { e.preventDefault(); if (canDeploy) onDeploy(); }}
          aria-busy={isRunning}
          className="grid grid-cols-1 gap-6"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="byok" className="flex items-center gap-2 text-base font-medium">
              <KeyRound className="size-4 text-muted-foreground" /> OpenRouter API key
            </Label>
            <Input
              id="byok"
              type="password"
              autoComplete="new-password"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              placeholder="sk-or-v1-..."
              required
              disabled={isRunning}
              value={byok}
              onChange={(e) => setByok(e.target.value)}
              className="h-14 max-w-2xl text-lg font-mono"
            />
            <p className="text-sm text-muted-foreground">
              Sent as <code className="rounded bg-muted px-1 py-0.5 text-foreground/90">Authorization: Bearer</code>. Cleared from React state after submit.
            </p>
          </div>

          <div>
            <Button
              type="submit"
              disabled={!canDeploy}
              aria-busy={isRunning}
              className="h-16 w-full text-lg font-semibold tracking-wide shadow-lg shadow-primary/20 transition-all hover:shadow-xl hover:shadow-primary/30 disabled:shadow-none"
            >
              {isRunning ? (
                <>
                  <Spinner className="size-5 motion-reduce:animate-none" aria-hidden="true" />
                  <span className="ml-2">Deploying {trimmedName || "agent"} ({selectedRecipe?.display_name ?? recipe} on {model})…</span>
                </>
              ) : uiError?.kind === "rate_limited" && remainingSec > 0 ? (
                <span>Retry in {remainingSec}s</span>
              ) : (
                <>
                  <Rocket className="mr-2 size-5" />
                  <span>Deploy {trimmedName ? `"${trimmedName}"` : "agent"}</span>
                </>
              )}
            </Button>

            {!canDeploy && !isRunning && (
              <p className="mt-3 text-center text-sm text-muted-foreground">
                {!recipe
                  ? "↑ pick a recipe to begin"
                  : !model
                    ? "↑ pick a model"
                    : !nameValid
                      ? agentName.length === 0
                        ? "↑ name your agent"
                        : "name must start with a letter or number; letters, numbers, spaces, _ and - only"
                      : !byok
                        ? "↑ paste your OpenRouter key"
                        : ""}
              </p>
            )}

            {uiError?.kind === "validation" && uiError.message && (
              <p role="alert" className="mt-3 text-center text-sm text-destructive">
                {uiError.message}
              </p>
            )}
          </div>
        </form>
      </section>

      {/* ─── Result Area ───────────────────────────────────────────── */}
      <section className="min-h-[1px]">
        {isRunning && (
          <Alert role="status" aria-live="polite" className="border-primary/40 bg-primary/5 py-6">
            <Spinner className="size-5 motion-reduce:animate-none" aria-hidden="true" />
            <AlertTitle className="text-lg">
              Running {selectedRecipe?.display_name ?? recipe} on {model}…
            </AlertTitle>
            {selectedRecipe?.expected_runtime_seconds != null && (
              <AlertDescription className="text-base">
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
              {uiError.requestId && <span className="mt-1 block font-mono text-xs">Request ID: {uiError.requestId}</span>}
            </AlertDescription>
          </Alert>
        )}

        {!isRunning && uiError?.kind === "unauthorized" && (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>Invalid or missing API key</AlertTitle>
            <AlertDescription>
              Check your OpenRouter / Anthropic / OpenAI key and try again.
              {uiError.requestId && <span className="mt-1 block font-mono text-xs">Request ID: {uiError.requestId}</span>}
            </AlertDescription>
          </Alert>
        )}

        {!isRunning && uiError?.kind === "infra" && (
          <Alert className="border-amber-500 bg-amber-500/10">
            <AlertCircle className="text-amber-500" aria-hidden="true" />
            <AlertTitle className="text-amber-300">Infrastructure error</AlertTitle>
            <AlertDescription>
              {uiError.message}
              {uiError.requestId && <span className="mt-1 block font-mono text-xs">Request ID: {uiError.requestId}</span>}
            </AlertDescription>
          </Alert>
        )}

        {!isRunning && uiError?.kind === "network" && (
          <Alert>
            <WifiOff aria-hidden="true" />
            <AlertTitle>Could not reach API</AlertTitle>
            <AlertDescription>Check your connection and try again.</AlertDescription>
            <Button variant="outline" size="sm" onClick={onDeploy}>Retry</Button>
          </Alert>
        )}

        {!isRunning && (uiError?.kind === "unknown" || uiError?.kind === "not_found") && (
          <Alert variant="destructive">
            <AlertCircle aria-hidden="true" />
            <AlertTitle>Request failed</AlertTitle>
            <AlertDescription>
              {uiError.message}
              {uiError.kind === "not_found" && uiError.requestId && (
                <span className="mt-1 block font-mono text-xs">Request ID: {uiError.requestId}</span>
              )}
            </AlertDescription>
          </Alert>
        )}
      </section>
    </div>
  );
}

// ─── SectionHeader ────────────────────────────────────────────────────
function SectionHeader({
  step,
  icon,
  title,
  subtitle,
}: {
  step: number;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="mb-5 flex items-start gap-4">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-primary/30 bg-primary/10 text-primary">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-xs uppercase tracking-widest text-primary/80">Step {step}</span>
        </div>
        <h2 className="mt-0.5 text-2xl font-bold text-foreground sm:text-3xl">{title}</h2>
        <p className="mt-1 text-base text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}

// ─── RecipeCard ──────────────────────────────────────────────────────
function RecipeCard({
  recipe,
  selected,
  onSelect,
  disabled,
}: {
  recipe: RecipeSummary;
  selected: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  const tagline = RECIPE_TAGLINES[recipe.name] ?? recipe.description?.split("\n")[0]?.trim() ?? "";
  const repoOwnerRepo = recipe.source_repo?.replace(/^https?:\/\/(www\.)?github\.com\//, "") ?? "";
  const accent = RECIPE_ACCENTS[recipe.name] ?? RECIPE_ACCENTS.hermes;
  const initials = (recipe.display_name ?? recipe.name).slice(0, 2).toUpperCase();
  const version = recipe.upstream_version?.split(/\s|\//)[0];

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled}
      aria-pressed={selected}
      className={cn(
        "group relative isolate flex h-full flex-col overflow-hidden rounded-2xl border text-left transition-all duration-200",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        selected
          ? cn("border-primary/70 bg-card/80 shadow-2xl ring-1 ring-primary/40", accent.glow)
          : "border-border/40 bg-card/20 backdrop-blur-sm hover:-translate-y-1 hover:border-border/80 hover:bg-card/60 hover:shadow-xl",
        disabled && "cursor-not-allowed opacity-50",
      )}
    >
      {/* Top gradient wash — recipe-tinted */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 -z-10 h-32 bg-gradient-to-b opacity-60 transition-opacity duration-300",
          accent.from,
          accent.to,
          selected ? "opacity-100" : "group-hover:opacity-90",
        )}
      />

      {/* Selected check chip */}
      {selected && (
        <div className="absolute right-4 top-4 z-10 flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg shadow-primary/40 ring-2 ring-background">
          <Check className="size-4" strokeWidth={3} />
        </div>
      )}

      {/* Header: avatar + title block */}
      <div className="flex items-start gap-3 p-5 pb-3">
        <div
          className={cn(
            "flex size-12 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br font-mono text-base font-bold text-white shadow-inner",
            accent.from.replace("/30", "/60"),
            accent.to.replace("/10", "/40"),
          )}
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1 pr-7">
          <h3 className="text-lg font-semibold leading-tight text-foreground" title={recipe.display_name ?? recipe.name}>
            {recipe.display_name ?? recipe.name}
          </h3>
          <p className="font-mono text-xs text-muted-foreground/80">{recipe.name}</p>
        </div>
      </div>

      {/* Tagline */}
      {tagline && (
        <p className="line-clamp-3 px-5 text-[15px] leading-relaxed text-foreground/85">
          {tagline}
        </p>
      )}

      {/* Stats strip */}
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1.5 px-5 text-xs text-muted-foreground">
        {version && (
          <span className="inline-flex items-center gap-1 font-mono">
            <span className="text-foreground/70">{version}</span>
          </span>
        )}
        {recipe.image_size_gb != null && (
          <span className="inline-flex items-center gap-1">
            <HardDrive className="size-3 opacity-60" />
            <span className="font-mono">{recipe.image_size_gb.toFixed(1)}GB</span>
          </span>
        )}
        {recipe.expected_runtime_seconds != null && (
          <span className="inline-flex items-center gap-1">
            <Timer className="size-3 opacity-60" />
            <span className="font-mono">~{Math.round(recipe.expected_runtime_seconds)}s</span>
          </span>
        )}
      </div>

      {/* Footer: source repo */}
      {recipe.source_repo && (
        <a
          href={recipe.source_repo}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="mt-auto flex items-center gap-1.5 border-t border-border/40 px-5 py-3 font-mono text-[11px] text-muted-foreground/80 transition-colors hover:bg-muted/30 hover:text-foreground"
        >
          <Github className="size-3.5 shrink-0" />
          <span className="truncate">{repoOwnerRepo}</span>
          {recipe.source_ref && (
            <code className="ml-auto rounded bg-muted/60 px-1.5 py-0.5 text-[10px] text-foreground/80">
              {shortRef(recipe.source_ref)}
            </code>
          )}
          <ExternalLink className="size-3 shrink-0 opacity-50" />
        </a>
      )}
    </button>
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
  selected,
}: {
  models: OpenRouterModel[] | null;
  value: string;
  onChange: (id: string) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
  disabled: boolean;
  selected: OpenRouterModel | null;
}) {
  const loading = models === null;
  const ctx = formatContext(selected?.context_length);
  const promptPrice = formatPricePerMTok(selected?.pricing?.prompt);
  const completionPrice = formatPricePerMTok(selected?.pricing?.completion);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled || loading}
          className={cn(
            "h-auto min-h-[4rem] w-full max-w-3xl justify-between gap-3 px-5 py-3 text-left text-base font-normal",
            // Override the default outline-variant accent hover (--accent is bright orange + dark fg → unreadable).
            "bg-card/40 text-foreground hover:!bg-card/70 hover:!text-foreground hover:border-primary/50",
            "data-[state=open]:!bg-card/70 data-[state=open]:border-primary",
            value && "border-primary/40 bg-card/70",
          )}
        >
          {loading ? (
            <span className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-5 animate-spin" />
              Loading models from OpenRouter…
            </span>
          ) : value ? (
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="truncate font-mono text-base text-foreground">{value}</span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                {selected?.name && <span className="truncate">{selected.name}</span>}
                {ctx && <Badge variant="outline" className="text-[10px]">{ctx} ctx</Badge>}
                {promptPrice && <Badge variant="outline" className="text-[10px]">{promptPrice}/M in</Badge>}
                {completionPrice && <Badge variant="outline" className="text-[10px]">{completionPrice}/M out</Badge>}
              </div>
            </div>
          ) : (
            <span className="text-muted-foreground">Select a model — search by family, provider, or “free”…</span>
          )}
          <ChevronsUpDown className="ml-2 size-5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="z-50 w-[var(--radix-popover-trigger-width)] border-border/80 bg-popover/95 p-0 shadow-2xl backdrop-blur-md"
        align="start"
        sideOffset={8}
        side="bottom"
        avoidCollisions={false}
      >
        <Command
          filter={(value, search) => {
            const tokens = search.toLowerCase().split(/\s+/).filter(Boolean);
            return tokens.every((t) => value.includes(t)) ? 1 : 0;
          }}
        >
          <CommandInput
            placeholder="Search 345+ models — try ‘claude opus’, ‘gpt-4o’, ‘free’…"
            className="h-12 text-base"
          />
          <CommandList className="max-h-96">
            <CommandEmpty>No model matches.</CommandEmpty>
            <CommandGroup>
              {(models ?? []).map((m) => {
                const promptP = formatPricePerMTok(m.pricing?.prompt);
                const completionP = formatPricePerMTok(m.pricing?.completion);
                const c = formatContext(m.context_length);
                const isSelected = value === m.id;
                return (
                  <CommandItem
                    key={m.id}
                    value={`${m.id} ${m.name}`}
                    onSelect={() => { onChange(m.id); setOpen(false); }}
                    className={cn(
                      // Override the harsh accent fill — use subtle bg + left rail when selected/focused
                      "flex flex-col items-start gap-1 px-3 py-2.5 text-base",
                      "data-[selected=true]:bg-primary/8 data-[selected=true]:text-foreground",
                      "data-[selected=true]:border-l-2 data-[selected=true]:border-l-primary",
                      "border-l-2 border-l-transparent",
                      isSelected && "bg-primary/12",
                    )}
                  >
                    <div className="flex w-full items-center justify-between gap-2">
                      <span className="truncate font-mono text-sm font-medium text-foreground">{m.id}</span>
                      {isSelected && <Check className="size-4 shrink-0 text-primary" />}
                    </div>
                    <div className="flex w-full flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <span className="truncate text-foreground/70">{m.name}</span>
                      <div className="ml-auto flex shrink-0 items-center gap-1.5">
                        {c && <Badge variant="outline" className="text-[10px]">{c}</Badge>}
                        {promptP && <Badge variant="outline" className="text-[10px]">{promptP}/M in</Badge>}
                        {completionP && <Badge variant="outline" className="text-[10px]">{completionP}/M out</Badge>}
                      </div>
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
