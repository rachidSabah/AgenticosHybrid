"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { Sparkles, Terminal, X, CornerDownLeft } from "lucide-react";

export function GlobalHUDOverlay() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.altKey) && e.code === "Space") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await api.post<any>("/api/desktop/hud/query", { query: query.trim() });
      if (res) setResult(res);
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/60 backdrop-blur-md">
      <div className="w-full max-w-2xl rounded-2xl border border-border/80 bg-surface/90 p-4 shadow-2xl space-y-3">
        <div className="flex items-center justify-between border-b border-border/40 pb-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-accent">
            <Sparkles size={14} /> AgenticOS Global Command HUD (Ctrl+Space)
          </div>
          <button onClick={() => setOpen(false)} className="text-faint hover:text-text">
            <X size={14} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Type any command: 'run tests', 'deploy canary', 'inspect swarm'..."
            className="w-full rounded-xl border border-border/60 bg-surface/40 px-4 py-3 text-sm text-text outline-none focus:border-accent"
          />
          <button type="submit" className="absolute right-3 text-faint hover:text-accent">
            <CornerDownLeft size={16} />
          </button>
        </form>

        {result && (
          <div className="rounded-xl border border-border/40 bg-surface/30 p-3 text-xs space-y-1 font-mono">
            <div className="text-accent font-semibold">Action: {result.action_taken} ({result.execution_time_ms}ms)</div>
            <div className="text-emerald-400">{result.output_snippet}</div>
          </div>
        )}
      </div>
    </div>
  );
}