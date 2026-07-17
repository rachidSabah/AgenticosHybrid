"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Badge, Empty, StatusDot } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { MemoryItem, MemoryScope } from "@/lib/types";

const SCOPES: MemoryScope[] = ["working", "conversation", "project", "shared", "long_term"];

export function MemoryExplorer() {
  const [scope, setScope] = useState<MemoryScope>("working");
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [writeKey, setWriteKey] = useState("");
  const [writeVal, setWriteVal] = useState("");
  const [query, setQuery] = useState("");
  const memoryEvents = useStore((s) => s.memory);
  const [status, setStatus] = useState("");

  const refresh = useCallback(async () => {
    try {
      setItems(await api.memoryScope(scope));
    } catch {
      setItems([]);
    }
  }, [scope]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <Panel title="Memory Scopes" subtitle="Backed by the Memory System" className="col-span-3">
        <div className="space-y-2">
          {SCOPES.map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-left text-sm transition ${
                scope === s ? "border-accent/60 bg-accent/10" : "border-border/60 hover:border-border"
              }`}
            >
              <StatusDot status="healthy" pulse={scope === s} />
              {s}
            </button>
          ))}
          <div className="pt-2">
            <button className="pill bg-accent/15 text-accent hover:bg-accent/25" onClick={() => api.enforceRetention().then((r) => setStatus(`Evicted ${r.evicted}`)).catch((e) => setStatus("err: " + (e as Error).message))}>
              Enforce retention
            </button>
          </div>
          {memoryEvents.length > 0 && (
            <div className="pt-2 text-[11px] text-faint">{memoryEvents.length} live write events observed</div>
          )}
        </div>
      </Panel>

      <Panel
        title={`${scope} memory`}
        subtitle={`${items.length} entries`}
        className="col-span-5"
        actions={
          <input
            className="w-40 rounded-lg border border-border/60 bg-surface/50 px-2 py-1 text-xs outline-none focus:border-accent/60"
            placeholder="recall query…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && query)
                api.recallMemory(scope, query).then(setItems).catch(() => {});
            }}
          />
        }
      >
        <div className="space-y-2">
          {items.map((m) => (
            <div key={m.id} className="rounded-xl border border-border/60 px-3 py-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{m.key}</span>
                <Badge tone="info">{m.scope}</Badge>
                <button
                  className="ml-auto text-[11px] text-faint hover:text-danger"
                  onClick={() => api.forgetMemory(m.id).then(refresh).catch(() => {})}
                >
                  forget
                </button>
              </div>
              <div className="mt-1 line-clamp-3 text-xs text-muted">{m.value}</div>
            </div>
          ))}
          {items.length === 0 && <Empty title="No entries" hint="Write or recall to populate." />}
        </div>
      </Panel>

      <Panel title="Write" subtitle="Persist a memory item" className="col-span-4">
        <div className="space-y-3">
          <input
            className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
            placeholder="key"
            value={writeKey}
            onChange={(e) => setWriteKey(e.target.value)}
          />
          <textarea
            className="h-40 w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
            placeholder="value"
            value={writeVal}
            onChange={(e) => setWriteVal(e.target.value)}
          />
          <button
            className="w-full rounded-lg bg-accent/20 py-2 text-sm text-accent hover:bg-accent/30"
            onClick={async () => {
              if (!writeKey || !writeVal) return;
              try {
                await api.writeMemory({ scope, key: writeKey, value: writeVal });
                setWriteKey("");
                setWriteVal("");
                setStatus("written");
                refresh();
              } catch (e) {
                setStatus("err: " + (e as Error).message);
              }
            }}
          >
            Write to {scope}
          </button>
          {status && <div className="text-xs text-muted">{status}</div>}
        </div>
      </Panel>
    </div>
  );
}
