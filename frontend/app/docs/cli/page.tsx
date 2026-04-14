import { Terminal, Copy } from "lucide-react"

const commands = [
  {
    name: "agent init",
    description: "Initialize a new agent project",
    usage: "agent init <name> [options]",
    options: [
      { flag: "--clone <framework>", desc: "Agent framework to use (hermes-agent, zeroclaw, openclaw)" },
      { flag: "--template <name>", desc: "Use a predefined template" },
      { flag: "--typescript", desc: "Use TypeScript (default)" },
    ],
    example: `agent init my-assistant --clone hermes-agent`,
  },
  {
    name: "agent config",
    description: "Manage agent configuration",
    usage: "agent config <command> [key] [value]",
    options: [
      { flag: "set <key> <value>", desc: "Set a configuration value" },
      { flag: "get <key>", desc: "Get a configuration value" },
      { flag: "list", desc: "List all configuration values" },
    ],
    example: `agent config set model anthropic/claude-3-sonnet
agent config set OPENROUTER_API_KEY sk-xxx`,
  },
  {
    name: "agent dev",
    description: "Start the agent in development mode",
    usage: "agent dev [options]",
    options: [
      { flag: "--port <number>", desc: "Port for the dev server (default: 3000)" },
      { flag: "--interactive", desc: "Enable interactive CLI mode" },
      { flag: "--verbose", desc: "Enable verbose logging" },
    ],
    example: `agent dev --interactive`,
  },
  {
    name: "agent deploy",
    description: "Deploy the agent to production",
    usage: "agent deploy [options]",
    options: [
      { flag: "--channel <channels>", desc: "Channels to deploy to (comma-separated)" },
      { flag: "--env <environment>", desc: "Deployment environment (staging, production)" },
      { flag: "--a2a", desc: "Enable A2A protocol" },
    ],
    example: `agent deploy --channel discord,telegram --a2a`,
  },
  {
    name: "agent list",
    description: "List all deployed agents",
    usage: "agent list [options]",
    options: [
      { flag: "--status <status>", desc: "Filter by status (running, stopped)" },
      { flag: "--json", desc: "Output as JSON" },
    ],
    example: `agent list --status running`,
  },
  {
    name: "agent stop",
    description: "Stop a running agent",
    usage: "agent stop <agent-id>",
    options: [
      { flag: "--all", desc: "Stop all running agents" },
      { flag: "--force", desc: "Force stop without graceful shutdown" },
    ],
    example: `agent stop my-assistant
agent stop --all`,
  },
  {
    name: "agent logs",
    description: "View agent logs",
    usage: "agent logs <agent-id> [options]",
    options: [
      { flag: "--follow", desc: "Follow log output" },
      { flag: "--tail <lines>", desc: "Number of lines to show" },
      { flag: "--since <time>", desc: "Show logs since timestamp" },
    ],
    example: `agent logs my-assistant --follow --tail 100`,
  },
]

export default function CLIPage() {
  return (
    <article className="prose prose-invert max-w-none">
      {/* Header */}
      <div className="not-prose mb-8">
        <div className="mb-4 flex items-center gap-2 text-primary">
          <Terminal className="h-5 w-5" />
          <span className="text-sm font-medium">Reference</span>
        </div>
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">
          CLI Reference
        </h1>
        <p className="mt-3 text-lg text-muted-foreground">
          Complete reference for the Agent Playground command-line interface.
        </p>
      </div>

      {/* Installation */}
      <h2>Installation</h2>
      <div className="not-prose overflow-hidden rounded-lg border border-border/50 bg-background/50">
        <div className="flex items-center justify-between border-b border-border/50 bg-muted/30 px-4 py-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Terminal</span>
          </div>
          <button className="text-muted-foreground hover:text-foreground">
            <Copy className="h-4 w-4" />
          </button>
        </div>
        <pre className="p-4"><code className="text-sm">{`npm install -g @agentplayground/cli`}</code></pre>
      </div>

      {/* Commands */}
      <h2>Commands</h2>
      
      <div className="not-prose space-y-6">
        {commands.map((cmd) => (
          <div key={cmd.name} className="rounded-xl border border-border/50 bg-card/30 p-5">
            <h3 className="mb-1 font-mono text-lg font-semibold text-primary">{cmd.name}</h3>
            <p className="mb-4 text-sm text-muted-foreground">{cmd.description}</p>
            
            <div className="mb-4">
              <span className="text-xs font-medium uppercase text-muted-foreground">Usage</span>
              <pre className="mt-1 rounded-lg bg-background/50 p-3 text-sm">
                <code>{cmd.usage}</code>
              </pre>
            </div>

            <div className="mb-4">
              <span className="text-xs font-medium uppercase text-muted-foreground">Options</span>
              <div className="mt-2 space-y-2">
                {cmd.options.map((opt, i) => (
                  <div key={i} className="flex gap-4 text-sm">
                    <code className="shrink-0 text-primary">{opt.flag}</code>
                    <span className="text-muted-foreground">{opt.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <span className="text-xs font-medium uppercase text-muted-foreground">Example</span>
              <pre className="mt-1 rounded-lg bg-background/50 p-3 text-sm">
                <code>{cmd.example}</code>
              </pre>
            </div>
          </div>
        ))}
      </div>

      {/* Environment Variables */}
      <h2>Environment Variables</h2>
      <p>The CLI respects the following environment variables:</p>
      
      <div className="not-prose overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/50">
              <th className="py-3 pr-4 text-left font-medium text-foreground">Variable</th>
              <th className="py-3 pr-4 text-left font-medium text-foreground">Description</th>
              <th className="py-3 text-left font-medium text-foreground">Default</th>
            </tr>
          </thead>
          <tbody className="text-muted-foreground">
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono text-primary">OPENROUTER_API_KEY</td>
              <td className="py-3 pr-4">Your OpenRouter API key</td>
              <td className="py-3">-</td>
            </tr>
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono text-primary">AGENT_CONFIG_PATH</td>
              <td className="py-3 pr-4">Custom config file path</td>
              <td className="py-3">./agent.config.yaml</td>
            </tr>
            <tr className="border-b border-border/30">
              <td className="py-3 pr-4 font-mono text-primary">AGENT_LOG_LEVEL</td>
              <td className="py-3 pr-4">Logging level</td>
              <td className="py-3">info</td>
            </tr>
            <tr>
              <td className="py-3 pr-4 font-mono text-primary">AGENT_A2A_ENABLED</td>
              <td className="py-3 pr-4">Enable A2A by default</td>
              <td className="py-3">false</td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  )
}
