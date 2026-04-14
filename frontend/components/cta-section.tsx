"use client"

import { Button } from "@/components/ui/button"
import { ArrowRight, Sparkles, Terminal, Github, ExternalLink } from "lucide-react"

export function CTASection() {
  return (
    <section className="relative overflow-hidden py-16 sm:py-24 lg:py-32">
      {/* Background */}
      <div className="absolute inset-0 grid-pattern opacity-20" />
      <div className="absolute left-1/2 top-1/2 h-[400px] w-[400px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-[100px] sm:h-[600px] sm:w-[600px] sm:blur-[128px]" />

      <div className="relative z-10 mx-auto max-w-5xl px-4 text-center sm:px-6 lg:px-8">
        {/* Install Command Preview */}
        <div className="mx-auto mb-8 max-w-2xl overflow-hidden rounded-xl border border-border bg-card/30 backdrop-blur-sm sm:mb-12 sm:rounded-2xl">
          <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-2.5 sm:px-4 sm:py-3">
            <div className="flex gap-1.5">
              <div className="h-2.5 w-2.5 rounded-full bg-red-500/80 sm:h-3 sm:w-3" />
              <div className="h-2.5 w-2.5 rounded-full bg-amber-500/80 sm:h-3 sm:w-3" />
              <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/80 sm:h-3 sm:w-3" />
            </div>
            <span className="ml-2 font-mono text-[10px] text-muted-foreground sm:text-xs">terminal</span>
          </div>
          <div className="space-y-2 p-4 text-left font-mono text-xs sm:space-y-3 sm:p-6 sm:text-sm">
            <div className="text-muted-foreground"># Install Hermes Agent</div>
            <div className="flex flex-wrap">
              <span className="text-muted-foreground">$</span>
              <span className="text-green-400">{" curl"}</span>
              <span className="text-amber-400">{" -fsSL"}</span>
              <span className="break-all text-blue-400">{" https://hermes-agent.nousresearch.com/install.sh"}</span>
              <span className="text-muted-foreground">{" |"}</span>
              <span className="text-green-400">{" bash"}</span>
            </div>
            <div className="pt-2 text-muted-foreground sm:pt-0"># Configure with OpenRouter</div>
            <div>
              <span className="text-muted-foreground">$</span>
              <span className="text-green-400">{" hermes"}</span>
              <span className="text-foreground">{" setup"}</span>
              <span className="text-amber-400">{" --provider"}</span>
              <span className="text-emerald-400">{" openrouter"}</span>
            </div>
            <div className="pt-2 text-muted-foreground sm:pt-0"># Launch your agent</div>
            <div>
              <span className="text-muted-foreground">$</span>
              <span className="text-green-400">{" hermes"}</span>
              <span className="text-foreground">{" start"}</span>
              <span className="hidden text-emerald-400 sm:inline">{" # That's it!"}</span>
            </div>
          </div>
        </div>

        {/* CTA Content */}
        <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 sm:mb-6 sm:gap-2">
          <Sparkles className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
          <span className="text-xs text-primary sm:text-sm">Open Source - MIT Licensed</span>
        </div>

        <h2 className="mb-4 text-2xl font-bold text-foreground text-balance sm:mb-6 sm:text-4xl md:text-5xl lg:text-6xl">
          Ready to Deploy Your <span className="glow-text text-primary">Agent Army</span>?
        </h2>

        <p className="mx-auto mb-8 max-w-xl text-base leading-relaxed text-muted-foreground text-pretty sm:mb-10 sm:max-w-2xl sm:text-lg md:text-xl">
          Pick any clone from the ClawVerse, pair it with any OpenRouter model, 
          and deploy N agents across all your channels. No vendor lock-in.
        </p>

        <div className="flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-4">
          <Button
            size="lg"
            className="glow-primary h-12 w-full bg-primary px-6 text-base text-primary-foreground hover:bg-primary/90 sm:h-14 sm:w-auto sm:px-8 sm:text-lg"
            asChild
          >
            <a href="#playground">
              <Terminal className="mr-2 h-4 w-4 sm:h-5 sm:w-5" />
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
            <a href="https://github.com" target="_blank" rel="noopener noreferrer">
              <Github className="mr-2 h-4 w-4 sm:h-5 sm:w-5" />
              View on GitHub
              <ExternalLink className="ml-2 h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </a>
          </Button>
        </div>

        {/* Trust Indicators */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4 text-xs text-muted-foreground sm:mt-12 sm:gap-6 sm:text-sm">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            43+ Active Clones
          </div>
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            200+ OpenRouter Models
          </div>
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            8 Channel Integrations
          </div>
        </div>
      </div>
    </section>
  )
}
