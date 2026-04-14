"use client"

import { AgentConfigurator } from "./agent-configurator"
import { Sparkles, Terminal, ExternalLink } from "lucide-react"

export function PlaygroundSection() {
  return (
    <section className="relative overflow-hidden py-16 sm:py-24 lg:py-32" id="playground">
      {/* Background */}
      <div className="absolute inset-0 grid-pattern opacity-20" />
      
      {/* Gradient accents */}
      <div className="absolute left-1/4 top-0 hidden h-64 w-64 rounded-full bg-primary/10 blur-[100px] sm:block sm:h-80 sm:w-80 lg:h-96 lg:w-96 lg:blur-[128px]" />
      <div className="absolute bottom-0 right-1/4 hidden h-64 w-64 rounded-full bg-accent/10 blur-[100px] sm:block sm:h-80 sm:w-80 lg:h-96 lg:w-96 lg:blur-[128px]" />

      <div className="relative z-10 mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="mb-8 text-center sm:mb-12">
          <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 sm:mb-4 sm:gap-2">
            <Sparkles className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
            <span className="text-xs text-primary sm:text-sm">Agent Playground</span>
          </div>
          <h2 className="mb-3 text-2xl font-bold text-foreground text-balance sm:mb-4 sm:text-4xl md:text-5xl">
            Deploy <span className="text-primary">N Agents</span> with Any Combination
          </h2>
          <p className="mx-auto max-w-xl text-base text-muted-foreground text-pretty sm:max-w-3xl sm:text-lg md:text-xl">
            Select from the ClawVerse ecosystem, pair with any OpenRouter model, 
            and deploy multiple agent instances across channels in seconds.
          </p>
          
          {/* Links to source projects */}
          <div className="mt-4 flex flex-wrap items-center justify-center gap-3 sm:mt-6 sm:gap-6">
            <a 
              href="https://clawclones.com/#clones" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-primary sm:gap-2 sm:text-sm"
            >
              <Terminal className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              ClawClones.com
              <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            </a>
            <a 
              href="https://hermes-agent.nousresearch.com/" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-primary sm:gap-2 sm:text-sm"
            >
              <Terminal className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              Hermes Agent
              <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            </a>
            <a 
              href="https://openrouter.ai/models" 
              target="_blank" 
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-primary sm:gap-2 sm:text-sm"
            >
              <Sparkles className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
              OpenRouter Models
              <ExternalLink className="h-2.5 w-2.5 sm:h-3 sm:w-3" />
            </a>
          </div>
        </div>

        {/* Main Configurator */}
        <div className="rounded-xl border border-border/50 bg-card/30 p-4 backdrop-blur-sm sm:rounded-2xl sm:p-6 lg:p-8">
          <AgentConfigurator />
        </div>

        {/* Install Command */}
        <div className="mx-auto mt-6 max-w-2xl sm:mt-8">
          <div className="rounded-xl border border-border/50 bg-card/50 p-3 backdrop-blur-sm sm:p-4">
            <div className="mb-2 flex items-center gap-2">
              <Terminal className="h-3.5 w-3.5 text-primary sm:h-4 sm:w-4" />
              <span className="text-xs text-muted-foreground sm:text-sm">Quick Install (Hermes Agent)</span>
            </div>
            <div className="overflow-x-auto rounded-lg bg-background/50 p-2.5 font-mono text-xs text-foreground sm:p-3 sm:text-sm">
              <span className="text-muted-foreground">$</span>{" "}
              <span className="text-green-400">curl</span>{" "}
              <span className="text-amber-400">-fsSL</span>{" "}
              <span className="break-all text-blue-400">https://hermes-agent.nousresearch.com/install.sh</span>{" "}
              <span className="text-muted-foreground">|</span>{" "}
              <span className="text-green-400">bash</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
