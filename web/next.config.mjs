/**
 * The browser talks only to this app; `/api/*` is proxied to the API.
 *
 * That is not a convenience. Accounts live in an httpOnly session cookie, and a
 * cookie set by a different site is a third-party cookie that browsers now
 * block — so the API has to appear on this origin. It also removes CORS from the
 * browser path entirely.
 *
 * PDE_API_ORIGIN is read when the server starts (and at build time on Vercel).
 * NEXT_PUBLIC_API_BASE, the variable earlier deployments already set, is honoured
 * as a fallback so an existing deployment keeps working without a new variable.
 *
 * @type {import('next').NextConfig}
 */
const API_ORIGIN = (
  process.env.PDE_API_ORIGIN ||
  process.env.NEXT_PUBLIC_API_BASE ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default nextConfig;
