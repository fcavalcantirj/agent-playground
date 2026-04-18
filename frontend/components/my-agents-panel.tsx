"use client";

import { useCallback, useEffect, useImperativeHandle, useState, forwardRef } from "react";
import {
  Loader2,
  Box,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
  Cpu,
  Clock,
} from "lucide-react";

import { apiGet } from "@/lib/api";
import {
  parseApiError,
  PERSONALITIES,
  type AgentListResponse,
  type AgentSummary,
  type PersonalityId,
  type UiError,
} from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const RECIPE_ACCENTS: Record<string, { from: string; to: string; ring: string }> = {
  hermes:   { from: "from-violet-500/40",  to: "to-purple-500/10",  ring: "ring-violet-500/30" },
  nanobot:  { from: "from-amber-500/40",   to: "to-yellow-500/10",  ring: "ring-amber-500/30" },
  nullclaw: { from: "from-indigo-500/40",  to: "to-blue-500/10",    ring: "ring-indigo-500/30" },
  openclaw: { from: "from-emerald-500/40", to: "to-teal-500/10",    ring: "ring-emerald-500/30" },
  picoclaw: { from: "from-rose-500/40",    to: "to-orange-500/10",  ring: "ring-rose-500/30" },
};

function timeAgo(iso?: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60_000) return "just now";
  const m = Math.floor(ms / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function personalityFor(id?: PersonalityId | string | null) {
  if (!id) return null;
  return PERSONALITIES.find((p) => p.id === id) ?? null;
}

export type MyAgentsPanelHandle = {
  refetch: () => void;
};

export const MyAgentsPanel = forwardRef<
  MyAgentsPanelHandle,
  { highlightAgentId?: string | null }
>(function MyAgentsPanel({ highlightAgentId }, ref) {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [error, setError] = useState<UiError | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiGet<AgentListResponse>("/api/v1/agents");
      setAgents(data.agents);
      setError(null);
    } catch (e) {
      setError(parseApiError(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useImperativeHandle(ref, () => ({ refetch: load }), [load]);

  if (agents === null && !error) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-border/40 bg-card/30 px-6 py-8 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        <span className="text-sm">Loading your deployed agents…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-amber-500/40 bg-amber-500/5 p-6 text-amber-200">
        <p className="text-sm">Couldn't load your agents: {error.message}</p>
        <Button variant="outline" size="sm" className="mt-3" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!agents || agents.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border/60 bg-card/20 px-6 py-12 text-center">
        <Box className="size-8 text-muted-foreground/60" />
        <h3 className="text-base font-semibold text-foreground">No agents deployed yet</h3>
        <p className="max-w-sm text-sm text-muted-foreground">
          Configure your first agent below — pick a recipe, a model, give it a name and a personality, and click Deploy.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-5 flex items-baseline justify-between gap-3">
        <h2 className="text-3xl font-bold text-foreground sm:text-4xl">
          Your agents <span className="font-normal text-muted-foreground">({agents.length})</span>
        </h2>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-card/40 px-3 py-1.5 text-sm text-foreground/80 transition-colors hover:border-primary/40 hover:bg-card/70 hover:text-foreground"
        >
          ↻ refresh
        </button>
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {agents.map((a) => (
          <AgentCard key={a.id} agent={a} highlight={a.id === highlightAgentId} />
        ))}
      </div>
    </div>
  );
});

function AgentCard({ agent, highlight }: { agent: AgentSummary; highlight: boolean }) {
  const accent = RECIPE_ACCENTS[agent.recipe_name] ?? RECIPE_ACCENTS.hermes;
  const persona = personalityFor(agent.personality);
  const verdictBadge = (() => {
    if (!agent.last_verdict) {
      return { label: "Not run", icon: Activity, classes: "bg-muted/60 text-foreground/80 ring-1 ring-border/60" };
    }
    if (agent.last_verdict === "PASS") {
      return { label: "PASS", icon: CheckCircle2, classes: "bg-emerald-500/20 text-emerald-200 ring-1 ring-emerald-400/40" };
    }
    if (agent.last_category === "INFRA_FAIL") {
      return { label: "INFRA", icon: AlertTriangle, classes: "bg-amber-500/20 text-amber-200 ring-1 ring-amber-400/40" };
    }
    return { label: agent.last_verdict, icon: XCircle, classes: "bg-rose-500/20 text-rose-200 ring-1 ring-rose-400/40" };
  })();

  const VIcon = verdictBadge.icon;

  return (
    <div
      className={cn(
        "group relative isolate flex h-full flex-col overflow-hidden rounded-2xl border bg-card/40 backdrop-blur-sm transition-all",
        highlight
          ? cn("border-primary/70 ring-2 shadow-2xl", accent.ring)
          : "border-border/50 hover:-translate-y-0.5 hover:border-border/80 hover:bg-card/60 hover:shadow-xl",
      )}
    >
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 -z-10 h-28 bg-gradient-to-b opacity-80",
          accent.from,
          accent.to,
        )}
      />

      <div className="flex items-start justify-between gap-3 p-5 pb-3">
        <div className="min-w-0 flex-1">
          <h3
            className="line-clamp-2 break-words text-xl font-bold leading-tight text-foreground"
            title={agent.name}
          >
            {agent.name}
          </h3>
          <p className="mt-1.5 flex items-center gap-1.5 truncate font-mono text-sm text-foreground/70">
            <Box className="size-3.5 shrink-0 opacity-80" />
            {agent.recipe_name}
          </p>
        </div>
        <div
          className={cn(
            "inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-bold uppercase tracking-wider",
            verdictBadge.classes,
          )}
        >
          <VIcon className="size-3.5" />
          {verdictBadge.label}
        </div>
      </div>

      <div className="px-5 pb-4">
        <p
          className="flex items-center gap-1.5 truncate font-mono text-sm text-foreground/80"
          title={agent.model}
        >
          <Cpu className="size-3.5 shrink-0 opacity-80" />
          {agent.model}
        </p>
      </div>

      {persona && (
        <div className="mx-5 mb-4 flex items-center gap-2.5 rounded-lg border border-border/50 bg-muted/30 px-3 py-2 text-sm">
          <span className="text-lg leading-none" aria-hidden>{persona.emoji}</span>
          <span className="truncate font-medium text-foreground/90">{persona.label}</span>
        </div>
      )}

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border/50 bg-background/30 px-5 py-3 text-sm text-foreground/70">
        <span className="inline-flex items-center gap-1.5">
          <Sparkles className="size-3.5 opacity-80" />
          {agent.total_runs} run{agent.total_runs === 1 ? "" : "s"}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Clock className="size-3.5 opacity-80" />
          {timeAgo(agent.last_run_at ?? agent.created_at)}
        </span>
      </div>
    </div>
  );
}
