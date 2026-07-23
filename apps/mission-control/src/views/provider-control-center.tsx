"use client";

import { useEffect, useState, useMemo } from "react";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ModelInfo, ProviderHealthRecord, ProviderInfo } from "@/lib/types";

export function ProviderControlCenter() {
  // ── Primary source: live WebSocket data from EventBus ──
  const providersLive = useStore((s) => s.providers);
  const connected = useStore((s) => s.connected);

  // ── Fallback source: REST snapshot (used only if WS is empty) ──
  const [restHealth, setRestHealth] = useState<ProviderHealthRecord[]>([]);
  const [configs, setConfigs] = useState<ProviderInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.providerHealth()
      .then(setRestHealth)
      .catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.providers()
      .then(setConfigs)
      .catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.models(selected)
      .then((m) => setModels((prev) => ({ ...prev, [selected]: m })))
      .catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, [selected]);

  // ── Merge: WS data wins; REST fills any gaps WS hasn't seen yet ──
  const rows: ProviderHealthRecord[] = useMemo(() => {
    const liveArr = Object.values(providersLive ?? {});
    const safeRest = Array.isArray(restHealth) ? restHealth : [];
    if (liveArr.length > 0) {
      // WS has data — merge in any REST-only providers not yet reported via EventBus
      const liveKeys = new Set(liveArr.map((p) => p.provider));
      const restOnly = safeRest.filter((r) => r && r.provider && !liveKeys.has(r.provider));
      return [...liveArr, ...restOnly];
    }
    // WS empty — use REST snapshot
    return safeRest;
  }, [providersLive, restHealth]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <Panel
        title="Providers"
        subtitle={`${rows.length} registered${connected ? " · live" : ""}`}
        className="col-span-5"
      >
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
              {/* Pulse only if data came via live WS */}
              <StatusDot
                status={p.status}
                pulse={!!providersLive[p.provider] && p.status === "healthy"}
              />
              <span className="flex-1 text-sm">{p.provider}</span>
              <span className="text-xs text-faint">{p.latency_ms.toFixed(0)}ms</span>
              {p.error && <Badge tone="danger">err</Badge>}
              {providersLive[p.provider] && (
                <span className="text-[9px] text-ok" title="Live via EventBus">●</span>
              )}
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
                      ctx {m.context_window?.toLocaleString() ?? "—"} · ${m.input_cost_per_1k ?? "?"}/{m.output_cost_per_1k ?? "?"}
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
