/** @type {import('next').NextConfig} */
// In local dev the Next.js dev server runs on :3000 and the Phase 19 Python
// api_server runs on :8000 (or behind Caddy in prod). The rewrite forwards
// `/api/v1/*` → `${API_PROXY_TARGET}/v1/*` so browser fetches from client
// components stay same-origin (future session cookies will work without CORS).
const API_PROXY_TARGET =
  process.env.NEXT_PUBLIC_API_PROXY_TARGET || "http://127.0.0.1:8000"

const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_PROXY_TARGET}/v1/:path*`,
      },
      {
        source: "/api/healthz",
        destination: `${API_PROXY_TARGET}/healthz`,
      },
      {
        source: "/api/readyz",
        destination: `${API_PROXY_TARGET}/readyz`,
      },
    ]
  },
  // Dead-route redirects (D-22c-UI-02 + D-22c-UI-03): /signup and
  // /forgot-password are not part of Phase 22c's user journey — OAuth is
  // the only entry path. Fire at the Next config layer BEFORE the page
  // routes render. `permanent: false` emits HTTP 307 (temporary) so a
  // future phase can re-enable the original pages without fighting
  // browser-cache poisoning.
  async redirects() {
    return [
      { source: "/signup", destination: "/login", permanent: false },
      { source: "/forgot-password", destination: "/login", permanent: false },
    ]
  },
}

export default nextConfig
