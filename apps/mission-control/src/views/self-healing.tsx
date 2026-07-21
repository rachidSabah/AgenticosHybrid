"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import {
  AlertTriangle, AlertCircle, Info, CheckCircle2, XCircle,
  Activity,
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

const SEVERITY_CONFIG: Record<SeverityLevel, { color: string; bg: string; icon: typeof AlertCircle; label: string }> = {
  critical: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", icon: AlertTriangle, label: "CRITICAL" },
  high: { color: "#f97316", bg: "rgba(249,115,22,0.12)", icon: AlertCircle, label: "HIGH" },
  medium: { color: "#eab308", bg: "rgba(234,179,8,0.12)", icon: Info, label: "MEDIUM" },
  low: { color: "#6b7280", bg: "rgba(107,114,128,0.12)", icon: Info, label: "LOW" },
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

      // Add system status check
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
      await api.repairSystem([subsystem]);
      // Mark matching issues as resolved
      setIssues((prev) =>
        prev.map((i) =>
          i.subsystem === subsystem && !i.resolved_at
            ? { ...i, resolved_at: new Date(), resolution: "Auto-repaired" }
            : i
        )
      );
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
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* Header stats */}
      <div className="col-span-12 flex flex-wrap gap-3">
        <Stat label="Unresolved" value={unresolved.length} tone={unresolved.length > 0 ? "warn" : "ok"} />
        <Stat label="Critical" value={critical} tone={critical > 0 ? "danger" : "ok"} />
        <Stat label="High" value={high} tone={high > 0 ? "warn" : "ok"} />
        <Stat label="Medium" value={medium} />
        <Stat label="Low" value={low} />
        <Stat label="Providers" value={Object.keys(providers).length} />
        <Stat label="Agents" value={Object.keys(agents).length} />
      </div>

      {/* Actions bar */}
      <div className="col-span-12 flex items-center gap-3">
        <button
          onClick={runSystemCheck}
          disabled={running}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          {running ? "Scanning…" : "Run System Check"}
        </button>
        <button
          onClick={() => api.repairSystem().then(() => setIssues([]))}
          className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
        >
          Repair All
        </button>
        <div className="flex items-center gap-2 text-[11px] text-faint">
          <StatusDot status={connected ? "healthy" : "failed"} pulse={connected} />
          <span>{connected ? "EventBus connected" : "EventBus disconnected"}</span>
        </div>
        {error && <span className="text-[11px] text-danger">{error}</span>}
      </div>

      {/* Severity legend */}
      <div className="col-span-12 flex items-center gap-4 text-[10px] text-faint">
        {(Object.entries(SEVERITY_CONFIG) as [SeverityLevel, typeof SEVERITY_CONFIG['critical']][]).map(([key, cfg]) => (
          <span key={key} className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: cfg.color }} />
            {cfg.label}
          </span>
        ))}
        <span className="ml-auto">
          Auto-repair: <span className="text-ok">LOW/MEDIUM</span> · Approval: <span className="text-warn">HIGH/CRITICAL</span>
        </span>
      </div>

      {/* Active Issues */}
      <Panel title="Active Issues" subtitle={`${unresolved.length} unresolved`} className="col-span-12 md:col-span-6 flex-1">
        {unresolved.length === 0 ? (
          <Empty title="No active issues" hint="System is healthy. Run a system check to verify all subsystems." />
        ) : (
          <div className="space-y-1.5">
            {unresolved.map((issue) => {
              const cfg = SEVERITY_CONFIG[issue.severity];
              const Icon = cfg.icon;
              return (
                <motion.div
                  key={issue.id}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start gap-2.5 rounded-xl border border-border/40 bg-surface/15 px-3 py-2.5"
                >
                  <Icon size={14} style={{ color: cfg.color, marginTop: 2 }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium">{issue.subsystem}</span>
                      <span className="rounded px-1.5 py-0.5 text-[9px] font-medium"
                        style={{ backgroundColor: cfg.bg, color: cfg.color }}>
                        {cfg.label}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-muted">{issue.description}</p>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-faint">
                      <span>{issue.detected_at.toLocaleTimeString()}</span>
                    </div>
                  </div>
                  {/* Auto-repair button for low/medium */}
                  {issue.severity === "low" || issue.severity === "medium" ? (
                    <button
                      onClick={() => autoRepair(issue.subsystem)}
                      className="shrink-0 rounded-md bg-ok/10 px-2 py-1 text-[9px] text-ok hover:bg-ok/20 transition-colors"
                    >
                      Repair
                    </button>
                  ) : (
                    <span className="shrink-0 rounded-md bg-warn/10 px-2 py-1 text-[9px] text-warn">
                      Review
                    </span>
                  )}
                </motion.div>
              );
            })}
          </div>
        )}
      </Panel>

      {/* Resolution History */}
      <Panel title="History" subtitle={`${resolved.length} resolved`} className="col-span-12 md:col-span-6 flex-1">
        {resolved.length === 0 ? (
          <Empty title="No history" hint="Resolved issues will appear here." />
        ) : (
          <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
            {resolved.slice(0, 30).map((issue) => {
              const cfg = SEVERITY_CONFIG[issue.severity];
              return (
                <div key={issue.id} className="flex items-start gap-2.5 rounded-xl px-3 py-2">
                  {issue.error ? (
                    <XCircle size={14} className="text-danger shrink-0 mt-0.5" />
                  ) : (
                    <CheckCircle2 size={14} className="text-ok shrink-0 mt-0.5" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-muted">{issue.subsystem}</span>
                      <span className="rounded px-1.5 py-0.5 text-[9px]" style={{ backgroundColor: cfg.bg, color: cfg.color }}>
                        {cfg.label}
                      </span>
                    </div>
                    <p className="text-[11px] text-faint">{issue.resolution || issue.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      {/* System health summary */}
      <div className="col-span-12">
        <Panel title="System Status" subtitle="Current backend state">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-3">
              <StatusDot status={connected ? "healthy" : "failed"} pulse={connected} />
              <div>
                <div className="text-[11px] text-faint">WebSocket</div>
                <div className="text-xs font-medium">{connected ? "Connected" : "Disconnected"}</div>
              </div>
            </div>
            <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-3">
              <StatusDot status={Object.keys(providers).length > 0 ? "healthy" : "idle"} />
              <div>
                <div className="text-[11px] text-faint">Providers</div>
                <div className="text-xs font-medium">{Object.keys(providers).length} registered</div>
              </div>
            </div>
            <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-3">
              <StatusDot status={Object.keys(agents).length > 0 ? "healthy" : "idle"} />
              <div>
                <div className="text-[11px] text-faint">Agents</div>
                <div className="text-xs font-medium">{Object.keys(agents).length} active</div>
              </div>
            </div>
            <div className="glass rounded-xl px-3 py-2.5 flex items-center gap-3">
              <StatusDot status={critical === 0 && high === 0 ? "healthy" : "failed"} />
              <div>
                <div className="text-[11px] text-faint">Status</div>
                <div className="text-xs font-medium">
                  {critical > 0 || high > 0 ? "Issues detected" : "Healthy"}
                </div>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
