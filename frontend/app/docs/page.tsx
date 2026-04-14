import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, BookOpen, Zap, Terminal, Layers, Network, Code2 } from "lucide-react"

const quickLinks = [
  {
    title: "Quick Start",
    description: "Get your first agent running in under 5 minutes",
    href: "/docs/quickstart",
    icon: Zap,
  },
  {
    title: "Agent Basics",
    description: "Understand how agents work and how to configure them",
    href: "/docs/agents",
    icon: Layers,
  },
  {
    title: "A2A Protocol",
    description: "Enable agent-to-agent communication",
    href: "/docs/a2a",
    icon: Network,
  },
  {
    title: "API Reference",
    description: "Complete API documentation for developers",
    href: "/docs/api",
    icon: Code2,
  },
]

export default function DocsPage() {
  return (
    <article className="prose prose-invert max-w-none">
      {/* Header */}
      <div className="not-prose mb-8">
        <div className="mb-4 flex items-center gap-2 text-primary">
          <BookOpen className="h-5 w-5" />
          <span className="text-sm font-medium">Documentation</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">
          Welcome to Agent Playground
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          Learn how to build, deploy, and manage autonomous AI agents with any model from OpenRouter.
        </p>
      </div>

      {/* Quick Links */}
      <div className="not-prose mb-12 grid gap-4 sm:grid-cols-2">
        {quickLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="group rounded-xl border border-border/50 bg-card/30 p-5 transition-all hover:border-primary/50 hover:bg-card/50"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <link.icon className="h-5 w-5" />
            </div>
            <h3 className="font-semibold text-foreground group-hover:text-primary">
              {link.title}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {link.description}
            </p>
          </Link>
        ))}
      </div>

      {/* Introduction */}
      <h2>What is Agent Playground?</h2>
      <p>
        Agent Playground is a comprehensive platform for deploying autonomous AI agents that can interact 
        with users across multiple channels like Telegram, Discord, Slack, and more. It supports any 
        language model available through OpenRouter and implements the A2A protocol for agent-to-agent communication.
      </p>

      <h2>Key Features</h2>
      <ul>
        <li><strong>Multi-Model Support</strong> - Use any model from OpenRouter including GPT-4, Claude, Llama, and more</li>
        <li><strong>ClawClones Integration</strong> - Choose from Hermes-agent, ZeroClaw, OpenClaw, and other agent frameworks</li>
        <li><strong>Channel Flexibility</strong> - Deploy agents to Telegram, Discord, Slack, WhatsApp, and webhooks</li>
        <li><strong>A2A Protocol</strong> - Enable real-time communication between agents for collaborative tasks</li>
        <li><strong>Web & Application Interfaces</strong> - Manage agents through our dashboard or CLI</li>
      </ul>

      <h2>Quick Example</h2>
      <p>Here&apos;s how simple it is to deploy an agent:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4">
          <code className="text-sm">
{`# Install the CLI
npm install -g @agentplayground/cli

# Initialize a new agent
agent init my-assistant --clone hermes-agent

# Configure your model
agent config set model claude-3-sonnet

# Deploy to Discord
agent deploy --channel discord`}
          </code>
        </pre>
      </div>

      <h2>Next Steps</h2>
      <p>
        Ready to get started? Check out our Quick Start guide to deploy your first agent in minutes.
      </p>
      
      <div className="not-prose mt-6 flex flex-col gap-3 sm:flex-row">
        <Button asChild className="gap-2 bg-primary text-primary-foreground">
          <Link href="/docs/quickstart">
            Quick Start Guide
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
        <Button asChild variant="outline" className="gap-2">
          <Link href="/docs/agents">
            Learn About Agents
          </Link>
        </Button>
      </div>
    </article>
  )
}
