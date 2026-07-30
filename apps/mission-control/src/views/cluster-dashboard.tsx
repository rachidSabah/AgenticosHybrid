"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";

/**
 * Phase 16 — Cluster Federation Dashboard.
 *
 * Renders LIVE cluster state from /api/cluster/* endpoints and the
 * cluster.* WebSocket events ingested by the store. Single-node
 * deployments show a cluster of size 1 (the local node, which is
 * also the leader by default).
 */

type ClusterTab = "overview" | "topology" | "nodes" | "brains" | "failover";

type NodeInfo = {
  id: string;
  host: string;
  port: number;
  display_name: string;
  status: string;
  role: string;
  is_local: boolean;
  version: string;
  brain_count: number;
  capability_count: number;
  active_missions: number;
  cpu_usage: number;
  memory_usage: number;
  network_latency_ms: number;
  health_score: number;
  issues: string[];
  last_heartbeat: string;
};

type Topology = {
  cluster_id: string;
  nodes: NodeInfo[];
  connections: Array<{ source: string; target: string; latency_ms: number; healthy: boolean }>;
  leader_id: string;
  quorum_size: number;
  total_brains: number;
  total_capabilities: number;
  total_active_missions: number;
  cluster_health: number;
};

type ClusterStats = {
  total_nodes: number;
  active_nodes: number;
  degraded_nodes: number;
  unreachable_nodes: number;
  total_brains: number;
  local_brains: number;
  remote_brains: number;
  total_capabilities: number;
  unique_capabilities: number;
  active_missions: number;
  failover_count: number;
  consensus_count: number;
  average_node_health: number;
  average_network_latency: number;
  cluster_utilization: number;
};

type RemoteBrain = {
  brain_id: string;
  node_id: string;
  display_name: string;
  provider: string;
  host: string;
  capabilities: string[];
  health: number;
  latency: number;
  availability: number;
  version: string;
  last_synced: string;
};

type FailoverAction = {
  id: string;
  trigger: string;
  action_type: string;
  target_node_id: string;
  target_brain_id: string;
  replacement_node_id: string;
  replacement_brain_id: string;
  rationale: string;
  status: string;
  created_at: string;
};

export function ClusterDashboard() {
  const [tab, setTab] = useState<ClusterTab>("overview");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border/60 px-4 pt-2">
        {(["overview", "topology", "nodes", "brains", "failover"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t ? "bg-surface/40 text-text" : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "overview"
              ? "Overview"
              : t === "topology"
                ? "Topology"
                : t === "nodes"
                  ? "Nodes"
                  : t === "brains"
                    ? "Distributed Brains"
                    : "Failover"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "overview" && <OverviewTab />}
        {tab === "topology" && <TopologyTab />}
        {tab === "nodes" && <NodesTab />}
        {tab === "brains" && <BrainsTab />}
        {tab === "failover" && <FailoverTab />}
      </div>
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────

function OverviewTab() {
  const [stats, setStats] = useState<ClusterStats | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const clusterLive = useStore((s) => s.cluster);
  const connected = useStore((s) => s.connected);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, st] = await Promise.all([
        api.get<ClusterStats>("/api/cluster/statistics"),
        api.get<Record<string, unknown>>("/api/cluster/status"),
      ]);
      setStats(s);
      setStatus(st);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    void useStore.getState().hydrateCluster();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const liveStats = (clusterLive?.statistics as ClusterStats | null) ?? stats;

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Nodes" value={liveStats?.total_nodes ?? 0} />
        <Stat label="Active" value={liveStats?.active_nodes ?? 0} tone="ok" />
        <Stat label="Degraded" value={liveStats?.degraded_nodes ?? 0} tone="warn" />
        <Stat label="Total Brains" value={liveStats?.total_brains ?? 0} />
        <Stat label="Remote Brains" value={liveStats?.remote_brains ?? 0} />
        <Stat label="Capabilities" value={liveStats?.unique_capabilities ?? 0} />
        <Stat label="Failovers" value={liveStats?.failover_count ?? 0} />
        <div className="ml-auto flex items-center gap-2">
          <Badge tone={connected ? "ok" : "default"}>{connected ? "LIVE" : "Local"}</Badge>
          <button
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20 disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <Panel
        title="Cluster Health"
        subtitle={status ? (status.is_leader ? "Leader (this node)" : "Follower") : "—"}
        className="col-span-6"
      >
        {!liveStats ? (
          <Empty title="No cluster data" hint="Cluster controller not running." />
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-xs text-faint">Average Node Health</div>
              <div className="mt-1 h-2 w-full rounded-full bg-surface/40">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-500 to-rose-500"
                  style={{ width: `${liveStats.average_node_health.toFixed(0)}%` }}
                />
              </div>
              <div className="mt-1 text-[11px] text-faint">{liveStats.average_node_health.toFixed(1)}%</div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <Metric label="Avg Latency" value={`${liveStats.average_network_latency.toFixed(0)}ms`} />
              <Metric label="Utilization" value={`${(liveStats.cluster_utilization * 100).toFixed(0)}%`} />
              <Metric label="Active Missions" value={String(liveStats.active_missions)} />
              <Metric label="Consensuses" value={String(liveStats.consensus_count)} />
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Cluster Actions" subtitle="Federation controls" className="col-span-6">
        <div className="grid grid-cols-3 gap-3">
          <ActionButton label="Discover" description="Re-discover nodes" endpoint="/api/cluster/discover" />
          <ActionButton label="Rebalance" description="Rebalance workload" endpoint="/api/cluster/rebalance" />
          <ActionButton label="Sync" description="Sync remote brains" endpoint="/api/cluster/synchronize" />
          <ActionButton label="Elect Leader" description="Force leader election" endpoint="/api/cluster/elect-leader" />
          <ActionButton label="Rebuild" description="Rebuild federated graph" endpoint="/api/cluster/rebuild" />
        </div>
      </Panel>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/60 p-2">
      <div className="text-faint">{label}</div>
      <div className="mt-0.5 text-sm font-medium">{value}</div>
    </div>
  );
}

function ActionButton({ label, description, endpoint }: { label: string; description: string; endpoint: string }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const onClick = useCallback(async () => {
    setRunning(true);
    setResult(null);
    try {
      const r = await api.post<Record<string, unknown>>(endpoint, {});
      setResult(JSON.stringify(r).slice(0, 150));
    } catch (e) {
      setResult(String(e));
    } finally {
      setRunning(false);
    }
  }, [endpoint]);
  return (
    <div className="rounded-xl border border-border/60 p-3">
      <div className="text-xs font-medium">{label}</div>
      <div className="mt-0.5 text-[11px] text-faint">{description}</div>
      <button
        onClick={onClick}
        disabled={running}
        className="mt-2 w-full rounded-lg bg-indigo-500/20 px-3 py-1.5 text-[11px] text-indigo-300 transition hover:bg-indigo-500/30 disabled:opacity-50"
      >
        {running ? "Running…" : "Run"}
      </button>
      {result && <div className="mt-2 truncate text-[10px] text-faint">{result}</div>}
    </div>
  );
}

// ── Topology Tab ──────────────────────────────────────────────────────

function TopologyTab() {
  const [topo, setTopo] = useState<Topology | null>(null);

  const load = useCallback(async () => {
    try {
      const t = await api.get<Topology>("/api/cluster/topology");
      setTopo(t);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Nodes" value={topo?.nodes.length ?? 0} />
        <Stat label="Connections" value={topo?.connections.length ?? 0} />
        <Stat label="Leader" value={topo?.leader_id ? "Elected" : "—"} tone="ok" />
        <Stat label="Quorum" value={topo?.quorum_size ?? 0} />
        <Stat label="Cluster Health" value={`${((topo?.cluster_health ?? 0) * 100).toFixed(0)}%`} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Cluster Topology Graph" subtitle="Nodes and connections" className="col-span-12">
        {!topo || topo.nodes.length === 0 ? (
          <Empty title="No topology" hint="Add remote nodes to populate." />
        ) : (
          <div className="space-y-3">
            {/* Node circles with connection lines */}
            <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border/60 p-4">
              {topo.nodes.map((n) => {
                const isLeader = n.id === topo.leader_id;
                const color =
                  n.status === "active" ? "bg-emerald-500" :
                  n.status === "degraded" ? "bg-amber-500" :
                  n.status === "unreachable" ? "bg-rose-500" : "bg-slate-500";
                return (
                  <div key={n.id} className="flex flex-col items-center gap-1">
                    <div
                      className={`flex h-16 w-16 items-center justify-center rounded-full ${color} text-[10px] font-bold text-white`}
                      title={`${n.display_name} (${n.status})`}
                    >
                      {isLeader ? "★" : n.is_local ? "◉" : "○"}
                    </div>
                    <div className="max-w-[80px] truncate text-[10px] text-faint">{n.display_name}</div>
                    {isLeader && <div className="text-[10px] text-amber-400">leader</div>}
                  </div>
                );
              })}
            </div>
            {/* Connections list */}
            {topo.connections.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-faint">Connections ({topo.connections.length})</div>
                <div className="grid grid-cols-3 gap-2">
                  {topo.connections.slice(0, 30).map((c, i) => (
                    <div key={i} className="rounded-lg border border-border/60 px-2 py-1 text-[11px]">
                      <span className="text-faint">{c.source}</span>
                      <span className="mx-1 text-indigo-400">→</span>
                      <span className="text-faint">{c.target}</span>
                      <div className="text-[10px] text-faint">{c.latency_ms.toFixed(0)}ms {c.healthy ? "✓" : "✗"}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Nodes Tab ─────────────────────────────────────────────────────────

function NodesTab() {
  const [nodes, setNodes] = useState<NodeInfo[]>([]);

  const load = useCallback(async () => {
    try {
      const n = await api.get<NodeInfo[]>("/api/cluster/nodes");
      setNodes(Array.isArray(n) ? n : []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Total Nodes" value={nodes.length} />
        <Stat label="Active" value={nodes.filter((n) => n.status === "active").length} tone="ok" />
        <Stat label="Degraded" value={nodes.filter((n) => n.status === "degraded").length} tone="warn" />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Cluster Nodes" subtitle={`${nodes.length} total`} className="col-span-12">
        {nodes.length === 0 ? (
          <Empty title="No nodes" hint="Cluster controller not running." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {nodes.map((n) => (
              <div key={n.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{n.display_name}</span>
                    {n.is_local && <Badge tone="ok">local</Badge>}
                    {n.role === "leader" && <Badge tone="warn">leader</Badge>}
                    <Badge tone={n.status === "active" ? "ok" : n.status === "degraded" ? "warn" : "danger"}>
                      {n.status}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-faint">{n.host}:{n.port} · v{n.version}</div>
                </div>
                <div className="mt-2 grid grid-cols-6 gap-2 text-[11px]">
                  <Metric label="Brains" value={String(n.brain_count)} />
                  <Metric label="Caps" value={String(n.capability_count)} />
                  <Metric label="Missions" value={String(n.active_missions)} />
                  <Metric label="CPU" value={`${n.cpu_usage.toFixed(0)}%`} />
                  <Metric label="Memory" value={`${n.memory_usage.toFixed(0)}%`} />
                  <Metric label="Health" value={`${n.health_score.toFixed(0)}%`} />
                </div>
                {n.issues.length > 0 && (
                  <div className="mt-2 text-[11px] text-rose-400">⚠ {n.issues.join("; ")}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Distributed Brains Tab ────────────────────────────────────────────

function BrainsTab() {
  const [data, setData] = useState<{ remote_brains: RemoteBrain[]; stats: Record<string, unknown> } | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ remote_brains: RemoteBrain[]; stats: Record<string, unknown> }>("/api/cluster/brains");
      setData(d);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Local Brains" value={String(data?.stats?.local_brains ?? 0)} />
        <Stat label="Remote Brains" value={String(data?.stats?.remote_brains ?? 0)} />
        <Stat label="Total" value={String(data?.stats?.total_brains ?? 0)} />
        <Stat label="Sync Count" value={String(data?.stats?.sync_count ?? 0)} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Remote Brains" subtitle="Brains on other cluster nodes" className="col-span-12">
        {!data || data.remote_brains.length === 0 ? (
          <Empty title="No remote brains" hint="Add remote nodes to discover their brains." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {data.remote_brains.map((b) => (
              <div key={`${b.node_id}:${b.brain_id}`} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{b.display_name || b.brain_id}</span>
                    <Badge tone={b.health >= 80 ? "ok" : b.health >= 50 ? "warn" : "danger"}>
                      health {b.health.toFixed(0)}%
                    </Badge>
                  </div>
                  <div className="text-[11px] text-faint">{b.node_id} · {b.provider || "unknown"}</div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {b.capabilities.map((c) => (
                    <span key={c} className="rounded bg-surface/40 px-1.5 py-0.5 text-[10px] text-faint">{c}</span>
                  ))}
                </div>
                <div className="mt-1 text-[10px] text-faint">
                  latency {b.latency.toFixed(0)}ms · availability {(b.availability * 100).toFixed(0)}% · synced {b.last_synced.slice(0, 19)}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Failover Tab ──────────────────────────────────────────────────────

function FailoverTab() {
  const [data, setData] = useState<{ actions: FailoverAction[]; stats: Record<string, unknown> } | null>(null);
  const [brainId, setBrainId] = useState("");
  const [nodeId, setNodeId] = useState("");

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ actions: FailoverAction[]; stats: Record<string, unknown> }>("/api/cluster/failover");
      setData(d);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const trigger = useCallback(async () => {
    if (!brainId.trim() || !nodeId.trim()) return;
    try {
      await api.post("/api/cluster/failover", { brain_id: brainId, node_id: nodeId });
      setBrainId("");
      setNodeId("");
      await load();
    } catch {
      // ignore
    }
  }, [brainId, nodeId, load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Triggers" value={String(data?.stats?.triggers_detected ?? 0)} />
        <Stat label="Started" value={String(data?.stats?.actions_started ?? 0)} />
        <Stat label="Completed" value={String(data?.stats?.actions_completed ?? 0)} tone="ok" />
        <Stat label="Failed" value={String(data?.stats?.actions_failed ?? 0)} tone={(Number(data?.stats?.actions_failed ?? 0)) > 0 ? "danger" : "default"} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Manual Failover" subtitle="Trigger a recovery action" className="col-span-12">
        <div className="flex gap-2">
          <input
            type="text"
            value={brainId}
            onChange={(e) => setBrainId(e.target.value)}
            placeholder="brain_id"
            className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text placeholder:text-faint"
          />
          <input
            type="text"
            value={nodeId}
            onChange={(e) => setNodeId(e.target.value)}
            placeholder="node_id"
            className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text placeholder:text-faint"
          />
          <button
            onClick={trigger}
            disabled={!brainId.trim() || !nodeId.trim()}
            className="rounded-lg bg-rose-500/30 px-4 py-2 text-xs text-rose-300 transition hover:bg-rose-500/40 disabled:opacity-50"
          >
            Trigger
          </button>
        </div>
      </Panel>

      <Panel title="Failover Actions" subtitle={`${data?.actions.length ?? 0} total`} className="col-span-12">
        {!data || data.actions.length === 0 ? (
          <Empty title="No actions" hint="Failures will trigger automatic actions." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {data.actions.map((a) => (
              <div key={a.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone={a.status === "completed" ? "ok" : a.status === "failed" ? "danger" : "warn"}>
                      {a.status}
                    </Badge>
                    <span className="text-xs font-medium">{a.trigger}</span>
                    <span className="text-[10px] text-faint">{a.action_type}</span>
                  </div>
                  <div className="text-[10px] text-faint">{a.created_at.slice(0, 19)}</div>
                </div>
                <div className="mt-1 text-[11px] text-faint">{a.rationale}</div>
                {a.replacement_brain_id && (
                  <div className="mt-1 text-[11px] text-emerald-400">
                    → {a.replacement_brain_id} on {a.replacement_node_id}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
