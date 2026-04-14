"use client"

import { Check, Copy, Terminal, Package, Globe, Server } from "lucide-react"
import { useState } from "react"

function CodeBlock({ code, language = "bash" }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="group relative overflow-hidden rounded-lg border border-border/50 bg-muted/30">
      <div className="flex items-center justify-between border-b border-border/50 bg-muted/50 px-4 py-2">
        <span className="text-xs text-muted-foreground">{language}</span>
        <button
          onClick={copy}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied!" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm">
        <code className="text-muted-foreground">{code}</code>
      </pre>
    </div>
  )
}

const installMethods = [
  {
    title: "npm",
    icon: Package,
    code: "npm install -g @agentplayground/cli",
  },
  {
    title: "yarn",
    icon: Package,
    code: "yarn global add @agentplayground/cli",
  },
  {
    title: "pnpm",
    icon: Package,
    code: "pnpm add -g @agentplayground/cli",
  },
]

export default function InstallationPage() {
  return (
    <article className="max-w-3xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground sm:text-4xl">Installation</h1>
        <p className="mt-3 text-muted-foreground">
          Get Agent Playground up and running in your environment.
        </p>
      </div>

      {/* Prerequisites */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Prerequisites</h2>
        <div className="rounded-xl border border-border/50 bg-card/30 p-5">
          <ul className="space-y-3 text-sm text-muted-foreground">
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Node.js 18+</strong> - We recommend using the latest LTS version</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">OpenRouter API Key</strong> - Get one at openrouter.ai</span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <span><strong className="text-foreground">Git</strong> - For cloning agent templates</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Install CLI */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Install the CLI</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Choose your preferred package manager to install the Agent Playground CLI globally:
        </p>
        <div className="space-y-3">
          {installMethods.map((method) => (
            <div key={method.title}>
              <p className="mb-2 text-sm font-medium text-foreground">{method.title}</p>
              <CodeBlock code={method.code} />
            </div>
          ))}
        </div>
      </section>

      {/* Verify Installation */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Verify Installation</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          After installation, verify everything is working:
        </p>
        <CodeBlock code="agentplayground --version" />
        <p className="mt-3 text-sm text-muted-foreground">
          You should see the version number printed to your terminal.
        </p>
      </section>

      {/* Authentication */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Authentication</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Log in to your Agent Playground account:
        </p>
        <CodeBlock code="agentplayground login" />
        <p className="mt-3 text-sm text-muted-foreground">
          This will open a browser window for authentication. Once complete, you&apos;re ready to create and deploy agents.
        </p>
      </section>

      {/* Environment Setup */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Environment Setup</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          Configure your OpenRouter API key:
        </p>
        <CodeBlock 
          code={`# Add to your .bashrc, .zshrc, or .env file
export OPENROUTER_API_KEY="your-api-key-here"`}
          language="bash"
        />
        <p className="mt-3 text-sm text-muted-foreground">
          Alternatively, you can set it per-project in a <code className="rounded bg-muted px-1.5 py-0.5 text-xs">.env</code> file.
        </p>
      </section>

      {/* Installation Options */}
      <section className="mb-10">
        <h2 className="mb-4 text-xl font-semibold text-foreground">Installation Options</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Terminal className="mb-3 h-8 w-8 text-primary" />
            <h3 className="mb-1 font-semibold text-foreground">Local CLI</h3>
            <p className="text-xs text-muted-foreground">
              Run agents locally for development and testing.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Globe className="mb-3 h-8 w-8 text-primary" />
            <h3 className="mb-1 font-semibold text-foreground">Web Dashboard</h3>
            <p className="text-xs text-muted-foreground">
              Configure and deploy agents via the web interface.
            </p>
          </div>
          <div className="rounded-xl border border-border/50 bg-card/30 p-4">
            <Server className="mb-3 h-8 w-8 text-primary" />
            <h3 className="mb-1 font-semibold text-foreground">Self-Hosted</h3>
            <p className="text-xs text-muted-foreground">
              Deploy on your own infrastructure with Docker.
            </p>
          </div>
        </div>
      </section>

      {/* Next Steps */}
      <section>
        <h2 className="mb-4 text-xl font-semibold text-foreground">Next Steps</h2>
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-5">
          <p className="text-sm text-muted-foreground">
            Now that you have Agent Playground installed, check out the{" "}
            <a href="/docs/quickstart" className="font-medium text-primary hover:underline">
              Quick Start guide
            </a>{" "}
            to create your first agent.
          </p>
        </div>
      </section>
    </article>
  )
}
