"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { AnimatedText, GlitchText } from "./animated-text"
import { ArrowRight, Play, Sparkles, Zap, Shield, Layers, Terminal } from "lucide-react"

export function HeroSection() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <section className="relative flex min-h-[100svh] items-center justify-center overflow-hidden pt-14 sm:pt-16">
      {/* Grid Pattern */}
      <div className="absolute inset-0 grid-pattern opacity-30" />

      {/* Gradient Orbs - Hidden on mobile for performance */}
      <div className="absolute -left-16 top-1/4 hidden h-64 w-64 animate-float rounded-full bg-primary/30 blur-[100px] sm:block sm:h-80 sm:w-80 lg:-left-32 lg:h-96 lg:w-96 lg:blur-[128px]" />
      <div className="absolute -right-16 bottom-1/4 hidden h-64 w-64 animate-float rounded-full bg-accent/20 blur-[100px] sm:block sm:h-80 sm:w-80 lg:-right-32 lg:h-96 lg:w-96 lg:blur-[128px]" style={{ animationDelay: "1.5s" }} />

      <div className="relative z-10 mx-auto w-full max-w-6xl px-4 py-12 text-center sm:px-6 sm:py-16 lg:px-8 lg:py-20">
        {/* Announcement Badge */}
        <div
          className={cn(
            "mb-6 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1.5 transition-all duration-700 sm:mb-8 sm:gap-2 sm:px-4 sm:py-2",
            mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
          )}
        >
          <Terminal className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
          <span className="text-xs text-primary sm:text-sm">Powered by ClawClones + OpenRouter</span>
          <ArrowRight className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
        </div>

        {/* Main Heading */}
        <h1
          className={cn(
            "mb-4 text-3xl font-bold tracking-tight transition-all delay-100 duration-700 sm:mb-6 sm:text-5xl md:text-6xl lg:text-7xl",
            mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
          )}
        >
          <span className="text-foreground">Deploy </span>
          <span className="glow-text text-primary">
            <AnimatedText words={["Hermes", "ZeroClaw", "OpenClaw", "NullClaw", "Moltis"]} />
          </span>
          <br className="sm:hidden" />
          <span className="text-foreground"> Agents</span>
          <br className="hidden sm:block" />
          <span className="text-foreground"> in </span>
          <GlitchText text="Seconds" className="text-foreground" />
        </h1>

        {/* Subheading */}
        <p
          className={cn(
            "mx-auto mb-8 max-w-xl text-base leading-relaxed text-muted-foreground text-balance transition-all delay-200 duration-700 sm:mb-10 sm:max-w-3xl sm:text-xl md:text-2xl",
            mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
          )}
        >
          Select any clone from the ClawVerse, pair with any OpenRouter model, 
          and launch N agents across Telegram, Discord, Slack, and more.
        </p>

        {/* CTA Buttons */}
        <div
          className={cn(
            "mb-12 flex flex-col items-center justify-center gap-3 transition-all delay-300 duration-700 sm:mb-16 sm:flex-row sm:gap-4",
            mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
          )}
        >
          <Button
            size="lg"
            className="glow-primary h-12 w-full bg-primary px-6 text-base text-primary-foreground hover:bg-primary/90 sm:h-14 sm:w-auto sm:px-8 sm:text-lg"
            asChild
          >
            <a href="#playground">
              Launch Playground
              <ArrowRight className="ml-2 h-4 w-4 sm:h-5 sm:w-5" />
            </a>
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="h-12 w-full border-border px-6 text-base hover:bg-muted/50 sm:h-14 sm:w-auto sm:px-8 sm:text-lg"
            asChild
          >
            <a href="https://clawclones.com/#clones" target="_blank" rel="noopener noreferrer">
              <Play className="mr-2 h-4 w-4 sm:h-5 sm:w-5" />
              Explore Clones
            </a>
          </Button>
        </div>

        {/* Stats */}
        <div
          className={cn(
            "mx-auto grid max-w-4xl grid-cols-2 gap-3 transition-all delay-400 duration-700 sm:gap-4 md:grid-cols-4 md:gap-6",
            mounted ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
          )}
        >
          <StatCard icon={<Layers className="h-4 w-4 sm:h-5 sm:w-5" />} value="43+" label="Active Clones" />
          <StatCard icon={<Sparkles className="h-4 w-4 sm:h-5 sm:w-5" />} value="200+" label="OpenRouter Models" />
          <StatCard icon={<Shield className="h-4 w-4 sm:h-5 sm:w-5" />} value="5" label="Sandbox Backends" />
          <StatCard icon={<Zap className="h-4 w-4 sm:h-5 sm:w-5" />} value="8" label="Channel Integrations" />
        </div>

        {/* Clone highlights */}
        <div
          className={cn(
            "mt-12 transition-all delay-500 duration-700 sm:mt-16 lg:mt-20",
            mounted ? "opacity-100" : "opacity-0"
          )}
        >
          <p className="mb-4 text-xs uppercase tracking-wider text-muted-foreground sm:mb-6 sm:text-sm">Top Clones by Pulse Score</p>
          <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-3 md:gap-4">
            {[
              { name: "Hermes-agent", pulse: "90%", lang: "Python" },
              { name: "ZeroClaw", pulse: "87%", lang: "Rust" },
              { name: "NullClaw", pulse: "88%", lang: "Zig" },
              { name: "nanobot", pulse: "85%", lang: "Python" },
            ].map((clone) => (
              <div 
                key={clone.name} 
                className="rounded-lg border border-border/50 bg-card/50 px-3 py-1.5 transition-colors hover:border-primary/50 sm:px-4 sm:py-2"
              >
                <span className="text-sm font-medium text-foreground sm:text-base">{clone.name}</span>
                <span className="ml-1.5 text-xs text-primary sm:ml-2">{clone.pulse}</span>
                <span className="ml-1.5 hidden text-xs text-muted-foreground sm:ml-2 sm:inline">{clone.lang}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Scroll Indicator - Hidden on mobile */}
      <div className="absolute bottom-6 left-1/2 hidden -translate-x-1/2 animate-bounce sm:bottom-8 sm:block">
        <div className="flex h-10 w-6 items-start justify-center rounded-full border-2 border-muted-foreground/30 p-1">
          <div className="h-3 w-1.5 animate-pulse rounded-full bg-primary" />
        </div>
      </div>
    </section>
  )
}

function StatCard({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div className="rounded-xl border border-border bg-card/30 p-3 backdrop-blur-sm transition-colors hover:border-primary/30 sm:p-4">
      <div className="mb-1 flex items-center justify-center gap-1.5 text-primary sm:mb-2 sm:gap-2">
        {icon}
        <span className="text-lg font-bold text-foreground sm:text-2xl">{value}</span>
      </div>
      <p className="text-xs text-muted-foreground sm:text-sm">{label}</p>
    </div>
  )
}
