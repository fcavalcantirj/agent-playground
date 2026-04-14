"use client"

import { useState } from "react"
import { Navbar } from "@/components/navbar"
import { ParticleBackground } from "@/components/particle-background"
import { HeroSection } from "@/components/hero-section"
import { FeaturesSection } from "@/components/features-section"
import { PlaygroundSection } from "@/components/playground-section"
import { CTASection } from "@/components/cta-section"
import { Footer } from "@/components/footer"

export default function Home() {
  const [isLoggedIn] = useState(true)

  return (
    <main className="relative min-h-screen bg-background overflow-x-hidden">
      {/* Animated Particle Background */}
      <ParticleBackground />

      {/* Navigation */}
      <Navbar
        isLoggedIn={isLoggedIn}
        user={{
          name: "Alex Chen",
          email: "alex@example.com",
        }}
      />

      {/* Hero Section */}
      <HeroSection />

      {/* Features Section */}
      <FeaturesSection />

      {/* Interactive Playground */}
      <PlaygroundSection />

      {/* CTA Section */}
      <CTASection />

      {/* Footer */}
      <Footer />
    </main>
  )
}
