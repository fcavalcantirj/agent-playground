"use client"

import { useState, use } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import {
  ArrowLeft,
  Search,
  Download,
  RefreshCw,
  Filter,
  Info,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  Terminal,
} from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

interface LogEntry {
  id: string
  timestamp: string
  level: "info" | "warning" | "error" | "success"
  message: string
  details?: string
}

const mockLogs: LogEntry[] = [
  { id: "1", timestamp: "2024-01-15 14:32:45.123", level: "info", message: "Agent started successfully", details: "PID: 12345" },
  { id: "2", timestamp: "2024-01-15 14:32:45.456", level: "info", message: "Connecting to Discord webhook..." },
  { id: "3", timestamp: "2024-01-15 14:32:46.789", level: "success", message: "Discord webhook connected" },
  { id: "4", timestamp: "2024-01-15 14:32:47.012", level: "info", message: "Connecting to Telegram bot API..." },
  { id: "5", timestamp: "2024-01-15 14:32:48.345", level: "success", message: "Telegram bot connected" },
  { id: "6", timestamp: "2024-01-15 14:33:12.678", level: "info", message: "Received message from user@discord", details: "Channel: #support" },
  { id: "7", timestamp: "2024-01-15 14:33:13.901", level: "info", message: "Processing message with Claude 3 Sonnet..." },
  { id: "8", timestamp: "2024-01-15 14:33:15.234", level: "success", message: "Response generated", details: "Tokens: 156, Latency: 1.3s" },
  { id: "9", timestamp: "2024-01-15 14:33:15.567", level: "info", message: "Message sent to Discord" },
  { id: "10", timestamp: "2024-01-15 14:45:23.890", level: "warning", message: "Rate limit approaching", details: "80% of quota used" },
  { id: "11", timestamp: "2024-01-15 15:12:34.123", level: "info", message: "A2A task received from Research Agent" },
  { id: "12", timestamp: "2024-01-15 15:12:35.456", level: "info", message: "Processing A2A request..." },
  { id: "13", timestamp: "2024-01-15 15:12:38.789", level: "success", message: "A2A task completed", details: "Artifact: research_summary.json" },
  { id: "14", timestamp: "2024-01-15 16:00:00.000", level: "info", message: "Scheduled health check passed" },
  { id: "15", timestamp: "2024-01-15 17:23:45.678", level: "error", message: "Failed to process message", details: "Error: Context length exceeded" },
  { id: "16", timestamp: "2024-01-15 17:23:46.901", level: "info", message: "Retrying with truncated context..." },
  { id: "17", timestamp: "2024-01-15 17:23:48.234", level: "success", message: "Message processed successfully on retry" },
]

const levelConfig = {
  info: { icon: Info, color: "text-blue-400", bg: "bg-blue-500/10" },
  warning: { icon: AlertTriangle, color: "text-yellow-400", bg: "bg-yellow-500/10" },
  error: { icon: AlertCircle, color: "text-red-400", bg: "bg-red-500/10" },
  success: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-500/10" },
}

export default function AgentLogsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const [logs, setLogs] = useState(mockLogs)
  const [searchQuery, setSearchQuery] = useState("")
  const [levelFilter, setLevelFilter] = useState<"all" | LogEntry["level"]>("all")
  const [autoRefresh, setAutoRefresh] = useState(true)

  const filteredLogs = logs.filter(log => {
    const matchesSearch = log.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (log.details?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false)
    const matchesLevel = levelFilter === "all" || log.level === levelFilter
    return matchesSearch && matchesLevel
  })

  const handleRefresh = () => {
    // In production, this would fetch new logs
    setLogs([...mockLogs])
  }

  const handleExport = () => {
    const logText = filteredLogs.map(log => 
      `[${log.timestamp}] [${log.level.toUpperCase()}] ${log.message}${log.details ? ` - ${log.details}` : ''}`
    ).join('\n')
    
    const blob = new Blob([logText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `agent-${id}-logs.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <Link 
          href={`/dashboard/agents/${id}`}
          className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Agent
        </Link>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground sm:text-3xl">Agent Logs</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Real-time logs and activity for Customer Support Bot
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={handleRefresh} className="gap-2">
              <RefreshCw className={cn("h-4 w-4", autoRefresh && "animate-spin")} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
            <Button variant="outline" onClick={handleExport} className="gap-2">
              <Download className="h-4 w-4" />
              <span className="hidden sm:inline">Export</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-col gap-3 sm:mb-6 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search logs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-background/50 pl-9"
          />
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" className="gap-2">
              <Filter className="h-4 w-4" />
              {levelFilter === "all" ? "All Levels" : levelFilter.charAt(0).toUpperCase() + levelFilter.slice(1)}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setLevelFilter("all")}>All Levels</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setLevelFilter("info")}>Info</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setLevelFilter("success")}>Success</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setLevelFilter("warning")}>Warning</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setLevelFilter("error")}>Error</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Logs */}
      <div className="rounded-xl border border-border/50 bg-card/30 backdrop-blur-sm">
        <div className="flex items-center justify-between border-b border-border/50 p-4">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Console Output</span>
          </div>
          <span className="text-xs text-muted-foreground">{filteredLogs.length} entries</span>
        </div>
        
        <ScrollArea className="h-[500px] sm:h-[600px]">
          <div className="font-mono text-xs sm:text-sm">
            {filteredLogs.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <Terminal className="mb-3 h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm text-muted-foreground">No logs found</p>
              </div>
            ) : (
              filteredLogs.map((log) => {
                const config = levelConfig[log.level]
                const Icon = config.icon
                return (
                  <div 
                    key={log.id}
                    className={cn(
                      "flex items-start gap-2 border-b border-border/30 px-4 py-2.5 hover:bg-muted/30 sm:gap-3",
                      log.level === "error" && "bg-red-500/5"
                    )}
                  >
                    <div className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded", config.bg)}>
                      <Icon className={cn("h-3 w-3", config.color)} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="shrink-0 text-[10px] text-muted-foreground sm:text-xs">
                          {log.timestamp}
                        </span>
                        <span className={cn("shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase", config.bg, config.color)}>
                          {log.level}
                        </span>
                      </div>
                      <p className="mt-1 text-foreground">{log.message}</p>
                      {log.details && (
                        <p className="mt-0.5 text-muted-foreground">{log.details}</p>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  )
}
