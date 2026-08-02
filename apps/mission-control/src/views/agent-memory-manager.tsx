"use client";

import { useMemo } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { Database, HardDrive } from "lucide-react";

export function AgentMemoryManager() {
  // Derive memory entries EXCLUSIVELY from the live store. No hardcoded
  // memory data — when no agents are discovered, the memory list is empty.
  const storeMemory = useStore((s) => s.memory);
  const connected = useStore((s) => s.connected);

  const memories = useMemo(() => {
    // Surface store memory entries (from WS memory.written events) if present.
    // When no memory events have been observed, the list is empty.
    return storeMemory.map((entry, idx) => ({
      id: String(entry.id ?? `mem-${idx}`),
      scope: String(entry.scope ?? "short_term"),
      agent: String(entry.agent_id ?? "unknown"),
      key: String(entry.key ?? "memory"),
      content: String(entry.value ?? ""),
      size: entry.embedding ? `${entry.embedding.length} dims` : "—",
    }));
  }, [storeMemory]);

  const shortTermCount = memories.filter((m) => m.scope === "short_term").length;
  const longTermCount = memories.filter((m) => m.scope === "long_term").length;
  const vectorCount = memories.filter((m) => m.scope === "vector_store").length;

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
        <Badge tone={connected ? "ok" : "warn"}>{connected ? "Memory Index Synced" : "Local Memory Store"}</Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Total Memories" value={memories.length} tone="accent" />
        <Stat label="Short-Term Items" value={shortTermCount} tone="default" />
        <Stat label="Long-Term Items" value={longTermCount} tone="ok" />
        <Stat label="Vector Embeddings" value={vectorCount} tone="accent" />
      </div>

      <Panel title="Agent Memory Inspector & Store" subtitle="Live inspection, editing, and pruning">
        <div className="space-y-2">
          {memories.length === 0 ? (
            <Empty title="No memory entries" hint="Memory events from discovered agents will appear here." />
          ) : (
            memories.map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 font-semibold text-text">
                    <HardDrive size={14} className="text-accent" />
                    {m.key} <span className="text-[10px] text-faint">({m.agent})</span>
                  </div>
                  <div className="text-[11px] text-faint font-mono bg-black/40 p-2 rounded">
                    {m.content}
                  </div>
                </div>
                <div className="text-right space-y-1">
                  <Badge tone="default">{m.scope}</Badge>
                  <div className="text-[10px] text-faint font-mono">{m.size}</div>
                </div>
              </div>
            ))
          )}
        </div>
      </Panel>
    </div>
  );
}
