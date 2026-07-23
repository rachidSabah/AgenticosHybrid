"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { Database, Search, Trash2, Cpu, RefreshCw, HardDrive } from "lucide-react";

export function AgentMemoryManager() {
  const [memories, setMemories] = useState([
    { id: "mem-1", scope: "short_term", agent: "Claude Code", key: "session_context", content: "Active refactoring task on mission-control codebase", size: "1.2 KB" },
    { id: "mem-2", scope: "long_term", agent: "Hermes", key: "architecture_rules", content: "FastAPI hexagonal control plane mapping over kernel Platform", size: "4.8 KB" },
    { id: "mem-3", scope: "vector_store", agent: "AGY CLI", key: "mcp_tool_index", content: "36 native TouchDesigner MCP tools indexed into HNSW vector store", size: "18.4 KB" },
    { id: "mem-4", scope: "long_term", agent: "OpenCode", key: "user_preferences", content: "Vanilla CSS design system with glassmorphism dark theme tokens", size: "2.1 KB" },
  ]);

  const connected = useStore((s) => s.connected);

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
        <Stat label="Short-Term Items" value={1} tone="default" />
        <Stat label="Long-Term Items" value={2} tone="ok" />
        <Stat label="Vector Embeddings" value="18.4 KB" tone="accent" />
      </div>

      <Panel title="Agent Memory Inspector & Store" subtitle="Live inspection, editing, and pruning">
        <div className="space-y-2">
          {memories.map((m) => (
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
          ))}
        </div>
      </Panel>
    </div>
  );
}
