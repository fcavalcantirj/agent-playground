/** @type {import('next').NextConfig} */
// Ported from the legacy web/next.config.ts: the Go API is same-origin in
// prod, but in local dev the Next.js dev server runs on :3000 and the Go
// API on :8080. The rewrite forwards /api/* to the backend so browser
// cookies (HttpOnly ap_session, set by the Go API) stay on one origin
// and fetch('/api/...') from client components Just Works.
const API_PROXY_TARGET =
  process.env.NEXT_PUBLIC_API_PROXY_TARGET || "http://localhost:8080"

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
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
