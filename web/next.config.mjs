/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: { API_BASE: process.env.API_BASE ?? "http://localhost:8000" },
};
export default nextConfig;
