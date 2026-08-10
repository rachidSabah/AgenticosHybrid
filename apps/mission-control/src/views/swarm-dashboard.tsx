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

type ConsensusRound = {
  id: string;
  swarm_id: string;
  consensus_type: string;
  proposal: string;
  votes: Record<string, string>;
  result: string;
  confidence: number;
  created_at: string;
};

function SwarmDashboardTab() {
  const [metrics, setMetrics] = useState<SwarmMetricsSummary | null>(null);
  const [swarms, setSwarms] = useState<SwarmSummary[]>([]);
  const [busy, setBusy] = useState<"monitor" | "consensus" | null>(null);
  const [actionMsg, setActionMsg] = useState<{ tone: "ok" | "warn" | "danger" | "default"; text: string } | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [goalInput, setGoalInput] = useState("");
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null);

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

  // All derived values come from real metrics / real swarms — no fabricated fallbacks.
  const agentsOnlineCount = metrics?.agents_online ?? Object.keys(storeProviders).length;
  const totalSwarms = metrics?.total_swarms ?? swarms.length;
  const activeSwarms = metrics?.active_swarms ?? swarms.filter((s) => s.status === "active").length;
  const totalTasks = metrics?.total_tasks ?? 0;
  const completedTasks = metrics?.completed_tasks ?? 0;
  const failedTasks = metrics?.failed_tasks ?? 0;
  const progressPercent = totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0;
  const activeSwarm = swarms.find((s) => s.status === "active");

  const runAnalyze = async () => {
    const desc = goalInput.trim();
    if (!desc) return;
    setAnalyzing(true);
    try {
      const res = await api.swarmAnalyzeGoal({ description: desc });
      setAnalysis(res.analysis);
    } catch {
      setAnalysis(null);
    }
    setAnalyzing(false);
  };

  const runMonitor = async () => {
    setBusy("monitor");
    try {
      const plans = (await api.swarmPlans()) as SwarmPlanSummary | SwarmPlanSummary[];
      const list = Array.isArray(plans) ? plans : [plans];
      const active = list.find((p) => p.status === "running" || p.status === "pending" || p.status === "planned");
      if (!active) {
        setActionMsg({ tone: "warn", text: "No active plan to monitor — dispatch a goal first." });
        return;
      }
      const res = await api.swarmSupervisorMonitor(active.id);
      setActionMsg({ tone: res.status === "active" ? "ok" : "warn", text: `Monitoring plan "${active.id}": ${res.status}` });
    } catch {
      setActionMsg({ tone: "danger", text: "Monitor execution failed — backend unavailable." });
    } finally {
      setBusy(null);
    }
  };

  const runConsensus = async () => {
    setBusy("consensus");
    try {
      const res = (await api.swarmConsensus()) as unknown;
      if (Array.isArray(res)) {
        const rounds = res as ConsensusRound[];
        setActionMsg(
          rounds.length > 0
            ? { tone: "ok", text: `${rounds.length} consensus round(s) · ${rounds.filter((r) => r.result === "approved").length} approved` }
            : { tone: "warn", text: "No consensus rounds recorded yet." }
        );
      } else {
        const r = res as { status?: string; message?: string };
        setActionMsg({ tone: r.status ? "ok" : "default", text: r.message ?? "Consensus endpoint returned a response." });
      }
    } catch {
      setActionMsg({ tone: "danger", text: "Consensus lookup failed — backend unavailable." });
    } finally {
      setBusy(null);
    }
  };

  const actionToneClass = {
    ok: "border-ok/40 bg-ok/10 text-ok",
    warn: "border-warn/40 bg-warn/10 text-warn",
    danger: "border-danger/40 bg-danger/10 text-danger",
    default: "border-border/40 bg-surface/10 text-muted",
  };

  return (
    <div className="flex h-full flex-col gap-3">
      {/* ── Summary Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <KpiCard label="Total Swarms" value={totalSwarms} delta="all time" tone="accent" />
        <KpiCard label="Active" value={activeSwarms} delta="executing" tone="ok" />
        <KpiCard label="Agents Online" value={agentsOnlineCount} delta="connected" tone="ok" />
        <KpiCard label="Failed Tasks" value={failedTasks} delta="cumulative" tone={failedTasks ? "danger" : "default"} />
      </div>

      {/* ── Active Swarm Card (real swarm + real progress) ── */}
      <div className="glass rounded-xl border border-border/50 p-4 shrink-0 panel-glow">
        {swarms.length === 0 ? (
          <Empty title="No swarms yet" hint="Create a swarm in the Swarms tab or dispatch a goal." />
        ) : (
          <>
            <div className="flex items-center justify-between mb-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold truncate">{activeSwarm?.name ?? "Swarms"}</h3>
                <div className="text-[10px] text-faint mt-0.5 truncate">
                  {activeSwarm
                    ? `Topology: ${activeSwarm.topology} · Status: ${activeSwarm.status}`
                    : `${swarms.length} swarm(s) · ${activeSwarms} active`}
                </div>
              </div>
              <Badge tone={activeSwarm ? "ok" : "default"}>{activeSwarm ? activeSwarm.status : "idle"}</Badge>
            </div>
            {/* Gradient progress bar — magenta → cyan → green */}
            <div className="beam h-2 w-full overflow-hidden rounded-full bg-border/30">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[#d980ff] via-[#00f0ff] to-[#10b981] transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, progressPercent))}%` }}
              />
            </div>
            <div className="mt-2 flex items-center justify-between text-[10px] text-faint">
              <span>{totalTasks > 0 ? `Progress: ${progressPercent}%` : "No tasks tracked"}</span>
              <span>{totalTasks > 0 ? `${completedTasks}/${totalTasks} tasks completed` : "—"}</span>
            </div>
          </>
        )}
      </div>

      {/* ── Two-column content ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[2fr_1fr]">
        {/* Left: Swarms list — real data, real empty state */}
        <Panel title="Active Swarms" subtitle={`${swarms.length} total`} className="min-h-0">
          <div className="min-h-0 max-h-[400px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-2">
            {swarms.length === 0 ? (
              <Empty title="No swarms active" hint="Swarms appear here when created or when a goal is dispatched." />
            ) : (
              swarms.map((s, idx) => (
                <div key={s.id || `swarm-${idx}`} className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 px-3 py-2.5 hover:bg-cyan-400/10 transition">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs font-semibold text-cyan-200 truncate">{s.name}</span>
                      <Badge tone={s.status === "active" ? "ok" : "default"}>{s.status}</Badge>
                    </div>
                    <span className="text-[10px] font-mono text-cyan-300 shrink-0">{s.agent_count} agents</span>
                  </div>
                  <div className="mt-1 text-[10px] font-mono text-white/50 truncate">{s.topology}</div>
                </div>
              ))
            )}
          </div>
        </Panel>

        {/* Right: Quick Actions — real orchestration calls */}
        <Panel title="Quick Actions" subtitle="Orchestration controls" className="min-h-0">
          <div className="space-y-2">
            {/* Analyze Goal — real /api/swarm/planner/analyze */}
            <div className="rounded-xl border border-border/60 p-3">
              <div className="text-xs font-medium">Analyze Goal</div>
              <div className="mt-0.5 text-[11px] text-faint">Decompose a goal into tasks</div>
              <div className="mt-2 flex gap-1.5">
                <input
                  type="text"
                  value={goalInput}
                  onChange={(e) => setGoalInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && runAnalyze()}
                  placeholder="Describe a goal…"
                  className="min-w-0 w-full rounded-lg border border-border/40 bg-surface/10 px-2 py-1 text-[11px] focus:border-accent/50 focus:outline-none"
                />
                <button
                  onClick={runAnalyze}
                  disabled={analyzing || !goalInput.trim()}
                  className="shrink-0 rounded-lg bg-accent/20 px-2.5 py-1 text-[11px] font-medium text-accent hover:bg-accent/30 disabled:opacity-40 transition"
                >
                  {analyzing ? "…" : "Run"}
                </button>
              </div>
              {analysis && (
                <pre className="mt-2 max-h-32 overflow-y-auto no-scrollbar whitespace-pre-wrap rounded-lg bg-surface/20 p-2 text-[10px] font-mono text-muted">
                  {JSON.stringify(analysis, null, 2)}
                </pre>
              )}
            </div>

            {/* Monitor Execution — real /api/swarm/supervisor/monitor */}
            <button
              onClick={runMonitor}
              disabled={busy === "monitor"}
              className="w-full rounded-xl border border-border/60 p-3 text-left hover:bg-surface/30 disabled:opacity-40 transition"
            >
              <div className="flex items-center gap-2 text-xs font-medium">
                Monitor Execution
                {busy === "monitor" && <span className="h-3 w-3 animate-spin rounded-full border border-accent/40 border-t-accent" />}
              </div>
              <div className="mt-0.5 text-[11px] text-faint">Supervise active plans</div>
            </button>

            {/* View Consensus — real /api/consensus */}
            <button
              onClick={runConsensus}
              disabled={busy === "consensus"}
              className="w-full rounded-xl border border-border/60 p-3 text-left hover:bg-surface/30 disabled:opacity-40 transition"
            >
              <div className="flex items-center gap-2 text-xs font-medium">
                View Consensus
                {busy === "consensus" && <span className="h-3 w-3 animate-spin rounded-full border border-accent/40 border-t-accent" />}
              </div>
              <div className="mt-0.5 text-[11px] text-faint">Inspect voting rounds</div>
            </button>

            {/* Real result of the last orchestration action */}
            {actionMsg && (
              <div className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${actionToneClass[actionMsg.tone]}`}>
                {actionMsg.text}
              </div>
            )}

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
        actions={
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
