"use client"

import { useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"
import {
  Layers,
  Brain,
  Shield,
  MessageSquare,
  Clock,
  Server,
  Sparkles,
} from "lucide-react"

const features = [
  {
    icon: Layers,
    title: "Any Clone + Any Model",
    description:
      "Mix and match 43+ ClawClones with 200+ OpenRouter models. Create the perfect agent combination for your use case.",
    gradient: "from-primary/20 to-primary/5",
  },
  {
    icon: Brain,
    title: "Persistent Memory",
    description:
      "Agents remember context across sessions. Auto-generated skills let them learn and improve over time.",
    gradient: "from-amber-500/20 to-amber-500/5",
  },
  {
    icon: Shield,
    title: "Real Sandboxing",
    description:
      "Five sandbox backends - Local, Docker, SSH, Singularity, Modal. Container hardening and namespace isolation.",
    gradient: "from-emerald-500/20 to-emerald-500/5",
  },
  {
    icon: MessageSquare,
    title: "Multi-Channel Deploy",
    description:
      "Telegram, Discord, Slack, WhatsApp, Signal, Email, CLI - start on one, pick up on another seamlessly.",
    gradient: "from-cyan-500/20 to-cyan-500/5",
  },
  {
    icon: Clock,
    title: "Scheduled Automations",
    description:
      "Natural language cron scheduling for reports, backups, and briefings running unattended.",
    gradient: "from-violet-500/20 to-violet-500/5",
  },
  {
    icon: Server,
    title: "Parallel Sub-Agents",
    description:
      "Isolated subagents with their own conversations, terminals, and Python RPC scripts for zero-context-cost pipelines.",
    gradient: "from-pink-500/20 to-pink-500/5",
  },
]

export function FeaturesSection() {
  return (
    <section className="relative overflow-hidden py-16 sm:py-24 lg:py-32" id="features">
      {/* Background Elements */}
      <div className="absolute inset-0 grid-pattern opacity-20" />
      <div className="absolute left-1/2 top-1/2 hidden h-[600px] w-[600px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/5 blur-[128px] sm:block sm:h-[800px] sm:w-[800px]" />

      <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="mb-10 text-center sm:mb-16">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 sm:mb-4">
            <Sparkles className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
            <span className="text-xs text-primary sm:text-sm">ClawVerse Capabilities</span>
          </div>
          <h2 className="mb-3 text-2xl font-bold text-foreground text-balance sm:mb-4 sm:text-4xl md:text-5xl">
            An Agent That <span className="text-primary">Grows</span> With You
          </h2>
          <p className="mx-auto max-w-xl text-base text-muted-foreground text-pretty sm:max-w-2xl sm:text-lg md:text-xl">
            Not a coding copilot or chatbot wrapper. Autonomous agents that live on your server, 
            remember what they learn, and get more capable the longer they run.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid gap-4 sm:grid-cols-2 sm:gap-5 lg:grid-cols-3 lg:gap-6">
          {features.map((feature, index) => (
            <FeatureCard key={feature.title} feature={feature} index={index} />
          ))}
        </div>

        {/* Interactive Demo Preview */}
        <div className="relative mt-12 sm:mt-16 lg:mt-20">
          <div className="pointer-events-none absolute inset-0 z-10 bg-gradient-to-t from-background via-transparent to-transparent" />
          <div className="overflow-hidden rounded-xl border border-border bg-card/30 backdrop-blur-sm sm:rounded-2xl">
            {/* Terminal Header */}
            <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-2.5 sm:px-4 sm:py-3">
              <div className="flex gap-1.5">
                <div className="h-2.5 w-2.5 rounded-full bg-red-500/80 sm:h-3 sm:w-3" />
                <div className="h-2.5 w-2.5 rounded-full bg-amber-500/80 sm:h-3 sm:w-3" />
                <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/80 sm:h-3 sm:w-3" />
              </div>
              <span className="ml-2 font-mono text-[10px] text-muted-foreground sm:text-xs">agent-playground ~ hermes setup</span>
            </div>

            {/* Terminal Content */}
            <div className="space-y-1.5 p-4 font-mono text-xs sm:space-y-2 sm:p-6 sm:text-sm">
              <TerminalLine prefix="$" text="curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" />
              <TerminalLine prefix="✓" text="Hermes Agent installed successfully" isSuccess />
              <TerminalLine prefix="$" text="hermes setup" />
              <TerminalLine prefix="?" text="Select your preferred model provider:" isInfo />
              <TerminalLine prefix="" text="  › OpenRouter (200+ models)" isHighlight />
              <TerminalLine prefix="" text="    Anthropic" isInfo />
              <TerminalLine prefix="" text="    OpenAI" isInfo />
              <TerminalLine prefix="?" text="Select channels to enable:" isInfo />
              <TerminalLine prefix="" text="  ✓ Telegram" isSuccess />
              <TerminalLine prefix="" text="  ✓ Discord" isSuccess />
              <TerminalLine prefix="" text="  ✓ CLI" isSuccess />
              <TerminalLine prefix="✓" text="Configuration saved to ~/.hermes/config.yaml" isSuccess />
              <div className="h-2" />
              <TerminalLine prefix="→" text="Run 'hermes start' to launch your agent" isHighlight />
            </div>
          </div>
        </div>

        {/* Clone comparison callout */}
        <div className="mt-8 rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:mt-12 sm:p-6">
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center sm:gap-6">
            <div className="flex-1">
              <h3 className="mb-1.5 text-base font-semibold text-foreground sm:mb-2 sm:text-lg">Comparing Clones?</h3>
              <p className="text-sm text-muted-foreground">
                Each clone has different strengths - security, performance, size, or team features. 
                Use our Pulse Score to find the right fit.
              </p>
            </div>
            <div className="flex w-full gap-2 sm:w-auto sm:gap-3">
              <div className="flex-1 rounded-lg border border-green-500/30 bg-green-500/10 px-3 py-2 text-center sm:flex-none sm:px-4">
                <div className="text-lg font-bold text-green-400 sm:text-2xl">85%+</div>
                <div className="text-[10px] text-muted-foreground sm:text-xs">Excellent</div>
              </div>
              <div className="flex-1 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-center sm:flex-none sm:px-4">
                <div className="text-lg font-bold text-yellow-400 sm:text-2xl">70-84%</div>
                <div className="text-[10px] text-muted-foreground sm:text-xs">Good</div>
              </div>
              <div className="flex-1 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-center sm:flex-none sm:px-4">
                <div className="text-lg font-bold text-red-400 sm:text-2xl">&lt;70%</div>
                <div className="text-[10px] text-muted-foreground sm:text-xs">Caution</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

function FeatureCard({
  feature,
  index,
}: {
  feature: (typeof features)[0]
  index: number
}) {
  const [isVisible, setIsVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
        }
      },
      { threshold: 0.1 }
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [])

  const Icon = feature.icon

  return (
    <div
      ref={ref}
      className={cn(
        "group relative rounded-xl border border-border bg-card/30 p-4 backdrop-blur-sm transition-all duration-500 hover:border-primary/30 sm:p-6",
        isVisible ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0"
      )}
      style={{ transitionDelay: `${index * 100}ms` }}
    >
      {/* Gradient Background */}
      <div
        className={cn(
          "absolute inset-0 rounded-xl opacity-0 transition-opacity duration-500 group-hover:opacity-100",
          `bg-gradient-to-br ${feature.gradient}`
        )}
      />

      <div className="relative z-10">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 transition-colors group-hover:bg-primary/20 sm:mb-4 sm:h-12 sm:w-12">
          <Icon className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
        </div>
        <h3 className="mb-1.5 text-base font-semibold text-foreground transition-colors group-hover:text-primary sm:mb-2 sm:text-lg">
          {feature.title}
        </h3>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {feature.description}
        </p>
      </div>
    </div>
  )
}

function TerminalLine({
  prefix,
  text,
  isSuccess,
  isInfo,
  isHighlight,
}: {
  prefix: string
  text: string
  isSuccess?: boolean
  isInfo?: boolean
  isHighlight?: boolean
}) {
  return (
    <div
      className={cn(
        "leading-relaxed break-all",
        isSuccess && "text-emerald-400",
        isInfo && "text-muted-foreground",
        isHighlight && "text-primary",
        !isSuccess && !isInfo && !isHighlight && "text-foreground"
      )}
    >
      {prefix && <span className="mr-2">{prefix}</span>}
      {text}
    </div>
  )
}
