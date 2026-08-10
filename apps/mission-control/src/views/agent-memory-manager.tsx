"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { Database, HardDrive, Trash2 } from "lucide-react";
import type { MemoryItem, MemoryScope } from "@/lib/types";

const SCOPES: MemoryScope[] = ["working", "conversation", "project", "shared", "long_term"];

export function AgentMemoryManager() {
  // Real memory loaded from the backend memory system (never hardcoded).
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(SCOPES.map((s) => api.memoryScope(s).catch(() => [] as MemoryItem[])));
      setMemories(results.flat());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shortTermCount = memories.filter((m) => m.scope === "working" || m.scope === "conversation").length;
  const longTermCount = memories.filter((m) => m.scope === "long_term").length;
  const vectorCount = memories.filter((m) => Array.isArray(m.embedding) && m.embedding.length > 0).length;

  const handleForget = async (id: string) => {
    try {
      const r = await api.forgetMemory(id);
      if (r?.forgotten) {
        setMemories((prev) => prev.filter((m) => m.id !== id));
        setStatus(`Forgot ${id}`);
      } else {
        setStatus(`Backend did not confirm forget for ${id}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Database size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">ENTERPRISE AGENT MEMORY MANAGER</h1>
            <p className="text-[11px] text-faint">Short/long-term memory, vector stores, pruning & inspection console</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={memories.length > 0 ? "ok" : "default"}>
            {memories.length > 0 ? `${memories.length} items loaded` : "No items"}
          </Badge>
          <button
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-border/60 px-3 py-1.5 text-xs text-faint transition hover:bg-surface/20 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Total Memories" value={memories.length} tone="accent" />
        <Stat label="Short-Term Items" value={shortTermCount} tone="default" />
        <Stat label="Long-Term Items" value={longTermCount} tone="ok" />
        <Stat label="Vector Embeddings" value={vectorCount} tone="accent" />
      </div>

      <Panel title="Agent Memory Inspector & Store" subtitle="Live memory items from the backend">
        {loading && memories.length === 0 ? (
          <Empty title="Loading memory…" />
        ) : memories.length === 0 ? (
          <Empty title="No memory entries" hint="Memory written by agents will appear here. Use Memory Explorer to write an entry." />
        ) : (
          <div className="space-y-2">
            {memories.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
                <div className="space-y-1 min-w-0">
                  <div className="flex items-center gap-2 font-semibold text-text">
                    <HardDrive size={14} className="text-accent shrink-0" />
                    <span className="truncate">{m.key}</span>
                    {m.agent_id && <span className="text-[10px] text-faint shrink-0">({m.agent_id})</span>}
                  </div>
                  <div className="text-[11px] text-faint font-mono bg-black/40 p-2 rounded break-words">{m.value}</div>
                </div>
                <div className="text-right space-y-1 shrink-0 ml-2">
                  <Badge tone="default">{m.scope}</Badge>
                  <div className="text-[10px] text-faint font-mono">
                    {Array.isArray(m.embedding) && m.embedding.length > 0 ? `${m.embedding.length} dims` : "no vector"}
                  </div>
                  <button
                    onClick={() => handleForget(m.id)}
                    className="inline-flex items-center gap-1 rounded border border-danger/40 bg-danger/10 px-2 py-0.5 text-[10px] text-danger hover:bg-danger/20 transition"
                  >
                    <Trash2 size={10} /> forget
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {status && <div className="mt-2 text-xs text-muted">{status}</div>}
        {error && <div className="mt-2 text-xs text-danger">{error}</div>}
      </Panel>
    </div>
  );
}
