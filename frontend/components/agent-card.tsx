"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { 
  Cpu, 
  Zap, 
  Shield, 
  Terminal,
  Rocket,
  Check,
  Star,
  TrendingUp,
  Github
} from "lucide-react"

export interface ClawClone {
  id: string
  name: string
  language: string
  description: string
  pulseScore: number
  stars: string
  isHot?: boolean
  icon: "hermes" | "zeroclaw" | "openclaw" | "nullclaw" | "moltis" | "ironclaw" | "safeclaw" | "nanobot"
  category: "secure" | "local" | "zero-cost" | "teams" | "edge" | "replacement"
  capabilities: string[]
}

const cloneIcons = {
  hermes: Terminal,
  zeroclaw: Zap,
  openclaw: Cpu,
  nullclaw: Shield,
  moltis: Rocket,
  ironclaw: Shield,
  safeclaw: Shield,
  nanobot: Cpu,
}

const languageColors: Record<string, string> = {
  Python: "text-yellow-400",
  Rust: "text-orange-400",
  Go: "text-cyan-400",
  TypeScript: "text-blue-400",
  Zig: "text-amber-400",
  C: "text-gray-400",
}

interface AgentCardProps {
  clone: ClawClone
  isSelected: boolean
  onSelect: () => void
  instanceCount?: number
}

export function AgentCard({ clone, isSelected, onSelect, instanceCount = 0 }: AgentCardProps) {
  const [isHovered, setIsHovered] = useState(false)
  const Icon = cloneIcons[clone.icon] || Terminal

  return (
    <button
      onClick={onSelect}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      className={cn(
        "group relative w-full rounded-xl border p-3 text-left transition-all duration-300 sm:p-4",
        "bg-card/50 backdrop-blur-sm",
        isSelected 
          ? "border-primary shadow-[0_0_30px_rgba(249,115,22,0.3)]" 
          : "border-border/50 hover:border-primary/50",
        isHovered && !isSelected && "shadow-[0_0_20px_rgba(249,115,22,0.15)]"
      )}
    >
      {/* Hot badge */}
      {clone.isHot && (
        <div className="absolute -right-1.5 -top-1.5 flex items-center gap-0.5 rounded-full bg-gradient-to-r from-orange-500 to-amber-500 px-1.5 py-0.5 text-[8px] font-bold text-white sm:-right-2 sm:-top-2 sm:gap-1 sm:px-2 sm:text-[10px]">
          <TrendingUp className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
          HOT
        </div>
      )}

      {/* Selected indicator */}
      {isSelected && (
        <div className="absolute right-2.5 top-2.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary sm:right-3 sm:top-3 sm:h-5 sm:w-5">
          <Check className="h-2.5 w-2.5 text-primary-foreground sm:h-3 sm:w-3" />
        </div>
      )}

      {/* Instance count badge */}
      {instanceCount > 0 && (
        <div className="absolute -left-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[10px] font-bold text-accent-foreground sm:-left-2 sm:-top-2 sm:h-6 sm:w-6 sm:text-xs">
          {instanceCount}
        </div>
      )}

      {/* Glow effect */}
      <div className={cn(
        "absolute inset-0 rounded-xl opacity-0 transition-opacity duration-300",
        "bg-gradient-to-r from-primary/20 via-transparent to-accent/20",
        (isHovered || isSelected) && "opacity-100"
      )} />

      <div className="relative flex items-start gap-2.5 sm:gap-3">
        {/* Icon */}
        <div className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-300 sm:h-10 sm:w-10",
          "bg-gradient-to-br from-primary/20 to-accent/20",
          isSelected && "from-primary/40 to-accent/40 shadow-[0_0_15px_rgba(249,115,22,0.3)]",
          isHovered && !isSelected && "from-primary/30 to-accent/30"
        )}>
          <Icon className={cn(
            "h-4 w-4 transition-colors duration-300 sm:h-5 sm:w-5",
            isSelected ? "text-primary" : "text-muted-foreground"
          )} />
        </div>

        <div className="min-w-0 flex-1">
          {/* Header */}
          <div className="mb-0.5 flex items-center gap-1.5 sm:mb-1 sm:gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground sm:text-base">{clone.name}</h3>
            <span className={cn("shrink-0 font-mono text-[10px] sm:text-xs", languageColors[clone.language] || "text-muted-foreground")}>
              {clone.language}
            </span>
          </div>

          {/* Description */}
          <p className="mb-1.5 line-clamp-2 text-[10px] leading-relaxed text-muted-foreground sm:mb-2 sm:text-xs">
            {clone.description}
          </p>

          {/* Stats */}
          <div className="flex items-center gap-2 text-[10px] sm:gap-3 sm:text-xs">
            {/* Pulse Score */}
            <div className="flex items-center gap-1">
              <div className={cn(
                "h-1.5 w-1.5 rounded-full sm:h-2 sm:w-2",
                clone.pulseScore >= 85 ? "bg-green-500" :
                clone.pulseScore >= 70 ? "bg-yellow-500" : "bg-red-500"
              )} />
              <span className="text-muted-foreground">{clone.pulseScore}%</span>
            </div>

            {/* Stars */}
            <div className="flex items-center gap-0.5 text-muted-foreground sm:gap-1">
              <Star className="h-2.5 w-2.5 fill-yellow-500 text-yellow-500 sm:h-3 sm:w-3" />
              <span>{clone.stars}</span>
            </div>

            {/* GitHub link indicator */}
            <Github className="ml-auto h-2.5 w-2.5 text-muted-foreground transition-colors group-hover:text-foreground sm:h-3 sm:w-3" />
          </div>
        </div>
      </div>
    </button>
  )
}

// Default clones data based on ClawClones.com
export const defaultClones: ClawClone[] = [
  {
    id: "hermes-agent",
    name: "Hermes-agent",
    language: "Python",
    description: "The ultimate open-source alternative. Focuses on extreme performance and developer ergonomics. Lives where you do - Telegram, Discord, Slack, WhatsApp.",
    pulseScore: 90,
    stars: "35.2k",
    isHot: true,
    icon: "hermes",
    category: "replacement",
    capabilities: ["function_calling", "streaming", "multi_turn", "tool_use", "code_execution", "memory"]
  },
  {
    id: "zeroclaw",
    name: "ZeroClaw",
    language: "Rust",
    description: "Hyper-optimized Rust rewrite that runs on $10 hardware with under 5MB RAM - 99% less memory than OpenClaw.",
    pulseScore: 87,
    stars: "29.8k",
    isHot: true,
    icon: "zeroclaw",
    category: "edge",
    capabilities: ["low_memory", "fast_inference", "edge_deployment", "arm_support"]
  },
  {
    id: "nullclaw",
    name: "NullClaw",
    language: "Zig",
    description: "The ultimate minimalist - 678 KB static binary that boots in under 2ms and uses ~1 MB RAM.",
    pulseScore: 88,
    stars: "7.1k",
    icon: "nullclaw",
    category: "edge",
    capabilities: ["minimal_footprint", "instant_boot", "static_binary", "embedded"]
  },
  {
    id: "openclaw",
    name: "OpenClaw",
    language: "TypeScript",
    description: "The OG personal AI assistant that sparked the self-hosted agent movement - 300K+ stars.",
    pulseScore: 72,
    stars: "351.8k",
    icon: "openclaw",
    category: "replacement",
    capabilities: ["web_ui", "plugins", "community_extensions", "multi_model"]
  },
  {
    id: "moltis",
    name: "Moltis",
    language: "Rust",
    description: "Rust-native framework with sandboxed execution and local key storage. Single-binary with voice, memory, and multi-platform integrations.",
    pulseScore: 78,
    stars: "2.5k",
    icon: "moltis",
    category: "secure",
    capabilities: ["sandboxed_execution", "local_keys", "voice_support", "memory"]
  },
  {
    id: "ironclaw",
    name: "IronClaw",
    language: "Rust",
    description: "Prioritizes isolation, telemetry discipline, and safer defaults. Top pick for security-focused deployments.",
    pulseScore: 82,
    stars: "11.5k",
    icon: "ironclaw",
    category: "secure",
    capabilities: ["process_isolation", "audit_logging", "safe_defaults", "no_telemetry"]
  },
  {
    id: "safeclaw",
    name: "SafeClaw",
    language: "Python",
    description: "Projects that skew toward on-device inference, tighter data boundaries, and lower cloud dependence.",
    pulseScore: 75,
    stars: "125",
    icon: "safeclaw",
    category: "local",
    capabilities: ["local_inference", "data_isolation", "offline_mode", "privacy_first"]
  },
  {
    id: "nanobot",
    name: "nanobot",
    language: "Python",
    description: "Bias toward multi-user coordination, workplace channels, orchestration, and enterprise posture.",
    pulseScore: 85,
    stars: "38.5k",
    icon: "nanobot",
    category: "teams",
    capabilities: ["multi_user", "team_channels", "orchestration", "enterprise_auth", "rbac"]
  }
]
