"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Loader2,
  Clock,
  WifiOff,
  AlertCircle,
  Check,
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
import { Button } from "@/components/ui/button";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Spinner } from "@/components/ui/spinner";

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
  const [recipeQuery, setRecipeQuery] = useState("");
  const [recentModels, setRecentModels] = useState<string[]>([]);

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

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<{ agents: Array<{ model: string; last_run_at?: string | null; created_at: string }> }>(
          "/api/v1/agents",
        );
        if (cancelled) return;
        const ordered = [...data.agents]
          .sort((a, b) => {
            const at = new Date(a.last_run_at ?? a.created_at).getTime();
            const bt = new Date(b.last_run_at ?? b.created_at).getTime();
            return bt - at;
          })
          .map((a) => a.model);
        const deduped: string[] = [];
        for (const id of ordered) if (!deduped.includes(id)) deduped.push(id);
        setRecentModels(deduped);
      } catch {
        // best-effort only — empty recent list is fine
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
              <div className="mb-6 flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="relative w-full sm:max-w-md">
                  <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-foreground/50" />
                  <input
                    type="search"
                    placeholder={`Search ${recipes.length} recipe${recipes.length === 1 ? "" : "s"}…`}
                    value={recipeQuery}
                    onChange={(e) => setRecipeQuery(e.target.value)}
                    disabled={isRunning}
                    className={cn(
                      "h-12 w-full rounded-lg border border-border/60 bg-card/50 pl-11 pr-3 text-base text-foreground placeholder:text-foreground/50",
                      "focus-visible:border-primary focus-visible:bg-card/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
                    )}
                  />
                </div>
                <p className="text-sm font-medium text-foreground/70">
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
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
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

      {/* ─── STEP 2 — Model browser (inline) ────────────────────────── */}
      <section>
        <SectionHeader
          step={2}
          icon={<Cpu className="size-5" />}
          title="Pick a model"
          subtitle={
            orError
              ? `OpenRouter catalog unreachable (${orError}) — type the model id directly.`
              : selectedRecipe?.verified_models?.length
                ? `${selectedRecipe.verified_models.length} model${selectedRecipe.verified_models.length === 1 ? "" : "s"} verified end-to-end with ${selectedRecipe.display_name ?? selectedRecipe.name} — pinned on top. Or pick any of ${orModels?.length ?? "…"} OpenRouter models.`
                : `Filter ${orModels?.length ?? "…"} OpenRouter models by provider or price. Your recently-used models are pinned on top.`
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
          <ModelBrowser
            models={orModels}
            value={model}
            onChange={setModel}
            disabled={isRunning}
            selected={selectedModelMeta}
            recentModels={recentModels}
            verifiedModels={selectedRecipe?.verified_models ?? []}
            recipeName={selectedRecipe?.display_name ?? selectedRecipe?.name ?? null}
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

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          {/* Name — 1/3 column */}
          <div className="flex flex-col gap-3">
            <Label htmlFor="agent-name" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <Boxes className="size-5 text-foreground/70" /> Agent name
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
            <p className="text-sm leading-relaxed text-foreground/70">
              Stored in your account. Letters, numbers, spaces, <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground/90">_</code> and <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground/90">-</code>. Must be unique among your agents.
            </p>
          </div>

          {/* Personality — 2/3 column */}
          <div className="flex flex-col gap-3 lg:col-span-2">
            <Label className="flex items-center gap-2 text-base font-semibold text-foreground">
              <MessageSquareText className="size-5 text-foreground/70" /> Personality preset
            </Label>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
                      "group flex h-full items-start gap-3 rounded-xl border p-4 text-left transition-all",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                      active
                        ? "border-primary/70 bg-primary/10 shadow-lg shadow-primary/15"
                        : "border-border/50 bg-card/40 hover:border-primary/40 hover:bg-card/70",
                      isRunning && "cursor-not-allowed opacity-60",
                    )}
                  >
                    <span className="text-3xl leading-none" aria-hidden>{p.emoji}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-semibold text-foreground">{p.label}</span>
                        {active && <Check className="size-4 text-primary" />}
                      </div>
                      <p className="mt-1 text-sm leading-snug text-foreground/70">{p.description}</p>
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
          <div className="flex flex-col gap-3">
            <Label htmlFor="byok" className="flex items-center gap-2 text-base font-semibold text-foreground">
              <KeyRound className="size-5 text-foreground/70" /> OpenRouter API key
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
            <p className="text-sm leading-relaxed text-foreground/70">
              Sent as <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground/90">Authorization: Bearer</code>. Cleared from React state after submit.
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
              <p className="mt-4 text-center text-base text-foreground/70">
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
              <p role="alert" className="mt-4 text-center text-base font-medium text-destructive">
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
    <div className="mb-6 flex items-start gap-4">
      <div className="flex size-14 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/15 text-primary shadow-sm shadow-primary/10">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-sm font-bold uppercase tracking-widest text-primary">Step {step}</span>
        </div>
        <h2 className="mt-1 text-2xl font-bold text-foreground sm:text-3xl">{title}</h2>
        <p className="mt-1.5 text-base leading-relaxed text-foreground/75">{subtitle}</p>
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
      <div className="flex items-start gap-4 p-6 pb-4">
        <div
          className={cn(
            "flex size-14 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-gradient-to-br font-mono text-lg font-bold text-white shadow-inner",
            accent.from.replace("/30", "/70"),
            accent.to.replace("/10", "/50"),
          )}
        >
          {initials}
        </div>
        <div className="min-w-0 flex-1 pr-8">
          <h3 className="text-xl font-bold leading-tight text-foreground" title={recipe.display_name ?? recipe.name}>
            {recipe.display_name ?? recipe.name}
          </h3>
          <p className="mt-1 font-mono text-sm text-foreground/60">{recipe.name}</p>
        </div>
      </div>

      {/* Tagline */}
      {tagline && (
        <p className="line-clamp-3 px-6 text-base leading-relaxed text-foreground/90">
          {tagline}
        </p>
      )}

      {/* Stats strip */}
      <div className="mt-5 flex flex-wrap items-center gap-2 px-6 pb-4">
        {version && (
          <span className="inline-flex items-center gap-1 rounded-md border border-border/50 bg-muted/40 px-2 py-1 font-mono text-xs text-foreground/85">
            {version}
          </span>
        )}
        {recipe.image_size_gb != null && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-muted/40 px-2 py-1 text-xs text-foreground/85">
            <HardDrive className="size-3.5 opacity-80" />
            <span className="font-mono">{recipe.image_size_gb.toFixed(1)}GB</span>
          </span>
        )}
        {recipe.expected_runtime_seconds != null && (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-muted/40 px-2 py-1 text-xs text-foreground/85">
            <Timer className="size-3.5 opacity-80" />
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
          className="mt-auto flex items-center gap-2 border-t border-border/50 bg-background/30 px-6 py-3 font-mono text-sm text-foreground/75 transition-colors hover:bg-muted/30 hover:text-foreground"
        >
          <Github className="size-4 shrink-0" />
          <span className="truncate">{repoOwnerRepo}</span>
          {recipe.source_ref && (
            <code className="ml-auto rounded bg-muted/70 px-1.5 py-0.5 text-xs text-foreground/90">
              {shortRef(recipe.source_ref)}
            </code>
          )}
          <ExternalLink className="size-3.5 shrink-0 opacity-60" />
        </a>
      )}
    </button>
  );
}

// ─── ModelBrowser ─────────────────────────────────────────────────────
function isFreeModel(m: OpenRouterModel): boolean {
  const p = Number.parseFloat(m.pricing?.prompt ?? "0");
  const c = Number.parseFloat(m.pricing?.completion ?? "0");
  return Number.isFinite(p) && p === 0 && Number.isFinite(c) && c === 0;
}

function ModelBrowser({
  models,
  value,
  onChange,
  disabled,
  selected,
  recentModels,
  verifiedModels,
  recipeName,
}: {
  models: OpenRouterModel[] | null;
  value: string;
  onChange: (id: string) => void;
  disabled: boolean;
  selected: OpenRouterModel | null;
  recentModels: string[];
  verifiedModels: string[];
  recipeName: string | null;
}) {
  const [query, setQuery] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);
  const [testedOnly, setTestedOnly] = useState(false);
  const [selectedProviders, setSelectedProviders] = useState<Set<string>>(() => new Set());

  const verifiedSet = useMemo(() => new Set(verifiedModels), [verifiedModels]);
  const hasVerified = verifiedModels.length > 0;

  // Auto-clear testedOnly if the recipe changes and new one has no verified list
  useEffect(() => {
    if (!hasVerified) setTestedOnly(false);
  }, [hasVerified]);

  const loading = models === null;

  const { topProviders, providerCounts } = useMemo(() => {
    const counts = new Map<string, number>();
    for (const m of models ?? []) {
      const p = m.id.split("/")[0] || "other";
      counts.set(p, (counts.get(p) ?? 0) + 1);
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    return {
      topProviders: sorted.slice(0, 8).map(([p]) => p),
      providerCounts: counts,
    };
  }, [models]);

  const filtered = useMemo(() => {
    if (!models) return [];
    const tokens = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    return models.filter((m) => {
      if (testedOnly && !verifiedSet.has(m.id)) return false;
      if (freeOnly && !isFreeModel(m)) return false;
      if (selectedProviders.size > 0) {
        const p = m.id.split("/")[0] || "other";
        if (!selectedProviders.has(p)) return false;
      }
      if (tokens.length) {
        const hay = `${m.id} ${m.name}`.toLowerCase();
        if (!tokens.every((t) => hay.includes(t))) return false;
      }
      return true;
    });
  }, [models, query, freeOnly, testedOnly, verifiedSet, selectedProviders]);

  const sorted = useMemo(() => {
    const recentRank = new Map<string, number>();
    recentModels.forEach((id, i) => recentRank.set(id, i));
    return [...filtered].sort((a, b) => {
      // Tier 1: verified for this recipe — always on top
      const av = verifiedSet.has(a.id);
      const bv = verifiedSet.has(b.id);
      if (av && !bv) return -1;
      if (!av && bv) return 1;
      // Tier 2: user's recent picks
      const ar = recentRank.get(a.id);
      const br = recentRank.get(b.id);
      if (ar !== undefined && br !== undefined) return ar - br;
      if (ar !== undefined) return -1;
      if (br !== undefined) return 1;
      // Tier 3: alphabetical
      return a.id.localeCompare(b.id);
    });
  }, [filtered, recentModels, verifiedSet]);

  const toggleProvider = (p: string) =>
    setSelectedProviders((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });

  const hasFilters = query.length > 0 || freeOnly || testedOnly || selectedProviders.size > 0;
  const clearFilters = () => {
    setQuery("");
    setFreeOnly(false);
    setTestedOnly(false);
    setSelectedProviders(new Set());
  };

  if (loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-border/50 bg-card/30 p-8 text-foreground/80">
        <Loader2 className="size-5 animate-spin" />
        <span className="text-base">Loading models from OpenRouter…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Selected model bar */}
      {selected && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-primary/50 bg-primary/10 px-5 py-4 shadow-sm shadow-primary/10">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
            <Check className="size-5" strokeWidth={2.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="truncate font-mono text-lg font-semibold text-foreground">{selected.id}</span>
              {isFreeModel(selected) && (
                <span className="inline-flex items-center rounded-md border border-emerald-500/50 bg-emerald-500/20 px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-emerald-200">
                  free
                </span>
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-foreground/75">
              <span className="truncate">{selected.name}</span>
              {formatContext(selected.context_length) && (
                <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                  {formatContext(selected.context_length)} ctx
                </span>
              )}
              {!isFreeModel(selected) && formatPricePerMTok(selected.pricing?.prompt) && (
                <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                  {formatPricePerMTok(selected.pricing?.prompt)}/M in
                </span>
              )}
              {!isFreeModel(selected) && formatPricePerMTok(selected.pricing?.completion) && (
                <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                  {formatPricePerMTok(selected.pricing?.completion)}/M out
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => onChange("")}
            disabled={disabled}
            className="shrink-0 rounded-md border border-border/60 bg-card/50 px-3 py-1.5 text-sm font-medium text-foreground/80 transition-colors hover:border-primary/50 hover:bg-card/80 hover:text-foreground disabled:opacity-50"
          >
            Change
          </button>
        </div>
      )}

      {/* Toolbar: search + FREE + provider chips */}
      <div className="flex flex-col gap-3 rounded-2xl border border-border bg-card/50 p-4 shadow-lg shadow-black/20 ring-1 ring-white/5">
        <div className="flex flex-col items-stretch gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <SearchIcon className="pointer-events-none absolute left-3.5 top-1/2 size-5 -translate-y-1/2 text-foreground/50" />
            <input
              type="search"
              placeholder="Search models — 'claude opus', 'gpt-4o'…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={disabled}
              className={cn(
                "h-12 w-full rounded-lg border border-border bg-background/70 pl-11 pr-3 text-base text-foreground placeholder:text-foreground/50",
                "focus-visible:border-primary focus-visible:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30",
              )}
            />
          </div>
          {hasVerified && (
            <button
              type="button"
              onClick={() => setTestedOnly((v) => !v)}
              disabled={disabled}
              aria-pressed={testedOnly}
              title={`${verifiedModels.length} model${verifiedModels.length === 1 ? "" : "s"} tested with ${recipeName ?? "this recipe"}`}
              className={cn(
                "inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-lg border px-5 text-base font-semibold transition-all",
                testedOnly
                  ? "border-primary/70 bg-primary/20 text-primary shadow-sm shadow-primary/20"
                  : "border-border/60 bg-card/50 text-foreground/85 hover:border-primary/40 hover:bg-primary/5 hover:text-primary",
              )}
            >
              <span className="text-lg leading-none" aria-hidden>🧪</span>
              Tested ({verifiedModels.length})
            </button>
          )}
          <button
            type="button"
            onClick={() => setFreeOnly((v) => !v)}
            disabled={disabled}
            aria-pressed={freeOnly}
            className={cn(
              "inline-flex h-12 shrink-0 items-center justify-center gap-2 rounded-lg border px-5 text-base font-semibold transition-all",
              freeOnly
                ? "border-emerald-500/60 bg-emerald-500/20 text-emerald-200 shadow-sm shadow-emerald-500/20"
                : "border-border/60 bg-card/50 text-foreground/85 hover:border-emerald-500/40 hover:bg-emerald-500/5 hover:text-emerald-200",
            )}
          >
            <span className="text-lg leading-none" aria-hidden>🆓</span>
            FREE only
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 font-mono text-xs font-semibold uppercase tracking-wider text-foreground/60">
            Provider
          </span>
          {topProviders.map((p) => {
            const active = selectedProviders.has(p);
            const count = providerCounts.get(p) ?? 0;
            return (
              <button
                key={p}
                type="button"
                onClick={() => toggleProvider(p)}
                disabled={disabled}
                aria-pressed={active}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-all",
                  active
                    ? "border-primary/70 bg-primary/15 font-semibold text-foreground shadow-sm shadow-primary/20"
                    : "border-border/60 bg-card/40 text-foreground/80 hover:border-primary/40 hover:bg-card/70",
                )}
              >
                {p}
                <span
                  className={cn(
                    "font-mono text-xs",
                    active ? "text-foreground/70" : "text-foreground/50",
                  )}
                >
                  {count}
                </span>
              </button>
            );
          })}
          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="ml-auto rounded-md px-2 py-1 text-sm text-foreground/70 hover:bg-muted/40 hover:text-foreground"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Results header */}
      <div className="flex items-baseline justify-between px-1 text-sm text-foreground/70">
        <span>
          <span className="font-semibold text-foreground">{sorted.length}</span>
          <span className="text-foreground/60"> of {models.length} models</span>
          {hasVerified && (
            <span className="ml-2 text-emerald-400/80">· tested for {recipeName} pinned ↑</span>
          )}
          {!hasVerified && recentModels.length > 0 && (
            <span className="ml-2 text-foreground/50">· your recent picks pinned ↑</span>
          )}
        </span>
      </div>

      {/* List */}
      {sorted.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border bg-card/30 p-10 text-center">
          <p className="text-base text-foreground/75">No model matches your filters.</p>
          <button
            type="button"
            onClick={clearFilters}
            className="mt-3 text-sm font-semibold text-primary hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="model-browser-scroll max-h-[36rem] overflow-y-auto rounded-2xl border border-border bg-card/50 shadow-lg shadow-black/20 ring-1 ring-white/5">
          <ul className="divide-y divide-border">
            {sorted.map((m) => (
              <ModelRow
                key={m.id}
                model={m}
                isSelected={value === m.id}
                isRecent={recentModels.includes(m.id)}
                isVerified={verifiedSet.has(m.id)}
                onSelect={() => onChange(m.id)}
                disabled={disabled}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ModelRow({
  model,
  isSelected,
  isRecent,
  isVerified,
  onSelect,
  disabled,
}: {
  model: OpenRouterModel;
  isSelected: boolean;
  isRecent: boolean;
  isVerified: boolean;
  onSelect: () => void;
  disabled: boolean;
}) {
  const promptP = formatPricePerMTok(model.pricing?.prompt);
  const completionP = formatPricePerMTok(model.pricing?.completion);
  const c = formatContext(model.context_length);
  const free = isFreeModel(model);

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        disabled={disabled}
        aria-pressed={isSelected}
        className={cn(
          "flex w-full flex-col gap-2 px-5 py-4 text-left transition-colors",
          "focus-visible:outline-none focus-visible:bg-primary/15",
          "hover:bg-muted/50",
          isSelected
            ? "bg-primary/20 border-l-4 border-l-primary pl-[calc(1.25rem-4px)] shadow-inner"
            : isVerified
              ? "border-l-4 border-l-emerald-500/60 bg-emerald-500/[0.04] pl-[calc(1.25rem-4px)]"
              : "border-l-4 border-l-transparent pl-[calc(1.25rem-4px)]",
          disabled && "cursor-not-allowed opacity-50",
        )}
      >
        <div className="flex w-full items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className="truncate font-mono text-base font-semibold text-foreground">
              {model.id}
            </span>
            {isVerified && (
              <span
                title="Recipe author tested this model end-to-end and it passed the smoke"
                className="inline-flex shrink-0 items-center gap-1 rounded-md border border-emerald-500/60 bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-200"
              >
                <span aria-hidden>🧪</span>
                tested
              </span>
            )}
            {isRecent && (
              <span className="inline-flex shrink-0 items-center rounded-md border border-primary/50 bg-primary/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary">
                recent
              </span>
            )}
            {free && (
              <span className="inline-flex shrink-0 items-center rounded-md border border-emerald-500/50 bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-200">
                free
              </span>
            )}
          </div>
          {isSelected && <Check className="size-5 shrink-0 text-primary" strokeWidth={2.5} />}
        </div>
        <div className="flex w-full flex-wrap items-center gap-2">
          <span className="truncate text-sm text-foreground/75">{model.name}</span>
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            {c && (
              <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                {c}
              </span>
            )}
            {!free && promptP && (
              <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                {promptP}/M in
              </span>
            )}
            {!free && completionP && (
              <span className="inline-flex items-center rounded-md border border-border/60 bg-muted/60 px-2 py-0.5 font-mono text-xs text-foreground/85">
                {completionP}/M out
              </span>
            )}
          </div>
        </div>
      </button>
    </li>
  );
}
