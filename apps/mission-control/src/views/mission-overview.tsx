"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
import { safeFixed } from "@/lib/safe";
import type { ProviderHealthRecord, CapabilityInfo, AuditEntry, MissionType, GatewayHealth } from "@/lib/types";

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

// ── Top Header KPI Cards ──
function MetricStatCard({
  label,
  value,
  subtitle,
  gradientBg,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
  gradientBg?: string;
}) {
  return (
    <div
      className="relative flex flex-col justify-between rounded-xl border border-white/10 p-4 transition-all duration-200"
      style={{
        background: gradientBg || "rgba(255, 255, 255, 0.03)",
        backdropFilter: "blur(16px)",
      }}
    >
      <div>
        <div className="text-3xl font-bold tracking-tight text-white/95 tabular-nums">
          {value}
        </div>
        <div className="mt-1 text-xs font-medium text-white/60">
          {label}
        </div>
      </div>
      {subtitle && (
        <div className="mt-2 text-[10px] text-white/40 truncate">
          {subtitle}
        </div>
      )}
    </div>
  );
}

// ── Left Cards (Active Mission / Agent Cards) ──
function MissionCardItem({ mission, index }: { mission: MissionType; index: number }) {
  const taskCount = mission.plan?.task_count ?? 0;
  const completed = mission.plan?.tasks?.filter((t) => t.status === "completed").length ?? 0;
  const progress = taskCount > 0 ? Math.round((completed / taskCount) * 100) : 0;
  const statusText = mission.status === "executing" || mission.status === "running" ? "Active" : mission.status;
  const isErr = mission.status === "failed" || Boolean(mission.error);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06 }}
      className="relative rounded-xl border border-white/10 bg-[#161a23]/70 p-4 backdrop-blur-md shadow-lg"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white/90 truncate pr-2">
          {mission.title || "Active Mission"}
        </h3>
        <span
          className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium ${
            isErr
              ? "bg-red-500/20 text-red-400 border border-red-500/30"
              : "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
          }`}
        >
          {isErr ? "!" : statusText}
        </span>
      </div>

      <p className="mt-1.5 text-xs text-white/50 line-clamp-2 leading-relaxed">
        {mission.description || "No description provided"}
      </p>

      {/* Health & Status Indicator dots */}
      <div className="mt-3 flex items-center justify-between text-xs text-white/70">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-[11px] text-white/70">Health</span>
          <span className="h-2 w-2 rounded-full bg-amber-400 ml-1" />
          <span className="text-[11px] text-white/70">Status</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
          <span className="h-1.5 w-1.5 rounded-full bg-red-400" />
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-indigo-400 transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
    </motion.div>
  );
}

// ── Agent Fleet Left Card fallback item ──
function DefaultAgentCard({ title, desc, badge = "Active", tone = "active", dots = ["emerald", "emerald", "amber", "red"] }: {
  title: string;
  desc: string;
  badge?: string;
  tone?: "active" | "error";
  dots?: string[];
}) {
  return (
    <div className="relative rounded-xl border border-white/10 bg-[#161a23]/70 p-4 backdrop-blur-md shadow-lg">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white/90 truncate pr-2">
          {title}
        </h3>
        <span
          className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-medium ${
            tone === "error"
              ? "bg-red-500/20 text-red-400 border border-red-500/30"
              : "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
          }`}
        >
          {badge}
        </span>
      </div>

      <p className="mt-1.5 text-xs text-white/50 line-clamp-2 leading-relaxed">
        {desc}
      </p>

      <div className="mt-3 flex items-center justify-between text-xs text-white/70">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-[11px] text-white/70">Status</span>
        </div>
        <div className="flex items-center gap-1">
          {dots.map((d, idx) => (
            <span
              key={idx}
              className={`h-1.5 w-1.5 rounded-full ${
                d === "emerald" ? "bg-emerald-400" : d === "amber" ? "bg-amber-400" : "bg-red-400"
              }`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Activity Line & Area Chart (Exact match for Screenshot) ──
function ActivityChart({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  const [timeRange, setTimeRange] = useState("Past 24 hours");

  // Generate real chart data from events bucketed into 16 time slots over the last 24h
  const now = Date.now();
  const SLOTS = 16;
  const WINDOW = 24 * 60 * 60 * 1000; // 24 hours
  const buckets = Array.from({ length: SLOTS }, (_, i) => {
    const slotStart = now - WINDOW + (i / SLOTS) * WINDOW;
    const slotEnd = now - WINDOW + ((i + 1) / SLOTS) * WINDOW;
    const count = events.filter(e => {
      const t = new Date(e.timestamp).getTime();
      return t >= slotStart && t < slotEnd;
    }).length;
    return count;
  });
  const maxBucket = Math.max(...buckets, 1);
  // Map to SVG Y coords (0 = top = busy, 120 = bottom = idle)
  const pointsActive = buckets.map((count, i) => [
    (i / (SLOTS - 1)) * 480,
    120 - (count / maxBucket) * 110,
  ]);

  // Resources line: track task/agent events specifically
  const resourceBuckets = Array.from({ length: SLOTS }, (_, i) => {
    const slotStart = now - WINDOW + (i / SLOTS) * WINDOW;
    const slotEnd = now - WINDOW + ((i + 1) / SLOTS) * WINDOW;
    const count = events.filter(e => {
      const t = new Date(e.timestamp).getTime();
      return t >= slotStart && t < slotEnd && (e.topic.startsWith('task.') || e.topic.startsWith('agent.'));
    }).length;
    return count;
  });
  const maxResource = Math.max(...resourceBuckets, 1);
  const pointsResources = resourceBuckets.map((count, i) => [
    (i / (SLOTS - 1)) * 480,
    120 - (count / maxResource) * 110,
  ]);

  const activePathD = "M " + pointsActive.map(([x, y]) => `${x},${y}`).join(" L ");
  const resourcesPathD = "M " + pointsResources.map(([x, y]) => `${x},${y}`).join(" L ");

  return (
    <div className="relative flex flex-col rounded-xl border border-white/10 bg-[#161a23]/70 p-5 backdrop-blur-md shadow-lg">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-semibold text-white/90">Agent Activity</h2>
          <p className="text-xs text-white/40 mt-0.5">Agent Activity</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-white/40">Last 24 activity</span>
          <button className="rounded-lg border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/80 hover:bg-white/10 transition">
            {timeRange}
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center justify-end gap-4 mb-2 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-cyan-400" />
          <span className="text-white/60">Active</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-amber-400" />
          <span className="text-white/60">Resources</span>
        </div>
      </div>

      {/* SVG Chart */}
      <div className="relative h-44 w-full">
        <svg viewBox="0 0 480 130" className="h-full w-full" preserveAspectRatio="none">
          {/* Horizontal grid lines */}
          <line x1="0" y1="10" x2="480" y2="10" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
          <line x1="0" y1="40" x2="480" y2="40" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
          <line x1="0" y1="70" x2="480" y2="70" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
          <line x1="0" y1="100" x2="480" y2="100" stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />

          {/* Highlight region overlay around 16pm - 20pm */}
          <rect x="350" y="10" width="45" height="110" fill="rgba(255,255,255,0.05)" rx="4" />

          {/* Active Area Fill */}
          <path
            d={`${activePathD} L 480,120 L 0,120 Z`}
            fill="url(#activeGradient)"
            opacity="0.25"
          />

          {/* Resources Area Fill */}
          <path
            d={`${resourcesPathD} L 480,120 L 0,120 Z`}
            fill="url(#resourcesGradient)"
            opacity="0.3"
          />

          {/* Lines */}
          <path d={activePathD} fill="none" stroke="#38bdf8" strokeWidth="2" strokeLinecap="round" />
          <path d={resourcesPathD} fill="none" stroke="#fbbf24" strokeWidth="2" strokeLinecap="round" />

          <defs>
            <linearGradient id="activeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" />
              <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
            </linearGradient>
            <linearGradient id="resourcesGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fbbf24" />
              <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
            </linearGradient>
          </defs>
        </svg>

        {/* Y Axis Labels — real event counts */}
        <div className="absolute top-0 left-0 text-[9px] text-white/30">{maxBucket}</div>
        <div className="absolute top-1/3 left-0 text-[9px] text-white/30">{Math.round(maxBucket / 2)}</div>
        <div className="absolute bottom-2 left-0 text-[9px] text-white/30">0</div>
      </div>

      {/* X Axis Time Labels */}
      <div className="flex justify-between mt-2 px-4 text-[10px] text-white/40">
        <span>00 am</span>
        <span>03 am</span>
        <span>06 am</span>
        <span>09 am</span>
        <span>12 am</span>
        <span>16 pm</span>
        <span>20 pm</span>
        <span>24 hrs</span>
      </div>
    </div>
  );
}

// ── Event Log (Exact Match for Screenshot) ──
function EventLogPanel({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  const logList = useMemo(() => {
    if (events.length === 0) {
      return [
        { agent: "System Orchestrator", msg: "EventBus connected · Awaiting mission dispatches" },
        { agent: "Runtime Registry", msg: "Background health and discovery monitors active" },
      ];
    }
    return events.slice(0, 10).map((e) => {
      const p = e.payload as Record<string, any>;
      const agentLabel = String(p.provider || p.agent_id || p.source || e.source || "EventBus");
      const detailMsg = String(p.title || p.command || p.status_text || e.topic || "Event processed");
      return {
        agent: agentLabel,
        msg: detailMsg,
      };
    });
  }, [events]);

  return (
    <div className="relative flex flex-col rounded-xl border border-white/10 bg-[#161a23]/70 p-5 backdrop-blur-md shadow-lg flex-1 min-h-[220px]">
      <div className="flex items-center justify-between mb-3 border-b border-white/5 pb-3">
        <h2 className="text-base font-semibold text-white/90">Event Log</h2>
        <div className="flex items-center gap-2 text-white/40">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      <div className="space-y-2.5 overflow-y-auto max-h-[200px] pr-1">
        {logList.map((item, idx) => (
          <div key={idx} className="flex items-center gap-3 text-xs">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
            <span className="w-36 shrink-0 font-medium text-white/70 truncate">{item.agent}</span>
            <span className="text-white/50 truncate">{item.msg}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main Component ──
export function MissionOverview() {
  const m = useStore(useShallow(selectMetrics));
  const agentsMap = useStore((s) => s.agents);
  const events = useStore((s) => s.events);
  const tasksMap = useStore((s) => s.tasks);
  const providersMap = useStore((s) => s.providers);
  const missions = useStore((s) => s.missions);
  const performance = useStore((s) => s.performance);

  const [gwHealth, setGwHealth] = useState<GatewayHealth | null>(null);

  useEffect(() => {
    void useStore.getState().hydrate();
    api.gatewayHealth().then((h) => setGwHealth(h)).catch(() => {});
  }, []);

  // Compute live metrics dynamically from active state
  const activeAgentCount = useMemo(() => {
    const storeAgentCount = Object.keys(agentsMap).length;
    const providerCount = Object.values(providersMap).filter(
      (p) => p.status === "healthy" || p.status === "unknown"
    ).length;
    return Math.max(storeAgentCount, providerCount, m.agents || 0);
  }, [agentsMap, providersMap, m.agents]);

  const runningTaskCount = useMemo(() => {
    return Object.values(tasksMap).filter((t) => t.status === "running" || t.status === "in_progress").length || m.tasks || 0;
  }, [tasksMap, m.tasks]);

  const uptimeVal = gwHealth?.status === "active"
    ? formatUptime(gwHealth.uptime_seconds)
    : performance?.uptime_seconds
    ? formatUptime(performance.uptime_seconds)
    : "100%";

  const avgResponse = m.latency > 0
    ? `${Math.round(m.latency)}ms`
    : performance?.uptime_seconds
    ? `<1s`
    : "—";

  const missionList = useMemo(
    () =>
      Object.values(missions).sort(
        (a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
      ),
    [missions]
  );

  return (
    <div className="flex flex-col h-full w-full max-w-full p-3 sm:p-6 bg-[#0c0e14] text-white overflow-y-auto no-hscroll min-h-full pb-12 space-y-4 sm:space-y-6">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between min-w-0">
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white/95 truncate">
          Mission Overview
        </h1>
      </div>

      {/* ── Main Layout Grid (Fully Responsive Column Breakdown) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-6 min-w-0">
        
        {/* LEFT COLUMN (Missions & Agent Cards) - 4 cols desktop, stacked on mobile */}
        <div className="lg:col-span-4 flex flex-col gap-4 min-w-0">
          {missionList.length > 0 ? (
            missionList.slice(0, 4).map((ms, idx) => (
              <MissionCardItem key={ms.id || idx} mission={ms} index={idx} />
            ))
          ) : Object.keys(agentsMap).length > 0 ? (
            Object.values(agentsMap)
              .sort((a, b) => {
                const aHost = a.role.includes("CLI") || a.role.includes("Agent") || a.role.includes("Code") || a.role.includes("Open") ? 1 : 0;
                const bHost = b.role.includes("CLI") || b.role.includes("Agent") || b.role.includes("Code") || b.role.includes("Open") ? 1 : 0;
                return bHost - aHost;
              })
              .slice(0, 4)
              .map((agent, idx) => {
                const isHealthy = agent.health === "healthy" || agent.status === "running" || agent.status === "idle" || agent.status === "recovered";
                const displayStatus = isHealthy ? (agent.status === "running" ? "active" : "idle") : agent.status;
                const cleanCaps = (agent.capabilities || []).filter((c) => !c.startsWith("cli:")).slice(0, 3).join(", ");
                return (
                  <DefaultAgentCard
                    key={agent.id || idx}
                    title={agent.role || `Agent ${idx + 1}`}
                    desc={`Status: ${displayStatus} · Health: ${agent.health} · Capabilities: ${cleanCaps || "General Execution"}`}
                    badge={isHealthy ? "Active" : agent.status}
                    tone={isHealthy ? "active" : "error"}
                    dots={isHealthy ? ["emerald", "emerald", "emerald", "emerald"] : ["amber", "amber", "amber", "red"]}
                  />
                );
              })
          ) : (
            <div className="rounded-xl border border-white/10 bg-[#161a23]/70 p-6 flex flex-col items-center gap-3 text-center">
              <div className="text-2xl">🛸</div>
              <div className="text-sm font-medium text-white/70">No active missions</div>
              <div className="text-xs text-white/40">Submit a mission from Prompt Center to see live data here.</div>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN (Stats, Chart, Logs) - 8 cols desktop, stacked on mobile */}
        <div className="lg:col-span-8 flex flex-col gap-4 sm:gap-6 min-w-0">
          
          {/* Top KPI Stat Cards Grid — 2 cols mobile, 4 cols tablet+ */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 min-w-0">
            <MetricStatCard
              label="Active Agents"
              value={activeAgentCount}
              gradientBg="linear-gradient(135deg, rgba(67, 56, 202, 0.25) 0%, rgba(30, 27, 75, 0.3) 100%)"
            />
            <MetricStatCard
              label="Running Tasks"
              value={runningTaskCount}
              gradientBg="linear-gradient(135deg, rgba(30, 58, 138, 0.25) 0%, rgba(15, 23, 42, 0.3) 100%)"
            />
            <MetricStatCard
              label="Uptime"
              value={uptimeVal}
              gradientBg="linear-gradient(135deg, rgba(6, 78, 59, 0.25) 0%, rgba(2, 44, 34, 0.3) 100%)"
            />
            <MetricStatCard
              label="Avg Response"
              value={avgResponse}
              gradientBg="linear-gradient(135deg, rgba(55, 65, 81, 0.25) 0%, rgba(17, 24, 39, 0.3) 100%)"
            />
          </div>

          {/* Activity Chart */}
          <ActivityChart events={events} />

          {/* Event Log */}
          <EventLogPanel events={events} />

        </div>

      </div>
    </div>
  );
}
