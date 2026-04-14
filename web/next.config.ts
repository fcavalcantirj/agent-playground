import type { NextConfig } from "next";

const API_PROXY_TARGET =
  process.env.NEXT_PUBLIC_API_PROXY_TARGET || "http://localhost:8080";

const nextConfig: NextConfig = {
  async rewrites() {
    // Forward all /api/* calls to the Go backend during local dev.
    // In production the Go API and Next.js are deployed same-origin so
    // this rewrite is a no-op behind the reverse proxy.
    return [
      {
        source: "/api/:path*",
        destination: `${API_PROXY_TARGET}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
