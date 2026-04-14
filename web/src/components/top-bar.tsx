"use client";

import { useState } from "react";
import { LogOut } from "lucide-react";

import { apiPost } from "@/lib/api";
import { cn } from "@/lib/utils";
import { UserAvatar } from "@/components/user-avatar";
import type { SessionUser } from "@/lib/api";

/**
 * Authenticated top bar.
 *
 * Per UI-SPEC Screen 2:
 *  - 56px total height (44px content + vertical padding)
 *  - Background: card color
 *  - Left: "Agent Playground" heading (text-xl font-semibold)
 *  - Right: user display name (md+ only), UserAvatar (32px),
 *    sign-out icon button (LogOut, 44px touch target, aria-label="Sign out")
 *  - Sign-out: icon-only on mobile, "Sign out" text + icon on desktop
 *  - Sign-out action: POST /api/dev/logout then call onSignOut so the
 *    parent client component re-checks /api/me and swaps screens.
 */
export function TopBar({
  user,
  onSignOut,
}: {
  user: SessionUser;
  onSignOut: () => void | Promise<void>;
}) {
  const [isPending, setIsPending] = useState(false);

  async function handleSignOut() {
    setIsPending(true);
    try {
      await apiPost("/api/dev/logout");
    } catch {
      // Swallow: even if the server rejects, the parent's auth re-check
      // is the source of truth — the user will see the unauthenticated
      // state if the session was in fact cleared on the server side.
    }
    try {
      await onSignOut();
    } finally {
      setIsPending(false);
    }
  }

  return (
    <header
      className={cn(
        "sticky top-0 z-10 flex h-14 w-full items-center justify-between gap-3 border-b border-border bg-card px-4",
      )}
    >
      <h1 className="text-xl font-semibold tracking-tight text-foreground">
        Agent Playground
      </h1>

      <div className="flex items-center gap-3">
        <span className="hidden text-sm text-muted-foreground md:inline">
          {user.display_name}
        </span>
        <UserAvatar
          displayName={user.display_name}
          avatarUrl={user.avatar_url}
        />
        <button
          type="button"
          onClick={handleSignOut}
          disabled={isPending}
          aria-label="Sign out"
          className={cn(
            "inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-2 rounded-lg",
            "bg-transparent px-3 text-sm font-medium text-muted-foreground",
            "transition-colors duration-150",
            "hover:bg-muted hover:text-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
            "disabled:cursor-not-allowed disabled:opacity-60",
          )}
        >
          <LogOut className="size-4" aria-hidden="true" />
          <span className="hidden md:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
