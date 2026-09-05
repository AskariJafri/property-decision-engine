/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // The API's location comes from NEXT_PUBLIC_API_BASE, read in lib/api.ts.
  // NEXT_PUBLIC_* variables are inlined into the browser bundle at build time,
  // so changing one requires a rebuild, not just a restart.
  //
  // Optional: uncomment to proxy the API through this app's own origin instead.
  // That removes the need for NEXT_PUBLIC_API_BASE and for any CORS
  // configuration, because the browser then only ever talks to one host.
  // async rewrites() {
  //   return [
  //     { source: "/api/:path*", destination: "https://<your-api>.vercel.app/api/:path*" },
  //   ];
  // },
};
export default nextConfig;
