"use client"

import { 
  MessageSquare, 
  Send, 
  Hash, 
  MessageCircle, 
  Mail, 
  Terminal, 
  Webhook,
  Check,
  ExternalLink
} from "lucide-react"
import Link from "next/link"

const channels = [
  {
    name: "Telegram",
    icon: Send,
    description: "Connect your agent to Telegram for personal or group chats.",
    features: ["Personal chats", "Group conversations", "Inline queries", "Commands"],
    setup: "Create a bot via @BotFather and add the token to your agent config.",
    color: "bg-blue-500/20 text-blue-400",
  },
  {
    name: "Discord",
    icon: Hash,
    description: "Deploy agents to Discord servers with full slash command support.",
    features: ["Slash commands", "Channel responses", "Thread support", "Reactions"],
    setup: "Create a Discord application and add the bot token to your configuration.",
    color: "bg-indigo-500/20 text-indigo-400",
  },
  {
    name: "Slack",
    icon: MessageSquare,
    description: "Integrate agents into your Slack workspace for team collaboration.",
    features: ["Direct messages", "Channel mentions", "Threads", "App home"],
    setup: "Create a Slack app with Bot Token Scopes and install to your workspace.",
    color: "bg-purple-500/20 text-purple-400",
  },
  {
    name: "WhatsApp",
    icon: MessageCircle,
    description: "Connect agents to WhatsApp Business API for customer support.",
    features: ["Text messages", "Media support", "Templates", "Quick replies"],
    setup: "Configure via Meta Business Suite with WhatsApp Business API access.",
    color: "bg-green-500/20 text-green-400",
  },
  {
    name: "Email",
    icon: Mail,
    description: "Let agents handle email conversations automatically.",
    features: ["Inbox monitoring", "Auto-replies", "Attachments", "Threading"],
    setup: "Connect via IMAP/SMTP or integrate with email providers like SendGrid.",
    color: "bg-red-500/20 text-red-400",
  },
  {
    name: "CLI",
    icon: Terminal,
    description: "Run agents locally in your terminal for development and testing.",
    features: ["Interactive mode", "Piped input", "JSON output", "Debug logging"],
    setup: "Use `agentplayground run` to start an interactive CLI session.",
    color: "bg-slate-500/20 text-slate-400",
  },
  {
    name: "Webhook",
    icon: Webhook,
    description: "Generic HTTP webhook for custom integrations.",
    features: ["REST API", "Custom payloads", "Authentication", "Async responses"],
    setup: "Configure a webhook URL and authentication method in your agent settings.",
    color: "bg-orange-500/20 text-orange-400",
  },
]

export default function ChannelsPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Channels</h1>
        <p className="mt-3 text-muted-foreground">
          Configure where your agents communicate with users.
        </p>
      </div>

      {/* Overview */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Multi-Channel Support</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Each agent can be connected to multiple channels simultaneously. Messages from all channels 
          are processed by the same agent instance, maintaining context and memory across platforms.
        </p>
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-4">
          <div className="flex items-start gap-3">
            <Check className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <p className="text-sm text-muted-foreground">
              <strong className="text-foreground">Unified Experience:</strong> Your agent behaves consistently 
              across all channels while adapting to platform-specific features.
            </p>
          </div>
        </div>
      </section>

      {/* Available Channels */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Available Channels</h2>
        <div className="space-y-4">
          {channels.map((channel) => (
            <div
              key={channel.name}
              className="rounded-xl border border-border/50 bg-card/30 p-4 sm:p-5"
            >
              <div className="mb-3 flex items-center gap-3">
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${channel.color}`}>
                  <channel.icon className="h-5 w-5" />
                </div>
                <h3 className="text-lg font-semibold text-foreground">{channel.name}</h3>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">{channel.description}</p>
              
              <div className="mb-3 flex flex-wrap gap-1.5">
                {channel.features.map((feature) => (
                  <span
                    key={feature}
                    className="rounded bg-muted/50 px-2 py-0.5 text-[10px] text-muted-foreground"
                  >
                    {feature}
                  </span>
                ))}
              </div>

              <div className="rounded-lg bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">
                  <strong className="text-foreground">Setup:</strong> {channel.setup}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Channel Configuration */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Configuration Example</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Add channels to your agent configuration file:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
          <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
            <span className="text-xs text-muted-foreground">agent.config.json</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm">
            <code className="text-muted-foreground">{`{
  "name": "my-agent",
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "$TELEGRAM_BOT_TOKEN"
    },
    "discord": {
      "enabled": true,
      "token": "$DISCORD_BOT_TOKEN",
      "guildId": "123456789"
    },
    "webhook": {
      "enabled": true,
      "path": "/api/agent",
      "auth": "bearer"
    }
  }
}`}</code>
          </pre>
        </div>
      </section>

      {/* Best Practices */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Best Practices</h2>
        <div className="space-y-3">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Use Environment Variables</h3>
            <p className="text-xs text-muted-foreground">
              Never hardcode API tokens. Use environment variables for all sensitive credentials.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Start with One Channel</h3>
            <p className="text-xs text-muted-foreground">
              Test your agent thoroughly on one channel before expanding to multiple platforms.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Handle Rate Limits</h3>
            <p className="text-xs text-muted-foreground">
              Each platform has different rate limits. Agent Playground handles these automatically.
            </p>
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Next Steps</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            href="/docs/a2a"
            className="flex-1 rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <h3 className="font-medium text-foreground">A2A Protocol</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Enable agent-to-agent communication
            </p>
          </Link>
          <Link
            href="/docs/config"
            className="flex-1 rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <h3 className="font-medium text-foreground">Configuration</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Advanced configuration options
            </p>
          </Link>
        </div>
      </section>
    </article>
  )
}
