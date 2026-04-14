"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { apiPost, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Dev-mode login button.
 *
 * POSTs to /api/dev/login (no body) — the Go API is responsible for
 * setting the ap_session cookie when AP_DEV_MODE=true. On success we
 * call router.refresh() so the root server component re-fetches
 * `/api/me` and the authenticated shell renders in place.
 *
 * Per UI-SPEC the button is:
 *  - full-width on mobile
 *  - min-h-[44px] (D-13 touch target)
 *  - emerald primary bg, white text
 *  - shows Loader2 spinner while pending
 *  - error copy exactly matches the UI-SPEC copywriting contract
 */
export function DevLoginForm({ className }: { className?: string }) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setError(null);
    try {
      await apiPost("/api/dev/login");
      // Refresh the server tree so the root page re-reads /api/me and
      // switches to the authenticated shell.
      startTransition(() => {
        router.refresh();
      });
    } catch (err) {
      // Network errors (TypeError) vs HTTP errors (ApiError).
      if (err instanceof ApiError) {
        setError("Login failed. Check the API server is running and try again.");
      } else {
        setError("Could not reach the server. Check your connection.");
      }
    }
  }

  const disabled = isPending;

  return (
    <div className={cn("flex w-full flex-col items-stretch gap-2", className)}>
      <button
        type="button"
        onClick={handleLogin}
        disabled={disabled}
        aria-busy={disabled}
        className={cn(
          // Layout: full-width, 44px touch target per D-13.
          "inline-flex w-full min-h-[44px] items-center justify-center gap-2 rounded-lg",
          // Color: emerald primary bg, white text.
          "bg-primary text-primary-foreground",
          // Typography: label weight.
          "text-sm font-medium",
          // Motion: smooth transitions that respect reduced-motion.
          "transition-[background-color,opacity,transform] duration-150",
          "hover:bg-primary/90 active:translate-y-px",
          // Focus visible ring, 2px offset per UI-SPEC accessibility.
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          // Disabled state.
          "disabled:cursor-not-allowed disabled:opacity-60",
        )}
      >
        {isPending ? (
          <>
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            <span className="sr-only">Signing in…</span>
            <span aria-hidden="true">Signing in…</span>
          </>
        ) : (
          <span>Dev Login</span>
        )}
      </button>
      {error ? (
        <p
          role="alert"
          className="text-sm text-destructive"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
