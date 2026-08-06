"use client";

import { useEffect, useState, useMemo } from "react";
import { safeFixed } from "@/lib/safe";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ModelInfo, ProviderHealthRecord, ProviderInfo } from "@/lib/types";

type Tab = "dashboard" | "providers" | "models" | "logs" | "settings";

export function ProviderControlCenter() {
  const providersLive = useStore((s) => s.providers);
  const connected = useStore((s) => s.connected);

  const [restHealth, setRestHealth] = useState<ProviderHealthRecord[]>([]);
  const [configs, setConfigs] = useState<ProviderInfo[]>([]);
  const [models, setModels] = useState<Record<string, ModelInfo[]>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("dashboard");

  useEffect(() => {
    api.providerHealth()
      .then(setRestHealth)
      .catch(() => {});
    api.providers()
      .then(setConfigs)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    api.models(selected)
      .then((m) => setModels((prev) => ({ ...prev, [selected]: m })))
      .catch(() => {});
  }, [selected]);

  const rows: ProviderHealthRecord[] = useMemo(() => {
    const liveArr = Object.values(providersLive ?? {});
    const safeRest = Array.isArray(restHealth) ? restHealth : [];
    if (liveArr.length > 0) {
      const liveKeys = new Set(liveArr.map((p) => p.provider));
      const restOnly = safeRest.filter((r) => r && r.provider && !liveKeys.has(r.provider));
      return [...liveArr, ...restOnly];
    }
    return safeRest;
  }, [providersLive, restHealth]);

  const healthyCount = rows.filter((r) => r.status === "healthy").length;
  const degradedCount = rows.filter((r) => r.status === "degraded").length;
  const downCount = rows.filter((r) => r.status === "down" || r.status === "unknown").length;
  const avgLatency = rows.length > 0
    ? Math.round(rows.reduce((sum, r) => sum + (r?.latency_ms || 0), 0) / rows.length)
    : 0;

  const tabs: { id: Tab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "providers", label: "Providers" },
    { id: "models", label: "Models" },
    { id: "logs", label: "Logs" },
    { id: "settings", label: "Settings" },
  ];

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* ── Header with tabs ── */}
      <div className="flex items-center justify-between border-b border-border/40 pb-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Provider Control Center</h2>
        </div>
        <nav className="flex items-center gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                tab === t.id
                  ? "bg-accent/20 text-accent"
                  : "text-faint hover:bg-surface/30 hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Summary Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="glass rounded-xl px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-faint">Providers</div>
          <div className="text-2xl font-bold tabular-nums text-text">{rows.length}</div>
        </div>
        <div className="glass rounded-xl px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-faint">Healthy</div>
          <div className="text-2xl font-bold tabular-nums text-ok">{healthyCount}</div>
        </div>
        <div className="glass rounded-xl px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-faint">Degraded</div>
          <div className="text-2xl font-bold tabular-nums text-warn">{degradedCount}</div>
        </div>
        <div className="glass rounded-xl px-4 py-3">
          <div className="text-[10px] uppercase tracking-wider text-faint">Avg Latency</div>
          <div className="text-2xl font-bold tabular-nums text-accent">{avgLatency}ms</div>
        </div>
      </div>

      {/* ── Main Content: Two-column layout ── */}
      <div className="grid flex-1 gap-4 min-h-0 grid-cols-1 lg:grid-cols-[2fr_1fr]">
        {/* Left panel: Provider list or content based on tab */}
        <div className="min-h-0">
          {tab === "dashboard" || tab === "providers" ? (
            <Panel
              title="Providers"
              subtitle={`${rows.length} registered${connected ? " · live" : ""}`}
              className="h-full"
            >
              <div className="min-h-0 max-h-[500px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
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
                    <StatusDot
                      status={p.status}
                      pulse={!!providersLive[p.provider] && p.status === "healthy"}
                    />
                    <span className="flex-1 text-sm truncate">{p.provider}</span>
                    <span className="text-xs text-faint tabular-nums">{safeFixed(p?.latency_ms, 0)}ms</span>
                    {p.error && <Badge tone="danger">err</Badge>}
                    {providersLive[p.provider] && (
                      <span className="text-[9px] text-ok" title="Live via EventBus">●</span>
                    )}
                  </button>
                ))}
                {rows.length === 0 && <Empty title="No providers" hint="Register a provider to begin." />}
              </div>
            </Panel>
          ) : tab === "models" ? (
            <Panel title="Models" subtitle={`${selected ?? "Select a provider"}`} className="h-full">
              <div className="min-h-0 max-h-[500px] overflow-y-auto overflow-x-hidden no-scrollbar">
                {!selected ? (
                  <Empty title="No provider selected" hint="Pick a provider from the list." />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {(models[selected] ?? []).map((m) => (
                      <div key={m.id} className="rounded-xl border border-border/60 px-3 py-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium">{m.id}</span>
                          <Badge tone="info">ctx {m.context_window?.toLocaleString() ?? "—"}</Badge>
                        </div>
                        <div className="mt-1 text-[11px] text-faint">
                          ${m.input_cost_per_1k ?? "?"} / ${m.output_cost_per_1k ?? "?"} per 1k tokens
                        </div>
                      </div>
                    ))}
                    {(models[selected] ?? []).length === 0 && (
                      <div className="col-span-2 text-sm text-faint">No models exposed for this provider.</div>
                    )}
                  </div>
                )}
              </div>
            </Panel>
          ) : tab === "logs" ? (
            <Panel title="Provider Logs" subtitle="Recent activity" className="h-full">
              <div className="min-h-0 max-h-[500px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1">
                {rows.map((p) => (
                  <div key={p.provider} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-surface/30">
                    <StatusDot status={p.status} />
                    <span className="flex-1 truncate">{p.provider}</span>
                    <span className="text-faint tabular-nums">{safeFixed(p?.latency_ms, 0)}ms</span>
                    {p.error && <span className="text-danger text-[10px] truncate max-w-[120px]">{p.error}</span>}
                  </div>
                ))}
                {rows.length === 0 && <Empty title="No logs available" />}
              </div>
            </Panel>
          ) : (
            <Panel title="Provider Settings" subtitle="Configuration" className="h-full">
              <div className="space-y-3">
                <div className="rounded-xl border border-border/60 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-faint mb-2">API Key Status</div>
                  {selected ? (
                    <div className="flex items-center gap-2">
                      <Badge tone="ok">Configured</Badge>
                      <span className="text-xs text-faint">{selected}</span>
                    </div>
                  ) : (
                    <Empty title="No provider selected" hint="Select a provider to manage its API key." />
                  )}
                </div>
                <div className="rounded-xl border border-border/60 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Routing Policy</div>
                  <select className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text">
                    <option value="latency">Latency-optimized</option>
                    <option value="cost">Cost-optimized</option>
                    <option value="round-robin">Round-robin</option>
                  </select>
                </div>
              </div>
            </Panel>
          )}
        </div>

        {/* Right panel: Provider detail */}
        <Panel title="Provider Detail" subtitle={selected ?? "Select a provider"} className="min-h-0">
          {!selected ? (
            <Empty title="Provider telemetry" hint="Pick a provider to inspect models and routing." />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                <Badge tone="info">{selected}</Badge>
                {(configs.find((c) => c.name === selected)?.kind) && (
                  <Badge>{configs.find((c) => c.name === selected)!.kind}</Badge>
                )}
              </div>

              {/* Latency gauge */}
              <div className="rounded-xl border border-border/60 p-3">
                <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Latency</div>
                <div className="flex items-end gap-2">
                  <span className="text-2xl font-bold tabular-nums text-accent">
                    {safeFixed(rows.find((r) => r.provider === selected)?.latency_ms, 0)}ms
                  </span>
                  <span className="text-[10px] text-faint mb-1">avg response</span>
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-border/30 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-ok to-accent"
                    style={{ width: `${Math.min(100, Math.max(0, 100 - (rows.find((r) => r.provider === selected)?.latency_ms || 0) / 10))}%` }}
                  />
                </div>
              </div>

              {/* Status badge */}
              <div className="rounded-xl border border-border/60 p-3">
                <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Status</div>
                <div className="flex items-center gap-2">
                  <StatusDot status={rows.find((r) => r.provider === selected)?.status ?? "unknown"} pulse />
                  <span className="text-sm capitalize">{rows.find((r) => r.provider === selected)?.status ?? "unknown"}</span>
                </div>
              </div>

              {/* Models count */}
              <div className="rounded-xl border border-border/60 p-3">
                <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Models</div>
                <div className="text-2xl font-bold tabular-nums">{(models[selected] ?? []).length}</div>
                <div className="text-[10px] text-faint">available models</div>
              </div>
            </div>
          )}
        </Panel>
      </div>

      {error && (
        <div className="rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">
          {error}
        </div>
      )}
    </div>
  );
}
