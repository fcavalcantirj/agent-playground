"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import {
  Plus,
  Search,
  Square,
  MoreVertical,
  ExternalLink,
  Activity,
  Clock,
  Zap,
  Terminal,
  Settings2,
  Loader2,
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { apiGet, apiPost } from "@/lib/api"
import {
  parseApiError,
  type AgentListResponse,
  type AgentStatusResponse,
  type AgentStopResponse,
  type AgentSummary,
  type UiError,
} from "@/lib/api-types"

// Module-scope sleep helper — kept out of the component so it isn't recreated
// on every render and Turbopack HMR can hot-swap component bodies cleanly.
const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

// Local copy of timeAgo (mirrors frontend/components/my-agents-panel.tsx lines 37–48
// — kept inline to keep the diff scoped to this file per plan instructions).
function timeAgo(iso?: string | null): string {
  if (!iso) return "—"
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return "just now"
  const m = Math.floor(ms / 60_000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

type StatusEntry = AgentStatusResponse | "loading" | "error"

export default function DashboardPage() {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null)
  const [listError, setListError] = useState<UiError | null>(null)
  const [statuses, setStatuses] = useState<Record<string, StatusEntry>>({})
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "stopped">("all")

  // ---- Task 2 — Stop wiring state ----
  const [stoppingId, setStoppingId] = useState<string | null>(null)
  const [bearerPromptFor, setBearerPromptFor] = useState<string | null>(null)
  const [bearerInput, setBearerInput] = useState("")
  const [stopError, setStopError] = useState<{ id: string; message: string } | null>(null)

  // Lifetime refs for the polling loop. The mountedRef gates every state setter
  // inside async paths (status fetch, stop confirm, polling) so unmount during
  // a long-running poll cannot trigger React "set state on unmounted" warnings.
  // The pollAbortRef is the AbortController for the in-flight /status request
  // inside pollUntilStopped — calling .abort() on unmount cancels the fetch.
  const mountedRef = useRef(true)
  const pollAbortRef = useRef<AbortController | null>(null)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      pollAbortRef.current?.abort()
    }
  }, [])

  const loadAgents = useCallback(async () => {
    try {
      const data = await apiGet<AgentListResponse>("/api/v1/agents")
      setAgents(data.agents)
      setListError(null)

      // Mark each row as "loading" up-front so the UI can render the
      // checking… state without a flash. Then fan out parallel /status
      // probes; each one updates its own slot. A single failed status
      // MUST NOT prevent other agents from rendering.
      setStatuses(prev => {
        const next: Record<string, StatusEntry> = { ...prev }
        for (const a of data.agents) next[a.id] = "loading"
        return next
      })

      await Promise.allSettled(
        data.agents.map(async (a) => {
          try {
            const s = await apiGet<AgentStatusResponse>(`/api/v1/agents/${a.id}/status`)
            setStatuses(prev => ({ ...prev, [a.id]: s }))
          } catch {
            setStatuses(prev => ({ ...prev, [a.id]: "error" }))
          }
        }),
      )
    } catch (e) {
      setListError(parseApiError(e))
    }
  }, [])

  useEffect(() => {
    loadAgents()
  }, [loadAgents])

  // ---- Task 2 — Stop click → Bearer prompt → POST /stop → poll /status ----

  function onStopClick(agent: AgentSummary) {
    if (stoppingId !== null) return // another stop in flight; UI also disables
    setStopError(null)
    setBearerInput("")
    setBearerPromptFor(agent.id)
  }

  function onCancelBearer() {
    setBearerPromptFor(null)
    setBearerInput("")
  }

  // Poll /status every 2s until runtime_running=false or 60s ceiling.
  // Transient fetch errors don't break the loop — only an abort cancels it.
  const pollUntilStopped = useCallback(async (agentId: string) => {
    pollAbortRef.current?.abort()
    const ctrl = new AbortController()
    pollAbortRef.current = ctrl

    for (let i = 0; i < 30; i++) {
      await sleep(2000)
      if (ctrl.signal.aborted || !mountedRef.current) return
      try {
        const s = await apiGet<AgentStatusResponse>(
          `/api/v1/agents/${agentId}/status`,
          { signal: ctrl.signal },
        )
        if (!mountedRef.current) return
        setStatuses(prev => ({ ...prev, [agentId]: s }))
        if (!s.runtime_running) return
      } catch {
        // Transient errors (mid-stop daemon flap, network blip) are expected;
        // keep polling. The only exit paths are runtime_running=false, abort,
        // or the 30-iteration ceiling.
      }
    }
  }, [])

  async function onConfirmStop(agentId: string) {
    setStoppingId(agentId)
    setBearerPromptFor(null)
    setStopError(null)

    // BYOK discipline (mirrors playground-form lines 374–376):
    // clear the Bearer from React state BEFORE the await so an unmount,
    // re-render, or devtools snapshot cannot capture it.
    const key = bearerInput.trim()
    setBearerInput("")

    try {
      await apiPost<AgentStopResponse>(
        `/api/v1/agents/${agentId}/stop`,
        undefined,
        { Authorization: `Bearer ${key}` },
      )
    } catch (e) {
      if (mountedRef.current) {
        setStopError({ id: agentId, message: parseApiError(e).message })
        setStoppingId(null)
      }
      return
    }

    // Stop request returned; poll /status until container is gone.
    await pollUntilStopped(agentId)

    if (!mountedRef.current) return
    // Refresh the full list so total_runs / last_run_at / etc are fresh,
    // then release the spinner.
    await loadAgents()
    if (mountedRef.current) setStoppingId(null)
  }

  // Helpers that read the per-row status row safely.
  function statusOf(id: string): StatusEntry | undefined {
    return statuses[id]
  }
  function isRunning(id: string): boolean {
    const s = statusOf(id)
    return s !== undefined && s !== "loading" && s !== "error" && s.runtime_running === true
  }
  function isStopped(id: string): boolean {
    const s = statusOf(id)
    if (s === undefined || s === "loading" || s === "error") return false
    return s.runtime_running === false && s.container_status != null
  }

  const filteredAgents = (agents ?? []).filter(agent => {
    const q = searchQuery.toLowerCase()
    const matchesSearch =
      agent.name.toLowerCase().includes(q) ||
      agent.recipe_name.toLowerCase().includes(q)
    if (!matchesSearch) return false
    if (statusFilter === "all") return true
    if (statusFilter === "running") return isRunning(agent.id)
    if (statusFilter === "stopped") return isStopped(agent.id)
    return true
  })

  const allStatusesLoaded =
    agents !== null &&
    agents.every(a => {
      const s = statuses[a.id]
      return s !== undefined && s !== "loading"
    })
  const runningCount = agents
    ? agents.filter(a => isRunning(a.id)).length
    : 0
  const totalRuns = agents
    ? agents.reduce((s, a) => s + a.total_runs, 0)
    : 0

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl">My Agents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage and monitor your deployed agents
          </p>
        </div>
        <Button asChild className="gap-2 bg-primary text-primary-foreground">
          <Link href="/playground">
            <Plus className="h-4 w-4" />
            New Agent
          </Link>
        </Button>
      </div>

      {/* Stats */}
      <div className="mb-6 grid gap-4 sm:mb-8 sm:grid-cols-3">
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Activity className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">
                {allStatusesLoaded ? runningCount : "—"}
              </p>
              <p className="text-xs text-muted-foreground">Running Agents</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10">
              <Zap className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{agents?.length ?? 0}</p>
              <p className="text-xs text-muted-foreground">Total Agents</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10">
              <Zap className="h-5 w-5 text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{totalRuns.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">Total runs</p>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-xs flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search agents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-background/50 pl-9"
          />
        </div>
        <div className="flex gap-2">
          {(["all", "running", "stopped"] as const).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                statusFilter === status
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted/50 text-muted-foreground hover:bg-muted"
              )}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Body — loading / error / empty / populated */}
      {agents === null && !listError ? (
        <div className="flex items-center gap-3 rounded-2xl border border-border/40 bg-card/30 px-6 py-8 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          <span className="text-sm">Loading your deployed agents…</span>
        </div>
      ) : listError ? (
        <div className="rounded-2xl border border-amber-500/40 bg-amber-500/5 p-6 text-amber-200">
          <p className="text-sm">Couldn&apos;t load your agents: {listError.message}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={loadAgents}>Retry</Button>
        </div>
      ) : agents !== null && agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12 text-center">
          <Activity className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-base font-semibold text-foreground">No agents deployed yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Head to the playground to deploy your first agent.
          </p>
          <Button asChild className="mt-4 bg-primary text-primary-foreground">
            <Link href="/playground">Go to playground</Link>
          </Button>
        </div>
      ) : (
        <ScrollArea className="h-[calc(100vh-400px)] min-h-[300px]">
          <div className="space-y-3">
            {filteredAgents.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12 text-center">
                <Activity className="mb-3 h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">No agents match your filters</p>
              </div>
            ) : (
              filteredAgents.map((agent) => {
                const sEntry = statusOf(agent.id)
                const running = isRunning(agent.id)
                const channelChip =
                  sEntry && sEntry !== "loading" && sEntry !== "error"
                    ? sEntry.channel ?? null
                    : null

                let pill: { label: string; muted: boolean; pulse: boolean }
                if (sEntry === undefined || sEntry === "loading") {
                  pill = { label: "checking…", muted: true, pulse: false }
                } else if (sEntry === "error") {
                  pill = { label: "status unavailable", muted: true, pulse: false }
                } else if (sEntry.runtime_running === true) {
                  pill = { label: "running", muted: false, pulse: true }
                } else if (sEntry.container_status == null) {
                  pill = { label: "never started", muted: true, pulse: false }
                } else {
                  pill = { label: "stopped", muted: true, pulse: false }
                }

                return (
                  <div
                    key={agent.id}
                    className={cn(
                      "rounded-xl border p-4 transition-all sm:p-5",
                      running
                        ? "border-green-500/30 bg-green-500/5"
                        : "border-border/50 bg-card/30"
                    )}
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                      {/* Agent Info */}
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex items-center gap-2">
                          <h3 className="truncate font-semibold text-foreground">{agent.name}</h3>
                          <span className={cn(
                            "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                            pill.muted
                              ? "bg-muted text-muted-foreground"
                              : "bg-green-500/20 text-green-400"
                          )}>
                            {sEntry === "loading" ? (
                              <Loader2 className="h-2.5 w-2.5 animate-spin" />
                            ) : (
                              <span className={cn(
                                "h-1.5 w-1.5 rounded-full",
                                pill.pulse
                                  ? "animate-pulse bg-green-500"
                                  : "bg-muted-foreground"
                              )} />
                            )}
                            {pill.label}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          Recipe: {agent.recipe_name} · {agent.model}
                          {agent.last_verdict ? ` · last: ${agent.last_verdict}` : ""}
                        </p>

                        {/* Channels & Stats */}
                        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Zap className="h-3 w-3" />
                            {agent.total_runs} run{agent.total_runs === 1 ? "" : "s"}
                          </div>
                          <div className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {timeAgo(agent.last_run_at ?? agent.created_at)}
                          </div>
                          {channelChip ? (
                            <div className="flex gap-1">
                              <span className="rounded bg-muted/50 px-1.5 py-0.5">{channelChip}</span>
                            </div>
                          ) : null}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2">
                        {running ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => onStopClick(agent)}
                            disabled={
                              sEntry === "loading" ||
                              (stoppingId !== null && stoppingId !== agent.id)
                            }
                            className="gap-1.5 border-green-500/30 text-green-400 hover:bg-green-500/10"
                          >
                            {stoppingId === agent.id ? (
                              <>
                                <Loader2 className="h-3 w-3 animate-spin" />
                                Stopping…
                              </>
                            ) : (
                              <>
                                <Square className="h-3 w-3" />
                                Stop
                              </>
                            )}
                          </Button>
                        ) : (
                          // /start requires Bearer + channel_inputs (see AgentStartRequest);
                          // /playground is where the user supplies them. Re-deploying via
                          // /playground UPSERTs into the same agent_instances row keyed by
                          // (user, recipe, model).
                          <Button asChild variant="outline" size="sm" className="gap-1.5">
                            <Link
                              href={`/playground?recipe=${agent.recipe_name}&model=${encodeURIComponent(agent.model)}`}
                            >
                              <Plus className="h-3 w-3" />
                              Start
                            </Link>
                          </Button>
                        )}

                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild>
                              <Link href={`/dashboard/agents/${agent.id}`}>
                                <ExternalLink className="mr-2 h-4 w-4" />
                                View Details
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem asChild>
                              <Link href={`/dashboard/agents/${agent.id}/logs`}>
                                <Terminal className="mr-2 h-4 w-4" />
                                View Logs
                              </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem asChild>
                              <Link href={`/dashboard/agents/${agent.id}/settings`}>
                                <Settings2 className="mr-2 h-4 w-4" />
                                Settings
                              </Link>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>

                    {stopError?.id === agent.id ? (
                      <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-xs text-rose-300">
                        <span>Stop failed: {stopError.message}</span>
                        <button
                          type="button"
                          onClick={() => setStopError(null)}
                          className="underline underline-offset-2 hover:text-rose-200"
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : null}
                  </div>
                )
              })
            )}
          </div>
        </ScrollArea>
      )}

      {/* Bearer-prompt confirm dialog for /stop */}
      <Dialog
        open={bearerPromptFor !== null}
        onOpenChange={(open) => {
          if (!open) onCancelBearer()
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              Confirm stop
              {bearerPromptFor
                ? ` for ${
                    agents?.find(a => a.id === bearerPromptFor)?.name ?? bearerPromptFor
                  }`
                : ""}
            </DialogTitle>
            <DialogDescription>
              The /stop endpoint requires an Authorization: Bearer header but
              does not read its value. Your input is cleared from React state
              immediately after the request.
            </DialogDescription>
          </DialogHeader>
          <Input
            type="password"
            autoComplete="off"
            placeholder="Bearer key (any non-empty value works for /stop — your provider key)"
            value={bearerInput}
            onChange={(e) => setBearerInput(e.target.value)}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                bearerPromptFor &&
                bearerInput.trim().length > 0
              ) {
                onConfirmStop(bearerPromptFor)
              }
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={onCancelBearer}>
              Cancel
            </Button>
            <Button
              onClick={() => bearerPromptFor && onConfirmStop(bearerPromptFor)}
              disabled={bearerInput.trim().length === 0 || !bearerPromptFor}
            >
              Stop
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
