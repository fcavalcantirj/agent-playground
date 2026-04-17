"use client"

import { Footer } from "@/components/footer"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { PlaygroundForm } from "@/components/playground-form"

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
            Pick a fully-pinned dockerized agent, pick any of 345 OpenRouter models, paste your key, ship a real run. Verdicts come back with run id, exit code, wall time, and stderr.
          </p>

          <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border/60 bg-border/40 sm:grid-cols-4">
            <Stat label="Dockerized agents" value="5" sub="recipe-pinned, sha-locked" />
            <Stat label="OpenRouter models" value="345" sub="fetched live, no catalog" />
            <Stat label="Cold start" value="~1s" sub="picoclaw fastest path" />
            <Stat label="Lock-in" value="0%" sub="BYOK, run, throw away" />
          </dl>
        </div>

        <PlaygroundForm />
      </div>
      
      <Footer />
    </main>
  )
}
