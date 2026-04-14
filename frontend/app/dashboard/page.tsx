"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import {
  Plus,
  Search,
  Play,
  Square,
  MoreVertical,
  Trash2,
  Copy,
  ExternalLink,
  Activity,
  MessageSquare,
  Clock,
  Zap,
  Terminal,
  Settings2,
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface Agent {
  id: string
  name: string
  clone: string
  model: string
  status: "running" | "stopped"
  channels: string[]
  messagesProcessed: number
  uptime: string
  lastActive: string
}

const mockAgents: Agent[] = [
  {
    id: "1",
    name: "Customer Support Bot",
    clone: "Hermes-agent",
    model: "Claude 3 Sonnet",
    status: "running",
    channels: ["Discord", "Telegram"],
    messagesProcessed: 12453,
    uptime: "14d 6h",
    lastActive: "2 min ago",
  },
  {
    id: "2",
    name: "Code Assistant",
    clone: "ZeroClaw",
    model: "GPT-4 Turbo",
    status: "running",
    channels: ["Slack", "CLI"],
    messagesProcessed: 8721,
    uptime: "7d 12h",
    lastActive: "5 min ago",
  },
  {
    id: "3",
    name: "Research Agent",
    clone: "OpenClaw",
    model: "Claude 3 Opus",
    status: "stopped",
    channels: ["Webhook"],
    messagesProcessed: 3412,
    uptime: "-",
    lastActive: "2 days ago",
  },
  {
    id: "4",
    name: "Data Analyst",
    clone: "nanobot",
    model: "Llama 3.1 70B",
    status: "running",
    channels: ["Telegram", "WhatsApp"],
    messagesProcessed: 5678,
    uptime: "3d 8h",
    lastActive: "1 hour ago",
  },
]

export default function DashboardPage() {
  const [agents, setAgents] = useState(mockAgents)
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | "running" | "stopped">("all")

  const filteredAgents = agents.filter(agent => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.clone.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesStatus = statusFilter === "all" || agent.status === statusFilter
    return matchesSearch && matchesStatus
  })

  const runningCount = agents.filter(a => a.status === "running").length
  const totalMessages = agents.reduce((sum, a) => sum + a.messagesProcessed, 0)

  const toggleAgentStatus = (id: string) => {
    setAgents(agents.map(agent => 
      agent.id === id 
        ? { ...agent, status: agent.status === "running" ? "stopped" : "running" }
        : agent
    ))
  }

  const deleteAgent = (id: string) => {
    setAgents(agents.filter(agent => agent.id !== id))
  }

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
              <p className="text-2xl font-bold text-foreground">{runningCount}</p>
              <p className="text-xs text-muted-foreground">Running Agents</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10">
              <MessageSquare className="h-5 w-5 text-green-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{totalMessages.toLocaleString()}</p>
              <p className="text-xs text-muted-foreground">Messages Processed</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10">
              <Zap className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-2xl font-bold text-foreground">{agents.length}</p>
              <p className="text-xs text-muted-foreground">Total Agents</p>
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

      {/* Agents List */}
      <ScrollArea className="h-[calc(100vh-400px)] min-h-[300px]">
        <div className="space-y-3">
          {filteredAgents.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/50 py-12 text-center">
              <Activity className="mb-3 h-10 w-10 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">No agents found</p>
              <Button asChild variant="link" className="mt-2">
                <Link href="/playground">Create your first agent</Link>
              </Button>
            </div>
          ) : (
            filteredAgents.map((agent) => (
              <div
                key={agent.id}
                className={cn(
                  "rounded-xl border p-4 transition-all sm:p-5",
                  agent.status === "running"
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
                        agent.status === "running"
                          ? "bg-green-500/20 text-green-400"
                          : "bg-muted text-muted-foreground"
                      )}>
                        <span className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          agent.status === "running" ? "animate-pulse bg-green-500" : "bg-muted-foreground"
                        )} />
                        {agent.status}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {agent.clone} + {agent.model}
                    </p>
                    
                    {/* Channels & Stats */}
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <MessageSquare className="h-3 w-3" />
                        {agent.messagesProcessed.toLocaleString()} messages
                      </div>
                      <div className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {agent.lastActive}
                      </div>
                      <div className="flex gap-1">
                        {agent.channels.map((ch) => (
                          <span key={ch} className="rounded bg-muted/50 px-1.5 py-0.5">
                            {ch}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleAgentStatus(agent.id)}
                      className={cn(
                        "gap-1.5",
                        agent.status === "running" && "border-green-500/30 text-green-400 hover:bg-green-500/10"
                      )}
                    >
                      {agent.status === "running" ? (
                        <>
                          <Square className="h-3 w-3" />
                          Stop
                        </>
                      ) : (
                        <>
                          <Play className="h-3 w-3" />
                          Start
                        </>
                      )}
                    </Button>
                    
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
                        <DropdownMenuItem>
                          <Copy className="mr-2 h-4 w-4" />
                          Duplicate
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem 
                          className="text-destructive focus:text-destructive"
                          onClick={() => deleteAgent(agent.id)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
