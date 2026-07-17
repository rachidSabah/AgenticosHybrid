"use client";

import { useEffect, useState } from "react";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { ProviderConfig } from "@/lib/types";

// MCP Manager. Exposes the real provider/connection configs the OS uses as its
// model-context servers. Each row maps to a backend provider adapter; health and
// key-status are live, fetched through existing control-plane endpoints.
export function McpManager() {
  const [configs, setConfigs] = useState<ProviderConfig[]>([]);
  const [statusById, setStatusById] = useState<Record<string, { healthy: boolean; latency_ms: number }>>({});
  const [keyStatus, setKeyStatus] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api.providerConfigs().then(setConfigs).catch(() => {});
  }, []);

  function test(name: string) {
    api.testProvider(name).then((r) => setStatusById((s) => ({ ...s, [name]: { healthy: r.healthy, latency_ms: r.latency_ms } }))).catch(() => {});
    api.apiKeyStatus(name).then((r) => setKeyStatus((s) => ({ ...s, [name]: r.has_key }))).catch(() => {});
  }

  return (
    <div className="h-full p-4">
      <Panel title="MCP Servers" subtitle={`${configs.length} configured connections`} className="h-full">
        <div className="space-y-2">
          {configs.map((c) => {
            const st = statusById[c.name];
            return (
              <div key={c.name} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
                <StatusDot status={st ? (st.healthy ? "healthy" : "down") : "unknown"} pulse={st?.healthy} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm">{c.name}</div>
                  <div className="text-[11px] text-faint">
                    {c.kind} · {keyStatus[c.name] === undefined ? "key ?" : keyStatus[c.name] ? "key ✓" : "no key"}
                    {st && ` · ${st.latency_ms.toFixed(0)}ms`}
                  </div>
                </div>
                <Badge tone="info">{c.kind}</Badge>
                <button className="pill bg-surface/60 text-muted hover:bg-surface" onClick={() => test(c.name)}>
                  Test
                </button>
              </div>
            );
          })}
          {configs.length === 0 && <Empty title="No MCP servers" hint="Provider configs appear here." />}
        </div>
      </Panel>
    </div>
  );
}
