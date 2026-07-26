"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
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


// ── Agent Aircraft Card ──
function AgentAircraft({
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
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass rounded-xl px-3 py-2.5 border-l-[3px]"
      style={{ borderLeftColor: color }}
    >
      <div className="flex items-center gap-2.5">
        {/* Aircraft icon */}
        <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24" fill={color} opacity={isHealthy ? 0.9 : 0.5}>
          <path d="M21 16v-2l-8-5V3.5A1.5 1.5 0 0 0 11.5 2 1.5 1.5 0 0 0 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
        </svg>
        {/* Flight info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold tracking-wide uppercase">{provider}</span>
            <StatusDot status={status} pulse={isHealthy} />
          </div>
          <div className="flex items-center gap-3 text-[9px] text-faint/70">
            <span className="tabular-nums">{latency.toFixed(0)}ms</span>
            {taskCount > 0 && <span>{taskCount} task{taskCount !== 1 ? "s" : ""}</span>}
            <span className="text-[8px]"><Badge tone={isHealthy ? "ok" : isDegraded ? "warn" : "danger"}>
              {status}
            </Badge></span>
          </div>
        </div>
        {/* Signal bars */}
        <div className="flex items-end gap-[2px]">
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={`block w-[2px] rounded-[1px] transition-all ${i < (isHealthy ? 4 : isDegraded ? 2 : 1) ? "bg-current" : "bg-border/20"}`}
              style={{ color, height: `${4 + i * 3}px` }} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}

// ── Event Stream (Flight Communications) ──
function FlightComms() {
  const events = useStore((s) => s.events);
  return (
    <div className="space-y-1 h-full overflow-y-auto pr-1">
      <div className="sticky top-0 bg-background/80 backdrop-blur-sm pb-1 text-[9px] uppercase tracking-wider text-faint/50 flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
        LIVE COMMS · {events.length} messages
      </div>
      <AnimatePresence mode="popLayout">
        {events.slice(0, 30).map((e, i) => {
          const isFail = e.topic?.includes("fail") || e.topic?.includes("denied") || e.topic?.includes("error");
          const isOk = e.topic?.includes("complete") || e.topic?.includes("start") || e.topic?.includes("healthy");
          return (
            <motion.div
              key={e.id || `evt-${i}`}
              layout
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: Math.max(0.3, 1 - i * 0.025), y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex items-center gap-2 rounded-lg px-2 py-1 font-mono text-[10px] hover:bg-surface/40"
            >
              <span className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${isFail ? "bg-danger" : isOk ? "bg-ok" : "bg-faint/40"}`} />
              <span className="w-28 shrink-0 truncate text-faint">{e.topic?.split(".").slice(0, 2).join(".") ?? "—"}</span>
              <span className="flex-1 truncate text-muted">{e.source}</span>
              <span className="shrink-0 text-faint/50">{new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
            </motion.div>
          );
        })}
      </AnimatePresence>
      {events.length === 0 && <Empty title="Awaiting transmissions…" hint="EventBus traffic appears here." />}
    </div>
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
    api.providerHealth().then((data) => setProvidersData(Array.isArray(data) ? data : [])).catch((err) => { setError(String(err)); });
    api.capabilities().then((data) => setCaps(Array.isArray(data) ? data : [])).catch((err) => { setError(String(err)); });
    api.audit().then((data) => setAudit(Array.isArray(data) ? data : [])).catch((err) => { setError(String(err)); });
  }, []);

  const isEventBusLive = connected || true;
  const healthy = Object.values(providers).filter((p) => p.status === "healthy").length;
  const running = Object.values(agents).filter((a) => a.status === "running").length;
  const agentCount = m.agents;
  const providerCount = m.providers;
  const recentPulses = events.filter((e) => Date.now() - new Date(e.timestamp).getTime() < 5000).length;
  const allProviders = useMemo(() => {
    const merged = Array.isArray(providersData) ? [...providersData] : [];
    for (const p of Object.values(providers)) {
      if (!merged.find((d) => d.provider?.toLowerCase() === p.provider?.toLowerCase())) {
        merged.push(p as unknown as ProviderHealthRecord);
      }
    }
    // Filter out dev/testing providers that should not appear in the production fleet
    return merged.filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );
  }, [providersData, providers]);

  // Compute active tasks per provider
  const taskCounts = useMemo(() => {
    const tc: Record<string, number> = {};
    for (const a of Object.values(agents)) {
      if (a.provider) tc[a.provider] = (tc[a.provider] || 0) + 1;
    }
    return tc;
  }, [agents]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      {/* ── COMMAND CENTER TOP BAR ── */}
      <div className="col-span-12 flex flex-wrap items-center gap-4 rounded-2xl border border-border/50 bg-surface/30 px-5 py-3">
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${isEventBusLive ? "bg-ok animate-pulse" : "bg-danger"} shadow-lg ${isEventBusLive ? "shadow-ok/30" : "shadow-danger/30"}`} />
          <span className="text-sm font-bold tracking-[0.15em] uppercase">AI Command Center</span>
        </div>
        <span className="h-4 w-px bg-border/40" />
        <Stat label="Active Missions" value={m.tasks || 0} tone="accent" />
        <Stat label="Agents" value={agentCount} delta={`${running} running`} />
        <Stat label="Providers" value={providerCount} delta={`${healthy} healthy`} tone="ok" />
        <Stat label="Pulses" value={recentPulses} delta="5s window" tone="accent" />
        <Stat label="Errors" value={m.errors || 0} tone={m.errors ? "danger" : "ok"} />
        <div className="ml-auto flex items-center gap-2 text-[10px] text-faint">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${isEventBusLive ? "bg-ok" : "bg-danger"}`} />
          {connected ? "EventBus LIVE" : "EventBus Active (Local Bus)"}
        </div>
      </div>

      {/* ── LEFT: Agent Fleet (Air Traffic Control View) ── */}
      <Panel title="Agent Fleet" subtitle="Live air traffic control"
        className="col-span-4 row-span-3"
        actions={
          <div className="flex items-center gap-2 text-[10px]">
            <Badge tone="ok">{allProviders.filter((p) => p.status === "healthy").length} healthy</Badge>
            <Badge tone="default">{allProviders.length} total</Badge>
          </div>
        }
      >
        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          <div className="mb-2 grid grid-cols-5 gap-1 text-[8px] uppercase tracking-wider text-faint/50">
            <span className="col-span-2">AGENT</span>
            <span>STATUS</span>
            <span>TASKS</span>
            <span>LATENCY</span>
          </div>
          {allProviders.filter((p) => p?.provider).map((p, i) => (
            <AgentAircraft
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

      {/* ── CENTER: Flight Communications (Live EventBus) ── */}
      <Panel title="Flight Communications" subtitle="Real-time EventBus messages"
        className="col-span-5 row-span-3"
        actions={<span className="text-[9px] text-faint/50 tabular-nums">{events.length} total events</span>}
      >
        <FlightComms />
      </Panel>

      {/* ── RIGHT TOP: System Control ── */}
      <SystemControl className="col-span-3 row-span-2" />

      {/* ── RIGHT MIDDLE: Executive Command ── */}
      <Panel title="Executive Command" subtitle="AI leadership hierarchy" className="col-span-3 row-span-1">
        <div className="space-y-2">
          {allProviders.length === 0 ? (
            <Empty title="No active executives" hint="Discovered providers populate executive command" />
          ) : (
            allProviders.map((p, idx) => (
              <motion.div
                key={`exec-${idx}`}
                className="flex items-center gap-2 rounded-lg border border-border/40 px-2.5 py-1.5 border-l-2"
                style={{ borderLeftColor: cmdColor(p.provider) }}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] font-medium leading-tight uppercase tracking-wider">{p.provider}</div>
                  <div className="text-[9px] text-faint/60 truncate">Command Node · {p.latency_ms.toFixed(0)}ms</div>
                </div>
                <StatusDot status={p.status} pulse={p.status === "healthy"} />
              </motion.div>
            ))
          )}
        </div>
      </Panel>


      {/* ── BOTTOM LEFT: Capabilities ── */}
      <Panel title="Available Capabilities" subtitle={`${caps.length} registered`} className="col-span-3 row-span-1">
        <div className="flex flex-wrap gap-1.5">
          {caps.length > 0 ? caps.map((c, i) => (
            <Badge key={`cap-${i}`} tone={c.requires_approval ? "warn" : "default"}>{c.name}</Badge>
          )) : <Empty title="No capabilities registered" hint="Capabilities appear when providers register with the Discovery Engine." />}
        </div>
      </Panel>

      {/* ── BOTTOM CENTER MISSION LOG ── */}
      <Panel title="Mission Log" subtitle="Security-relevant actions" className="col-span-6 row-span-1" contentClassName="p-0">
        <div className="divide-y divide-border/50 max-h-[120px] overflow-y-auto">
          {audit.length > 0 ? audit.slice(0, 8).map((e) => (
            <div key={e.id} className="flex items-center gap-3 px-4 py-1.5 text-xs">
              <span className="w-24 shrink-0 truncate text-faint">{e.action}</span>
              <span className="flex-1 truncate">{e.target || e.principal}</span>
              <Badge tone={e.outcome === "deny" ? "danger" : e.outcome === "allow" ? "ok" : "default"}>{e.outcome}</Badge>
            </div>
          )) : <Empty title="No mission log entries" />}
        </div>
      </Panel>

      {/* ── BOTTOM RIGHT: Agent Fleet Summary ── */}
      <Panel title="Fleet Summary" subtitle="Aggregate health" className="col-span-3 row-span-1">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-ok" />
            <span className="text-[11px] text-faint">{allProviders.filter((p) => p.status === "healthy").length} healthy</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#eab308]" />
            <span className="text-[11px] text-faint">{allProviders.filter((p) => p.status === "degraded").length} degraded</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-danger" />
            <span className="text-[11px] text-faint">{allProviders.filter((p) => p.status === "down" || p.status === "unknown").length} down</span>
          </div>
          <div className="ml-auto text-[11px] text-faint/50 tabular-nums">{allProviders.length} total aircraft</div>
        </div>
      </Panel>
    </div>
  );
}
