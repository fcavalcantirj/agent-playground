"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ParticleBackground } from "@/components/particle-background"
import { Terminal, Github, Mail, Lock, ArrowRight, Eye, EyeOff } from "lucide-react"

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)

  // Surface backend OAuth error codes as toast notifications. Codes are
  // handled as exact-string matches (D-22c-FE-03) — any unmapped value is
  // silently ignored to avoid reflecting attacker-controlled strings into
  // the UI (T-22c-25 in this plan's threat model).
  useEffect(() => {
    const err = new URLSearchParams(window.location.search).get("error")
    if (err === "access_denied") toast.error("Sign-in cancelled")
    else if (err === "state_mismatch") toast.error("Security check failed — try again")
    else if (err === "oauth_failed") toast.error("Sign-in failed — try again")
  }, [])

  // OAuth requires a top-level page navigation so the browser can follow
  // the 302 chain into Google/GitHub and back. fetch() cannot do this.
  const onGoogle = () => {
    window.location.href = "/api/v1/auth/google"
  }
  const onGitHub = () => {
    window.location.href = "/api/v1/auth/github"
  }

  // Email/password sign-in is not implemented in v1 — the form is kept
  // visually present but every input is disabled and submit is a no-op
  // (D-22c-UI-01). Users are steered to the OAuth buttons above.
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-background p-4">
      <ParticleBackground />

      <div className="relative z-10 w-full max-w-md">
        {/* Logo */}
        <Link href="/" className="mb-8 flex items-center justify-center gap-2">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary">
            <Terminal className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="text-xl font-bold text-foreground">
            Agent<span className="text-primary">Playground</span>
          </span>
        </Link>

        {/* Login Card */}
        <div className="rounded-2xl border border-border/50 bg-card/50 p-6 backdrop-blur-xl sm:p-8">
          <div className="mb-6 text-center">
            <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Sign in to manage your agents
            </p>
          </div>

          {/* OAuth Buttons */}
          <div className="mb-6 grid gap-3">
            <Button
              type="button"
              variant="outline"
              className="h-11 w-full gap-2"
              onClick={onGitHub}
            >
              <Github className="h-4 w-4" />
              Continue with GitHub
            </Button>
            <Button
              type="button"
              variant="outline"
              className="h-11 w-full gap-2"
              onClick={onGoogle}
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24">
                <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              Continue with Google
            </Button>
          </div>

          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border/50" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-card/50 px-2 text-muted-foreground">or continue with email</span>
            </div>
          </div>

          {/* Login Form — email/password not wired in v1; use Google or GitHub above. */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm text-muted-foreground">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="email"
                  placeholder="you@example.com"
                  className="h-11 bg-background/50 pl-10"
                  disabled
                />
              </div>
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-sm text-muted-foreground">Password</label>
              </div>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  className="h-11 bg-background/50 pl-10 pr-10"
                  disabled
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  disabled
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Use Google or GitHub above for now.
              </p>
            </div>

            <Button
              type="submit"
              className="h-11 w-full gap-2 bg-primary text-primary-foreground hover:bg-primary/90"
              disabled
            >
              Sign in
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          <p className="mt-6 text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{" "}
            <Link href="/signup" className="font-medium text-primary hover:underline">
              Sign up
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-muted-foreground">
          By continuing, you agree to our{" "}
          <Link href="/terms" className="hover:underline">Terms of Service</Link>
          {" "}and{" "}
          <Link href="/privacy" className="hover:underline">Privacy Policy</Link>
        </p>
      </div>
    </main>
  )
}
