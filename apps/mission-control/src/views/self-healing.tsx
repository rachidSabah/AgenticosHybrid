"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import {
  AlertTriangle, AlertCircle, Info, CheckCircle2, XCircle,
  Activity, ShieldCheck, Wrench, RefreshCw, Zap, Cpu, Server, Radio
} from "lucide-react";

type SeverityLevel = "critical" | "high" | "medium" | "low";

interface HealthIssue {
  id: string;
  subsystem: string;
  description: string;
  severity: SeverityLevel;
  detected_at: Date;
  resolved_at: Date | null;
  resolution: string | null;
  error: string | null;
}

const SEVERITY_CONFIG: Record<SeverityLevel, { color: string; bg: string; border: string; icon: typeof AlertCircle; label: string }> = {
  critical: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", border: "rgba(239,68,68,0.3)", icon: AlertTriangle, label: "CRITICAL" },
  high: { color: "#f97316", bg: "rgba(249,115,22,0.12)", border: "rgba(249,115,22,0.3)", icon: AlertCircle, label: "HIGH" },
  medium: { color: "#eab308", bg: "rgba(234,179,8,0.12)", border: "rgba(234,179,8,0.3)", icon: Info, label: "MEDIUM" },
  low: { color: "#3b82f6", bg: "rgba(59,130,246,0.12)", border: "rgba(59,130,246,0.3)", icon: Info, label: "LOW" },
};

function classifySeverity(eventTopic: string): SeverityLevel {
  if (eventTopic.includes("critical") || eventTopic.includes("failed")) return "critical";
  if (eventTopic.includes("degraded") || eventTopic.includes("denied") || eventTopic.includes("recovery")) return "high";
  if (eventTopic.includes("disconnected") || eventTopic.includes("timeout")) return "medium";
  if (eventTopic.includes("recovered") || eventTopic.includes("completed")) return "low";
  return "medium";
}

export function SelfHealingPanel() {
  const [issues, setIssues] = useState<HealthIssue[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live EventBus feed from store
  const events = useStore((s) => s.events);
  const connected = useStore((s) => s.connected);
  const providers = useStore((s) => s.providers);
  const agents = useStore((s) => s.agents);

  // Derive health issues from EventBus events
  const eventsHealth = useMemo(() => {
    const result: HealthIssue[] = [];
    for (const e of events.slice(0, 100)) {
      const p = e.payload as Record<string, any>;
      const topic = e.topic;
      if (
        topic.includes("failed") || topic.includes("degraded") ||
        topic.includes("denied") || topic.includes("recovery") ||
        topic.includes("disconnected") || topic.includes("timeout") ||
        topic.includes("recovered")
      ) {
        result.push({
          id: e.id,
          subsystem: p?.source ?? p?.agent_id ?? p?.provider ?? topic.split(".")[0] ?? "system",
          description: p?.reason ?? p?.error ?? `Topic: ${topic}`,
          severity: classifySeverity(topic),
          detected_at: new Date(e.timestamp),
          resolved_at: topic.includes("recovered") ? new Date() : null,
          resolution: topic.includes("recovered") ? "Auto-recovered" : null,
          error: p?.error ?? null,
        });
      }
    }
    return result;
  }, [events]);

  // Merge derived events into local state (keep existing resolved issues)
  useEffect(() => {
    setIssues((prev) => {
      const merged = [...prev];
      for (const h of eventsHealth) {
        if (!merged.find((m) => m.id === h.id)) {
          merged.unshift(h);
        }
      }
      return merged.slice(0, 200);
    });
  }, [eventsHealth]);

  // Check provider health for auto-detected issues
  const providerIssues = useMemo(() => {
    const result: HealthIssue[] = [];
    for (const [name, record] of Object.entries(providers)) {
      if (record.status === "degraded" || record.status === "down") {
        result.push({
          id: `provider-${name}`,
          subsystem: `provider:${name}`,
          description: `Provider ${name} is ${record.status}${record.error ? `: ${record.error}` : ""}`,
          severity: record.status === "down" ? "critical" : "high",
          detected_at: new Date(record.last_checked ?? Date.now()),
          resolved_at: null,
          resolution: null,
          error: record.error ?? null,
        });
      }
    }
    return result;
  }, [providers]);

  // Add provider issues to state
  useEffect(() => {
    setIssues((prev) => {
      const merged = [...prev];
      for (const h of providerIssues) {
        const existing = merged.findIndex((m) => m.id === h.id);
        if (existing >= 0) {
          merged[existing] = h;
        } else {
          merged.unshift(h);
        }
      }
      return merged.slice(0, 200);
    });
  }, [providerIssues]);

  const runSystemCheck = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      // Run diagnostics and repair in parallel
      const [diagResult, integResult, healthResult, recoveryResult] = await Promise.allSettled([
        api.runDiagnostics(),
        api.integrityCheck(),
        api.health(),
        api.recoveryStatus(),
      ]);

      const diag = diagResult.status === "fulfilled" ? diagResult.value : null;
      const integ = integResult.status === "fulfilled" ? integResult.value : null;
      const health = healthResult.status === "fulfilled" ? healthResult.value : null;
      const recovery = recoveryResult.status === "fulfilled" ? recoveryResult.value : null;

      const newIssues: HealthIssue[] = [];

      if (health && health.status !== "ok") {
        newIssues.push({
          id: `health-${Date.now()}`,
          subsystem: "backend",
          description: health.status,
          severity: health.status === "degraded" ? "high" : "critical",
          detected_at: new Date(),
          resolved_at: null,
          resolution: null,
          error: null,
        });
      }

      if (diag) {
        const report = diag as Record<string, any>;
        for (const [key, value] of Object.entries(report)) {
          if (value === false || value === "fail") {
            newIssues.push({
              id: `diag-${key}-${Date.now()}`,
              subsystem: key,
              description: `Diagnostic check failed: ${key}`,
              severity: "medium",
              detected_at: new Date(),
              resolved_at: null,
              resolution: null,
              error: null,
            });
          }
        }
      }

      if (integ) {
        const ir = integ as Record<string, any>;
        if (ir.issues && Array.isArray(ir.issues)) {
          for (const issue of ir.issues) {
            newIssues.push({
              id: `integ-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              subsystem: "integrity",
              description: issue,
              severity: "high",
              detected_at: new Date(),
              resolved_at: null,
              resolution: null,
              error: null,
            });
          }
        }
      }

      if (recovery && recovery.in_recovery) {
        newIssues.push({
          id: `recovery-${Date.now()}`,
          subsystem: "recovery",
          description: "System is in recovery mode",
          severity: "high",
          detected_at: new Date(),
          resolved_at: null,
          resolution: null,
          error: null,
        });
      }

      if (!connected) {
        newIssues.push({
          id: `ws-${Date.now()}`,
          subsystem: "websocket",
          description: "EventBus WebSocket disconnected",
          severity: "medium",
          detected_at: new Date(),
          resolved_at: null,
          resolution: null,
          error: null,
        });
      }

      setIssues((prev) => [...newIssues, ...prev].slice(0, 200));
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  }, [connected]);

  const autoRepair = useCallback(async (subsystem: string) => {
    try {
      const res = await api.repairSystem([subsystem]);
      const failedList = res?.failed ?? [];
      void useStore.getState().hydrate();
      setIssues((prev) =>
        prev.map((i) => {
          if (i.subsystem !== subsystem || i.resolved_at) return i;
          if (failedList.includes(subsystem)) {
            return { ...i, resolution: `Repair failed: ${subsystem}` };
          }
          return { ...i, resolved_at: new Date(), resolution: "Auto-repaired (Mitigated)" };
        })
      );
      if (failedList.length > 0) setError(`Repair reported failures: ${failedList.join(", ")}`);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const unresolved = issues.filter((i) => !i.resolved_at);
  const resolved = issues.filter((i) => i.resolved_at);
  const critical = unresolved.filter((i) => i.severity === "critical").length;
  const high = unresolved.filter((i) => i.severity === "high").length;
  const medium = unresolved.filter((i) => i.severity === "medium").length;
  const low = unresolved.filter((i) => i.severity === "low").length;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background/95 p-4 space-y-3">
      {/* ── Futuristic Control Deck Header ── */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-surface/40 via-cyan-950/20 to-surface/40 p-3.5 backdrop-blur-xl shadow-[0_0_20px_rgba(6,182,212,0.05)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
            <ShieldCheck size={20} className="animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold tracking-wide text-text">Self-Healing Infrastructure</h1>
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono tracking-wider text-cyan-400 uppercase">
                Autonomous SRE
              </span>
            </div>
            <p className="text-xs text-faint">Real-time telemetry diagnostics, fault detection & automated mitigation</p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={runSystemCheck}
            disabled={running}
            className="flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3.5 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-500/60 transition shadow-[0_0_12px_rgba(6,182,212,0.15)] disabled:opacity-50"
          >
            <RefreshCw size={13} className={running ? "animate-spin" : ""} />
            <span>{running ? "Scanning…" : "Run System Check"}</span>
          </button>
          <button
            onClick={async () => {
              setRunning(true);
              try {
                const res = await api.repairSystem();
                const failedList = res?.failed ?? [];
                void useStore.getState().hydrate();
                setIssues((prev) =>
                  prev.map((i) => {
                    if (i.resolved_at) return i;
                    if (failedList.includes(i.subsystem)) {
                      return { ...i, resolution: "Repair failed" };
                    }
                    return { ...i, resolved_at: new Date(), resolution: "Auto-repaired (System Hardening)" };
                  })
                );
                if (failedList.length > 0) {
                  setError(`Repair All reported failures: ${failedList.join(", ")}`);
                }
              } catch (e) {
                setError(String(e));
              } finally {
                setRunning(false);
              }
            }}
            disabled={running}
            className="flex items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20 hover:border-emerald-500/60 transition shadow-[0_0_12px_rgba(16,185,129,0.15)] disabled:opacity-50"
          >
            <Wrench size={13} />
            <span>Repair All</span>
          </button>
        </div>
      </div>

      {/* ── Status Metrics Bar ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2">
        <Stat label="LIVE BUS" value={connected ? "CONNECTED" : "OFFLINE"} tone={connected ? "ok" : "warn"} />
        <Stat label="Unresolved" value={unresolved.length} tone={unresolved.length === 0 ? "ok" : "warn"} />
        <Stat label="Critical" value={critical} tone={critical > 0 ? "danger" : "ok"} />
        <Stat label="High" value={high} tone={high > 0 ? "warn" : "ok"} />
        <Stat label="Medium" value={medium} tone={medium > 0 ? "accent" : "default"} />
        <Stat label="Low" value={low} tone={low > 0 ? "accent" : "default"} />
        <Stat label="Providers" value={Object.keys(providers).length} tone="accent" />
      </div>

      {/* Notification / Error Banner */}
      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-3.5 py-2 text-xs text-rose-300">
          {error}
        </div>
      )}

      {/* ── Main Workspace split: Active Issues & Resolution History ── */}
      <div className="grid flex-1 gap-4 min-h-0 grid-cols-1 lg:grid-cols-12 overflow-hidden">
        {/* Active Issues Panel */}
        <Panel
          title="Active Issues"
          subtitle={`${unresolved.length} unresolved`}
          className="col-span-12 lg:col-span-6 flex flex-col h-full overflow-hidden border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
        >
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
            {unresolved.length === 0 ? (
              <Empty title="No active issues" hint="System is healthy. Run a system check to verify all subsystems." />
            ) : (
              <AnimatePresence>
                {unresolved.map((issue) => {
                  const cfg = SEVERITY_CONFIG[issue.severity];
                  const Icon = cfg.icon;
                  return (
                    <motion.div
                      key={issue.id}
                      layout
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, x: -10 }}
                      className="flex items-start gap-3 rounded-xl border p-3 transition"
                      style={{ backgroundColor: cfg.bg, borderColor: cfg.border }}
                    >
                      <Icon size={16} className="mt-0.5 shrink-0" style={{ color: cfg.color }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-text truncate">{issue.subsystem}</span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider"
                            style={{ backgroundColor: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}
                          >
                            {cfg.label}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-muted leading-relaxed">{issue.description}</p>
                        <div className="mt-1.5 flex items-center justify-between text-[10px] text-faint">
                          <span>Detected: {issue.detected_at.toLocaleTimeString()}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => autoRepair(issue.subsystem)}
                        className="shrink-0 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-medium text-emerald-300 hover:bg-emerald-500/20 transition-colors"
                      >
                        Auto-Repair
                      </button>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            )}
          </div>
        </Panel>

        {/* Resolution History Panel */}
        <Panel
          title="Resolution History"
          subtitle={`${resolved.length} resolved events`}
          className="col-span-12 lg:col-span-6 flex flex-col h-full overflow-hidden border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
        >
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
            {resolved.length === 0 ? (
              <Empty title="No history" hint="Resolved issues will appear here automatically." />
            ) : (
              resolved.slice(0, 40).map((issue) => {
                const cfg = SEVERITY_CONFIG[issue.severity];
                return (
                  <div
                    key={issue.id}
                    className="flex items-start gap-3 rounded-xl border border-border/40 bg-surface/20 p-2.5"
                  >
                    {issue.error ? (
                      <XCircle size={15} className="text-rose-400 shrink-0 mt-0.5" />
                    ) : (
                      <CheckCircle2 size={15} className="text-emerald-400 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-medium text-text">{issue.subsystem}</span>
                        <span
                          className="rounded px-1.5 py-0.5 text-[9px] font-mono uppercase"
                          style={{ backgroundColor: cfg.bg, color: cfg.color }}
                        >
                          {cfg.label}
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-faint">{issue.resolution || issue.description}</p>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Panel>
      </div>

      {/* ── System Subsystem Diagnostics Footer ── */}
      <Panel title="Subsystem Diagnostics" subtitle="Infrastructure component state" className="shrink-0 border border-cyan-500/15 bg-surface/30">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-xl border border-border/40 bg-surface/40 px-3 py-2 flex items-center gap-3">
            <Radio size={16} className="text-cyan-400" />
            <div>
              <div className="text-[10px] text-faint uppercase font-mono">WebSocket Bus</div>
              <div className="text-xs font-semibold text-text">{connected ? "Connected" : "Disconnected"}</div>
            </div>
          </div>
          <div className="rounded-xl border border-border/40 bg-surface/40 px-3 py-2 flex items-center gap-3">
            <Server size={16} className="text-cyan-400" />
            <div>
              <div className="text-[10px] text-faint uppercase font-mono">Providers Engine</div>
              <div className="text-xs font-semibold text-text">{Object.keys(providers).length} Registered</div>
            </div>
          </div>
          <div className="rounded-xl border border-border/40 bg-surface/40 px-3 py-2 flex items-center gap-3">
            <Cpu size={16} className="text-cyan-400" />
            <div>
              <div className="text-[10px] text-faint uppercase font-mono">Agent Constellation</div>
              <div className="text-xs font-semibold text-text">{Object.keys(agents).length} Active</div>
            </div>
          </div>
          <div className="rounded-xl border border-border/40 bg-surface/40 px-3 py-2 flex items-center gap-3">
            <Zap size={16} className={critical === 0 && high === 0 ? "text-emerald-400" : "text-amber-400"} />
            <div>
              <div className="text-[10px] text-faint uppercase font-mono">System Status</div>
              <div className="text-xs font-semibold text-text">
                {critical > 0 || high > 0 ? "Issues Detected" : "Nominal State"}
              </div>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

