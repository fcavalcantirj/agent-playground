"use client"

import { useRef, useState } from "react"

import { Footer } from "@/components/footer"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { PlaygroundForm } from "@/components/playground-form"
import { MyAgentsPanel, type MyAgentsPanelHandle } from "@/components/my-agents-panel"

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="bg-card/60 p-5 backdrop-blur-sm">
      <dt className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</dt>
      <dd className="mt-1.5 text-3xl font-bold tabular-nums text-foreground">{value}</dd>
      <dd className="mt-0.5 text-xs text-muted-foreground/80">{sub}</dd>
    </div>
  )
}

export default function PlaygroundPage() {
  const agentsRef = useRef<MyAgentsPanelHandle | null>(null)
  const [highlightAgentId, setHighlightAgentId] = useState<string | null>(null)

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-background">
      <ParticleBackground />
      <Navbar
        isLoggedIn={true}
        user={{
          name: "Alex Chen",
          email: "alex@example.com",
        }}
      />

      <div className="relative z-10 mx-auto max-w-7xl px-4 pb-16 pt-24 sm:px-6 sm:pb-20 sm:pt-28 lg:px-8">
        <div className="mb-10 sm:mb-14">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 font-mono text-xs uppercase tracking-widest text-primary backdrop-blur-sm">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            Live API · per-session container
          </div>
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            Any agent. Any model.{" "}
            <span className="bg-gradient-to-r from-primary via-amber-400 to-primary bg-clip-text text-transparent">
              One click.
            </span>
          </h1>
          <p className="mt-4 max-w-3xl text-lg text-muted-foreground sm:text-xl">
            Deploy a configured agent — pick a recipe, a model, give it a name and a personality, paste your OpenRouter key. Use it later from your agents list.
          </p>

          <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/40 sm:grid-cols-4">
            <Stat label="Dockerized agents" value="5" sub="recipe-pinned, sha-locked" />
            <Stat label="OpenRouter models" value="345" sub="fetched live, no catalog" />
            <Stat label="Cold start" value="~1s" sub="picoclaw fastest path" />
            <Stat label="Lock-in" value="0%" sub="BYOK, run, throw away" />
          </dl>
        </div>

        {/* My Agents — always visible on top, even when empty */}
        <section className="mb-14">
          <MyAgentsPanel ref={agentsRef} highlightAgentId={highlightAgentId} />
        </section>

        {/* Deploy a new agent */}
        <section>
          <div className="mb-6 flex items-baseline justify-between gap-3 border-t border-border/40 pt-10">
            <h2 className="text-2xl font-bold text-foreground sm:text-3xl">
              Deploy a <span className="text-primary">new agent</span>
            </h2>
            <p className="hidden text-sm text-muted-foreground sm:block">
              4 steps · ~10s for a smoke verdict
            </p>
          </div>

          <PlaygroundForm
            onDeployed={(verdict) => {
              setHighlightAgentId(verdict.agent_instance_id)
              agentsRef.current?.refetch()
              setTimeout(() => setHighlightAgentId(null), 6000)
            }}
          />
        </section>
      </div>

      <Footer />
    </main>
  )
}
