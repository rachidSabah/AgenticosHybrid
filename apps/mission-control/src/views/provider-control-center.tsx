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
  const [apiKeyStatus, setApiKeyStatus] = useState<Record<string, boolean>>({});
  const [routingPolicy, setRoutingPolicyState] = useState<"latency" | "cost" | "round_robin">("latency");
  const [routingSaving, setRoutingSaving] = useState(false);

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
    // Real API-key status from the backend (has_key flag).
    api.apiKeyStatus(selected)
      .then((r) => setApiKeyStatus((prev) => ({ ...prev, [selected]: !!r.has_key })))
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

  useEffect(() => {
    if (!selected && rows.length > 0) {
      setSelected(rows[0].provider);
    }
  }, [rows, selected]);

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
    <div className="flex h-full flex-col gap-3 p-4 bg-background text-text overflow-hidden">
      {/* ── Futuristic Control Center Header ── */}
      <div className="flex items-center justify-between border-b border-border/40 pb-2.5 bg-surface/20 px-4 py-2 rounded-2xl backdrop-blur-xl shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="h-3 w-3 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_10px_rgba(34,211,238,0.8)]" />
          <div>
            <h2 className="text-xs font-bold uppercase tracking-widest text-cyan-300">PROVIDER CONTROL CENTER</h2>
            <p className="text-[10px] text-faint">Real-time model routing, latency monitoring & API key vault</p>
          </div>
        </div>
        <nav className="flex items-center gap-1.5 bg-black/40 p-1 rounded-xl border border-border/40">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`rounded-lg px-3 py-1 text-xs font-medium transition-all ${
                tab === t.id
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_8px_rgba(34,211,238,0.3)]"
                  : "text-faint hover:bg-surface/30 hover:text-text"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ── Summary Stats Row (Futuristic KPI Cards) ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <div className="glass rounded-2xl px-4 py-3 border border-border/50 bg-gradient-to-br from-surface/40 to-cyan-950/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-cyan-400/80">Active Providers</div>
          <div className="text-2xl font-black tabular-nums text-text mt-0.5">{rows.length}</div>
        </div>
        <div className="glass rounded-2xl px-4 py-3 border border-ok/30 bg-gradient-to-br from-surface/40 to-emerald-950/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-ok/80">Healthy Engines</div>
          <div className="text-2xl font-black tabular-nums text-ok mt-0.5">{healthyCount}</div>
        </div>
        <div className="glass rounded-2xl px-4 py-3 border border-warn/30 bg-gradient-to-br from-surface/40 to-amber-950/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-warn/80">Degraded / Slow</div>
          <div className="text-2xl font-black tabular-nums text-warn mt-0.5">{degradedCount}</div>
        </div>
        <div className="glass rounded-2xl px-4 py-3 border border-indigo-500/30 bg-gradient-to-br from-surface/40 to-indigo-950/20">
          <div className="text-[10px] font-bold uppercase tracking-wider text-indigo-300/80">Avg Latency</div>
          <div className="text-2xl font-black tabular-nums text-indigo-300 mt-0.5">{avgLatency}<span className="text-xs text-faint ml-1">ms</span></div>
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
                <div className="rounded-xl border border-border/60 p-3 space-y-2">
                  <div className="text-[10px] uppercase tracking-wider text-faint mb-2">API Key Vault</div>
                  {selected ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        {apiKeyStatus[selected] === undefined ? (
                          <Badge tone="default">Checking…</Badge>
                        ) : apiKeyStatus[selected] ? (
                          <Badge tone="ok">Configured / System Env</Badge>
                        ) : (
                          <Badge tone="warn">Not configured</Badge>
                        )}
                        <span className="text-xs text-faint">{selected}</span>
                      </div>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          placeholder={`Enter API Key for ${selected}…`}
                          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-1.5 text-xs text-text placeholder:text-faint outline-none focus:border-cyan-500/60"
                          id="apiKeyInput"
                        />
                        <button
                          onClick={async () => {
                            const el = document.getElementById("apiKeyInput") as HTMLInputElement;
                            if (!el || !el.value.trim()) return;
                            try {
                              await api.storeApiKey(selected, el.value.trim());
                              setApiKeyStatus((prev) => ({ ...prev, [selected]: true }));
                              el.value = "";
                            } catch (err) {
                              console.error("Save API Key error:", err);
                            }
                          }}
                          className="rounded-lg bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-3 py-1.5 text-xs font-semibold hover:bg-cyan-500/30 transition"
                        >
                          Save Key
                        </button>
                      </div>
                    </div>
                  ) : (
                    <Empty title="No provider selected" hint="Select a provider to manage its API key." />
                  )}
                </div>
                <div className="rounded-xl border border-border/60 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Routing Policy</div>
                  <div className="flex items-center gap-2">
                    <select
                      value={routingPolicy}
                      disabled={routingSaving}
                      onChange={async (e) => {
                        const next = e.target.value as "latency" | "cost" | "round_robin";
                        setRoutingSaving(true);
                        try {
                          const r = await api.setRoutingPolicy(next);
                          if (r?.policy) setRoutingPolicyState(r.policy as "latency" | "cost" | "round_robin");
                        } catch {
                          // keep previous selection on failure
                        } finally {
                          setRoutingSaving(false);
                        }
                      }}
                      className="w-full rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text disabled:opacity-50"
                    >
                      <option value="latency">Latency-optimized</option>
                      <option value="cost">Cost-optimized</option>
                      <option value="round_robin">Round-robin</option>
                    </select>
                    {routingSaving && <span className="text-[10px] text-faint">saving…</span>}
                  </div>
                  <div className="mt-1.5 text-[10px] text-faint">Defaults to latency-optimized; changes are saved to the backend router.</div>
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
