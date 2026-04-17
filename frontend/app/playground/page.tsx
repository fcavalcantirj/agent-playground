"use client"

import { Footer } from "@/components/footer"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { PlaygroundForm } from "@/components/playground-form"

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
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
            Agent <span className="bg-gradient-to-r from-primary via-amber-400 to-primary bg-clip-text text-transparent">Playground</span>
          </h1>
          <p className="mt-4 max-w-3xl text-lg text-muted-foreground sm:text-xl">
            Pick any agent, pick any model, deploy in one click. Live container, real verdict, zero lock-in.
          </p>
        </div>

        <PlaygroundForm />
      </div>
      
      <Footer />
    </main>
  )
}
