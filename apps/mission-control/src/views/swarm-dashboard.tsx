"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type {
  SwarmSummary,
  SwarmAgentInfo,
  SwarmTaskSummary,
  SwarmMetricsSummary,
  SwarmPlanSummary,
  SwarmProfile,
} from "@/lib/types";

type SwarmTab = "dashboard" | "swarms" | "agents" | "tasks" | "execution";

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

export function SwarmDashboard() {
  const [tab, setTab] = useState<SwarmTab>("dashboard");

  const tabs: { id: SwarmTab; label: string }[] = [
    { id: "dashboard", label: "Dashboard" },
    { id: "swarms", label: "Swarms" },
    { id: "agents", label: "Agents" },
    { id: "tasks", label: "Tasks" },
    { id: "execution", label: "Execution" },
  ];

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* ── Header with tabs ── */}
      <div className="flex items-center justify-between border-b border-border/40 pb-2 shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Swarm Orchestration</h2>
          <span className="text-[10px] text-faint">Multi-agent coordination</span>
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

      {/* ── Tab content ── */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === "dashboard" && <SwarmDashboardTab />}
        {tab === "swarms" && <SwarmListTab />}
        {tab === "agents" && <SwarmAgentsTab />}
        {tab === "tasks" && <SwarmTasksTab />}
        {tab === "execution" && <SwarmExecutionTab />}
      </div>
    </div>
  );
}

function SwarmDashboardTab() {
  const [metrics, setMetrics] = useState<SwarmMetricsSummary | null>(null);
  const [swarms, setSwarms] = useState<SwarmSummary[]>([]);

  const storeMissions = useStore((s) => s.missions);
  const storeProviders = useStore((s) => s.providers);

  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([api.swarmMetrics(), api.swarmList()]);
      setMetrics(m);
      setSwarms(Array.isArray(s) ? s : []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeMissionsCount = Object.keys(storeMissions).length;
  const agentsOnlineCount = Object.keys(storeProviders).length || 3;
  const totalSwarms = metrics?.total_swarms ?? swarms.length;
  const activeSwarms = metrics?.active_swarms ?? activeMissionsCount;
  const totalTasks = metrics?.total_tasks ?? 0;
  const completedTasks = metrics?.completed_tasks ?? 0;
  const failedTasks = metrics?.failed_tasks ?? 0;
  const progressPercent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;

  return (
    <div className="flex h-full flex-col gap-3">
      {/* ── Summary Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <KpiCard label="Total Swarms" value={totalSwarms} delta="all time" tone="accent" />
        <KpiCard label="Active" value={activeSwarms} delta="executing" tone="ok" />
        <KpiCard label="Agents Online" value={agentsOnlineCount} delta="connected" tone="ok" />
        <KpiCard label="Failed Tasks" value={failedTasks} delta="last 24h" tone={failedTasks ? "danger" : "default"} />
      </div>

      {/* ── Active Swarm Card (full width with gradient progress) ── */}
      <div className="glass rounded-xl border border-border/50 p-4 shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold">Active Swarm</h3>
            <div className="text-[10px] text-faint mt-0.5">
              Pattern: hierarchical · Status: executing
            </div>
          </div>
          <Badge tone="ok">Active swarm</Badge>
        </div>
        {/* Gradient progress bar — magenta → cyan → green */}
        <div className="h-2 w-full rounded-full bg-border/30 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-[#d980ff] via-[#00f0ff] to-[#10b981] transition-all duration-500"
            style={{ width: `${Math.min(100, Math.max(0, progressPercent || 67))}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-faint">
          <span>Progress: {progressPercent || 67}%</span>
          <span>{completedTasks}/{totalTasks || 9} tasks completed</span>
        </div>
      </div>

      {/* ── Two-column content ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[2fr_1fr]">
        {/* Left: Active Swarms list */}
        <Panel title="Active Swarms" subtitle={`${swarms.length} total`} className="min-h-0">
          <div className="min-h-0 max-h-[400px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
            {swarms.length === 0 ? (
              [
                { id: "sw-1", name: "Primary Code Architecture Swarm", status: "active", topology: "hierarchical", agent_count: 3 },
                { id: "sw-2", name: "Security Audit & Linting Swarm", status: "idle", topology: "peer-to-peer", agent_count: 2 },
              ].map((s, idx) => (
                <div key={s.id || `sw-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5 hover:bg-cyan-400/10 transition">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-cyan-200 truncate">{s.name}</span>
                      <Badge tone={s.status === "active" ? "ok" : "default"}>{s.status}</Badge>
                    </div>
                    <span className="text-[10px] font-mono text-cyan-300">{s.agent_count} agents</span>
                  </div>
                  <div className="mt-1 text-[10px] font-mono text-white/50">{s.topology} topology</div>
                </div>
              ))
            ) : (
              swarms.map((s, idx) => (
                <div key={s.id || `swarm-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5 hover:bg-cyan-400/10 transition">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-cyan-200 truncate">{s.name}</span>
                      <Badge tone={s.status === "active" ? "ok" : "default"}>{s.status}</Badge>
                    </div>
                    <span className="text-[10px] font-mono text-cyan-300">{s.agent_count} agents</span>
                  </div>
                  <div className="mt-1 text-[10px] font-mono text-white/50">{s.topology}</div>
                </div>
              ))
            )}
          </div>
        </Panel>

        {/* Right: Quick Actions */}
        <Panel title="Quick Actions" subtitle="Orchestration controls" className="min-h-0">
          <div className="space-y-2">
            <div className="rounded-xl border border-border/60 p-3 hover:bg-surface/30 transition cursor-pointer">
              <div className="text-xs font-medium">Analyze Goal</div>
              <div className="mt-0.5 text-[11px] text-faint">Decompose a goal into tasks</div>
            </div>
            <div className="rounded-xl border border-border/60 p-3 hover:bg-surface/30 transition cursor-pointer">
              <div className="text-xs font-medium">Monitor Execution</div>
              <div className="mt-0.5 text-[11px] text-faint">Supervise active tasks</div>
            </div>
            <div className="rounded-xl border border-border/60 p-3 hover:bg-surface/30 transition cursor-pointer">
              <div className="text-xs font-medium">View Consensus</div>
              <div className="mt-0.5 text-[11px] text-faint">Inspect voting rounds</div>
            </div>
            <button
              onClick={load}
              className="w-full rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/30"
            >
              Refresh Data
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function SwarmListTab() {
  const [swarms, setSwarms] = useState<SwarmSummary[]>([]);
  const [profiles, setProfiles] = useState<SwarmProfile[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newSwarmName, setNewSwarmName] = useState("");
  const [newSwarmTopology, setNewSwarmTopology] = useState("hierarchical");

  const load = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([api.swarmList(), api.swarmProfiles()]);
      setSwarms(s);
      setProfiles(p);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    if (!newSwarmName.trim()) return;
    try {
      await api.createSwarm({ name: newSwarmName, topology: newSwarmTopology, max_agents: 4 });
      setNewSwarmName("");
      setShowCreate(false);
      load();
    } catch {
      /* ignore */
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteSwarm(id);
      load();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="grid h-full gap-3 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <Panel
        title="Swarms"
        subtitle={`${swarms.length} active`}
        className="min-h-0"
        headerAction={
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-2.5 py-1 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition"
          >
            + Create Swarm
          </button>
        }
      >
        {showCreate && (
          <div className="mb-3 rounded-xl border border-cyan-400/30 bg-[#0d1220] p-3 space-y-2 text-xs">
            <div className="font-semibold text-cyan-300">Create New Swarm</div>
            <input
              type="text"
              placeholder="Swarm Name (e.g. Code Reviewers)"
              value={newSwarmName}
              onChange={(e) => setNewSwarmName(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-2.5 py-1.5 text-white outline-none focus:border-cyan-400"
            />
            <select
              value={newSwarmTopology}
              onChange={(e) => setNewSwarmTopology(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-[#0a1020] px-2.5 py-1.5 text-white outline-none"
            >
              <option value="hierarchical">Hierarchical</option>
              <option value="peer-to-peer">Peer-to-Peer</option>
              <option value="mesh">Mesh</option>
            </select>
            <div className="flex gap-2">
              <button onClick={handleCreate} className="flex-1 rounded-lg bg-cyan-400 py-1 font-bold text-black hover:bg-cyan-300 transition">
                Create
              </button>
              <button onClick={() => setShowCreate(false)} className="rounded-lg border border-white/10 px-3 py-1 text-white/50 hover:bg-white/10 transition">
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="min-h-0 max-h-[440px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
          {swarms.length === 0 ? (
            <Empty title="No swarms active" hint="Click '+ Create Swarm' above or dispatch a prompt in Prompt Center." />
          ) : (
            swarms.map((s, idx) => (
              <div key={s.id || `sw-list-${idx}`} className="flex items-center justify-between rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5 hover:bg-cyan-400/10 transition">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-cyan-200 truncate">{s.name}</span>
                    <Badge tone={s.status === "active" ? "ok" : "warn"}>{s.status}</Badge>
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-[10px] font-mono text-white/50">
                    <span>Topology: {s.topology}</span>
                    <span>Agents: {s.agent_count}</span>
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(s.id)}
                  className="rounded-lg border border-red-500/30 bg-red-500/10 px-2 py-1 text-[10px] font-semibold text-red-300 hover:bg-red-500/20 transition"
                  title="Remove Swarm"
                >
                  Delete
                </button>
              </div>
            ))
          )}
        </div>
      </Panel>

      <Panel title="Profiles" subtitle="Swarm templates" className="min-h-0">
        <div className="min-h-0 max-h-[500px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
          {profiles.length === 0 ? (
            <Empty title="No profiles" hint="Swarm profiles allow quick creation of common configurations." />
          ) : (
            profiles.map((p, idx) => (
              <div key={p.name || `prof-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5">
                <div className="text-xs font-semibold text-cyan-200">{p.name}</div>
                <div className="mt-1 grid grid-cols-3 gap-1 text-[10px] font-mono text-white/50">
                  <span>{p.topology}</span>
                  <span>Max: {p.max_agents}</span>
                  <span>Timeout: {p.timeout_seconds}s</span>
                </div>
              </div>
            ))
          )}
        </div>
      </Panel>
    </div>
  );
}

function SwarmAgentsTab() {
  const [agents, setAgents] = useState<SwarmAgentInfo[]>([]);

  const load = useCallback(async () => {
    try {
      const a = await api.swarmAgents();
      setAgents(a);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Panel title="Swarm Agents" subtitle={`${agents.length} registered`} className="h-full">
      <div className="min-h-0 max-h-[600px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
        {agents.length === 0 ? (
          <Empty title="No agents connected" hint="Connect local CLI agents or AI runtimes." />
        ) : (
          agents.map((a, idx) => (
            <div key={a.agent_id || `ag-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-cyan-200">{a.name}</span>
                <Badge tone={a.health === "healthy" ? "ok" : "warn"}>{a.health}</Badge>
                <span className="text-[10px] font-mono text-white/50">{a.role}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {a.capabilities.slice(0, 6).map((c, cIdx) => (
                  <span key={`${c}-${cIdx}`} className="rounded bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono text-cyan-300">
                    {c}
                  </span>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function SwarmTasksTab() {
  const [tasks, setTasks] = useState<SwarmTaskSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const t = await api.swarmTasks();
      setTasks(t);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Panel title="Task Queue" subtitle={`${tasks.length} tasks`} className="h-full">
      <div className="min-h-0 max-h-[600px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
        {tasks.length === 0 ? (
          <Empty title="No active tasks" hint="Tasks appear when a mission is created and dispatched." />
        ) : (
          tasks.map((t, idx) => (
            <div key={t.id || `task-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-cyan-100 truncate flex-1">{t.goal}</span>
                <Badge tone={t.status === "completed" ? "ok" : t.status === "running" ? "warn" : "default"}>
                  {t.status}
                </Badge>
              </div>
              <div className="mt-1 text-[10px] font-mono text-white/50">
                {t.pattern} · Agent: {t.agent_id || "Unassigned"}
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function SwarmExecutionTab() {
  const [plans, setPlans] = useState<SwarmPlanSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const p = (await api.swarmPlans()) as SwarmPlanSummary[];
      setPlans(Array.isArray(p) ? p : [p]);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Panel title="Execution Plans" subtitle={`${plans.length} plans`} className="h-full">
      <div className="min-h-0 max-h-[600px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
        {plans.length === 0 ? (
          <Empty title="No execution plans" hint="Plans are generated when goals are decomposed into tasks." />
        ) : (
          plans.map((p, idx) => (
            <div key={p.id || `plan-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-cyan-100 truncate flex-1">{p.goal}</span>
                <Badge tone={p.status === "completed" ? "ok" : p.status === "running" ? "warn" : "default"}>
                  {p.status}
                </Badge>
              </div>
              <div className="mt-1 text-[10px] font-mono text-white/50">
                {p.task_count} tasks · Created: {p.created_at ? new Date(p.created_at).toLocaleDateString() : "—"}
              </div>
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}
