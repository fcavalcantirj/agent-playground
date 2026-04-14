"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { cn } from "@/lib/utils"
import { 
  Network, 
  Radio, 
  Zap,
  MessageSquare,
  ArrowRight,
  Circle,
  Activity,
  Link2,
  Unlink,
  Eye
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"

export interface A2AAgent {
  id: string
  name: string
  clone: string
  model: string
  position: { x: number; y: number }
  isRunning: boolean
  capabilities: string[]
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

export interface A2AConnection {
  id: string
  from: string
  to: string
  status: "active" | "pending" | "idle"
  taskType: string
  messageCount: number
}

export interface A2AMessage {
  id: string
  from: string
  to: string
  type: "task_request" | "task_response" | "artifact" | "status_update"
  content: string
  timestamp: Date
}

interface A2ANetworkProps {
  agents: A2AAgent[]
  connections: A2AConnection[]
  messages: A2AMessage[]
  onConnect: (fromId: string, toId: string) => void
  onDisconnect: (connectionId: string) => void
  selectedAgentId: string | null
  onSelectAgent: (id: string | null) => void
}

export function A2ANetwork({
  agents,
  connections,
  messages,
  onConnect,
  onDisconnect,
  selectedAgentId,
  onSelectAgent
}: A2ANetworkProps) {
  const canvasRef = useRef<HTMLDivElement>(null)
  const [connectingFrom, setConnectingFrom] = useState<string | null>(null)
  const [hoveredConnection, setHoveredConnection] = useState<string | null>(null)

  const getAgentPosition = (agentId: string) => {
    const agent = agents.find(a => a.id === agentId)
    return agent?.position || { x: 0, y: 0 }
  }

  const handleAgentClick = (agentId: string) => {
    if (connectingFrom) {
      if (connectingFrom !== agentId) {
        onConnect(connectingFrom, agentId)
      }
      setConnectingFrom(null)
    } else {
      onSelectAgent(agentId === selectedAgentId ? null : agentId)
    }
  }

  const startConnection = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setConnectingFrom(agentId)
  }

  const recentMessages = messages.slice(-5).reverse()

  return (
    <div className="relative h-full">
      {/* Network Visualization */}
      <div 
        ref={canvasRef}
        className="relative h-[400px] rounded-xl border border-border/50 bg-gradient-to-br from-background via-card/30 to-background overflow-hidden"
        onClick={() => {
          setConnectingFrom(null)
          onSelectAgent(null)
        }}
      >
        {/* Grid Background */}
        <div 
          className="absolute inset-0 opacity-20"
          style={{
            backgroundImage: `
              linear-gradient(to right, hsl(var(--border)) 1px, transparent 1px),
              linear-gradient(to bottom, hsl(var(--border)) 1px, transparent 1px)
            `,
            backgroundSize: '40px 40px'
          }}
        />

        {/* Connections */}
        <svg className="absolute inset-0 w-full h-full pointer-events-none">
          <defs>
            <linearGradient id="connectionGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.8" />
              <stop offset="50%" stopColor="hsl(var(--accent))" stopOpacity="1" />
              <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0.8" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          {connections.map(conn => {
            const fromPos = getAgentPosition(conn.from)
            const toPos = getAgentPosition(conn.to)
            const isHovered = hoveredConnection === conn.id
            const isActive = conn.status === "active"
            
            return (
              <g key={conn.id}>
                {/* Connection line */}
                <line
                  x1={`${fromPos.x}%`}
                  y1={`${fromPos.y}%`}
                  x2={`${toPos.x}%`}
                  y2={`${toPos.y}%`}
                  stroke={isActive ? "url(#connectionGradient)" : "hsl(var(--muted-foreground))"}
                  strokeWidth={isHovered ? 3 : 2}
                  strokeDasharray={conn.status === "pending" ? "5,5" : "none"}
                  opacity={isActive ? 1 : 0.4}
                  filter={isActive ? "url(#glow)" : "none"}
                  className="transition-all duration-300"
                />
                
                {/* Animated pulse for active connections */}
                {isActive && (
                  <circle r="4" fill="hsl(var(--primary))">
                    <animateMotion
                      dur="2s"
                      repeatCount="indefinite"
                      path={`M${fromPos.x * 4},${fromPos.y * 4} L${toPos.x * 4},${toPos.y * 4}`}
                    />
                  </circle>
                )}
              </g>
            )
          })}
        </svg>

        {/* Agent Nodes */}
        {agents.map(agent => (
          <div
            key={agent.id}
            className={cn(
              "absolute transform -translate-x-1/2 -translate-y-1/2 cursor-pointer transition-all duration-300 group",
              connectingFrom === agent.id && "scale-110"
            )}
            style={{
              left: `${agent.position.x}%`,
              top: `${agent.position.y}%`
            }}
            onClick={(e) => {
              e.stopPropagation()
              handleAgentClick(agent.id)
            }}
          >
            {/* Glow effect */}
            <div className={cn(
              "absolute inset-0 rounded-full blur-xl transition-opacity duration-300",
              agent.isRunning ? "opacity-60" : "opacity-0",
              selectedAgentId === agent.id ? "bg-primary" : "bg-accent"
            )} style={{ transform: 'scale(1.5)' }} />
            
            {/* Node */}
            <div className={cn(
              "relative w-16 h-16 rounded-full border-2 flex items-center justify-center transition-all duration-300",
              agent.isRunning 
                ? "bg-gradient-to-br from-primary/20 to-accent/20 border-primary shadow-[0_0_30px_rgba(var(--primary),0.3)]" 
                : "bg-card/80 border-border/50",
              selectedAgentId === agent.id && "ring-2 ring-primary ring-offset-2 ring-offset-background",
              connectingFrom && connectingFrom !== agent.id && "animate-pulse"
            )}>
              {/* Status indicator */}
              <div className={cn(
                "absolute -top-1 -right-1 w-4 h-4 rounded-full border-2 border-background",
                agent.isRunning ? "bg-green-500 animate-pulse" : "bg-muted-foreground"
              )} />
              
              {/* Icon */}
              <Network className={cn(
                "w-6 h-6",
                agent.isRunning ? "text-primary" : "text-muted-foreground"
              )} />
            </div>
            
            {/* Label */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 text-center whitespace-nowrap">
              <p className="text-xs font-medium text-foreground">{agent.name}</p>
              <p className="text-[10px] text-muted-foreground">{agent.model}</p>
            </div>

            {/* Connect button */}
            <button
              onClick={(e) => startConnection(agent.id, e)}
              className={cn(
                "absolute -bottom-1 -right-1 w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center",
                "opacity-0 group-hover:opacity-100 transition-opacity duration-200",
                "hover:scale-110"
              )}
            >
              <Link2 className="w-3 h-3" />
            </button>
          </div>
        ))}

        {/* Connection mode indicator */}
        {connectingFrom && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full bg-primary/20 border border-primary/50 text-primary text-sm flex items-center gap-2">
            <Radio className="w-4 h-4 animate-pulse" />
            Click another agent to connect via A2A
          </div>
        )}

        {/* Empty state */}
        {agents.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Network className="w-16 h-16 text-muted-foreground/30 mx-auto mb-4" />
              <p className="text-muted-foreground">No agents deployed yet</p>
              <p className="text-muted-foreground/70 text-sm">Create and deploy agents to visualize the A2A network</p>
            </div>
          </div>
        )}
      </div>

      {/* A2A Activity Feed */}
      <div className="mt-4 p-4 rounded-xl border border-border/50 bg-card/30">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-foreground flex items-center gap-2">
            <Activity className="w-4 h-4 text-primary" />
            A2A Protocol Activity
          </h4>
          <span className="text-xs text-muted-foreground">{messages.length} messages</span>
        </div>
        
        <ScrollArea className="h-[120px]">
          {recentMessages.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground text-sm">
              No A2A activity yet. Connect agents to see communication.
            </div>
          ) : (
            <div className="space-y-2">
              {recentMessages.map(msg => {
                const fromAgent = agents.find(a => a.id === msg.from)
                const toAgent = agents.find(a => a.id === msg.to)
                
                return (
                  <div 
                    key={msg.id}
                    className="flex items-start gap-3 p-2 rounded-lg bg-background/50 text-sm"
                  >
                    <div className={cn(
                      "px-2 py-0.5 rounded text-[10px] font-medium",
                      msg.type === "task_request" && "bg-blue-500/20 text-blue-400",
                      msg.type === "task_response" && "bg-green-500/20 text-green-400",
                      msg.type === "artifact" && "bg-purple-500/20 text-purple-400",
                      msg.type === "status_update" && "bg-yellow-500/20 text-yellow-400"
                    )}>
                      {msg.type.replace("_", " ")}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <span className="font-medium text-foreground">{fromAgent?.name || "Unknown"}</span>
                        <ArrowRight className="w-3 h-3" />
                        <span className="font-medium text-foreground">{toAgent?.name || "Unknown"}</span>
                      </div>
                      <p className="text-muted-foreground truncate">{msg.content}</p>
                    </div>
                    <span className="text-[10px] text-muted-foreground/70">
                      {msg.timestamp.toLocaleTimeString()}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </ScrollArea>
      </div>
    </div>
  )
}

// Agent Card Display Component (A2A Protocol compliant)
export function AgentCardDisplay({ agent }: { agent: A2AAgent }) {
  return (
    <div className="p-4 rounded-xl border border-border/50 bg-card/50 space-y-4">
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-semibold text-foreground">{agent.agentCard.name}</h4>
          <p className="text-sm text-muted-foreground">{agent.agentCard.description}</p>
        </div>
        <div className={cn(
          "px-2 py-1 rounded-full text-xs",
          agent.isRunning ? "bg-green-500/20 text-green-400" : "bg-muted text-muted-foreground"
        )}>
          {agent.isRunning ? "Online" : "Offline"}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">Capabilities</p>
        <div className="flex flex-wrap gap-2">
          {agent.agentCard.capabilities.streaming && (
            <span className="px-2 py-1 rounded bg-primary/10 text-primary text-xs">Streaming</span>
          )}
          {agent.agentCard.capabilities.pushNotifications && (
            <span className="px-2 py-1 rounded bg-accent/10 text-accent text-xs">Push Notifications</span>
          )}
          {agent.agentCard.capabilities.stateTransitionHistory && (
            <span className="px-2 py-1 rounded bg-green-500/10 text-green-400 text-xs">State History</span>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">Skills</p>
        <div className="flex flex-wrap gap-1">
          {agent.agentCard.skills.map(skill => (
            <span key={skill.id} className="px-2 py-0.5 rounded bg-muted/50 text-muted-foreground text-xs">
              {skill.name}
            </span>
          ))}
        </div>
      </div>

      <div className="pt-2 border-t border-border/50">
        <p className="text-xs text-muted-foreground">Agent Card URL</p>
        <code className="text-xs text-primary break-all">{agent.agentCard.url}</code>
      </div>
    </div>
  )
}
