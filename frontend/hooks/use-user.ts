"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { apiGet, ApiError, type SessionUser } from "@/lib/api";

/**
 * useUser — fetches /api/v1/users/me on mount; on HTTP 401 redirects the
 * user to /login. The hook returns `null` until the first fetch resolves
 * so consumers can eager-render while the navbar user slot shows a
 * skeleton (per D-22c-FE-02).
 *
 * Failure modes:
 *  - 401: redirect to /login (session invalid)
 *  - Network error / 5xx: keep user as null; consumer can decide
 *    (navbar shows skeleton indefinitely, which is better than flashing
 *    an empty state).
 */
export function useUser(): SessionUser | null {
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<SessionUser>("/api/v1/users/me")
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.push("/login");
          return;
        }
        // Non-401 error — leave user as null. The UI will continue to
        // render its skeleton state. Consider logging once in dev.
        // eslint-disable-next-line no-console
        console.warn("useUser: failed to fetch /users/me", err);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return user;
}
