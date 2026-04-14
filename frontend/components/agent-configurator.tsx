"use client"

import { useState, useCallback, useEffect } from "react"
import { cn } from "@/lib/utils"
import { AgentCard, ClawClone, defaultClones } from "./agent-card"
import { ModelSelector, OpenRouterModel, openRouterModels } from "./model-selector"
import { A2ANetwork, A2AAgent, A2AConnection, A2AMessage, AgentCardDisplay } from "./a2a-network"
import { TaskOrchestrator, A2ATask, A2ASubtask, A2AArtifact } from "./task-orchestrator"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { 
  Plus, 
  Trash2, 
  Play, 
  Settings2, 
  Layers,
  MessageSquare,
  Webhook,
  Terminal,
  Sparkles,
  Copy,
  RotateCcw,
  Zap,
  Shield,
  Server,
  Users,
  Cpu,
  Network,
  Workflow,
  Radio,
  Eye,
  Activity
} from "lucide-react"

export interface AgentInstance {
  id: string
  name: string
  clone: ClawClone
  model: OpenRouterModel
  channels: string[]
  isRunning: boolean
  config: {
    memory: boolean
    scheduling: boolean
    sandbox: string
    maxTokens: number
    a2aEnabled: boolean
  }
  position: { x: number; y: number }
  agentCard: {
    name: string
    description: string
    url: string
    capabilities: {
      streaming: boolean
      pushNotifications: boolean
      stateTransitionHistory: boolean
    }
    skills: { id: string; name: string }[]
  }
}

const channelOptions = [
  { id: "telegram", name: "Telegram", icon: MessageSquare },
  { id: "discord", name: "Discord", icon: MessageSquare },
  { id: "slack", name: "Slack", icon: MessageSquare },
  { id: "whatsapp", name: "WhatsApp", icon: MessageSquare },
  { id: "signal", name: "Signal", icon: Shield },
  { id: "email", name: "Email", icon: MessageSquare },
  { id: "cli", name: "CLI", icon: Terminal },
  { id: "webhook", name: "Webhook", icon: Webhook },
]

const sandboxOptions = [
  { id: "local", name: "Local", icon: Cpu },
  { id: "docker", name: "Docker", icon: Server },
  { id: "ssh", name: "SSH", icon: Terminal },
  { id: "modal", name: "Modal", icon: Zap },
]

const categoryFilters = [
  { id: "all", name: "All Clones" },
  { id: "replacement", name: "OpenClaw" },
  { id: "secure", name: "Secure" },
  { id: "edge", name: "Edge" },
  { id: "teams", name: "Teams" },
  { id: "local", name: "Local" },
]

// Generate random position for new agents
const generatePosition = (existingAgents: AgentInstance[]) => {
  const positions = [
    { x: 20, y: 25 }, { x: 50, y: 20 }, { x: 80, y: 25 },
    { x: 15, y: 50 }, { x: 50, y: 50 }, { x: 85, y: 50 },
    { x: 20, y: 75 }, { x: 50, y: 80 }, { x: 80, y: 75 },
  ]
  const usedPositions = existingAgents.map(a => `${a.position.x}-${a.position.y}`)
  const available = positions.filter(p => !usedPositions.includes(`${p.x}-${p.y}`))
  return available.length > 0 ? available[0] : { 
    x: 20 + Math.random() * 60, 
    y: 20 + Math.random() * 60 
  }
}

export function AgentConfigurator() {
  const [agents, setAgents] = useState<AgentInstance[]>([])
  const [connections, setConnections] = useState<A2AConnection[]>([])
  const [messages, setMessages] = useState<A2AMessage[]>([])
  const [tasks, setTasks] = useState<A2ATask[]>([])
  const [selectedClone, setSelectedClone] = useState<ClawClone | null>(null)
  const [selectedModel, setSelectedModel] = useState<OpenRouterModel | null>(null)
  const [agentName, setAgentName] = useState("")
  const [selectedChannels, setSelectedChannels] = useState<string[]>(["cli"])
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState("configure")
  const [config, setConfig] = useState({
    memory: true,
    scheduling: false,
    sandbox: "docker",
    maxTokens: 4096,
    a2aEnabled: true
  })

  const filteredClones = categoryFilter === "all" 
    ? defaultClones 
    : defaultClones.filter(c => c.category === categoryFilter)

  const selectedAgent = agents.find(a => a.id === selectedAgentId)

  // Simulate A2A messages when connections are active
  useEffect(() => {
    if (connections.length === 0) return
    
    const interval = setInterval(() => {
      const activeConnections = connections.filter(c => c.status === "active")
      if (activeConnections.length === 0) return
      
      const randomConn = activeConnections[Math.floor(Math.random() * activeConnections.length)]
      const fromAgent = agents.find(a => a.id === randomConn.from)
      const toAgent = agents.find(a => a.id === randomConn.to)
      
      if (!fromAgent || !toAgent) return
      
      const messageTypes: A2AMessage["type"][] = ["task_request", "task_response", "artifact", "status_update"]
      const messageContents = [
        "Processing data chunk 42/100...",
        "Analysis complete. Confidence: 94%",
        "Requesting capability: code_execution",
        "Task delegated successfully",
        "Artifact generated: summary.json",
        "State transition: working -> completed",
        "Streaming partial results...",
        "Coordination checkpoint reached"
      ]
      
      const newMessage: A2AMessage = {
        id: `msg-${Date.now()}`,
        from: Math.random() > 0.5 ? randomConn.from : randomConn.to,
        to: Math.random() > 0.5 ? randomConn.to : randomConn.from,
        type: messageTypes[Math.floor(Math.random() * messageTypes.length)],
        content: messageContents[Math.floor(Math.random() * messageContents.length)],
        timestamp: new Date()
      }
      
      setMessages(prev => [...prev.slice(-49), newMessage])
      
      // Update connection message count
      setConnections(prev => prev.map(c => 
        c.id === randomConn.id 
          ? { ...c, messageCount: c.messageCount + 1 }
          : c
      ))
    }, 3000)
    
    return () => clearInterval(interval)
  }, [connections, agents])

  const addAgent = () => {
    if (!selectedClone || !selectedModel) return
    
    const newAgent: AgentInstance = {
      id: `agent-${Date.now()}`,
      name: agentName || `${selectedClone.name} Agent`,
      clone: selectedClone,
      model: selectedModel,
      channels: selectedChannels,
      isRunning: false,
      config: { ...config },
      position: generatePosition(agents),
      agentCard: {
        name: agentName || `${selectedClone.name} Agent`,
        description: `${selectedClone.name} powered by ${selectedModel.name}`,
        url: `https://agents.local/${(agentName || selectedClone.name).toLowerCase().replace(/\s/g, '-')}/.well-known/agent.json`,
        capabilities: {
          streaming: true,
          pushNotifications: config.scheduling,
          stateTransitionHistory: config.memory
        },
        skills: selectedClone.capabilities.slice(0, 4).map((cap, i) => ({
          id: `skill-${i}`,
          name: cap
        }))
      }
    }
    
    setAgents([...agents, newAgent])
    setAgentName("")
    setSelectedChannels(["cli"])
  }

  const removeAgent = (id: string) => {
    setAgents(agents.filter(a => a.id !== id))
    setConnections(connections.filter(c => c.from !== id && c.to !== id))
    if (selectedAgentId === id) setSelectedAgentId(null)
  }

  const toggleAgent = (id: string) => {
    setAgents(agents.map(a => 
      a.id === id ? { ...a, isRunning: !a.isRunning } : a
    ))
    
    // Update connection status based on agent running state
    setConnections(connections.map(c => {
      const fromAgent = agents.find(a => a.id === c.from)
      const toAgent = agents.find(a => a.id === c.to)
      const bothRunning = (c.from === id ? !fromAgent?.isRunning : fromAgent?.isRunning) &&
                          (c.to === id ? !toAgent?.isRunning : toAgent?.isRunning)
      return { ...c, status: bothRunning ? "active" : "idle" }
    }))
  }

  const duplicateAgent = (agent: AgentInstance) => {
    const newAgent: AgentInstance = {
      ...agent,
      id: `agent-${Date.now()}`,
      name: `${agent.name} (Copy)`,
      isRunning: false,
      position: generatePosition([...agents, agent])
    }
    setAgents([...agents, newAgent])
  }

  const toggleChannel = (channelId: string) => {
    setSelectedChannels(prev => 
      prev.includes(channelId) 
        ? prev.filter(c => c !== channelId)
        : [...prev, channelId]
    )
  }

  const handleConnect = (fromId: string, toId: string) => {
    // Check if connection already exists
    const exists = connections.some(
      c => (c.from === fromId && c.to === toId) || (c.from === toId && c.to === fromId)
    )
    if (exists) return
    
    const fromAgent = agents.find(a => a.id === fromId)
    const toAgent = agents.find(a => a.id === toId)
    
    const newConnection: A2AConnection = {
      id: `conn-${Date.now()}`,
      from: fromId,
      to: toId,
      status: fromAgent?.isRunning && toAgent?.isRunning ? "active" : "pending",
      taskType: "collaboration",
      messageCount: 0
    }
    
    setConnections([...connections, newConnection])
    
    // Add initial A2A handshake message
    const handshakeMessage: A2AMessage = {
      id: `msg-${Date.now()}`,
      from: fromId,
      to: toId,
      type: "task_request",
      content: `A2A handshake initiated. Exchanging Agent Cards...`,
      timestamp: new Date()
    }
    setMessages(prev => [...prev, handshakeMessage])
  }

  const handleDisconnect = (connectionId: string) => {
    setConnections(connections.filter(c => c.id !== connectionId))
  }

  const handleCreateTask = (taskData: Partial<A2ATask>) => {
    const newTask: A2ATask = {
      id: `task-${Date.now()}`,
      name: taskData.name || "Untitled Task",
      description: taskData.description || "",
      status: "running",
      assignedAgents: taskData.assignedAgents || [],
      subtasks: [],
      artifacts: [],
      createdAt: new Date()
    }
    
    setTasks([...tasks, newTask])
    
    // Simulate task processing
    setTimeout(() => {
      const assignedAgentNames = newTask.assignedAgents.map(id => 
        agents.find(a => a.id === id)?.name || "Unknown"
      )
      
      const subtasks: A2ASubtask[] = assignedAgentNames.map((name, i) => ({
        id: `subtask-${Date.now()}-${i}`,
        name: `Processing by ${name}`,
        status: "running" as const,
        agentId: newTask.assignedAgents[i],
        agentName: name
      }))
      
      setTasks(prev => prev.map(t => 
        t.id === newTask.id ? { ...t, subtasks } : t
      ))
      
      // Complete subtasks over time
      subtasks.forEach((subtask, i) => {
        setTimeout(() => {
          setTasks(prev => prev.map(t => {
            if (t.id !== newTask.id) return t
            return {
              ...t,
              subtasks: t.subtasks.map(st => 
                st.id === subtask.id 
                  ? { ...st, status: "completed" as const, output: "Task completed successfully" }
                  : st
              )
            }
          }))
        }, 2000 + i * 1500)
      })
      
      // Complete the whole task
      setTimeout(() => {
        setTasks(prev => prev.map(t => 
          t.id === newTask.id 
            ? { 
                ...t, 
                status: "completed", 
                completedAt: new Date(),
                artifacts: [{
                  id: `artifact-${Date.now()}`,
                  name: "task_output.json",
                  type: "data",
                  content: JSON.stringify({ result: "success", agents: assignedAgentNames }, null, 2),
                  createdBy: assignedAgentNames[0]
                }]
              }
            : t
        ))
      }, 2000 + subtasks.length * 1500 + 1000)
      
    }, 500)
  }

  const handleCancelTask = (taskId: string) => {
    setTasks(tasks.map(t => 
      t.id === taskId ? { ...t, status: "failed" as const } : t
    ))
  }

  const getCloneInstanceCount = (cloneId: string) => {
    return agents.filter(a => a.clone.id === cloneId).length
  }

  const deployAllAgents = () => {
    setAgents(agents.map(a => ({ ...a, isRunning: true })))
    setConnections(connections.map(c => ({ ...c, status: "active" as const })))
  }

  const a2aAgents: A2AAgent[] = agents.map(a => ({
    id: a.id,
    name: a.name,
    clone: a.clone.name,
    model: a.model.name,
    position: a.position,
    isRunning: a.isRunning,
    capabilities: a.clone.capabilities,
    agentCard: a.agentCard
  }))

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Main Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid h-auto w-full grid-cols-2 gap-1.5 rounded-xl border border-border/30 bg-card/50 p-1.5 backdrop-blur-sm sm:flex sm:flex-wrap sm:gap-2">
          <TabsTrigger value="configure" className="flex-1 gap-1.5 px-2 py-2 text-xs sm:min-w-[100px] sm:gap-2 sm:px-3 sm:text-sm md:min-w-[120px]">
            <Settings2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            <span className="hidden xs:inline">Configure</span>
            <span className="xs:hidden">Config</span>
          </TabsTrigger>
          <TabsTrigger value="network" className="flex-1 gap-1.5 px-2 py-2 text-xs sm:min-w-[100px] sm:gap-2 sm:px-3 sm:text-sm md:min-w-[120px]">
            <Network className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            <span className="hidden xs:inline">A2A Network</span>
            <span className="xs:hidden">A2A</span>
          </TabsTrigger>
          <TabsTrigger value="tasks" className="flex-1 gap-1.5 px-2 py-2 text-xs sm:min-w-[100px] sm:gap-2 sm:px-3 sm:text-sm md:min-w-[120px]">
            <Workflow className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            Tasks
          </TabsTrigger>
          <TabsTrigger value="monitor" className="flex-1 gap-1.5 px-2 py-2 text-xs sm:min-w-[100px] sm:gap-2 sm:px-3 sm:text-sm md:min-w-[120px]">
            <Eye className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            Monitor
          </TabsTrigger>
        </TabsList>

        {/* Configure Tab */}
        <TabsContent value="configure" className="mt-4 sm:mt-6">
          <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-3">
            {/* Left Panel - Clone Selection */}
            <div className="space-y-3 sm:space-y-4 lg:col-span-1">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-base font-semibold text-foreground sm:gap-2 sm:text-lg">
                  <Layers className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                  Select Clone
                </h3>
                <span className="text-[10px] text-muted-foreground sm:text-xs">{defaultClones.length} available</span>
              </div>

              {/* Category Filter */}
              <ScrollArea className="w-full">
                <div className="flex gap-1.5 pb-2 sm:gap-2">
                  {categoryFilters.map(cat => (
                    <button
                      key={cat.id}
                      onClick={() => setCategoryFilter(cat.id)}
                      className={cn(
                        "whitespace-nowrap rounded-full px-2.5 py-1 text-[10px] font-medium transition-all duration-200 sm:px-3 sm:py-1.5 sm:text-xs",
                        categoryFilter === cat.id
                          ? "bg-primary text-primary-foreground shadow-[0_0_12px_rgba(249,115,22,0.3)]"
                          : "border border-border/50 bg-card/50 text-muted-foreground hover:border-primary/50 hover:bg-primary/10 hover:text-foreground"
                      )}
                    >
                      {cat.name}
                    </button>
                  ))}
                </div>
              </ScrollArea>

              {/* Clones Grid */}
              <ScrollArea className="h-[280px] sm:h-[350px] lg:h-[400px]">
                <div className="space-y-3 px-1 pb-1 pr-3 pt-3 sm:space-y-4 sm:pt-3">
                  {filteredClones.map(clone => (
                    <AgentCard
                      key={clone.id}
                      clone={clone}
                      isSelected={selectedClone?.id === clone.id}
                      onSelect={() => setSelectedClone(clone)}
                      instanceCount={getCloneInstanceCount(clone.id)}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>

            {/* Middle Panel - Configuration */}
            <div className="space-y-3 sm:space-y-4 lg:col-span-1">
              <div className="flex items-center gap-1.5 sm:gap-2">
                <Settings2 className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                <h3 className="text-base font-semibold text-foreground sm:text-lg">Configure Agent</h3>
              </div>

              <div className="space-y-3 rounded-xl border border-border/50 bg-card/50 p-3 backdrop-blur-sm sm:space-y-4 sm:p-4">
                {/* Agent Name */}
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:mb-2 sm:text-sm">Agent Name</label>
                  <Input
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    placeholder={selectedClone ? `${selectedClone.name} Agent` : "My Agent"}
                    className="bg-background/50 text-sm"
                  />
                </div>

                {/* Model Selection */}
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:mb-2 sm:text-sm">OpenRouter Model</label>
                  <ModelSelector
                    selectedModel={selectedModel}
                    onSelectModel={setSelectedModel}
                  />
                </div>

                {/* Channels */}
                <div>
                  <label className="mb-1.5 block text-xs text-muted-foreground sm:mb-2 sm:text-sm">Channels</label>
                  <div className="grid grid-cols-4 gap-1.5 sm:gap-2">
                    {channelOptions.map(channel => (
                      <button
                        key={channel.id}
                        onClick={() => toggleChannel(channel.id)}
                        className={cn(
                          "group flex flex-col items-center gap-0.5 rounded-lg border p-1.5 transition-all duration-200 sm:gap-1 sm:p-2",
                          selectedChannels.includes(channel.id)
                            ? "border-primary bg-primary/15 text-primary shadow-[0_0_10px_rgba(249,115,22,0.2)]"
                            : "border-border/50 bg-card/30 text-muted-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
                        )}
                      >
                        <channel.icon className={cn(
                          "h-3.5 w-3.5 transition-transform duration-200 group-hover:scale-110 sm:h-4 sm:w-4",
                          selectedChannels.includes(channel.id) && "text-primary"
                        )} />
                        <span className="text-[8px] sm:text-[10px]">{channel.name}</span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Advanced Config */}
                <Tabs defaultValue="runtime" className="w-full">
                  <TabsList className="w-full rounded-lg border border-border/30 bg-card/30 p-1">
                    <TabsTrigger value="runtime" className="flex-1 text-[10px] sm:text-xs">Runtime</TabsTrigger>
                    <TabsTrigger value="sandbox" className="flex-1 text-[10px] sm:text-xs">Sandbox</TabsTrigger>
                    <TabsTrigger value="a2a" className="flex-1 text-[10px] sm:text-xs">A2A</TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="runtime" className="mt-2.5 space-y-2.5 sm:mt-3 sm:space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-xs text-foreground sm:text-sm">Persistent Memory</p>
                        <p className="text-[10px] text-muted-foreground sm:text-xs">Remember context</p>
                      </div>
                      <Switch 
                        checked={config.memory}
                        onCheckedChange={(v) => setConfig({...config, memory: v})}
                      />
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-xs text-foreground sm:text-sm">Scheduling</p>
                        <p className="text-[10px] text-muted-foreground sm:text-xs">Cron automations</p>
                      </div>
                      <Switch 
                        checked={config.scheduling}
                        onCheckedChange={(v) => setConfig({...config, scheduling: v})}
                      />
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs text-muted-foreground sm:mb-2 sm:text-sm">Max Tokens</label>
                      <Input
                        type="number"
                        value={config.maxTokens}
                        onChange={(e) => setConfig({...config, maxTokens: parseInt(e.target.value) || 4096})}
                        className="bg-background/50 text-sm"
                      />
                    </div>
                  </TabsContent>
                  
                  <TabsContent value="sandbox" className="mt-2.5 sm:mt-3">
                    <div className="grid grid-cols-2 gap-1.5 sm:gap-2">
                      {sandboxOptions.map(sandbox => (
                        <button
                          key={sandbox.id}
                          onClick={() => setConfig({...config, sandbox: sandbox.id})}
                          className={cn(
                            "group flex items-center gap-1.5 rounded-lg border p-2 transition-all duration-200 sm:gap-2 sm:p-3",
                            config.sandbox === sandbox.id
                              ? "border-primary bg-primary/15 text-primary shadow-[0_0_10px_rgba(249,115,22,0.2)]"
                              : "border-border/50 bg-card/30 text-muted-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
                          )}
                        >
                          <sandbox.icon className={cn(
                            "h-3.5 w-3.5 transition-transform duration-200 group-hover:scale-110 sm:h-4 sm:w-4",
                            config.sandbox === sandbox.id && "text-primary"
                          )} />
                          <span className="text-xs sm:text-sm">{sandbox.name}</span>
                        </button>
                      ))}
                    </div>
                  </TabsContent>

                  <TabsContent value="a2a" className="mt-2.5 space-y-2.5 sm:mt-3 sm:space-y-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <p className="text-xs text-foreground sm:text-sm">Enable A2A Protocol</p>
                        <p className="text-[10px] text-muted-foreground sm:text-xs">Agent-to-agent communication</p>
                      </div>
                      <Switch 
                        checked={config.a2aEnabled}
                        onCheckedChange={(v) => setConfig({...config, a2aEnabled: v})}
                      />
                    </div>
                    {config.a2aEnabled && (
                      <div className="rounded-lg border border-primary/20 bg-primary/5 p-2.5 sm:p-3">
                        <div className="mb-1 flex items-center gap-1.5 text-xs text-primary sm:gap-2 sm:text-sm">
                          <Radio className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
                          A2A v1.0 Compliant
                        </div>
                        <p className="text-[10px] text-muted-foreground sm:text-xs">
                          Supports streaming, push notifications, and state history. 
                          Agent Card will be auto-generated.
                        </p>
                      </div>
                    )}
                  </TabsContent>
                </Tabs>

                {/* Add Button */}
                <Button 
                  onClick={addAgent}
                  disabled={!selectedClone || !selectedModel}
                  className="w-full bg-gradient-to-r from-primary to-accent text-sm transition-opacity hover:opacity-90 sm:text-base"
                >
                  <Plus className="mr-1.5 h-3.5 w-3.5 sm:mr-2 sm:h-4 sm:w-4" />
                  Add Agent Instance
                </Button>
              </div>
            </div>

            {/* Right Panel - Active Instances */}
            <div className="space-y-3 sm:space-y-4 lg:col-span-1">
              <div className="flex items-center justify-between">
                <h3 className="flex items-center gap-1.5 text-base font-semibold text-foreground sm:gap-2 sm:text-lg">
                  <Users className="h-4 w-4 text-primary sm:h-5 sm:w-5" />
                  Agent Instances
                </h3>
                <span className={cn(
                  "rounded-full px-2 py-0.5 text-[10px] font-medium sm:text-xs",
                  agents.length > 0 ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
                )}>
                  {agents.length} {agents.length === 1 ? "agent" : "agents"}
                </span>
              </div>

              <ScrollArea className="h-[280px] sm:h-[350px] lg:h-[420px]">
                {agents.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-border/50 p-4 text-center sm:p-6 mx-1">
                    <Sparkles className="mb-3 h-10 w-10 text-muted-foreground/50 sm:mb-4 sm:h-12 sm:w-12" />
                    <p className="text-xs text-muted-foreground sm:text-sm">No agents configured yet</p>
                    <p className="mt-1 text-[10px] text-muted-foreground/70 sm:text-xs">
                      Select a clone and model to create your first agent
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3 px-1 pb-1 pr-3 pt-3 sm:space-y-4">
                    {agents.map(agent => (
                      <div
                        key={agent.id}
                        className={cn(
                          "rounded-xl border p-3 transition-all sm:p-4",
                          agent.isRunning 
                            ? "border-green-500/50 bg-green-500/5 shadow-[0_0_20px_rgba(34,197,94,0.1)]" 
                            : "border-border/50 bg-card/50"
                        )}
                      >
                        {/* Header */}
                        <div className="mb-2.5 flex items-start justify-between gap-2 sm:mb-3">
                          <div className="min-w-0 flex-1">
                            <h4 className="truncate text-sm font-medium text-foreground sm:text-base">{agent.name}</h4>
                            <div className="mt-0.5 flex flex-wrap items-center gap-1 sm:mt-1 sm:gap-2">
                              <span className="text-[10px] text-muted-foreground sm:text-xs">{agent.clone.name}</span>
                              <span className="text-[10px] text-muted-foreground sm:text-xs">+</span>
                              <span className="truncate text-[10px] text-primary sm:text-xs">{agent.model.name}</span>
                            </div>
                          </div>
                          <div className={cn(
                            "flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium sm:px-2 sm:text-xs",
                            agent.isRunning 
                              ? "bg-green-500/20 text-green-400" 
                              : "bg-muted text-muted-foreground"
                          )}>
                            <div className={cn(
                              "h-1.5 w-1.5 rounded-full",
                              agent.isRunning ? "animate-pulse bg-green-500" : "bg-muted-foreground"
                            )} />
                            <span className="hidden xs:inline">{agent.isRunning ? "Running" : "Stopped"}</span>
                          </div>
                        </div>

                        {/* Channels & A2A */}
                        <div className="mb-2.5 flex flex-wrap gap-1 sm:mb-3">
                          {agent.channels.slice(0, 3).map(ch => (
                            <span key={ch} className="rounded bg-muted/50 px-1.5 py-0.5 text-[8px] text-muted-foreground sm:px-2 sm:text-[10px]">
                              {ch}
                            </span>
                          ))}
                          {agent.channels.length > 3 && (
                            <span className="rounded bg-muted/50 px-1.5 py-0.5 text-[8px] text-muted-foreground sm:px-2 sm:text-[10px]">
                              +{agent.channels.length - 3}
                            </span>
                          )}
                          {agent.config.a2aEnabled && (
                            <span className="flex items-center gap-0.5 rounded bg-primary/20 px-1.5 py-0.5 text-[8px] text-primary sm:gap-1 sm:px-2 sm:text-[10px]">
                              <Radio className="h-2 w-2 sm:h-2.5 sm:w-2.5" />
                              A2A
                            </span>
                          )}
                        </div>

                        {/* Config Summary */}
                        <div className="flex items-center gap-3 text-xs text-muted-foreground mb-3">
                          <span className="flex items-center gap-1">
                            <Server className="w-3 h-3" />
                            {agent.config.sandbox}
                          </span>
                          {agent.config.memory && (
                            <span className="flex items-center gap-1">
                              <Sparkles className="w-3 h-3" />
                              memory
                            </span>
                          )}
                          <span>{agent.config.maxTokens} tokens</span>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            onClick={() => toggleAgent(agent.id)}
                            className={cn(
                              "flex-1",
                              agent.isRunning 
                                ? "bg-red-500/20 text-red-400 hover:bg-red-500/30" 
                                : "bg-green-500/20 text-green-400 hover:bg-green-500/30"
                            )}
                            variant="ghost"
                          >
                            {agent.isRunning ? (
                              <>
                                <RotateCcw className="w-3 h-3 mr-1" />
                                Stop
                              </>
                            ) : (
                              <>
                                <Play className="w-3 h-3 mr-1" />
                                Start
                              </>
                            )}
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => duplicateAgent(agent)}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => removeAgent(agent.id)}
                            className="text-muted-foreground hover:text-red-400"
                          >
                            <Trash2 className="w-3 h-3" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>

              {/* Deploy All Button */}
              {agents.length > 0 && (
                <Button 
                  className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:opacity-90"
                  onClick={deployAllAgents}
                >
                  <Zap className="w-4 h-4 mr-2" />
                  Deploy All Agents ({agents.length})
                </Button>
              )}
            </div>
          </div>
        </TabsContent>

        {/* A2A Network Tab */}
        <TabsContent value="network" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <A2ANetwork
                agents={a2aAgents}
                connections={connections}
                messages={messages}
                onConnect={handleConnect}
                onDisconnect={handleDisconnect}
                selectedAgentId={selectedAgentId}
                onSelectAgent={setSelectedAgentId}
              />
            </div>
            <div className="lg:col-span-1">
              {selectedAgent ? (
                <div className="space-y-4">
                  <h4 className="text-lg font-semibold text-foreground flex items-center gap-2">
                    <Eye className="w-5 h-5 text-primary" />
                    Agent Card
                  </h4>
                  <AgentCardDisplay agent={{
                    ...a2aAgents.find(a => a.id === selectedAgent.id)!,
                    agentCard: selectedAgent.agentCard
                  }} />
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-border/50 rounded-xl">
                  <Network className="w-12 h-12 text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground text-sm">Select an agent to view its A2A Card</p>
                  <p className="text-muted-foreground/70 text-xs mt-1">
                    Click on an agent node in the network visualization
                  </p>
                </div>
              )}

              {/* Connection Stats */}
              <div className="mt-6 p-4 rounded-xl border border-border/50 bg-card/30">
                <h4 className="text-sm font-medium text-foreground mb-3">Network Stats</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-2xl font-bold text-primary">{agents.length}</p>
                    <p className="text-xs text-muted-foreground">Total Agents</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-accent">{connections.length}</p>
                    <p className="text-xs text-muted-foreground">Connections</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-green-400">
                      {agents.filter(a => a.isRunning).length}
                    </p>
                    <p className="text-xs text-muted-foreground">Running</p>
                  </div>
                  <div>
                    <p className="text-2xl font-bold text-foreground">{messages.length}</p>
                    <p className="text-xs text-muted-foreground">Messages</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Tasks Tab */}
        <TabsContent value="tasks" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <TaskOrchestrator
              tasks={tasks}
              onCreateTask={handleCreateTask}
              onCancelTask={handleCancelTask}
              agents={agents.map(a => ({ id: a.id, name: a.name, isRunning: a.isRunning }))}
            />
            
            <div className="space-y-4">
              <h4 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Workflow className="w-5 h-5 text-primary" />
                A2A Protocol Overview
              </h4>
              <div className="p-4 rounded-xl border border-border/50 bg-card/30 space-y-4">
                <p className="text-sm text-muted-foreground">
                  The Agent-to-Agent (A2A) protocol enables your agents to discover each other, 
                  negotiate capabilities, and collaborate on complex tasks.
                </p>
                
                <div className="space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
                      <Radio className="w-4 h-4 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Discovery</p>
                      <p className="text-xs text-muted-foreground">
                        Agents expose Agent Cards describing their capabilities and skills
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center flex-shrink-0">
                      <MessageSquare className="w-4 h-4 text-accent" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Communication</p>
                      <p className="text-xs text-muted-foreground">
                        JSON-RPC over HTTP/SSE with streaming support
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-lg bg-green-500/20 flex items-center justify-center flex-shrink-0">
                      <Workflow className="w-4 h-4 text-green-400" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Task Lifecycle</p>
                      <p className="text-xs text-muted-foreground">
                        Structured task management with artifacts and state transitions
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>

        {/* Monitor Tab */}
        <TabsContent value="monitor" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Running Agents */}
            <div className="space-y-4">
              <h4 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" />
                Running Agents
              </h4>
              <ScrollArea className="h-[400px]">
                {agents.filter(a => a.isRunning).length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    No agents currently running
                  </div>
                ) : (
                  <div className="space-y-3">
                    {agents.filter(a => a.isRunning).map(agent => (
                      <div
                        key={agent.id}
                        className="p-4 rounded-xl border border-green-500/30 bg-green-500/5"
                      >
                        <div className="flex items-center justify-between mb-2">
                          <h5 className="font-medium text-foreground">{agent.name}</h5>
                          <span className="text-xs text-green-400">Active</span>
                        </div>
                        <div className="text-xs text-muted-foreground space-y-1">
                          <p>Clone: {agent.clone.name}</p>
                          <p>Model: {agent.model.name}</p>
                          <p>Channels: {agent.channels.join(", ")}</p>
                        </div>
                        <div className="mt-3 pt-3 border-t border-border/30">
                          <div className="flex items-center justify-between text-xs">
                            <span className="text-muted-foreground">A2A Connections:</span>
                            <span className="text-primary">
                              {connections.filter(c => c.from === agent.id || c.to === agent.id).length}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>

            {/* Live Message Feed */}
            <div className="space-y-4">
              <h4 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-primary" />
                Live A2A Messages
              </h4>
              <ScrollArea className="h-[400px] p-4 rounded-xl border border-border/50 bg-card/30">
                {messages.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    No messages yet. Connect and run agents to see communication.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {[...messages].reverse().map(msg => {
                      const fromAgent = agents.find(a => a.id === msg.from)
                      const toAgent = agents.find(a => a.id === msg.to)
                      
                      return (
                        <div
                          key={msg.id}
                          className="p-3 rounded-lg bg-background/50 text-sm animate-in fade-in slide-in-from-top-2 duration-300"
                        >
                          <div className="flex items-center gap-2 mb-1">
                            <span className={cn(
                              "px-2 py-0.5 rounded text-[10px] font-medium",
                              msg.type === "task_request" && "bg-blue-500/20 text-blue-400",
                              msg.type === "task_response" && "bg-green-500/20 text-green-400",
                              msg.type === "artifact" && "bg-purple-500/20 text-purple-400",
                              msg.type === "status_update" && "bg-yellow-500/20 text-yellow-400"
                            )}>
                              {msg.type.replace("_", " ")}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {msg.timestamp.toLocaleTimeString()}
                            </span>
                          </div>
                          <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                            <span className="font-medium text-foreground">{fromAgent?.name || "Unknown"}</span>
                            <span>→</span>
                            <span className="font-medium text-foreground">{toAgent?.name || "Unknown"}</span>
                          </div>
                          <p className="text-muted-foreground">{msg.content}</p>
                        </div>
                      )
                    })}
                  </div>
                )}
              </ScrollArea>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
