"use client"

import { Network, ArrowRight, Shield, Zap, MessageSquare, Code2 } from "lucide-react"
import Link from "next/link"

export default function A2APage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">A2A Protocol</h1>
        <p className="mt-3 text-muted-foreground">
          Enable your agents to communicate and collaborate with each other.
        </p>
      </div>

      {/* What is A2A */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">What is A2A?</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          The Agent-to-Agent (A2A) Protocol is a standardized communication layer that allows 
          autonomous agents to discover, authenticate, and interact with each other. Think of it 
          as a universal language that lets any compatible agent work together.
        </p>
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-5">
          <div className="flex items-start gap-3">
            <Network className="mt-0.5 h-6 w-6 shrink-0 text-primary" />
            <div>
              <h3 className="font-medium text-foreground">Interoperable by Design</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                A2A is an open protocol. Agents built with different frameworks can communicate 
                seamlessly as long as they implement the A2A specification.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Key Features */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Key Features</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Shield className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Secure Authentication</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Agents authenticate using cryptographic keys, ensuring only authorized communication.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Zap className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Capability Discovery</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Agents can advertise and discover capabilities dynamically at runtime.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <MessageSquare className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Structured Messages</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Standardized message formats enable clear, unambiguous communication.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Code2 className="mb-2 h-5 w-5 text-primary" />
            <h3 className="font-medium text-foreground">Task Delegation</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              Agents can request help from specialized agents to complete complex tasks.
            </p>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">How It Works</h2>
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <div className="space-y-6">
            <div className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                1
              </div>
              <div>
                <h3 className="font-medium text-foreground">Discovery</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Agents register their capabilities with an A2A registry. Other agents can query 
                  the registry to find agents with specific skills.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                2
              </div>
              <div>
                <h3 className="font-medium text-foreground">Authentication</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Before communicating, agents verify each other&apos;s identity using public key 
                  cryptography and capability tokens.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                3
              </div>
              <div>
                <h3 className="font-medium text-foreground">Communication</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Agents exchange structured messages containing requests, responses, and context. 
                  All communication is encrypted end-to-end.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-bold text-primary-foreground">
                4
              </div>
              <div>
                <h3 className="font-medium text-foreground">Execution</h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  The receiving agent processes the request and returns results. Complex tasks 
                  can involve chains of agent collaboration.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Example */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Example: Agent Collaboration</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Here&apos;s how a customer support agent might delegate to a specialized billing agent:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
          <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
            <span className="text-xs text-muted-foreground">A2A Message Flow</span>
          </div>
          <pre className="overflow-x-auto p-4 text-xs">
            <code className="text-muted-foreground">{`// Support Agent sends request to Billing Agent
{
  "type": "a2a.request",
  "from": "agent://support-bot.acme.com",
  "to": "agent://billing.acme.com",
  "capability": "invoice.lookup",
  "params": {
    "customerId": "cust_123",
    "dateRange": "last-30-days"
  },
  "context": {
    "conversationId": "conv_abc",
    "priority": "high"
  }
}

// Billing Agent responds
{
  "type": "a2a.response",
  "requestId": "req_xyz",
  "status": "success",
  "data": {
    "invoices": [
      { "id": "inv_001", "amount": 299.00, "status": "paid" },
      { "id": "inv_002", "amount": 299.00, "status": "pending" }
    ]
  }
}`}</code>
          </pre>
        </div>
      </section>

      {/* Enabling A2A */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Enabling A2A</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Enable A2A support in your agent configuration:
        </p>
        <div className="overflow-hidden rounded-xl border border-border/50 bg-muted/30">
          <div className="border-b border-border/50 bg-muted/50 px-4 py-2">
            <span className="text-xs text-muted-foreground">agent.config.json</span>
          </div>
          <pre className="overflow-x-auto p-4 text-sm">
            <code className="text-muted-foreground">{`{
  "a2a": {
    "enabled": true,
    "registry": "https://registry.agentplayground.dev",
    "capabilities": [
      "customer.support",
      "ticket.create",
      "knowledge.search"
    ],
    "allowedAgents": ["*@acme.com"]
  }
}`}</code>
          </pre>
        </div>
      </section>

      {/* Use Cases */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Use Cases</h2>
        <div className="space-y-3">
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Multi-Agent Workflows</h3>
            <p className="text-xs text-muted-foreground">
              Chain multiple specialized agents to handle complex business processes automatically.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Cross-Organization Collaboration</h3>
            <p className="text-xs text-muted-foreground">
              Agents from different companies can work together while respecting security boundaries.
            </p>
          </div>
          <div className="rounded-lg border border-border/50 bg-card/30 p-4">
            <h3 className="mb-1 font-medium text-foreground">Skill Augmentation</h3>
            <p className="text-xs text-muted-foreground">
              General-purpose agents can call specialized agents for tasks requiring expertise.
            </p>
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Learn More</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Link
            href="/docs/security"
            className="flex-1 rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <h3 className="font-medium text-foreground">Security</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              A2A security best practices
            </p>
          </Link>
          <a
            href="https://a2aprotocol.org"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-1 items-center justify-between rounded-xl border border-border/50 bg-card/30 p-4 transition-colors hover:border-primary/30"
          >
            <div>
              <h3 className="font-medium text-foreground">A2A Specification</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Full protocol documentation
              </p>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
          </a>
        </div>
      </section>
    </article>
  )
}
