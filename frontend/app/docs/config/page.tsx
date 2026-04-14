"use client"

import { Settings, FileCode, Lock, Database, Zap } from "lucide-react"

const configSections = [
  {
    id: "basic",
    title: "Basic Configuration",
    code: `{
  "name": "my-agent",
  "description": "A helpful assistant",
  "clone": "hermes-agent",
  "model": "claude-3-sonnet",
  "version": "1.0.0"
}`,
    description: "Every agent starts with these basic settings. The name must be unique within your account."
  },
  {
    id: "model",
    title: "Model Configuration",
    code: `{
  "model": {
    "provider": "openrouter",
    "name": "anthropic/claude-3-sonnet",
    "temperature": 0.7,
    "maxTokens": 4096,
    "systemPrompt": "You are a helpful assistant..."
  }
}`,
    description: "Fine-tune model behavior with temperature, token limits, and custom system prompts."
  },
  {
    id: "channels",
    title: "Channel Configuration",
    code: `{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "$TELEGRAM_BOT_TOKEN"
    },
    "discord": {
      "enabled": true,
      "token": "$DISCORD_BOT_TOKEN",
      "guildId": "123456789",
      "commandPrefix": "!"
    }
  }
}`,
    description: "Configure one or more channels for your agent. Use environment variables for secrets."
  },
  {
    id: "memory",
    title: "Memory Configuration",
    code: `{
  "memory": {
    "type": "persistent",
    "backend": "redis",
    "ttl": 86400,
    "maxConversations": 100,
    "embeddings": {
      "enabled": true,
      "model": "text-embedding-3-small"
    }
  }
}`,
    description: "Control how your agent remembers conversations. Options include ephemeral, persistent, and vector-based memory."
  },
  {
    id: "tools",
    title: "Tools Configuration",
    code: `{
  "tools": [
    {
      "name": "web_search",
      "enabled": true,
      "provider": "tavily"
    },
    {
      "name": "code_interpreter",
      "enabled": true,
      "sandbox": "isolated"
    },
    {
      "name": "custom_api",
      "endpoint": "https://api.example.com",
      "auth": "$API_KEY"
    }
  ]
}`,
    description: "Extend your agent with built-in tools or custom API integrations."
  },
  {
    id: "a2a",
    title: "A2A Configuration",
    code: `{
  "a2a": {
    "enabled": true,
    "registry": "https://registry.agentplayground.dev",
    "capabilities": ["support", "billing"],
    "allowedAgents": ["*@mycompany.com"],
    "rateLimit": {
      "requests": 100,
      "window": "1m"
    }
  }
}`,
    description: "Enable agent-to-agent communication with capability advertising and access control."
  }
]

const envVariables = [
  { name: "OPENROUTER_API_KEY", description: "Your OpenRouter API key for model access", required: true },
  { name: "TELEGRAM_BOT_TOKEN", description: "Telegram bot token from @BotFather", required: false },
  { name: "DISCORD_BOT_TOKEN", description: "Discord application bot token", required: false },
  { name: "REDIS_URL", description: "Redis connection URL for persistent memory", required: false },
  { name: "AP_API_KEY", description: "Agent Playground API key for deployment", required: true },
]

export default function ConfigPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Configuration</h1>
        <p className="mt-3 text-muted-foreground">
          Complete reference for agent configuration options.
        </p>
      </div>

      {/* Overview */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Configuration File</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Agents are configured using a <code className="rounded bg-muted px-1.5 py-0.5 text-xs">agent.config.json</code> file 
          in your project root. All settings can be overridden via environment variables.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <FileCode className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">JSON Format</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Human-readable configuration with comments support via JSONC.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <Lock className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Environment Variables</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Secrets referenced as <code className="text-xs">$VAR_NAME</code> are loaded from environment.
            </p>
          </div>
        </div>
      </section>

      {/* Config Sections */}
      {configSections.map((section) => (
        <section key={section.id} className="mb-10">
          <h2 className="mb-2 text-xl font-semibold text-foreground">{section.title}</h2>
          <p className="mb-4 text-sm text-muted-foreground">{section.description}</p>
          <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
            <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
              <span className="text-xs text-muted-foreground">agent.config.json</span>
            </div>
            <pre className="overflow-x-auto p-4 text-sm">
              <code className="text-muted-foreground">{section.code}</code>
            </pre>
          </div>
        </section>
      ))}

      {/* Environment Variables */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Environment Variables</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Common environment variables used by Agent Playground:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 bg-muted/50">
                <th className="px-4 py-3 text-left font-medium text-foreground">Variable</th>
                <th className="px-4 py-3 text-left font-medium text-foreground">Description</th>
                <th className="px-4 py-3 text-center font-medium text-foreground">Required</th>
              </tr>
            </thead>
            <tbody>
              {envVariables.map((env) => (
                <tr key={env.name} className="border-b border-border/30 last:border-b-0">
                  <td className="px-4 py-3">
                    <code className="rounded bg-muted px-1.5 py-0.5 text-xs text-foreground">
                      {env.name}
                    </code>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{env.description}</td>
                  <td className="px-4 py-3 text-center">
                    {env.required ? (
                      <span className="text-green-500">Yes</span>
                    ) : (
                      <span className="text-muted-foreground">No</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Validation */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Configuration Validation</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Validate your configuration before deploying:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
          <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
            <span className="text-xs text-muted-foreground">bash</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm">
            <code className="text-muted-foreground">agentplayground config validate</code>
          </pre>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          This command checks for syntax errors, missing required fields, and validates environment variable references.
        </p>
      </section>

      {/* Best Practices */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Best Practices</h2>
        <div className="space-y-3">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Use Version Control</h3>
            <p className="text-xs text-muted-foreground">
              Keep your config file in git, but never commit secrets. Use .env files locally.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Environment-Specific Configs</h3>
            <p className="text-xs text-muted-foreground">
              Use agent.config.dev.json and agent.config.prod.json for different environments.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Start Minimal</h3>
            <p className="text-xs text-muted-foreground">
              Begin with basic configuration and add features incrementally as needed.
            </p>
          </div>
        </div>
      </section>
    </article>
  )
}
