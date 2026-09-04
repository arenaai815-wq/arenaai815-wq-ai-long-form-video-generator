/** @type {import('next').NextConfig} */
const API_ORIGIN = process.env.API_INTERNAL_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // The browser only ever talks to the Next.js origin. Requests to /api/* are proxied
  // server-side to the FastAPI backend, so no backend URL or secret is shipped to clients
  // and the preview/production host does not need CORS exceptions.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  experimental: { proxyTimeout: 1000 * 60 * 30 },
};

export default nextConfig;
