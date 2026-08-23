/** @type {import('next').NextConfig} */
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

const nextConfig = {
  reactStrictMode: true,
  output: "export",
  // Next mis-infers the workspace root when a parent lockfile exists
  // (E:\Agenticos\package-lock.json). Pin the tracing root to this app so
  // static export collection (e.g. /_not-found) resolves correctly.
  outputFileTracingRoot: __dirname,
  images: { unoptimized: true },
  // Mission Control is a client-heavy SPA shell over the FastAPI backend.
  // The backend URL is supplied at runtime via NEXT_PUBLIC_API_BASE.
  // Default points at the locally-running backend port (8080).
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8080",
  },
};

export default nextConfig;
