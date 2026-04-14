import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ArrowRight, Zap, Terminal, Check } from "lucide-react"

export default function QuickstartPage() {
  return (
    <article className="prose prose-invert max-w-none">
      {/* Header */}
      <div className="not-prose mb-8">
        <div className="mb-4 flex items-center gap-2 text-primary">
          <Zap className="h-5 w-5" />
          <span className="text-sm font-medium">Getting Started</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">
          Quick Start
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          Deploy your first agent in under 5 minutes.
        </p>
      </div>

      {/* Prerequisites */}
      <div className="not-prose mb-8 rounded-xl border border-border/50 bg-card/30 p-5">
        <h3 className="mb-3 font-semibold text-foreground">Prerequisites</h3>
        <ul className="space-y-2">
          {["Node.js 18+ installed", "An OpenRouter API key", "A Discord/Telegram bot token (optional)"].map((item) => (
            <li key={item} className="flex items-center gap-2 text-sm text-muted-foreground">
              <Check className="h-4 w-4 text-green-500" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <h2>Step 1: Install the CLI</h2>
      <p>First, install the Agent Playground CLI globally:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4"><code className="text-sm">{`npm install -g @agentplayground/cli

# Verify installation
agent --version`}</code></pre>
      </div>

      <h2>Step 2: Initialize Your Agent</h2>
      <p>Create a new agent project using the Hermes-agent framework:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4"><code className="text-sm">{`# Create a new agent
agent init my-assistant --clone hermes-agent

# Navigate to the project
cd my-assistant`}</code></pre>
      </div>

      <p>This creates a new directory with the following structure:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <pre className="p-4"><code className="text-sm text-muted-foreground">{`my-assistant/
├── agent.config.yaml    # Agent configuration
├── prompts/
│   └── system.md        # System prompt
├── tools/
│   └── example.ts       # Custom tools
└── package.json`}</code></pre>
      </div>

      <h2>Step 3: Configure Your Model</h2>
      <p>Set up your OpenRouter API key and select a model:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4"><code className="text-sm">{`# Set your OpenRouter API key
agent config set OPENROUTER_API_KEY your-key-here

# Choose a model
agent config set model anthropic/claude-3-sonnet

# Or use GPT-4
agent config set model openai/gpt-4-turbo`}</code></pre>
      </div>

      <h2>Step 4: Test Locally</h2>
      <p>Start the agent in interactive mode to test it:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4"><code className="text-sm">{`agent dev

# You'll see:
# ✓ Agent "my-assistant" started
# ✓ Model: claude-3-sonnet
# ✓ Interactive mode enabled
# 
# You: Hello!
# Agent: Hello! How can I assist you today?`}</code></pre>
      </div>

      <h2>Step 5: Deploy to a Channel</h2>
      <p>Deploy your agent to Discord, Telegram, or any other channel:</p>
      
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center gap-2 border-b border-border/50 bg-muted/30 px-4 py-2">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Terminal</span>
        </div>
        <pre className="p-4"><code className="text-sm">{`# Deploy to Discord
agent deploy --channel discord

# Or deploy to Telegram
agent deploy --channel telegram

# Deploy to multiple channels
agent deploy --channel discord,telegram,slack`}</code></pre>
      </div>

      <div className="not-prose my-8 rounded-xl border border-green-500/30 bg-green-500/5 p-5">
        <h3 className="mb-2 flex items-center gap-2 font-semibold text-green-400">
          <Check className="h-5 w-5" />
          Congratulations!
        </h3>
        <p className="text-sm text-muted-foreground">
          Your agent is now live and responding to messages. Visit your Discord/Telegram to start chatting!
        </p>
      </div>

      <h2>Next Steps</h2>
      <ul>
        <li><Link href="/docs/agents">Learn more about agent configuration</Link></li>
        <li><Link href="/docs/a2a">Enable A2A protocol for multi-agent systems</Link></li>
        <li><Link href="/docs/api">Integrate with the API</Link></li>
      </ul>

      <div className="not-prose mt-8 flex flex-col gap-3 sm:flex-row">
        <Button asChild className="gap-2 bg-primary text-primary-foreground">
          <Link href="/docs/agents">
            Learn About Agents
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/playground">
            Try the Playground
          </Link>
        </Button>
      </div>
    </article>
  )
}
