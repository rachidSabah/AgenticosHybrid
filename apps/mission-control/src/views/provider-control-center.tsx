"use client";

import { useEffect, useState } from "react";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ModelInfo, ProviderHealthRecord, ProviderInfo } from "@/lib/types";

export function ProviderControlCenter() {
  const providersLive = useStore((s) => s.providers);
  const [health, setHealth] = useState<ProviderHealthRecord[]>([]);
  const [configs, setConfigs] = useState<ProviderInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.providerHealth().then(setHealth).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.providers().then(setConfigs).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.models(selected).then((m) => setModels((prev) => ({ ...prev, [selected]: m }))).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, [selected]);

  const rows = health.length ? health : Object.values(providersLive);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <Panel title="Providers" subtitle={`${rows.length} registered`} className="col-span-5">
        <div className="space-y-2">
          {rows.map((p) => (
            <button
              key={p.provider}
              onClick={() => setSelected(p.provider)}
              className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${
                selected === p.provider
                  ? "border-accent/60 bg-accent/10"
                  : "border-border/60 hover:border-border bg-surface/40"
              }`}
            >
              <StatusDot status={p.status} pulse={p.status === "healthy"} />
              <span className="flex-1 text-sm">{p.provider}</span>
              <span className="text-xs text-faint">{p.latency_ms.toFixed(0)}ms</span>
              {p.error && <Badge tone="danger">err</Badge>}
            </button>
          ))}
          {rows.length === 0 && <Empty title="No providers" hint="Register a provider to begin." />}
        </div>
      </Panel>

      <Panel title="Provider Detail" subtitle={selected ?? "Select a provider"} className="col-span-7">
        {!selected ? (
          <Empty title="Provider telemetry" hint="Pick a provider to inspect models and routing." />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <Badge tone="info">{selected}</Badge>
              {(configs.find((c) => c.name === selected)?.kind) && (
                <Badge>{configs.find((c) => c.name === selected)!.kind}</Badge>
              )}
            </div>
            <div>
              <div className="mb-2 text-[11px] uppercase tracking-wide text-faint">Models</div>
              <div className="grid grid-cols-2 gap-2">
                {(models[selected] ?? []).map((m) => (
                  <div key={m.id} className="rounded-xl border border-border/60 px-3 py-2">
                    <div className="text-sm">{m.id}</div>
                    <div className="text-[11px] text-faint">
                      ctx {m.context_window?.toLocaleString() ?? "—"} · ${m.input_cost_per_1k ?? "?"}/${m.output_cost_per_1k ?? "?"}
                    </div>
                  </div>
                ))}
                {(models[selected] ?? []).length === 0 && (
                  <div className="col-span-2 text-sm text-faint">No models exposed for this provider.</div>
                )}
              </div>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
