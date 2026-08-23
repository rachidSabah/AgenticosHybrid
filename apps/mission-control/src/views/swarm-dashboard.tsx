"use client";

import { useCallback, useEffect, useState, useMemo } from "react";
import { motion } from "framer-motion";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type {
  SwarmSummary,
  SwarmAgentInfo,
  SwarmTaskSummary,
  SwarmMetricsSummary,
} from "@/lib/types";

// Role-specific card themes and icons
const ROLE_CONFIGS: Record<
  string,
  {
    icon: string;
    border: string;
    bg: string;
    progressFrom: string;
    progressTo: string;
    badgeDot: string;
  }
> = {
  Leader: {
    icon: "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
    border: "border-cyan-500/40",
    bg: "bg-[#112430]/70",
    progressFrom: "from-cyan-400",
    progressTo: "to-cyan-200",
    badgeDot: "bg-cyan-400",
  },
  Planner: {
    icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
    border: "border-emerald-500/40",
    bg: "bg-[#112925]/70",
    progressFrom: "from-emerald-400",
    progressTo: "to-teal-300",
    badgeDot: "bg-emerald-400",
  },
  Researcher: {
    icon: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
    border: "border-blue-500/40",
    bg: "bg-[#13233c]/70",
    progressFrom: "from-blue-500",
    progressTo: "to-cyan-400",
    badgeDot: "bg-blue-400",
  },
  Coder: {
    icon: "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4",
    border: "border-purple-500/40",
    bg: "bg-[#241738]/70",
    progressFrom: "from-purple-500",
    progressTo: "to-fuchsia-400",
    badgeDot: "bg-purple-400",
  },
  Reviewer: {
    icon: "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
    border: "border-green-500/40",
    bg: "bg-[#11261d]/70",
    progressFrom: "from-green-400",
    progressTo: "to-emerald-300",
    badgeDot: "bg-green-400",
  },
  Validator: {
    icon: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
    border: "border-amber-500/40",
    bg: "bg-[#2d2417]/70",
    progressFrom: "from-amber-400",
    progressTo: "to-yellow-300",
    badgeDot: "bg-amber-400",
  },
  Executor: {
    icon: "M13 10V3L4 14h7v7l9-11h-7z",
    border: "border-orange-500/40",
    bg: "bg-[#2d1c15]/70",
    progressFrom: "from-orange-500",
    progressTo: "to-amber-400",
    badgeDot: "bg-orange-400",
  },
  Observer: {
    icon: "M15 12a3 3 0 11-6 0 3 3 0 016 0z M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z",
    border: "border-slate-500/40",
    bg: "bg-[#181c26]/70",
    progressFrom: "from-slate-400",
    progressTo: "to-slate-200",
    badgeDot: "bg-slate-400",
  },
};

interface AgentCardProps {
  role: string;
  agentId: string;
  action: string;
  task: string;
  progress: number | null;
}

function RoleAgentCard({ role, agentId, action, task, progress }: AgentCardProps) {
  const cfg = ROLE_CONFIGS[role] || ROLE_CONFIGS.Leader;

  return (
    <div
      className={`relative flex flex-col justify-between rounded-xl border ${cfg.border} ${cfg.bg} p-4 backdrop-blur-md shadow-lg h-[155px]`}
    >
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={`flex h-6 w-6 items-center justify-center rounded-md ${cfg.border} bg-white/5`}>
              <svg className="h-3.5 w-3.5 text-white/90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={cfg.icon} />
              </svg>
            </div>
            <h3 className="text-sm font-bold text-white/95">{role}</h3>
          </div>
          <button className="text-white/40 hover:text-white/80">
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>
        </div>

        <div className="mt-2 text-[11px] text-white/60 font-mono">
          Agent ID: <span className="text-white/80">{agentId}</span>
        </div>

        <div className="mt-1 text-[11px] text-white/70 line-clamp-1">
          <span className="text-white/40">Action:</span> {action}
        </div>

        <div className="mt-0.5 text-[11px] text-white/70 line-clamp-1">
          <span className="text-white/40">Task:</span> {task}
        </div>
      </div>

      <div className="mt-2">
        <div className="flex items-center justify-between">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10 mr-3">
            {progress !== null ? (
              <div
                className={`h-full rounded-full bg-gradient-to-r ${cfg.progressFrom} ${cfg.progressTo}`}
                style={{ width: `${progress}%` }}
              />
            ) : (
              <div className="h-full w-full bg-white/20" />
            )}
          </div>
          <span className="text-xs font-semibold text-white/80 tabular-nums">
            {progress !== null ? `${progress}%` : "N/A"}
          </span>
        </div>
      </div>
    </div>
  );
}

export function SwarmDashboard() {
  const [metrics, setMetrics] = useState<SwarmMetricsSummary | null>(null);
  const [swarms, setSwarms] = useState<SwarmSummary[]>([]);
  const [agents, setAgents] = useState<SwarmAgentInfo[]>([]);
  const [consensusList, setConsensusList] = useState<Array<{ round_id?: string; topic?: string; status?: string; votes_cast?: number; agents?: number }>>([]);
  const [chatInput, setChatInput] = useState("");
  const [userLogs, setUserLogs] = useState<Array<{ author: string; time: string; text: string; color: string }>>([]);

  const storeEvents = useStore((s) => s.events);

  const loadData = useCallback(async () => {
    try {
      const [m, s, a, c] = await Promise.all([
        api.swarmMetrics(),
        api.swarmList(),
        api.swarmAgents(),
        api.swarmConsensus(),
      ]);
      setMetrics(m);
      setSwarms(Array.isArray(s) ? s : []);
      setAgents(Array.isArray(a) ? a : []);
      if (Array.isArray(c)) {
        setConsensusList(c);
      }
    } catch {
      /* fallback graceful */
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  // Active swarm derived ONLY from real swarms (backend state)
  const activeSwarm = swarms.find((s) => s.status === "executing" || s.status === "active") || swarms[0] || null;
  const swarmName = activeSwarm?.name || "No active swarm";
  const swarmPattern = activeSwarm?.topology || "—";
  const swarmStatus = activeSwarm?.status || "idle";

  // Progress derived ONLY from real task completion (completed/total). No fabricated fallback.
  const overallProgress = useMemo(() => {
    if (metrics && metrics.total_tasks > 0) {
      return Math.round((metrics.completed_tasks / metrics.total_tasks) * 100);
    }
    return null; // no measurable progress — display "progress unavailable"
  }, [metrics]);

  // Role cards built ONLY from real registered swarm agents. No synthetic
  // role/percentage data: if fewer real agents exist, fewer cards render.
  const roleCards: AgentCardProps[] = useMemo(() => {
    return agents.slice(0, 8).map((a, idx) => {
      const role = a.role ? a.role.charAt(0).toUpperCase() + a.role.slice(1) : `Agent ${idx + 1}`;
      // Progress is only meaningful when the backend reports task metrics;
      // per-agent progress derives from nothing fabricated — null = unavailable.
      let progress: number | null = null;
      if (metrics && metrics.total_tasks > 0 && metrics.completed_tasks >= metrics.total_tasks) {
        progress = 100; // all real tasks completed
      }
      return {
        role,
        agentId: a.agent_id,
        action: `Status: ${a.status || "unknown"}`,
        task: a.capabilities?.length ? `Capabilities: ${a.capabilities.join(", ")}` : `Agent: ${a.name}`,
        progress,
      };
    });
  }, [agents, metrics]);

  // Live activity log = real EventBus events + operator messages ONLY.
  // No fabricated historical entries (the old 2024-05-15 demo logs are gone).
  const liveLogs = useMemo(() => {
    const realEventLogs = storeEvents.slice(0, 10).map((e) => ({
      author: `${e.source || "System"}`,
      time: new Date(e.timestamp).toLocaleTimeString(),
      text: `${e.topic}: ${typeof e.payload === "string" ? e.payload : JSON.stringify(e.payload || {})}`,
      color: "border-indigo-400 text-indigo-300",
    }));

    return [...userLogs, ...realEventLogs];
  }, [storeEvents, userLogs]);

  const handleSendMessage = () => {
    if (!chatInput.trim()) return;
    const newMsg = {
      author: "Operator (User)",
      time: new Date().toLocaleTimeString(),
      text: chatInput,
      color: "border-cyan-400 text-cyan-300",
    };
    setUserLogs((prev) => [newMsg, ...prev]);
    setChatInput("");
  };

  const timelineRoles = useMemo(() => {
    if (agents.length > 0) {
      const colors = [
        "border-cyan-500 text-cyan-300 bg-cyan-500/10",
        "border-emerald-500 text-emerald-300 bg-emerald-500/10",
        "border-green-500 text-green-300 bg-green-500/10",
        "border-amber-500 text-amber-300 bg-amber-500/10",
        "border-orange-500 text-orange-300 bg-orange-500/10",
        "border-slate-500 text-slate-300 bg-slate-500/10",
      ];
      return agents.slice(0, 6).map((a, i) => {
        const parts = colors[i % colors.length].split(" ");
        return {
          name: a.role || `Agent-${i + 1}`,
          id: a.agent_id.slice(0, 8),
          action: `${a.role || "Agent"} ${a.status || "registered"}`,
          color: `${parts[0]} ${parts[1]}`,
          bg: parts[2],
        };
      });
    }
    // No real agents registered — return empty (renders nothing fake)
    return [];
  }, [agents]);

  // Metrics telemetry derived ONLY from real API values; honest "N/A" otherwise.
  const throughputStr = metrics && typeof metrics.completed_tasks === "number" && metrics.total_tasks > 0
    ? `${metrics.completed_tasks} of ${metrics.total_tasks} tasks completed`
    : "no tasks yet";
  const overheadStr = metrics && typeof metrics.avg_latency_ms === "number" && metrics.avg_latency_ms > 0
    ? `${metrics.avg_latency_ms.toFixed(0)}ms avg latency`
    : "latency N/A";
  const successRateStr = metrics && typeof metrics.total_tasks === "number" && metrics.total_tasks > 0
    ? `${Math.round((((metrics.total_tasks - (metrics.failed_tasks || 0)) / metrics.total_tasks) * 100))}%`
    : "no executions yet";

  return (
    <div className="flex h-full w-full max-w-full flex-col p-3 sm:p-6 pb-12 bg-[#0c0d14] text-white overflow-y-auto no-hscroll space-y-4">
      {/* Top Banner Card: Swarm Status */}
      <div className="relative rounded-2xl border border-white/10 bg-[#141724]/80 p-4 sm:p-5 backdrop-blur-md shadow-xl min-w-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-bold text-white/95 tracking-wide truncate">
              {swarmName}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-4 sm:gap-8 text-xs">
              <div>
                <span className="text-white/40 block text-[10px] uppercase font-medium">Pattern</span>
                <span className="font-semibold text-white/90">{swarmPattern}</span>
              </div>
              <div>
                <span className="text-white/40 block text-[10px] uppercase font-medium">Status</span>
                <span className="font-semibold text-white/90">{swarmStatus}</span>
              </div>
            </div>
          </div>
          <span className={`inline-flex items-center rounded-lg border px-3 py-1 text-xs font-semibold shrink-0 ${
            activeSwarm
              ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
              : "border-white/10 bg-white/5 text-white/40"
          }`}>
            {activeSwarm ? "Active swarm" : "No swarm"}
          </span>
        </div>

        {/* Progress bar — only rendered when real task metrics exist */}
        <div className="mt-4 flex items-center justify-between gap-3 min-w-0">
          <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/10">
            {overallProgress !== null ? (
              <div
                className="h-full rounded-full bg-gradient-to-r from-fuchsia-500 via-cyan-400 to-emerald-400 transition-all duration-700"
                style={{ width: `${overallProgress}%` }}
              />
            ) : (
              <div className="h-full w-0" />
            )}
          </div>
          <span className="text-sm font-bold text-white/90 tabular-nums shrink-0">
            {overallProgress !== null ? `${overallProgress}%` : "progress unavailable"}
          </span>
        </div>
      </div>

      {/* Main Content Grid: 8 Role Cards & Log/Consensus/Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-w-0">
        {/* Left Column (real agent cards; honest empty state when none) */}
        <div className="lg:col-span-8 grid grid-cols-1 sm:grid-cols-2 gap-3 min-w-0">
          {roleCards.length > 0 ? (
            roleCards.map((card) => (
              <RoleAgentCard key={card.role + card.agentId} {...card} />
            ))
          ) : (
            <div className="sm:col-span-2 rounded-xl border border-white/10 bg-[#141724]/60 p-6 text-center text-white/50 text-sm">
              No swarm agents registered. Bound agents will appear here when a swarm executes real tasks.
            </div>
          )}
        </div>

        {/* Right Column (Activity Log, Consensus Votes, Role Timeline) */}
        <div className="lg:col-span-4 flex flex-col gap-3 min-w-0">
          {/* Consensus Votes Box */}
          <div className="rounded-xl border border-white/10 bg-[#141724]/80 p-4 backdrop-blur-md shadow-md min-w-0">
            <h3 className="text-xs font-bold text-white/90 uppercase tracking-wider mb-3">
              Consensus Votes
            </h3>
            <div className="space-y-2 text-xs">
              {consensusList.length > 0 ? (
                consensusList.slice(0, 3).map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2 text-white/70">
                    <span className="truncate">{item.topic || `Round ${item.round_id || idx + 1}`}</span>
                    <span className="h-4 w-4 shrink-0 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-[10px] font-bold">✓</span>
                  </div>
                ))
              ) : (
                <div className="text-white/40 text-[11px]">No consensus rounds recorded</div>
              )}
            </div>
          </div>

          {/* Activity Log / Chat Stream */}
          <div className="flex flex-col flex-1 rounded-xl border border-white/10 bg-[#141724]/80 p-4 backdrop-blur-md shadow-md min-w-0">
            <div className="flex-1 space-y-2 overflow-y-auto max-h-[160px] pr-1">
              {liveLogs.map((msg, idx) => (
                <div key={idx} className={`border-l-2 ${msg.color} pl-2 text-[11px] leading-relaxed`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold truncate">{msg.author}</span>
                    <span className="text-[9px] opacity-40 shrink-0">{msg.time}</span>
                  </div>
                  <div className="text-white/60 mt-0.5 break-words">{msg.text}</div>
                </div>
              ))}
            </div>

            {/* Interactive Chat Prompt */}
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 min-w-0">
              <input
                type="text"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleSendMessage(); }}
                placeholder="Type a message to swarm..."
                className="w-full bg-transparent text-xs text-white placeholder-white/30 outline-none min-w-0"
              />
              <button
                onClick={handleSendMessage}
                className="text-white/50 hover:text-white shrink-0"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>

          {/* Role Assignments Timeline */}
          <div className="rounded-xl border border-white/10 bg-[#141724]/80 p-4 backdrop-blur-md shadow-md min-w-0">
            <h3 className="text-xs font-bold text-white/90 uppercase tracking-wider mb-3">
              Role Assignments Timeline
            </h3>
            <div className="space-y-2">
              {timelineRoles.length > 0 ? (
                timelineRoles.map((item, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-2 text-xs">
                    <div className={`rounded-md border ${item.color} ${item.bg} px-2 py-0.5 text-[10px] font-mono font-medium truncate shrink-0`}>
                      {item.name} <span className="opacity-60">{item.id}</span>
                    </div>
                    <div className="text-[11px] text-white/60 truncate">{item.action}</div>
                  </div>
                ))
              ) : (
                <div className="text-white/40 text-[11px]">No agents assigned yet</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Telemetry Metrics Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 pt-2 min-w-0">
        <div className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-[#141724]/60 px-4 py-2.5 min-w-0">
          <div className="flex items-center gap-2 text-xs text-white/70 min-w-0">
            <svg className="h-4 w-4 text-cyan-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 022 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span className="font-semibold truncate">Throughput</span>
          </div>
          <span className="text-xs font-mono text-white/50 shrink-0">{throughputStr}</span>
        </div>

        <div className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-[#141724]/60 px-4 py-2.5 min-w-0">
          <div className="flex items-center gap-2 text-xs text-white/70 min-w-0">
            <svg className="h-4 w-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
            </svg>
            <span className="font-semibold truncate">Coordination Overhead</span>
          </div>
          <span className="text-xs font-mono text-white/50 shrink-0">{overheadStr}</span>
        </div>

        <div className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-[#141724]/60 px-4 py-2.5 min-w-0">
          <div className="flex items-center gap-2 text-xs text-white/70 min-w-0">
            <svg className="h-4 w-4 text-emerald-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="font-semibold truncate">Success Rate</span>
          </div>
          <span className="text-xs font-mono text-white/50 shrink-0">{successRateStr}</span>
        </div>
      </div>
    </div>
  );
}
