"use client";

import { useStore } from "@/lib/store";

/**
 * Backend status indicator — shows "Backend Offline" when the WebSocket
 * is disconnected. Renders nothing when connected (no visual clutter).
 *
 * This is a non-intrusive indicator that doesn't block the UI — it just
 * shows a small banner at the top of the page when the backend is down.
 * The application remains fully usable (all API calls return safe defaults).
 */
export function BackendStatus() {
  const connected = useStore((s) => s.connected);
  if (connected) return null;
  return (
    <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-center gap-2 bg-amber-500/20 px-4 py-1.5 text-xs text-amber-300 backdrop-blur-sm">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
      Backend Offline — Retrying...
    </div>
  );
}
