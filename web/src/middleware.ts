import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Phase 1 middleware.
 *
 * The Phase 1 landing page lives at `/` and handles both auth states
 * internally (it calls `GET /api/me` and renders either the sign-in prompt
 * or the dashboard shell). We therefore do NOT redirect based on the
 * `ap_session` cookie here — the root is always accessible, and future
 * protected routes added in later phases can check this same cookie.
 *
 * The check below is intentionally a no-op for `/` so the landing page
 * can render in both authenticated and unauthenticated states; it serves
 * as a scaffold future phases will build on without re-architecting.
 *
 * Note: Next.js 16 renamed the `middleware` file convention to `proxy`,
 * but the `middleware.ts` file is still supported (deprecated). Phase 3
 * (auth) will migrate this to `proxy.ts` alongside the goth OAuth swap.
 */
export function middleware(request: NextRequest) {
  // Read the ap_session cookie set by the Go API on successful login.
  // In Phase 1 we only inspect it for future use; do not redirect.
  const session = request.cookies.get("ap_session");

  // Expose a lightweight header so downstream handlers can know if we
  // saw a session cookie at the edge. Pure UX hint, not a security gate.
  const res = NextResponse.next();
  if (session) {
    res.headers.set("x-ap-has-session", "1");
  }
  return res;
}

export const config = {
  // Run on every app route except static assets and the API proxy path.
  // The Go API handles /api/* so we skip middleware there to avoid a
  // wasteful round-trip through edge logic.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
