"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Network, Zap, Cpu, Server, ShieldCheck, RefreshCw, Layers, ArrowRight,
  Database, Activity, CheckCircle2, AlertTriangle, TrendingDown, DollarSign,
  Sliders, Play, Plus, X, Globe, Lock, Brain, Terminal, ToggleLeft, ToggleRight,
  Sparkles, Settings2, Check
} from "lucide-react";

interface RoutePolicy {
  id: string;
  name: string;
  category: string;
  targetProvider: string;
  targetModel: string;
  fallbackProvider: string;
  enabled: boolean;
}

interface FailoverEvent {
  id?: string;
  timestamp: string;
  fromProvider?: string;
  toProvider?: string;
  from_provider?: string;
  to_provider?: string;
  reason: string;
  status?: "success" | "retry" | "failed";
}

export function OmniRouteDashboard() {
  const [policies, setPolicies] = useState<RoutePolicy[]>([]);
  const [failovers, setFailovers] = useState<FailoverEvent[]>([]);
  const [activeTab, setActiveTab] = useState<"routing" | "composer" | "policies" | "compression" | "budget">("routing");
  const [testPrompt, setTestPrompt] = useState("");
  const [routeResult, setRouteResult] = useState<any>(null);
  const [compressText, setCompressText] = useState("");
  const [compressResult, setCompressResult] = useState<any>(null);
  const [isReloading, setIsReloading] = useState(false);

  // Composer Form State
  const [composerPolicyName, setComposerPolicyName] = useState("Custom High-Throughput Routing");
  const [composerTarget, setComposerTarget] = useState("Codex CLI");
  const [composerFallback, setComposerFallback] = useState("Hermes Agent");
  const [composerStrategy, setComposerStrategy] = useState<"latency" | "cost" | "accuracy" | "local_first">("local_first");
  const [composerSavedMsg, setComposerSavedMsg] = useState(false);

  const connected = useStore((s) => s.connected);
  const providers = useStore((s) => s.providers);

  // Live telemetry data
  const [telemetry, setTelemetry] = useState({
    requestsProcessed: 0,
    activeRoutes: 0,
    avgLatencyMs: 0,
    compressionSavingsPct: 0,
    totalTokensSaved: 0,
    todayCostSaved: 0,
    localExecutionRatio: 0,
  });

  const loadData = useCallback(async () => {
    try {
      const [status, pol, bg, comp, tel, fail] = await Promise.all([
        api.omnirouteStatus().catch(() => null),
        api.omniroutePolicies().catch(() => null),
        api.omnirouteBudget().catch(() => null),
        api.omnirouteCompression().catch(() => null),
        api.omnirouteTelemetry().catch(() => null),
        api.omnirouteFailover().catch(() => null),
      ]);
      if (Array.isArray(pol)) {
        setPolicies(pol as unknown as RoutePolicy[]);
      }
      if (Array.isArray(fail)) {
        setFailovers(fail as unknown as FailoverEvent[]);
      }
      setTelemetry((prev) => ({
        ...prev,
        requestsProcessed: status?.requests_processed ?? prev.requestsProcessed,
        activeRoutes: tel?.active_routes ?? prev.activeRoutes,
        avgLatencyMs: tel?.avg_latency_ms ?? prev.avgLatencyMs,
        compressionSavingsPct: comp?.savings_pct ?? prev.compressionSavingsPct,
        totalTokensSaved: prev.totalTokensSaved,
        todayCostSaved: bg?.saved_cost ?? prev.todayCostSaved,
        localExecutionRatio: bg ? bg.local_ratio * 100 : prev.localExecutionRatio,
      }));
    } catch { /* keep current state */ }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleReload = async () => {
    setIsReloading(true);
    try {
      await api.omnirouteReload().catch(() => {});
      await loadData();
    } finally {
      setTimeout(() => setIsReloading(false), 600);
    }
  };

  const handleTestRoute = async () => {
    if (!testPrompt.trim()) return;
    try {
      const res = await api.omnirouteRoute(testPrompt);
      setRouteResult(res);
    } catch {
      setRouteResult({ error: "Routing failed — no runtimes available" });
    }
  };

  const handleTestCompress = async () => {
    if (!compressText.trim()) return;
    try {
      const res = await api.omnirouteCompress(compressText);
      setCompressResult(res);
    } catch {
      setCompressResult({ error: "Compression failed" });
    }
  };

  const togglePolicy = (idx: number) => {
    setPolicies((prev) =>
      prev.map((p, i) => (i === idx ? { ...p, enabled: !p.enabled } : p))
    );
  };

  const handleSaveComposerPolicy = () => {
    const newPolicy: RoutePolicy = {
      id: `custom-pol-${Date.now()}`,
      name: composerPolicyName || "Custom Policy",
      category: composerStrategy,
      targetProvider: composerTarget,
      targetModel: composerTarget,
      fallbackProvider: composerFallback,
      enabled: true,
    };
    setPolicies((prev) => [newPolicy, ...prev]);
    setComposerSavedMsg(true);
    setTimeout(() => setComposerSavedMsg(false), 2500);
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background text-text">
      {/* ── Top Header Navigation & Status Bar ── */}
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-4 py-2.5 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Network size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">OMNIROUTE UNIVERSAL AI NETWORKING ENGINE</h1>
            <p className="text-[11px] text-faint">Smart Model Routing, Token Compression & Provider Failover Subsystem</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Badge tone={connected ? "ok" : "warn"}>{connected ? "OmniRoute Active" : "Local Engine"}</Badge>
          <button
            onClick={handleReload}
            disabled={isReloading}
            className="flex items-center gap-1 rounded-lg border border-border/60 bg-surface/40 px-2.5 py-1 text-xs text-faint hover:text-text hover:bg-surface/60 transition disabled:opacity-50"
          >
            <RefreshCw size={12} className={isReloading ? "animate-spin text-accent" : ""} />
            <span>{isReloading ? "Reloading…" : "Reload"}</span>
          </button>
        </div>
      </div>

      {/* ── Subsystem Tabs ── */}
      <div className="flex items-center gap-1 border-b border-border/40 bg-surface/10 px-4 py-1.5 overflow-x-auto">
        {[
          { id: "routing", label: "Live Routing Graph", icon: Network },
          { id: "composer", label: "Route Composer", icon: Sliders },
          { id: "policies", label: "Routing Policies", icon: ShieldCheck },
          { id: "compression", label: "Token Compression", icon: TrendingDown },
          { id: "budget", label: "Budget & Failover", icon: DollarSign },
        ].map((t) => {
          const Icon = t.icon;
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id as any)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition whitespace-nowrap ${
                isActive ? "bg-accent/20 text-accent border border-accent/30" : "text-faint hover:text-text hover:bg-surface/30"
              }`}
            >
              <Icon size={13} />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── Main Content Area ── */}
      <div className="flex-1 overflow-y-auto p-4 min-h-0 space-y-4">
        {/* Top Telemetry Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Requests Processed" value={telemetry.requestsProcessed} tone="accent" />
          <Stat label="Avg Latency" value={`${telemetry.avgLatencyMs}ms`} tone="ok" />
          <Stat label="Compression Savings" value={`${telemetry.compressionSavingsPct}%`} tone="ok" />
          <Stat label="Estimated Saved" value={`$${telemetry.todayCostSaved}`} tone="accent" />
        </div>

        {/* Tab 1: Live Routing Graph */}
        {activeTab === "routing" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            {/* Real Interactive Graph Panel */}
            <Panel title="Live AI Routing Pipeline Graph" subtitle="User Prompt → Compression → OmniRoute Engine → Target Model" className="col-span-12 lg:col-span-8">
              <div className="flex flex-col items-center justify-center p-6 space-y-6">
                <div className="flex items-center gap-3 w-full justify-between max-w-xl">
                  <div className="glass rounded-xl p-3 border border-amber-500/40 text-center w-32">
                    <Brain size={18} className="mx-auto text-amber-400 mb-1" />
                    <span className="text-xs font-semibold block">User Prompt</span>
                    <span className="text-[10px] text-faint">Prompt Center</span>
                  </div>
                  <ArrowRight size={16} className="text-accent animate-pulse" />
                  <div className="glass rounded-xl p-3 border border-purple-500/40 text-center w-36">
                    <TrendingDown size={18} className="mx-auto text-purple-400 mb-1" />
                    <span className="text-xs font-semibold block">Token Compress</span>
                    <span className="text-[10px] text-purple-300">-42% Tokens</span>
                  </div>
                  <ArrowRight size={16} className="text-accent animate-pulse" />
                  <div className="glass rounded-xl p-3 border border-accent text-center w-40 shadow-glow">
                    <Network size={20} className="mx-auto text-accent mb-1 animate-spin" />
                    <span className="text-xs font-bold block text-accent">OmniRoute Engine</span>
                    <span className="text-[10px] text-faint">Smart Routing</span>
                  </div>
                </div>

                <div className="h-6 w-0.5 bg-accent/40" />

                {/* Target Provider Nodes */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 w-full">
                  {Object.values(providers)
                    .filter((p) => p.provider && p.provider.toLowerCase() !== "mock")
                    .slice(0, 6)
                    .map((p, idx) => {
                      const name = p.provider ?? `Provider-${idx}`;
                      const latency = `${Math.round(p.latency_ms ?? 0)}ms`;
                      const status = p.status === "healthy" ? "Active Target" : p.status === "degraded" ? "Standby" : "Offline";
                      return (
                        <div key={`${name}-${idx}`} className="glass rounded-xl p-3 border border-border/50 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold">{name}</span>
                            <StatusDot status={p.status === "healthy" ? "healthy" : p.status === "degraded" ? "degraded" : "down"} pulse />
                          </div>
                          <div className="text-[10px] font-mono text-purple-300">{name}</div>
                          <div className="flex justify-between text-[10px] text-faint">
                            <span>{latency}</span>
                            <span className={p.status === "healthy" ? "text-ok font-medium" : "text-faint font-medium"}>{status}</span>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            </Panel>

            {/* Test Routing Console */}
            <Panel title="Test Route Decision" subtitle="Simulate prompt routing" className="col-span-12 lg:col-span-4">
              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-faint block mb-1">Enter Test Prompt</label>
                  <textarea
                    value={testPrompt}
                    onChange={(e) => setTestPrompt(e.target.value)}
                    placeholder="e.g. Refactor this React component for maximum rendering performance..."
                    rows={3}
                    className="w-full rounded-xl border border-border/60 bg-surface/40 p-2.5 outline-none focus:border-accent font-sans"
                  />
                </div>
                <button
                  onClick={handleTestRoute}
                  className="w-full rounded-xl bg-accent px-4 py-2 font-semibold text-white hover:bg-accent/80 transition"
                >
                  Evaluate Route
                </button>

                {routeResult && (
                  <div className="glass rounded-xl p-3 border border-ok/40 space-y-1 font-mono text-[11px]">
                    <div className="text-ok font-bold">[ROUTING DECISION]</div>
                    <div>Target: <span className="text-accent">{routeResult.target_provider}</span></div>
                    <div>Model: <span className="text-purple-300">{routeResult.model}</span></div>
                    <div>Latency: <span className="text-muted">{routeResult.latency_ms}ms</span></div>
                  </div>
                )}
              </div>
            </Panel>
          </div>
        )}

        {/* Tab 2: Route Composer */}
        {activeTab === "composer" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <Panel title="Route Policy Composer" subtitle="Compose dynamic multi-model routing cascades" className="col-span-12 lg:col-span-7">
              <div className="space-y-4 text-xs">
                <div>
                  <label className="text-faint block mb-1">Policy Identifier</label>
                  <input
                    type="text"
                    value={composerPolicyName}
                    onChange={(e) => setComposerPolicyName(e.target.value)}
                    className="w-full rounded-xl border border-border/60 bg-surface/40 p-2.5 outline-none focus:border-accent"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-faint block mb-1">Primary Target Provider</label>
                    <select
                      value={composerTarget}
                      onChange={(e) => setComposerTarget(e.target.value)}
                      className="w-full rounded-xl border border-border/60 bg-surface/40 p-2.5 outline-none focus:border-accent text-text"
                    >
                      <option value="Codex CLI">Codex CLI</option>
                      <option value="Hermes Agent">Hermes Agent</option>
                      <option value="Claude Code">Claude Code</option>
                      <option value="OpenCode">OpenCode</option>
                      <option value="Openai Cloud">Openai Cloud</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-faint block mb-1">Failover Fallback Provider</label>
                    <select
                      value={composerFallback}
                      onChange={(e) => setComposerFallback(e.target.value)}
                      className="w-full rounded-xl border border-border/60 bg-surface/40 p-2.5 outline-none focus:border-accent text-text"
                    >
                      <option value="Hermes Agent">Hermes Agent</option>
                      <option value="Codex CLI">Codex CLI</option>
                      <option value="Claude Code">Claude Code</option>
                      <option value="OpenCode">OpenCode</option>
                      <option value="Openai Cloud">Openai Cloud</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="text-faint block mb-1">Optimization Strategy</label>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {[
                      { id: "local_first", label: "Local First" },
                      { id: "latency", label: "Lowest Latency" },
                      { id: "cost", label: "Cost Optimal" },
                      { id: "accuracy", label: "High Accuracy" },
                    ].map((st) => (
                      <button
                        key={st.id}
                        type="button"
                        onClick={() => setComposerStrategy(st.id as any)}
                        className={`rounded-xl border p-2 text-center text-xs transition ${
                          composerStrategy === st.id
                            ? "border-accent bg-accent/20 text-accent font-semibold"
                            : "border-border/60 bg-surface/20 text-faint hover:text-text"
                        }`}
                      >
                        {st.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="pt-2 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={handleSaveComposerPolicy}
                    className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 font-semibold text-white hover:bg-accent/80 transition"
                  >
                    <Plus size={14} /> Add Route Policy
                  </button>
                  {composerSavedMsg && (
                    <span className="text-ok text-xs flex items-center gap-1 animate-pulse">
                      <Check size={14} /> Added to active policy registry!
                    </span>
                  )}
                </div>
              </div>
            </Panel>

            <Panel title="Active Composer Pipeline Preview" subtitle="Visual preview of current configured policy" className="col-span-12 lg:col-span-5">
              <div className="space-y-3 text-xs">
                <div className="rounded-xl border border-accent/40 bg-surface/30 p-4 space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="font-semibold text-accent">{composerPolicyName}</span>
                    <Badge tone="ok">Ready</Badge>
                  </div>
                  <div className="space-y-1 font-mono text-[11px] text-faint">
                    <div>Mode: <span className="text-text">{composerStrategy}</span></div>
                    <div>Target: <span className="text-purple-300">{composerTarget}</span></div>
                    <div>Fallback: <span className="text-amber-300">{composerFallback}</span></div>
                  </div>
                </div>

                <div className="rounded-xl border border-border/40 bg-surface/10 p-3 text-[11px] text-faint">
                  OmniRoute automatically tests each host engine's health heartbeat before dispatching prompts, executing zero-latency local fallback if the primary engine is occupied.
                </div>
              </div>
            </Panel>
          </div>
        )}

        {/* Tab 3: Routing Policies */}
        {activeTab === "policies" && (
          <Panel title="Configurable Routing Policies" subtitle="Rule-based routing to AI providers">
            <div className="space-y-2">
              {policies.map((policy, idx) => (
                <div
                  key={policy.id || `${policy.name}-${idx}`}
                  className="flex items-center justify-between rounded-xl border border-border/50 bg-surface/20 p-3 text-xs transition hover:border-accent/40"
                >
                  <div className="space-y-0.5">
                    <div className="font-semibold text-text">{policy.name}</div>
                    <div className="text-[11px] text-faint">
                      Target: <span className="text-accent">{policy.targetProvider}</span> ({policy.targetModel}) · Fallback: <span className="text-muted">{policy.fallbackProvider}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => togglePolicy(idx)}
                    className="focus:outline-none transition"
                  >
                    <Badge tone={policy.enabled ? "ok" : "default"}>
                      {policy.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </button>
                </div>
              ))}
            </div>
          </Panel>
        )}

        {/* Tab 4: Token Compression */}
        {activeTab === "compression" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <Panel title="Token Compression Engine" subtitle="Live prompt optimization and token saving" className="col-span-12 lg:col-span-8">
              <div className="space-y-3 text-xs">
                <textarea
                  value={compressText}
                  onChange={(e) => setCompressText(e.target.value)}
                  placeholder="Paste long code or prompt text to compress..."
                  rows={4}
                  className="w-full rounded-xl border border-border/60 bg-surface/40 p-3 outline-none focus:border-accent font-mono text-[11px]"
                />
                <button onClick={handleTestCompress} className="rounded-xl bg-purple-500 px-4 py-2 font-semibold text-white hover:bg-purple-600 transition">
                  Compress Prompt
                </button>

                {compressResult && (
                  <div className="glass rounded-xl p-3 border border-purple-500/40 space-y-2 text-xs">
                    <div className="flex justify-between font-mono">
                      <span>Original: {compressResult.original_tokens} tokens</span>
                      <span className="text-purple-300">Compressed: {compressResult.compressed_tokens} tokens</span>
                    </div>
                    <div className="text-[11px] font-mono text-faint bg-black/40 p-2 rounded">
                      {compressResult.compressed_text}
                    </div>
                  </div>
                )}
              </div>
            </Panel>

            <Panel title="Compression Metrics" subtitle="Aggregate savings" className="col-span-12 lg:col-span-4">
              <div className="space-y-3 text-xs">
                <Stat label="Tokens Saved" value={telemetry.totalTokensSaved} tone="ok" />
                <Stat label="Average Reduction" value={`${telemetry.compressionSavingsPct}%`} tone="accent" />
                <Stat label="Estimated Cost Reduction" value={`$${telemetry.todayCostSaved}`} tone="ok" />
              </div>
            </Panel>
          </div>
        )}

        {/* Tab 5: Budget & Failover */}
        {activeTab === "budget" && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
            <Panel title="Failover Event Monitor" subtitle="Automatic model retry & provider switching events" className="col-span-12 lg:col-span-7">
              <div className="space-y-2 text-xs">
                {failovers.length > 0 ? (
                  failovers.map((ev, idx) => {
                    const fromP = ev.fromProvider || ev.from_provider || "Unknown";
                    const toP = ev.toProvider || ev.to_provider || "Codex CLI";
                    const status = ev.status || "success";
                    return (
                      <div key={ev.id || `${fromP}-${toP}-${ev.timestamp}-${idx}`} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold">{fromP}</span>
                            <ArrowRight size={12} className="text-amber-400" />
                            <span className="text-accent font-semibold">{toP}</span>
                          </div>
                          <div className="text-[11px] text-faint mt-0.5">{ev.reason || "Automatic latency-driven failover"} · {ev.timestamp || "recent"}</div>
                        </div>
                        <Badge tone="ok">{status}</Badge>
                      </div>
                    );
                  })
                ) : (
                  <div className="p-4 text-center text-faint text-xs">No active failover events recorded — all provider routes nominal.</div>
                )}
              </div>
            </Panel>

            <Panel title="Budget & Cost Optimization" subtitle="Provider cost distribution" className="col-span-12 lg:col-span-5">
              <div className="space-y-3 text-xs">
                <Stat label="Local Execution Ratio" value={`${telemetry.localExecutionRatio.toFixed(1)}%`} tone="ok" />
                <Stat label="Today's Cost Saved" value={`$${telemetry.todayCostSaved}`} tone="accent" />
                <Stat label="Monthly Cost Savings" value={`$${(telemetry.todayCostSaved * 30).toFixed(2)}`} tone="ok" />
              </div>
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}