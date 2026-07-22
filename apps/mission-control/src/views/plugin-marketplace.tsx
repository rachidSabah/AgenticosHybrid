"use client";

import { useEffect, useState } from "react";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { CapabilityInfo, ProviderInfo } from "@/lib/types";

// Surfaces the real plugin/capability ecosystem already registered in the OS:
// provider adapters (plugins) and the capability engine registry. No fabricated
// marketplace entries — every row is a live backend artifact.
export function PluginMarketplace() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.providers().then(setProviders).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.capabilities().then(setCaps).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  return (
    <div className="scroll-page">
      <div className="rflex gap-4 p-4">
        <Panel title="Provider Plugins" subtitle={`${providers.length} loaded adapters`} className="flex-[7]">
          <div className="card-grid">
            {providers.map((p) => (
              <div key={p.name} className="card-fluid rounded-xl border border-border/60 p-3">
                <div className="flex items-center gap-2">
                  <StatusDot status="healthy" />
                  <span className="text-sm font-medium">{p.name}</span>
                  <Badge tone="info" >{p.kind}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">
                  {p.supports_streaming ? "streaming" : "no-stream"} · {p.supports_tools ? "tools" : "no-tools"}
                </div>
              </div>
            ))}
            {providers.length === 0 && <Empty title="No provider plugins" />}
          </div>
        </Panel>

        <Panel title="Capability Catalog" subtitle={`${caps.length} capabilities`} className="flex-[5]">
          <div className="space-y-2">
            {caps.map((c) => (
              <div key={c.name} className="flex items-center gap-2 rounded-xl border border-border/60 px-3 py-2">
                <span className="text-sm">{c.name}</span>
                {c.requires_approval ? <Badge tone="warn">approval</Badge> : <Badge tone="ok">auto</Badge>}
                <span className="ml-auto max-w-[40%] truncate text-[11px] text-faint">{c.description}</span>
              </div>
            ))}
            {caps.length === 0 && <Empty title="No capabilities" />}
          </div>
        </Panel>
      </div>
    </div>
  );
}
