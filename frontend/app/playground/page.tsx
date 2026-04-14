"use client"

import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { AgentConfigurator } from "@/components/agent-configurator"
import { Footer } from "@/components/footer"

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
        <div className="mb-8 sm:mb-12">
          <h1 className="text-2xl font-bold text-foreground sm:text-3xl lg:text-4xl">
            Agent <span className="text-primary">Playground</span>
          </h1>
          <p className="mt-2 text-sm text-muted-foreground sm:text-base">
            Configure, deploy, and manage your autonomous agents with any model from OpenRouter.
          </p>
        </div>
        
        <AgentConfigurator />
      </div>
      
      <Footer />
    </main>
  )
}
