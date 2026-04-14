"use client"

import { Layers, Cpu, MessageSquare, Zap, Shield, Code2 } from "lucide-react"
import Link from "next/link"

const agentTypes = [
  {
    name: "Hermes-agent",
    description: "The ultimate open-source alternative with extreme performance and developer ergonomics.",
    language: "Python",
    features: ["Multi-channel support", "Tool calling", "Memory persistence", "Streaming"],
    color: "text-purple-500",
    href: "https://hermes-agent.nousresearch.com/",
  },
  {
    name: "ZeroClaw",
    description: "Hyper-optimized Rust rewrite that runs on minimal hardware with under 5MB RAM.",
    language: "Rust",
    features: ["Low memory", "Fast inference", "Edge deployment", "ARM support"],
    color: "text-orange-500",
    href: "https://clawclones.com/#clones",
  },
  {
    name: "OpenClaw",
    description: "The OG personal AI assistant that sparked the self-hosted agent movement.",
    language: "TypeScript",
    features: ["Web UI", "Plugins", "Community extensions", "Multi-model"],
    color: "text-blue-500",
    href: "https://clawclones.com/#clones",
  },
  {
    name: "IronClaw",
    description: "Prioritizes isolation, telemetry discipline, and safer defaults for security.",
    language: "Rust",
    features: ["Process isolation", "Audit logging", "Safe defaults", "No telemetry"],
    color: "text-slate-500",
    href: "https://clawclones.com/#clones",
  },
]

export default function AgentsPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Agents</h1>
        <p className="mt-3 text-muted-foreground">
          Learn about the different agent frameworks (ClawClones) available in Agent Playground.
        </p>
      </div>

      {/* What is an Agent */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">What is an Agent?</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          An agent is an autonomous AI system that can perceive its environment, make decisions, 
          and take actions to achieve specific goals. In Agent Playground, agents combine:
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Cpu className="mb-2 h-6 w-6 text-primary" />
            <h3 className="text-sm font-medium text-foreground">Clone Framework</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              The underlying runtime and architecture
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Code2 className="mb-2 h-6 w-6 text-primary" />
            <h3 className="text-sm font-medium text-foreground">Language Model</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              The AI brain powering reasoning
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <MessageSquare className="mb-2 h-6 w-6 text-primary" />
            <h3 className="text-sm font-medium text-foreground">Channels</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Where the agent communicates
            </p>
          </div>
        </div>
      </section>

      {/* Available Clones */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Available ClawClones</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          ClawClones are open-source agent frameworks you can use as the foundation for your agents:
        </p>
        <div className="space-y-4">
          {agentTypes.map((agent) => (
            <div
              key={agent.name}
              className="rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30 sm:p-5"
            >
              <div className="mb-3 flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-foreground">{agent.name}</h3>
                  <span className={`text-xs font-mono ${agent.color}`}>{agent.language}</span>
                </div>
                <a
                  href={agent.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  Learn more
                </a>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">{agent.description}</p>
              <div className="flex flex-wrap gap-1.5">
                {agent.features.map((feature) => (
                  <span
                    key={feature}
                    className="rounded bg-muted/50 px-2 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {feature}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Agent Lifecycle */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Agent Lifecycle</h2>
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <ol className="space-y-4">
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                1
              </span>
              <div>
                <h3 className="font-medium text-foreground">Configuration</h3>
                <p className="text-sm text-muted-foreground">
                  Select a clone, model, and channels for your agent.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                2
              </span>
              <div>
                <h3 className="font-medium text-foreground">Deployment</h3>
                <p className="text-sm text-muted-foreground">
                  Deploy to our cloud or your own infrastructure.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                3
              </span>
              <div>
                <h3 className="font-medium text-foreground">Runtime</h3>
                <p className="text-sm text-muted-foreground">
                  Agent receives messages, processes them, and responds.
                </p>
              </div>
            </li>
            <li className="flex gap-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                4
              </span>
              <div>
                <h3 className="font-medium text-foreground">Monitoring</h3>
                <p className="text-sm text-muted-foreground">
                  Track performance, logs, and analytics in the dashboard.
                </p>
              </div>
            </li>
          </ol>
        </div>
      </section>

      {/* Agent Capabilities */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Agent Capabilities</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Zap className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Tool Calling</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Agents can use external tools and APIs to complete tasks.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Layers className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Memory</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Persistent memory allows agents to remember context across conversations.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <MessageSquare className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Multi-Channel</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Deploy agents to Discord, Slack, Telegram, and more simultaneously.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Shield className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">A2A Protocol</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Enable agents to communicate and collaborate with each other.
            </p>
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Next Steps</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            href="/docs/models"
            className="flex-1 rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <h3 className="font-medium text-foreground">Models</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Learn about available language models
            </p>
          </Link>
          <Link
            href="/docs/channels"
            className="flex-1 rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <h3 className="font-medium text-foreground">Channels</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Configure communication channels
            </p>
          </Link>
        </div>
      </section>
    </article>
  )
}
