"use client";

import { useEffect, useState } from "react";
import { Bot, Terminal } from "lucide-react";

import { apiGet, ApiError, type SessionUser } from "@/lib/api";
import { DevLoginForm } from "@/components/dev-login-form";
import { TopBar } from "@/components/top-bar";
import { EmptyState } from "@/components/empty-state";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: SessionUser };

/**
 * Phase 1 landing page — the only route in the app for Phase 1.
 *
 * Unauthenticated (Screen 1 from UI-SPEC):
 *   - "Agent Playground" Display heading (28px/600)
 *   - "Any agent. Any model. One click." tagline
 *   - "The easiest way to deploy any coding agent" mission line
 *   - Dev Login button (DevLoginForm)
 *   - "Development mode" badge with Terminal icon
 *
 * Authenticated (Screen 2 from UI-SPEC):
 *   - TopBar (product name + user + sign-out)
 *   - EmptyState (Bot icon + "No agents yet" + body)
 *   - Dev-mode footer hint
 *
 * Auth is checked client-side via GET /api/me:
 *   - 200 -> authenticated shell
 *   - 401 -> sign-in prompt
 *   - network error -> treat as anonymous (server probably not running)
 *
 * Note: this is a UX gate, not a security gate. The Go API is always the
 * authoritative source of truth for session state (Phase 1 threat register
 * T-1-10: accept).
 */
export default function Page() {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const user = await apiGet<SessionUser>("/api/me");
        if (!cancelled) {
          setAuth({ status: "authenticated", user });
        }
      } catch (err) {
        if (cancelled) return;
        // 401 -> anonymous; any other error (network, 500, etc.) also
        // falls through to anonymous so the user sees a login prompt.
        // DevLoginForm will surface a clearer error if they try to sign in.
        if (err instanceof ApiError && err.status !== 401) {
          // Non-401 API error: intentional fallthrough.
        }
        setAuth({ status: "anonymous" });
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  if (auth.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-40 animate-pulse rounded bg-muted" />
          <div className="h-4 w-56 animate-pulse rounded bg-muted" />
        </div>
      </main>
    );
  }

  if (auth.status === "authenticated") {
    return (
      <main className="flex min-h-screen flex-col bg-background">
        <TopBar user={auth.user} />
        <div className="flex flex-1 items-center justify-center px-4 py-16">
          <EmptyState
            icon={Bot}
            heading="No agents yet"
            body="Your coding agents will appear here. Agent setup arrives in a future update."
          />
        </div>
        <footer className="p-4 text-center text-sm text-muted-foreground">
          Phase 1 — Foundation shell
        </footer>
      </main>
    );
  }

  // Anonymous: Screen 1 sign-in prompt.
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="flex w-full max-w-[400px] flex-col items-center text-center">
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight text-foreground">
          Agent Playground
        </h1>
        <p className="mt-4 text-base leading-relaxed text-muted-foreground">
          Any agent. Any model. One click.
        </p>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          The easiest way to deploy any coding agent
        </p>

        <div className="mt-8 w-full">
          <DevLoginForm />
        </div>

        <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Terminal className="size-4" aria-hidden="true" />
          <span>Development mode</span>
        </div>
      </div>
    </main>
  );
}
