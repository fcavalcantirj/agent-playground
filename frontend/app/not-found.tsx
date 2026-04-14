import Link from "next/link"
import { Button } from "@/components/ui/button"
import { ParticleBackground } from "@/components/particle-background"
import { Terminal, Home, ArrowLeft, Search } from "lucide-react"

export default function NotFound() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-background p-4">
      <ParticleBackground />
      
      <div className="relative z-10 max-w-md text-center">
        {/* Logo */}
        <Link href="/" className="mb-8 inline-flex items-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary">
            <Terminal className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="text-xl font-bold text-foreground">
            Agent<span className="text-primary">Playground</span>
          </span>
        </Link>

        {/* Error Display */}
        <div className="mb-8">
          <h1 className="mb-2 text-8xl font-bold text-primary">404</h1>
          <h2 className="mb-3 text-2xl font-semibold text-foreground">Page not found</h2>
          <p className="text-muted-foreground">
            The page you&apos;re looking for doesn&apos;t exist or has been moved.
          </p>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Button asChild className="gap-2 bg-primary text-primary-foreground">
            <Link href="/">
              <Home className="h-4 w-4" />
              Go Home
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/docs">
              <Search className="h-4 w-4" />
              Browse Docs
            </Link>
          </Button>
        </div>

        {/* Helpful Links */}
        <div className="mt-10 rounded-xl border border-border/50 bg-card/30 p-5 backdrop-blur-sm">
          <p className="mb-3 text-sm font-medium text-foreground">Looking for something?</p>
          <div className="flex flex-wrap justify-center gap-3 text-sm">
            <Link href="/playground" className="text-primary hover:underline">Playground</Link>
            <span className="text-border">|</span>
            <Link href="/dashboard" className="text-primary hover:underline">Dashboard</Link>
            <span className="text-border">|</span>
            <Link href="/pricing" className="text-primary hover:underline">Pricing</Link>
            <span className="text-border">|</span>
            <Link href="/contact" className="text-primary hover:underline">Contact</Link>
          </div>
        </div>
      </div>
    </main>
  )
}
