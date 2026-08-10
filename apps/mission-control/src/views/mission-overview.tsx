"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
import { safeFixed } from "@/lib/safe";
import { SystemControl } from "@/components/system-control";
import type { ProviderHealthRecord, CapabilityInfo, AuditEntry, MissionType, GatewayHealth } from "@/lib/types";

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

/** Format a seconds value as a compact human uptime (e.g. "3d 4h"). */
export function formatUptime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${Math.floor(seconds % 60)}s`;
  return `${Math.floor(seconds)}s`;
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
    <div className="glass rounded-xl px-4 py-3 flex flex-col gap-1 panel-glow">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${toneClass}`}>{value}</div>
      {delta && <div className="text-[10px] text-faint/70 truncate">{delta}</div>}
    </div>
  );
}

// ── Mission Card (Left Column) — real missions from the store ──
function MissionCard({ mission, index }: { mission: MissionType; index: number }) {
  const taskCount = mission.plan?.task_count ?? 0;
  const completed = mission.plan?.tasks?.filter((t) => t.status === "completed").length ?? 0;
  const progress = taskCount > 0 ? Math.round((completed / taskCount) * 100) : 0;
  const statusTone =
    mission.status === "executing" || mission.status === "running"
      ? "ok"
      : mission.status === "planning" || mission.status === "planned"
        ? "accent"
        : mission.status === "failed"
          ? "danger"
          : "default";

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.08 }}
      className="glass rounded-xl border border-border/50 p-4 space-y-2 panel-glow"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <StatusDot status={mission.status} pulse={mission.status === "executing"} />
          <h3 className="text-sm font-semibold truncate">{mission.title}</h3>
        </div>
        <Badge tone={statusTone as "ok" | "accent" | "danger" | "default"}>{mission.status}</Badge>
      </div>
      <p className="text-[11px] text-muted line-clamp-2 leading-relaxed">
        {mission.description || "(no description)"}
      </p>
      {(mission.status === "executing" || mission.status === "paused") && taskCount > 0 && (
        <div className="beam h-1 w-full overflow-hidden rounded-full bg-border/30">
          <div
            className="h-full rounded-full bg-gradient-to-r from-accent to-info transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
      {taskCount > 0 && (
        <div className="flex items-center gap-3 text-[10px] text-faint">
          <span>{taskCount} tasks</span>
          {progress > 0 && <span>{progress}%</span>}
          {mission.deadline && <span>Due {new Date(mission.deadline).toLocaleDateString()}</span>}
        </div>
      )}
      {mission.error && (
        <div className="text-[10px] text-danger truncate" title={mission.error}>
          ⚠ {mission.error}
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

// ── Chart Panel (Right Column) — real EventBus volume over the last 24h ──
function ActivityChart({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  const { buckets, max } = useMemo(() => {
    const now = Date.now();
    const HOURS = 24;
    const window = HOURS * 3600 * 1000;
    const buckets: { events: number; errors: number }[] = [];
    for (let i = 0; i < HOURS; i++) {
      const start = now - (HOURS - i) * 3600 * 1000;
      const end = start + 3600 * 1000;
      let count = 0;
      let errs = 0;
      for (const e of events) {
        const t = new Date(e.timestamp).getTime();
        if (t >= start && t < end) {
          count++;
          if (e.topic?.includes("fail") || e.topic?.includes("error") || e.topic?.includes("denied")) errs++;
        }
      }
      buckets.push({ events: count, errors: errs });
    }
    const peak = Math.max(1, ...buckets.flatMap((b) => [b.events, b.errors]));
    return { buckets, max: peak };
  }, [events]);

  return (
    <Panel title="Agent Activity" subtitle="EventBus volume · last 24 hours" className="min-h-[200px]">
      <div className="flex items-center gap-4 mb-3 text-[10px]">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-accent" />
          <span className="text-faint">Events</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-danger" />
          <span className="text-faint">Failures</span>
        </span>
      </div>
      <div className="relative h-32 w-full">
        <svg viewBox="0 0 480 120" className="h-full w-full" preserveAspectRatio="none">
          {/* Grid lines */}
          {[0, 30, 60, 90, 120].map((y) => (
            <line key={y} x1="0" y1={y} x2="480" y2={y} stroke="rgb(var(--border) / 0.2)" strokeWidth="0.5" />
          ))}
          {/* Events line (accent) */}
          <polyline
            points={buckets.map((b, i) => `${(i / 23) * 480},${120 - (b.events / max) * 100}`).join(" ")}
            fill="none"
            stroke="rgb(var(--accent))"
            strokeWidth="2"
            strokeLinejoin="round"
          />
          {/* Errors line (danger) */}
          <polyline
            points={buckets.map((b, i) => `${(i / 23) * 480},${120 - (b.errors / max) * 100}`).join(" ")}
            fill="none"
            stroke="rgb(var(--danger))"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeDasharray="4 4"
          />
        </svg>
      </div>
      <div className="flex justify-between mt-1 text-[8px] text-faint/50">
        {["24h", "18h", "12h", "6h", "now"].map((h) => (
          <span key={h}>{h}</span>
        ))}
      </div>
    </Panel>
  );
}

// ── Event Log Panel (Right Column) — real events with working view toggle ──
function EventLogPanel({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  const [mode, setMode] = useState<"list" | "grid">("list");

  return (
    <Panel
      title="Event Log"
      subtitle={`${events.length} events`}
      className="min-h-[200px]"
      actions={
        <div role="group" aria-label="Event log view mode" className="flex items-center gap-1.5 text-[10px]">
          <button
            onClick={() => setMode("list")}
            aria-pressed={mode === "list"}
            className={`rounded-md border px-2 py-1 transition ${
              mode === "list" ? "border-accent/50 bg-accent/15 text-accent" : "border-border/40 hover:bg-surface/30"
            }`}
          >
            List
          </button>
          <button
            onClick={() => setMode("grid")}
            aria-pressed={mode === "grid"}
            className={`rounded-md border px-2 py-1 transition ${
              mode === "grid" ? "border-accent/50 bg-accent/15 text-accent" : "border-border/40 hover:bg-surface/30"
            }`}
          >
            Grid
          </button>
        </div>
      }
    >
      {events.length === 0 ? (
        <Empty title="No events" hint="EventBus traffic appears here." />
      ) : mode === "list" ? (
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
        </div>
      ) : (
        <div className="grid min-h-0 max-h-[240px] grid-cols-1 gap-1.5 overflow-y-auto overflow-x-hidden no-scrollbar sm:grid-cols-2">
          {events.slice(0, 50).map((e, i) => {
            const isFail = e.topic?.includes("fail") || e.topic?.includes("denied") || e.topic?.includes("error");
            return (
              <motion.div
                key={e.id || `grd-${i}`}
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={`rounded-lg border px-2 py-1.5 font-mono text-[10px] hover:bg-surface/40 ${
                  isFail ? "border-danger/30 bg-danger/5" : "border-border/30"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${isFail ? "bg-danger" : "bg-accent/60"}`} />
                  <span className="truncate text-faint">{e.topic ?? "—"}</span>
                </div>
                <div className="mt-0.5 truncate text-muted">{e.source}</div>
              </motion.div>
            );
          })}
        </div>
      )}
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
  const missions = useStore((s) => s.missions);

  const [providersData, setProvidersData] = useState<ProviderHealthRecord[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [gwHealth, setGwHealth] = useState<GatewayHealth | null>(null);

  useEffect(() => {
    void useStore.getState().hydrate();
    api.providerHealth().then((data) => setProvidersData(Array.isArray(data) ? data : [])).catch(() => {});
    api.capabilities().then((data) => setCaps(Array.isArray(data) ? data : [])).catch(() => {});
    api.audit().then((data) => setAudit(Array.isArray(data) ? data : [])).catch(() => {});
    api.gatewayHealth().then((h) => setGwHealth(h)).catch(() => {});
  }, []);

  const isEventBusLive = connected;
  const healthy = Object.values(providers).filter((p) => p.status === "healthy").length;
  const running = Object.values(agents).filter((a) => a.status === "running").length;
  const agentCount = m.agents;
  const providerCount = m.providers;
  const recentPulses = events.filter((e) => Date.now() - new Date(e.timestamp).getTime() < 5000).length;

  // Real missions from the store (WebSocket-ingested), newest first.
  const missionList = useMemo(
    () =>
      Object.values(missions).sort(
        (a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
      ),
    [missions]
  );

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

  // Real avg response latency across live providers (no fabricated number).
  const avgLatency = useMemo(() => {
    const live = allProviders.filter((p) => p.status === "healthy" || p.status === "degraded");
    if (live.length === 0) return null;
    return Math.round(live.reduce((sum, p) => sum + (p.latency_ms || 0), 0) / live.length);
  }, [allProviders]);

  // Real gateway uptime (from /api/v1/gateway/health). Offline → "—".
  const gwUp = gwHealth?.status === "active";
  const uptime = gwUp ? formatUptime(gwHealth.uptime_seconds) : "—";
  const uptimeDelta = gwUp
    ? `${gwHealth.requests_served} req served`
    : gwHealth?.status === "error"
      ? "gateway error"
      : "gateway offline";

  const taskCounts = useMemo(() => {
    const tc: Record<string, number> = {};
    for (const a of Object.values(agents)) {
      if (a.provider) tc[a.provider] = (tc[a.provider] || 0) + 1;
    }
    return tc;
  }, [agents]);

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_2fr] no-hscroll">
      {/* ── TOP BAR — full width, command center strip ── */}
      <div className="cmd-bar col-span-full flex-wrap px-4 py-2.5 no-hscroll">
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
        {/* Mission Cards — real store missions */}
        <div className="flex flex-col gap-2.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-faint/50 px-1">
            Active Missions · {missionList.length}
          </div>
          {missionList.length === 0 ? (
            <Empty title="No active missions" hint="Missions appear here when created in Mission Orchestrator." />
          ) : (
            missionList.slice(0, 6).map((ms, i) => (
              <MissionCard key={`${ms.id}-${ms.status}`} mission={ms} index={i} />
            ))
          )}
        </div>

        {/* Agent Fleet */}
        <Panel
          title="Agent Fleet"
          subtitle="Live air traffic control"
          className="flex-1 min-h-0"
          actions={
            <div className="flex items-center gap-1.5 text-[10px]">
              <Badge tone="ok">{healthy} healthy</Badge>
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
        {/* KPI Stat Cards Row — all real values */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard label="Active Agents" value={agentCount} delta={`${running} running`} tone="accent" />
          <KpiCard label="Running Tasks" value={m.tasks || 0} delta="live" tone="ok" />
          <KpiCard label="Uptime" value={uptime} delta={uptimeDelta} tone={gwUp ? "ok" : "warn"} />
          <KpiCard
            label="Avg Response"
            value={avgLatency !== null ? `${avgLatency}ms` : "—"}
            delta={avgLatency !== null ? "live latency" : "no live providers"}
            tone="default"
          />
        </div>

        {/* Chart Panel — real EventBus activity */}
        <ActivityChart events={events} />

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
    </div>
  );
}
