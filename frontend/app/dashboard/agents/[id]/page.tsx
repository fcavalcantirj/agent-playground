"use client"

import { useState, use } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import {
  ArrowLeft,
  Play,
  Square,
  Settings2,
  Activity,
  MessageSquare,
  Clock,
  Zap,
  Terminal,
  Trash2,
  Copy,
  Save,
  RefreshCw,
  Send,
  Bot,
  User,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
} from "lucide-react"

// Mock agent data
const getAgent = (id: string) => ({
  id,
  name: "Customer Support Bot",
  clone: "Hermes-agent",
  cloneVersion: "v2.1.4",
  model: "Claude 3 Sonnet",
  modelId: "anthropic/claude-3-sonnet",
  status: "running" as const,
  channels: ["Discord", "Telegram"],
  a2aEnabled: true,
  config: {
    memory: true,
    scheduling: false,
    maxTokens: 4096,
    temperature: 0.7,
    systemPrompt: "You are a helpful customer support assistant for Agent Playground. Be friendly, professional, and concise.",
  },
  stats: {
    messagesProcessed: 12453,
    avgResponseTime: "1.2s",
    uptime: "14d 6h 23m",
    successRate: 98.7,
    tokensUsed: 2847291,
    cost: 14.23,
  },
  createdAt: "2024-01-15T10:30:00Z",
  lastActive: "2 min ago",
})

const mockConversations = [
  { id: "1", role: "user", content: "How do I create a new agent?", timestamp: "10:30 AM" },
  { id: "2", role: "assistant", content: "To create a new agent, go to the Playground page and select a clone from the left panel. Then choose a model from OpenRouter, configure your channels, and click 'Add Agent Instance'. You can then deploy all configured agents at once.", timestamp: "10:30 AM" },
  { id: "3", role: "user", content: "What models are available?", timestamp: "10:32 AM" },
  { id: "4", role: "assistant", content: "Agent Playground supports all models available through OpenRouter, including:\n\n- Claude 3 (Opus, Sonnet, Haiku)\n- GPT-4 Turbo\n- Llama 3.1 (8B, 70B, 405B)\n- Hermes 3\n- Gemini Pro\n\nYou can filter models by capabilities like vision, function calling, and reasoning.", timestamp: "10:32 AM" },
]

const activityLog = [
  { id: "1", type: "success", message: "Message processed successfully", timestamp: "2 min ago" },
  { id: "2", type: "success", message: "A2A task completed with Research Agent", timestamp: "5 min ago" },
  { id: "3", type: "warning", message: "Rate limit approaching (80%)", timestamp: "1 hour ago" },
  { id: "4", type: "success", message: "Agent restarted successfully", timestamp: "2 hours ago" },
  { id: "5", type: "error", message: "Failed to connect to Discord webhook", timestamp: "3 hours ago" },
  { id: "6", type: "success", message: "Configuration updated", timestamp: "1 day ago" },
]

export default function AgentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const router = useRouter()
  const [agent, setAgent] = useState(getAgent(id))
  const [testMessage, setTestMessage] = useState("")
  const [conversations, setConversations] = useState(mockConversations)
  const [isSending, setIsSending] = useState(false)

  const toggleStatus = () => {
    setAgent({ ...agent, status: agent.status === "running" ? "stopped" : "running" })
    toast.success(agent.status === "running" ? "Agent stopped" : "Agent started")
  }

  const saveConfig = () => {
    toast.success("Configuration saved")
  }

  const deleteAgent = () => {
    toast.success("Agent deleted")
    router.push("/dashboard")
  }

  const sendTestMessage = () => {
    if (!testMessage.trim()) return
    setIsSending(true)
    
    const newUserMessage = {
      id: Date.now().toString(),
      role: "user" as const,
      content: testMessage,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }
    setConversations([...conversations, newUserMessage])
    setTestMessage("")

    setTimeout(() => {
      const newAssistantMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant" as const,
        content: "This is a simulated response from the agent. In production, this would be the actual response from the AI model based on your configuration.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      }
      setConversations(prev => [...prev, newAssistantMessage])
      setIsSending(false)
    }, 1500)
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <Link 
          href="/dashboard" 
          className="mb-4 inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to My Agents
        </Link>
        
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-foreground sm:text-3xl">{agent.name}</h1>
              <span className={cn(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
                agent.status === "running"
                  ? "bg-green-500/20 text-green-400"
                  : "bg-muted text-muted-foreground"
              )}>
                <span className={cn(
                  "h-2 w-2 rounded-full",
                  agent.status === "running" ? "animate-pulse bg-green-500" : "bg-muted-foreground"
                )} />
                {agent.status}
              </span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {agent.clone} ({agent.cloneVersion}) + {agent.model}
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={toggleStatus}
              className={cn(
                "gap-2",
                agent.status === "running" && "border-green-500/30 text-green-400 hover:bg-green-500/10"
              )}
            >
              {agent.status === "running" ? (
                <>
                  <Square className="h-4 w-4" />
                  Stop Agent
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Start Agent
                </>
              )}
            </Button>
            <Button variant="outline" className="gap-2">
              <Copy className="h-4 w-4" />
              <span className="hidden sm:inline">Duplicate</span>
            </Button>
            <Button variant="destructive" onClick={deleteAgent} className="gap-2">
              <Trash2 className="h-4 w-4" />
              <span className="hidden sm:inline">Delete</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="mb-6 grid gap-3 sm:mb-8 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <MessageSquare className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-xl font-bold text-foreground sm:text-2xl">{agent.stats.messagesProcessed.toLocaleString()}</p>
              <p className="text-[10px] text-muted-foreground sm:text-xs">Messages Processed</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-500/10">
              <TrendingUp className="h-5 w-5 text-green-500" />
            </div>
            <div>
              <p className="text-xl font-bold text-foreground sm:text-2xl">{agent.stats.successRate}%</p>
              <p className="text-[10px] text-muted-foreground sm:text-xs">Success Rate</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10">
              <Clock className="h-5 w-5 text-blue-500" />
            </div>
            <div>
              <p className="text-xl font-bold text-foreground sm:text-2xl">{agent.stats.avgResponseTime}</p>
              <p className="text-[10px] text-muted-foreground sm:text-xs">Avg Response Time</p>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-yellow-500/10">
              <Zap className="h-5 w-5 text-yellow-500" />
            </div>
            <div>
              <p className="text-xl font-bold text-foreground sm:text-2xl">${agent.stats.cost.toFixed(2)}</p>
              <p className="text-[10px] text-muted-foreground sm:text-xs">This Month</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="test" className="w-full">
        <TabsList className="mb-6 grid h-auto w-full grid-cols-2 gap-1 bg-muted/30 p-1 sm:flex sm:w-auto">
          <TabsTrigger value="test" className="gap-2 px-4 py-2 text-xs sm:text-sm">
            <Terminal className="h-4 w-4" />
            Test Console
          </TabsTrigger>
          <TabsTrigger value="config" className="gap-2 px-4 py-2 text-xs sm:text-sm">
            <Settings2 className="h-4 w-4" />
            Configuration
          </TabsTrigger>
          <TabsTrigger value="activity" className="gap-2 px-4 py-2 text-xs sm:text-sm">
            <Activity className="h-4 w-4" />
            Activity Log
          </TabsTrigger>
        </TabsList>

        {/* Test Console Tab */}
        <TabsContent value="test">
          <div className="rounded-xl border border-border/50 bg-card/30 backdrop-blur-sm">
            <div className="border-b border-border/50 p-4">
              <h3 className="font-semibold text-foreground">Test Console</h3>
              <p className="text-xs text-muted-foreground">Send test messages to your agent</p>
            </div>
            
            <ScrollArea className="h-[300px] sm:h-[400px]">
              <div className="space-y-4 p-4">
                {conversations.map((msg) => (
                  <div 
                    key={msg.id}
                    className={cn(
                      "flex gap-3",
                      msg.role === "user" ? "justify-end" : "justify-start"
                    )}
                  >
                    {msg.role === "assistant" && (
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/20">
                        <Bot className="h-4 w-4 text-primary" />
                      </div>
                    )}
                    <div className={cn(
                      "max-w-[80%] rounded-xl px-4 py-2.5",
                      msg.role === "user" 
                        ? "bg-primary text-primary-foreground" 
                        : "bg-muted/50"
                    )}>
                      <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                      <p className={cn(
                        "mt-1 text-[10px]",
                        msg.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground"
                      )}>
                        {msg.timestamp}
                      </p>
                    </div>
                    {msg.role === "user" && (
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                        <User className="h-4 w-4 text-muted-foreground" />
                      </div>
                    )}
                  </div>
                ))}
                {isSending && (
                  <div className="flex gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/20">
                      <Bot className="h-4 w-4 text-primary" />
                    </div>
                    <div className="rounded-xl bg-muted/50 px-4 py-2.5">
                      <div className="flex gap-1">
                        <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "0ms" }} />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "150ms" }} />
                        <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: "300ms" }} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>

            <div className="border-t border-border/50 p-4">
              <div className="flex gap-2">
                <Input
                  value={testMessage}
                  onChange={(e) => setTestMessage(e.target.value)}
                  placeholder="Type a test message..."
                  className="bg-background/50"
                  onKeyDown={(e) => e.key === "Enter" && sendTestMessage()}
                />
                <Button onClick={sendTestMessage} disabled={isSending || !testMessage.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Configuration Tab */}
        <TabsContent value="config">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
              <h3 className="mb-4 font-semibold text-foreground">Model Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">System Prompt</label>
                  <textarea
                    value={agent.config.systemPrompt}
                    onChange={(e) => setAgent({
                      ...agent,
                      config: { ...agent.config, systemPrompt: e.target.value }
                    })}
                    rows={4}
                    className="w-full resize-none rounded-lg border border-border/50 bg-background/50 p-3 text-sm focus:border-primary focus:outline-none"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Max Tokens</label>
                  <Input
                    type="number"
                    value={agent.config.maxTokens}
                    onChange={(e) => setAgent({
                      ...agent,
                      config: { ...agent.config, maxTokens: parseInt(e.target.value) || 4096 }
                    })}
                    className="bg-background/50"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:text-sm">Temperature: {agent.config.temperature}</label>
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={agent.config.temperature}
                    onChange={(e) => setAgent({
                      ...agent,
                      config: { ...agent.config, temperature: parseFloat(e.target.value) }
                    })}
                    className="w-full accent-primary"
                  />
                </div>
              </div>
            </div>

            <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:p-6">
              <h3 className="mb-4 font-semibold text-foreground">Runtime Options</h3>
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-foreground">Persistent Memory</p>
                    <p className="text-xs text-muted-foreground">Remember conversation context</p>
                  </div>
                  <Switch
                    checked={agent.config.memory}
                    onCheckedChange={(v) => setAgent({
                      ...agent,
                      config: { ...agent.config, memory: v }
                    })}
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-foreground">A2A Protocol</p>
                    <p className="text-xs text-muted-foreground">Agent-to-agent communication</p>
                  </div>
                  <Switch
                    checked={agent.a2aEnabled}
                    onCheckedChange={(v) => setAgent({ ...agent, a2aEnabled: v })}
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-foreground">Scheduled Tasks</p>
                    <p className="text-xs text-muted-foreground">Run on cron schedule</p>
                  </div>
                  <Switch
                    checked={agent.config.scheduling}
                    onCheckedChange={(v) => setAgent({
                      ...agent,
                      config: { ...agent.config, scheduling: v }
                    })}
                  />
                </div>
              </div>

              <div className="mt-6 flex gap-2">
                <Button onClick={saveConfig} className="flex-1 gap-2">
                  <Save className="h-4 w-4" />
                  Save Changes
                </Button>
                <Button variant="outline" className="gap-2">
                  <RefreshCw className="h-4 w-4" />
                  Reset
                </Button>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Activity Log Tab */}
        <TabsContent value="activity">
          <div className="rounded-xl border border-border/50 bg-card/30 backdrop-blur-sm">
            <div className="border-b border-border/50 p-4">
              <h3 className="font-semibold text-foreground">Activity Log</h3>
              <p className="text-xs text-muted-foreground">Recent events and actions</p>
            </div>
            <ScrollArea className="h-[400px]">
              <div className="divide-y divide-border/50">
                {activityLog.map((log) => (
                  <div key={log.id} className="flex items-start gap-3 p-4">
                    <div className={cn(
                      "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                      log.type === "success" && "bg-green-500/20",
                      log.type === "warning" && "bg-yellow-500/20",
                      log.type === "error" && "bg-red-500/20"
                    )}>
                      {log.type === "success" && <CheckCircle className="h-3.5 w-3.5 text-green-500" />}
                      {log.type === "warning" && <AlertTriangle className="h-3.5 w-3.5 text-yellow-500" />}
                      {log.type === "error" && <AlertTriangle className="h-3.5 w-3.5 text-red-500" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground">{log.message}</p>
                      <p className="text-xs text-muted-foreground">{log.timestamp}</p>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
