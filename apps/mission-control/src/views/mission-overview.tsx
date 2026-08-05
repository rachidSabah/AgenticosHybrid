"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
import { safeFixed } from "@/lib/safe";
import { SystemControl } from "@/components/system-control";
import type { ProviderHealthRecord, CapabilityInfo, AuditEntry } from "@/lib/types";

// ── Agent Identity Colors ──
const COMMAND_COLORS: Record<string, string> = {
  claude: "#d980ff",
  hermes: "#6366f1",
  opencode: "#22c55e",
  codex: "#fbbf24",
  gemini: "#38bdf8",
};
function cmdColor(provider: string): string {
  if (!provider) return "#818cf8";
  const key = Object.keys(COMMAND_COLORS).find((k) => provider.toLowerCase().includes(k));
  return key ? COMMAND_COLORS[key] : "#818cf8";
}

// ── KPI Stat Card ──
function KpiCard({
  label,
  value,
  delta,
  tone = "default",
}: {
  label: string;
  value: string | number;
  delta?: string;
  tone?: "default" | "ok" | "warn" | "danger" | "accent";
}) {
  const toneClass = {
    default: "text-text",
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
    accent: "text-accent",
  }[tone];
  return (
    <div className="glass rounded-xl px-4 py-3 flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${toneClass}`}>{value}</div>
      {delta && <div className="text-[10px] text-faint/70">{delta}</div>}
    </div>
  );
}

// ── Mission Card (Left Column) ──
function MissionCard({
  title,
  status,
  description,
  health,
  progress,
  index,
}: {
  title: string;
  status: string;
  description: string;
  health?: "healthy" | "degraded" | "down";
  progress?: number;
  index: number;
}) {
  const statusTone = status === "active" || status === "running" ? "ok" : status === "planning" ? "accent" : status === "failed" ? "danger" : "default";
  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08 }}
      className="glass rounded-xl border border-border/50 p-4 space-y-2"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold truncate">{title}</h3>
        <Badge tone={statusTone as "ok" | "accent" | "danger" | "default"}>{status}</Badge>
      </div>
      <p className="text-[11px] text-muted line-clamp-2 leading-relaxed">{description}</p>
      {health && (
        <div className="flex items-center gap-3 text-[10px] text-faint">
          <span className="flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${health === "healthy" ? "bg-ok" : "bg-faint/30"}`} />
            Health
          </span>
          <span className="flex items-center gap-1">
            <span className={`h-1.5 w-1.5 rounded-full ${health !== "down" ? "bg-warn" : "bg-faint/30"}`} />
            Status
          </span>
        </div>
      )}
      {progress !== undefined && (
        <div className="h-1 w-full rounded-full bg-border/30 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent to-info transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      )}
    </motion.div>
  );
}

// ── Agent Fleet Card (Left Column) ──
function AgentFleetCard({
  provider,
  status,
  latency,
  taskCount,
  index,
}: {
  provider: string;
  status: string;
  latency: number;
  taskCount: number;
  index: number;
}) {
  const color = cmdColor(provider);
  const isHealthy = status === "healthy";
  const isDegraded = status === "degraded" || taskCount > 5;

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      className="glass rounded-lg px-3 py-2 border-l-[3px] flex items-center gap-2.5"
      style={{ borderLeftColor: color }}
    >
      <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill={color} opacity={isHealthy ? 0.9 : 0.5}>
        <path d="M21 16v-2l-8-5V3.5A1.5 1.5 0 0 0 11.5 2 1.5 1.5 0 0 0 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
      </svg>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold tracking-wide uppercase truncate">{provider}</span>
          <StatusDot status={status} pulse={isHealthy} />
        </div>
        <div className="flex items-center gap-2 text-[9px] text-faint/70">
          <span className="tabular-nums">{safeFixed(latency, 0)}ms</span>
          {taskCount > 0 && <span>{taskCount} tasks</span>}
        </div>
      </div>
      <div className="flex items-end gap-[2px]">
        {Array.from({ length: 5 }, (_, i) => (
          <span
            key={i}
            className={`block w-[2px] rounded-[1px] ${i < (isHealthy ? 4 : isDegraded ? 2 : 1) ? "bg-current" : "bg-border/20"}`}
            style={{ color, height: `${4 + i * 3}px` }}
          />
        ))}
      </div>
    </motion.div>
  );
}

// ── Chart Panel (Right Column) ──
function ChartPanel() {
  // Generate sample data for the chart
  const dataPoints = Array.from({ length: 24 }, (_, i) => ({
    hour: i,
    agents: Math.floor(40 + Math.sin(i / 3) * 30 + Math.random() * 20),
    resources: Math.floor(30 + Math.cos(i / 4) * 25 + Math.random() * 15),
  }));

  const maxAgents = Math.max(...dataPoints.map((d) => d.agents));
  const maxResources = Math.max(...dataPoints.map((d) => d.resources));

  return (
    <Panel title="Agent Activity" subtitle="Last 24 hours" className="min-h-[200px]">
      <div className="flex items-center gap-4 mb-3 text-[10px]">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent" />
          <span className="text-faint">Active Agents</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-warn" />
          <span className="text-faint">Resources</span>
        </span>
      </div>
      <div className="relative h-32 w-full">
        <svg viewBox="0 0 480 120" className="h-full w-full" preserveAspectRatio="none">
          {/* Grid lines */}
          {[0, 30, 60, 90, 120].map((y) => (
            <line key={y} x1="0" y1={y} x2="480" y2={y} stroke="rgb(var(--border) / 0.2)" strokeWidth="0.5" />
          ))}
          {/* Agents line (accent) */}
          <polyline
            points={dataPoints.map((d, i) => `${(i / 23) * 480},${120 - (d.agents / maxAgents) * 100}`).join(" ")}
            fill="none"
            stroke="rgb(var(--accent))"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          {/* Resources line (warn) */}
          <polyline
            points={dataPoints.map((d, i) => `${(i / 23) * 480},${120 - (d.resources / maxResources) * 100}`).join(" ")}
            fill="none"
            stroke="rgb(var(--warn))"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeDasharray="4 4"
          />
        </svg>
      </div>
      <div className="flex justify-between mt-1 text-[8px] text-faint/50">
        {["00", "04", "08", "12", "16", "20", "24"].map((h) => (
          <span key={h}>{h}:00</span>
        ))}
      </div>
    </Panel>
  );
}

// ── Event Log Panel (Right Column) ──
function EventLogPanel({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  return (
    <Panel
      title="Event Log"
      subtitle={`${events.length} events`}
      className="min-h-[200px]"
      actions={
        <div className="flex items-center gap-1.5 text-[10px]">
          <button className="rounded-md border border-border/40 px-2 py-1 hover:bg-surface/30 transition">
            List
          </button>
          <button className="rounded-md border border-border/40 px-2 py-1 hover:bg-surface/30 transition">
            Grid
          </button>
        </div>
      }
    >
      <div className="min-h-0 max-h-[240px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1">
        <AnimatePresence mode="popLayout">
          {events.slice(0, 50).map((e, i) => {
            const isFail = e.topic?.includes("fail") || e.topic?.includes("denied") || e.topic?.includes("error");
            const isOk = e.topic?.includes("complete") || e.topic?.includes("start") || e.topic?.includes("healthy");
            return (
              <motion.div
                key={e.id || `evt-${i}`}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: Math.max(0.4, 1 - i * 0.02), y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-2 rounded-lg px-2 py-1 font-mono text-[10px] hover:bg-surface/40"
              >
                <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${isFail ? "bg-danger" : isOk ? "bg-ok" : "bg-faint/40"}`} />
                <span className="w-28 shrink-0 truncate text-faint">{e.topic?.split(".").slice(0, 2).join(".") ?? "—"}</span>
                <span className="flex-1 truncate text-muted">{e.source}</span>
                <span className="shrink-0 text-faint/50">{new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {events.length === 0 && <Empty title="No events" hint="EventBus traffic appears here." />}
      </div>
    </Panel>
  );
}

// ── Main Component ──
export function MissionOverview() {
  const m = useStore(useShallow(selectMetrics));
  const agents = useStore((s) => s.agents);
  const providers = useStore((s) => s.providers);
  const events = useStore((s) => s.events);
  const connected = useStore((s) => s.connected);

  const [providersData, setProvidersData] = useState<ProviderHealthRecord[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void useStore.getState().hydrate();
    api.providerHealth().then((data) => setProvidersData(Array.isArray(data) ? data : [])).catch(() => {});
    api.capabilities().then((data) => setCaps(Array.isArray(data) ? data : [])).catch(() => {});
    api.audit().then((data) => setAudit(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  const isEventBusLive = connected;
  const healthy = Object.values(providers).filter((p) => p.status === "healthy").length;
  const running = Object.values(agents).filter((a) => a.status === "running").length;
  const agentCount = m.agents;
  const providerCount = m.providers;
  const recentPulses = events.filter((e) => Date.now() - new Date(e.timestamp).getTime() < 5000).length;

  const allProviders = useMemo(() => {
    const merged: ProviderHealthRecord[] = Array.isArray(providersData) ? [...providersData] : [];
    for (const p of Object.values(providers)) {
      if (!merged.find((d) => d.provider?.toLowerCase() === p.provider?.toLowerCase())) {
        merged.push(p as unknown as ProviderHealthRecord);
      }
    }
    for (const a of Object.values(agents)) {
      const providerName = a.provider || a.id;
      if (!merged.find((d) => d.provider?.toLowerCase() === providerName?.toLowerCase())) {
        merged.push({
          provider: providerName,
          status: a.health === "healthy" ? "healthy" : a.health === "degraded" ? "degraded" : "down",
          latency_ms: 0,
        } as unknown as ProviderHealthRecord);
      }
    }
    return merged.filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );
  }, [providersData, providers, agents]);

  const taskCounts = useMemo(() => {
    const tc: Record<string, number> = {};
    for (const a of Object.values(agents)) {
      if (a.provider) tc[a.provider] = (tc[a.provider] || 0) + 1;
    }
    return tc;
  }, [agents]);

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_2fr]">
      {/* ── TOP BAR — full width ── */}
      <div className="col-span-full flex flex-wrap items-center gap-4 rounded-xl border border-border/50 bg-surface/30 backdrop-blur-lg px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className={`h-2.5 w-2.5 rounded-full ${isEventBusLive ? "bg-ok animate-pulse" : "bg-danger"}`} />
          <span className="text-xs font-bold tracking-[0.15em] uppercase">AI Command Center</span>
        </div>
        <span className="h-4 w-px bg-border/40" />
        <div className="flex items-center gap-3 text-[11px] text-faint">
          <span>{agentCount} agents</span>
          <span>·</span>
          <span>{providerCount} providers</span>
          <span>·</span>
          <span>{recentPulses} pulses/5s</span>
          <span>·</span>
          <span className={m.errors ? "text-danger" : "text-ok"}>{m.errors || 0} errors</span>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[10px] text-faint">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isEventBusLive ? "bg-ok" : "bg-danger"}`} />
          {connected ? "EventBus LIVE" : "EventBus Local"}
        </div>
      </div>

      {/* ── LEFT COLUMN: Mission Cards + Agent Fleet ── */}
      <div className="flex flex-col gap-3 min-h-0">
        {/* Mission Cards */}
        <div className="flex flex-col gap-2.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-faint/50 px-1">Active Missions</div>
          <MissionCard
            title="System Initialization"
            status="active"
            description="Core runtime discovery and brain registry initialization in progress."
            health="healthy"
            progress={85}
            index={0}
          />
          <MissionCard
            title="Agent Fleet Scan"
            status="running"
            description="Scanning for available AI runtimes and binding providers."
            health="degraded"
            progress={60}
            index={1}
          />
          <MissionCard
            title="Capability Registration"
            status="planning"
            description="Registering 11 built-in capabilities with the discovery engine."
            progress={30}
            index={2}
          />
        </div>

        {/* Agent Fleet */}
        <Panel
          title="Agent Fleet"
          subtitle="Live air traffic control"
          className="flex-1 min-h-0"
          actions={
            <div className="flex items-center gap-1.5 text-[10px]">
              <Badge tone="ok">{allProviders.filter((p) => p.status === "healthy").length} healthy</Badge>
              <Badge tone="default">{allProviders.length} total</Badge>
            </div>
          }
        >
          <div className="min-h-0 max-h-[300px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1.5">
            {allProviders.filter((p) => p?.provider).map((p, i) => (
              <AgentFleetCard
                key={`agent-${i}`}
                provider={p.provider}
                status={p.status}
                latency={p.latency_ms}
                taskCount={taskCounts[p.provider] || 0}
                index={i}
              />
            ))}
            {allProviders.length === 0 && (
              <Empty title="No agents detected" hint="Agents appear when they register with the EventBus." />
            )}
          </div>
        </Panel>

        {/* System Control */}
        <SystemControl className="shrink-0" />
      </div>

      {/* ── RIGHT COLUMN: KPI Stats + Chart + Event Log ── */}
      <div className="flex flex-col gap-3 min-h-0">
        {/* KPI Stat Cards Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="Active Agents" value={agentCount} delta={`${running} running`} tone="accent" />
          <KpiCard label="Running Tasks" value={m.tasks || 0} delta="live" tone="ok" />
          <KpiCard
            label="Uptime"
            value="99.2%"
            delta="30d window"
            tone="ok"
          />
          <KpiCard
            label="Avg Response"
            value="2.1s"
            delta="p95 latency"
            tone="default"
          />
        </div>

        {/* Chart Panel */}
        <ChartPanel />

        {/* Event Log */}
        <EventLogPanel events={events} />

        {/* Mission Log + Capabilities row */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Panel title="Mission Log" subtitle="Security audit trail" className="min-h-[120px]">
            <div className="min-h-0 max-h-[120px] overflow-y-auto overflow-x-hidden no-scrollbar divide-y divide-border/30">
              {audit.length > 0 ? audit.slice(0, 8).map((e) => (
                <div key={e.id} className="flex items-center gap-2 py-1.5 text-[10px]">
                  <span className="w-20 shrink-0 truncate text-faint">{e.action}</span>
                  <span className="flex-1 truncate text-muted">{e.target || e.principal}</span>
                  <Badge tone={e.outcome === "deny" ? "danger" : e.outcome === "allow" ? "ok" : "default"}>{e.outcome}</Badge>
                </div>
              )) : <Empty title="No audit entries" />}
            </div>
          </Panel>

          <Panel title="Capabilities" subtitle={`${caps.length} registered`} className="min-h-[120px]">
            <div className="flex flex-wrap gap-1.5">
              {caps.length > 0 ? caps.map((c, i) => (
                <Badge key={`cap-${i}`} tone={c.requires_approval ? "warn" : "default"}>{c.name}</Badge>
              )) : <Empty title="No capabilities" hint="Capabilities appear when providers register." />}
            </div>
          </Panel>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="col-span-full rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">
          {error}
        </div>
      )}
    </div>
  );
}
