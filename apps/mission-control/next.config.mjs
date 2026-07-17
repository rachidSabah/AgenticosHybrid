/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Mission Control is a client-heavy SPA shell over the FastAPI backend.
  // The backend URL is supplied at runtime via NEXT_PUBLIC_API_BASE.
  async rewrites() {
    const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${base}/api/:path*` },
      { source: "/ws/:path*", destination: `${base}/ws/:path*` },
    ];
  },
};

export default nextConfig;
