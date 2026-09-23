/** @type {import('next').NextConfig} */
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// output: "export" is required for Tauri (static bundle embedded in the binary).
// In dev mode (npm run dev) we skip it so the Next.js dev server works normally
// with full API route support, hot reload, and no static-export restrictions.
const isStaticBuild =
  process.env.NODE_ENV === "production" || process.env.NEXT_EXPORT === "1";

const nextConfig = {
  reactStrictMode: true,
  ...(isStaticBuild ? { output: "export" } : {}),
  outputFileTracingRoot: __dirname,
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};

export default nextConfig;
