"use client"

import { Shield, Lock, Key, Eye, AlertTriangle, Check, Server, RefreshCw } from "lucide-react"
import Link from "next/link"

const securityFeatures = [
  {
    icon: Lock,
    title: "End-to-End Encryption",
    description: "All communication between agents, channels, and our infrastructure is encrypted using TLS 1.3.",
  },
  {
    icon: Key,
    title: "API Key Security",
    description: "API keys are hashed and never stored in plain text. Keys can be rotated instantly.",
  },
  {
    icon: Eye,
    title: "Audit Logging",
    description: "Comprehensive logs of all agent activities for compliance and debugging.",
  },
  {
    icon: Server,
    title: "Process Isolation",
    description: "Each agent runs in an isolated container with restricted system access.",
  },
]

const bestPractices = [
  {
    title: "Never commit secrets to version control",
    description: "Use environment variables or secret management tools for API keys and tokens.",
    severity: "critical",
  },
  {
    title: "Rotate API keys regularly",
    description: "Generate new API keys periodically and revoke old ones promptly.",
    severity: "high",
  },
  {
    title: "Use principle of least privilege",
    description: "Grant agents only the minimum permissions needed for their function.",
    severity: "high",
  },
  {
    title: "Enable two-factor authentication",
    description: "Protect your Agent Playground account with 2FA for an extra layer of security.",
    severity: "high",
  },
  {
    title: "Monitor agent activity",
    description: "Regularly review logs and analytics to detect unusual behavior.",
    severity: "medium",
  },
  {
    title: "Keep dependencies updated",
    description: "Regularly update your agent clones to get the latest security patches.",
    severity: "medium",
  },
]

const severityColors = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  medium: "bg-blue-500/20 text-blue-400 border-blue-500/30",
}

export default function SecurityPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Security</h1>
        <p className="mt-3 text-muted-foreground">
          Learn about Agent Playground security features and best practices.
        </p>
      </div>

      {/* Security Overview */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Security Overview</h2>
        <div className="rounded-xl border border-green-500/30 bg-green-500/5 p-5">
          <div className="flex items-start gap-3">
            <Shield className="mt-0.5 h-6 w-6 shrink-0 text-green-500" />
            <div>
              <h3 className="font-medium text-foreground">Built with Security First</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Agent Playground is designed with security at its core. We implement industry-standard 
                security practices and undergo regular security audits.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Security Features */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Security Features</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {securityFeatures.map((feature) => (
            <div key={feature.title} className="rounded-xl border border-border/50 bg-card/30 p-4">
              <feature.icon className="mb-2 h-5 w-5 text-primary" />
              <h3 className="font-medium text-foreground">{feature.title}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{feature.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Authentication */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Authentication</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Agent Playground uses multiple layers of authentication:
        </p>
        <div className="space-y-3">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">User Authentication</h3>
            <p className="text-xs text-muted-foreground">
              OAuth 2.0 via GitHub or Google, plus optional 2FA with TOTP authenticator apps.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">API Authentication</h3>
            <p className="text-xs text-muted-foreground">
              Bearer token authentication with scoped API keys for programmatic access.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">A2A Authentication</h3>
            <p className="text-xs text-muted-foreground">
              Ed25519 digital signatures for agent-to-agent communication verification.
            </p>
          </div>
        </div>
      </section>

      {/* Data Protection */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Data Protection</h2>
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <ul className="space-y-3 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Data at Rest:</strong> AES-256 encryption for all stored data</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Data in Transit:</strong> TLS 1.3 for all network communication</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Data Retention:</strong> Configurable retention policies per agent</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Data Deletion:</strong> Complete data purge available on request</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Best Practices */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Security Best Practices</h2>
        <div className="space-y-3">
          {bestPractices.map((practice) => (
            <div
              key={practice.title}
              className={`rounded-lg border p-4 ${severityColors[practice.severity as keyof typeof severityColors]}`}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-medium text-foreground">{practice.title}</h3>
                <span className="shrink-0 rounded px-2 py-0.5 text-[10px] font-medium uppercase">
                  {practice.severity}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{practice.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* API Key Rotation */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">API Key Rotation</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Rotate your API keys via CLI without downtime:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
          <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
            <span className="text-xs text-muted-foreground">bash</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm">
            <code className="text-muted-foreground">{`# Generate a new API key
agentplayground keys rotate --name "production"

# The old key remains valid for 24 hours
# Update your environment, then revoke the old key
agentplayground keys revoke <old-key-id>`}</code>
          </pre>
        </div>
      </section>

      {/* Reporting */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Security Reporting</h2>
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/5 p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-yellow-500" />
            <div>
              <h3 className="font-medium text-foreground">Found a Vulnerability?</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                We appreciate responsible disclosure. Please report security vulnerabilities to{" "}
                <a href="mailto:security@agentplayground.dev" className="text-primary hover:underline">
                  security@agentplayground.dev
                </a>
                . We aim to respond within 24 hours.
              </p>
            </div>
          </div>
        </div>
      </section>
    </article>
  )
}
