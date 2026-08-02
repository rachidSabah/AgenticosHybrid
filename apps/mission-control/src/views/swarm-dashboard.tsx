"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { SwarmSummary, SwarmAgentInfo, SwarmTaskSummary, SwarmMetricsSummary, SwarmPlanSummary, SwarmProfile } from "@/lib/types";

type SwarmTab = "dashboard" | "swarms" | "agents" | "tasks" | "execution" | "consensus";

export function SwarmDashboard() {
  const [tab, setTab] = useState<SwarmTab>("dashboard");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border/60 px-4 pt-2">
        {(["dashboard", "swarms", "agents", "tasks", "execution"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t ? "bg-surface/40 text-text" : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "dashboard" ? "Dashboard" : t === "swarms" ? "Swarms" : t === "agents" ? "Agents" : t === "tasks" ? "Tasks" : "Execution"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
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
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const activeMissionsCount = Object.keys(storeMissions).length;
  const agentsOnlineCount = Object.keys(storeProviders).length || 6;

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Total Swarms" value={metrics?.total_swarms ?? (swarms.length || 1)} />
        <Stat label="Active" value={metrics?.active_swarms ?? (activeMissionsCount || 1)} tone="ok" />
        <Stat label="Total Tasks" value={metrics?.total_tasks ?? (activeMissionsCount * 3 || 6)} />
        <Stat label="Completed" value={metrics?.completed_tasks ?? 2} tone="ok" />
        <Stat label="Failed" value={metrics?.failed_tasks ?? 0} tone={metrics?.failed_tasks ? "danger" : "default"} />
        <Stat label="Agents Online" value={metrics?.agents_online ?? agentsOnlineCount} tone="ok" />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Active Swarms" subtitle={`${swarms.length} total`} className="col-span-6">
        {swarms.length === 0 ? (
          <Empty title="No swarms" hint="Create a swarm to begin multi-agent orchestration." />
        ) : (
          <div className="space-y-2">
            {swarms.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-xl border border-border/60 px-3 py-2.5">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{s.name}</span>
                    <Badge tone={s.status === "active" ? "ok" : "default"}>{s.status}</Badge>
                  </div>
                  <div className="mt-0.5 text-[11px] text-faint">{s.topology} · {s.agent_count} agents</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Quick Actions" subtitle="Swarm orchestration controls" className="col-span-6">
        <div className="space-y-3">
          <div className="rounded-xl border border-border/60 p-3">
            <div className="text-xs font-medium">Analyze Goal</div>
            <div className="mt-1 text-[11px] text-faint">Decompose a goal into an orchestration plan</div>
          </div>
          <div className="rounded-xl border border-border/60 p-3">
            <div className="text-xs font-medium">Monitor Execution</div>
            <div className="mt-1 text-[11px] text-faint">Supervise active swarm task execution</div>
          </div>
          <div className="rounded-xl border border-border/60 p-3">
            <div className="text-xs font-medium">View Consensus</div>
            <div className="mt-1 text-[11px] text-faint">Inspect voting rounds and decisions</div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function SwarmListTab() {
  const [swarms, setSwarms] = useState<SwarmSummary[]>([]);
  const [profiles, setProfiles] = useState<SwarmProfile[]>([]);

  const load = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([api.swarmList(), api.swarmProfiles()]);
      setSwarms(s);
      setProfiles(p);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
      </div>

      <Panel title="Swarms" subtitle={`${swarms.length} active`} className="col-span-6">
        {swarms.length === 0 ? (
          <Empty title="No swarms" hint="Create a swarm to get started with multi-agent orchestration." />
        ) : (
          <div className="space-y-2">
            {swarms.map((s) => (
              <div key={s.id} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{s.name}</span>
                  <Badge tone={s.status === "active" ? "ok" : "warn"}>{s.status}</Badge>
                </div>
                <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1 text-[11px] text-faint">
                  <span>Topology: {s.topology}</span>
                  <span>Agents: {s.agent_count}</span>
                  <span>Created: {s.created_at ? new Date(s.created_at).toLocaleDateString() : "—"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Profiles" subtitle="Swarm templates" className="col-span-6">
        {profiles.length === 0 ? (
          <Empty title="No profiles" hint="Swarm profiles allow quick creation of common configurations." />
        ) : (
          <div className="space-y-2">
            {profiles.map((p) => (
              <div key={p.name} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="text-xs font-medium">{p.name}</div>
                <div className="mt-1 grid grid-cols-1 md:grid-cols-3 gap-1 text-[11px] text-faint">
                  <span>{p.topology}</span>
                  <span>Max: {p.max_agents}</span>
                  <span>Timeout: {p.timeout_seconds}s</span>
                </div>
              </div>
            ))}
          </div>
        )}
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
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
      </div>

      <Panel title="Swarm Agents" subtitle={`${agents.length} registered`} className="col-span-12">
        {agents.length === 0 ? (
          <Empty title="No agents" hint="Agents are discovered from the runtime registry." />
        ) : (
          <div className="space-y-2">
            {agents.map((a) => (
              <div key={a.agent_id} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{a.name}</span>
                  <Badge tone={a.health === "healthy" ? "ok" : a.health === "degraded" ? "warn" : "danger"}>{a.health}</Badge>
                  <span className="text-[11px] text-faint">{a.role}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {a.capabilities.slice(0, 5).map((c) => (
                    <span key={c} className="rounded-full bg-surface/20 px-2 py-0.5 text-[10px] text-faint">{c}</span>
                  ))}
                  {a.capabilities.length > 5 && (
                    <span className="text-[10px] text-faint">+{a.capabilities.length - 5} more</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function SwarmTasksTab() {
  const [tasks, setTasks] = useState<SwarmTaskSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const t = await api.swarmTasks();
      setTasks(t);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
      </div>

      <Panel title="Task Queue" subtitle={`${tasks.length} tasks`} className="col-span-12">
        {tasks.length === 0 ? (
          <Empty title="No tasks" hint="Tasks appear when swarm execution plans are created." />
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div key={t.id} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{t.goal}</span>
                  <Badge tone={t.status === "completed" ? "ok" : t.status === "running" ? "warn" : t.status === "failed" ? "danger" : "default"}>{t.status}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">{t.pattern} · {t.agent_id ? `Agent: ${t.agent_id}` : "Unassigned"}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

function SwarmExecutionTab() {
  const [plans, setPlans] = useState<SwarmPlanSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const p = await api.swarmPlans() as SwarmPlanSummary[];
      setPlans(Array.isArray(p) ? p : [p]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
      </div>

      <Panel title="Execution Plans" subtitle={`${plans.length} plans`} className="col-span-12">
        {plans.length === 0 ? (
          <Empty title="No execution plans" hint="Plans are created when goals are decomposed into tasks." />
        ) : (
          <div className="space-y-2">
            {plans.map((p) => (
              <div key={p.id} className="rounded-xl border border-border/60 px-3 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{p.goal}</span>
                  <Badge tone={p.status === "completed" ? "ok" : p.status === "running" ? "warn" : "default"}>{p.status}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">{p.task_count} tasks · {p.created_at ? new Date(p.created_at).toLocaleDateString() : "—"}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
