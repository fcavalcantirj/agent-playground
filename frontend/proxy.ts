// frontend/proxy.ts — Next.js 16 edge gate (renamed from middleware.ts per Next 16.2).
// Source: nextjs.org/docs/app/api-reference/file-conventions/proxy
//
// Gates /dashboard/:path* on the PRESENCE of the `ap_session` cookie. Does NOT
// validate the cookie server-side — validity checks live on the backend
// (/api/v1/users/me returns 401 if the cookie references an expired or revoked
// session, and the dashboard layout's useUser() hook handles that 401 by
// redirecting to /login).
//
// Purpose: avoid the auth-flash where an unauthenticated visitor briefly sees
// the dashboard shell before a client-side redirect fires.

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export default function proxy(request: NextRequest) {
  const session = request.cookies.get("ap_session");
  if (!session) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl, 307);
  }
  return NextResponse.next();
}

export const config = {
  // Match ONLY dashboard subroutes. Landing page, /login, /api/*, and all
  // static assets pass through untouched.
  matcher: ["/dashboard/:path*"],
};
