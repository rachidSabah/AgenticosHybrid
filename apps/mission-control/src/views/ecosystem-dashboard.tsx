"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { safeFixed, safeNum } from "@/lib/safe";

/**
 * Phase 15 — Ecosystem Dashboard.
 *
 * Renders LIVE ecosystem state from /api/ecosystem/* endpoints and the
 * ecosystem.* WebSocket events ingested by the store. No mock data —
 * every number on this page is derived from BrainRegistry + EventBus.
 */

type EcoTab = "overview" | "capabilities" | "collaborations" | "evolution" | "marketplace";

type EcosystemStats = {
  total_runtimes: number;
  healthy_runtimes: number;
  degraded_runtimes: number;
  unhealthy_runtimes: number;
  total_capabilities: number;
  unique_capabilities: number;
  active_missions: number;
  completed_missions: number;
  failed_missions: number;
  active_swarms: number;
  total_collaborations: number;
  successful_collaborations: number;
  failed_collaborations: number;
  average_health: number;
  average_latency: number;
  average_confidence: number;
  evolution_recommendations: number;
  last_updated: string;
};

type EcosystemHealth = {
  level: string;
  health_score: number;
  availability_score: number;
  performance_score: number;
  collaboration_score: number;
  evolution_score: number;
  issues: string[];
  recommendations: string[];
  last_updated: string;
};

type GraphStats = {
  total_nodes: number;
  total_edges: number;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
  updates_count: number;
};

type NetworkStats = {
  total_links: number;
  unique_runtimes: number;
  total_collaborations: number;
  successful_collaborations: number;
  failed_collaborations: number;
  average_trust: number;
  updates_count: number;
};

type Recommendation = {
  id: string;
  type: string;
  title: string;
  rationale: string;
  target_id: string;
  target_type: string;
  priority: number;
  confidence: number;
  expected_impact: number;
  evidence: Record<string, unknown>;
  action: Record<string, unknown>;
  created_at: string;
};

type MarketStats = {
  published: number;
  awarded: number;
  completed: number;
  failed: number;
  cancelled: number;
  no_bids: number;
  active_tasks: number;
};

type MarketTask = {
  id: string;
  title: string;
  status: string;
  required_capabilities: string[];
  bids: Array<{ runtime_id: string; runtime_name: string; bid_score: number; confidence: number }>;
  selected_bid: { runtime_id: string; runtime_name: string; bid_score: number } | null;
  published_at: string;
  awarded_at: string;
  selection_rationale: string;
};

export function EcosystemDashboard() {
  const [tab, setTab] = useState<EcoTab>("overview");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 overflow-x-auto no-scrollbar border-b border-border/60 px-4 pt-2">
        {(["overview", "capabilities", "collaborations", "evolution", "marketplace"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t ? "bg-surface/40 text-text" : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "overview"
              ? "Overview"
              : t === "capabilities"
                ? "Capability Graph"
                : t === "collaborations"
                  ? "Collaboration Network"
                  : t === "evolution"
                    ? "Evolution Engine"
                    : "Task Marketplace"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "overview" && <OverviewTab />}
        {tab === "capabilities" && <CapabilitiesTab />}
        {tab === "collaborations" && <CollaborationsTab />}
        {tab === "evolution" && <EvolutionTab />}
        {tab === "marketplace" && <MarketplaceTab />}
      </div>
    </div>
  );
}

// ── Overview Tab ───────────────────────────────────────────────────────

function OverviewTab() {
  const [stats, setStats] = useState<EcosystemStats | null>(null);
  const [health, setHealth] = useState<EcosystemHealth | null>(null);
  const [loading, setLoading] = useState(false);

  // The store also receives ecosystem.* WebSocket events — use that
  // for instant updates between REST refreshes.
  const ecoLive = useStore((s) => s.ecosystem);
  const connected = useStore((s) => s.connected);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, h] = await Promise.all([
        api.get<EcosystemStats>("/api/ecosystem/statistics"),
        api.get<EcosystemHealth>("/api/ecosystem/health"),
      ]);
      setStats(s);
      setHealth(h);
    } catch {
      // ignore — ecosystem may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    void useStore.getState().hydrateEcosystem();
    // Refresh every 10s — cheaper than polling and the WebSocket
    // fills in the gaps in real time.
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  // Prefer live data when available
  const liveStats = (ecoLive?.stats as EcosystemStats | null) ?? stats;
  const liveHealth = (ecoLive?.health as EcosystemHealth | null) ?? health;

  const healthTone =
    liveHealth?.level === "optimal" || liveHealth?.level === "healthy"
      ? "ok"
      : liveHealth?.level === "degraded"
        ? "warn"
        : liveHealth?.level === "critical"
          ? "danger"
          : "default";

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <Stat label="Runtimes" value={liveStats?.total_runtimes ?? 0} />
        <Stat label="Healthy" value={liveStats?.healthy_runtimes ?? 0} tone="ok" />
        <Stat label="Capabilities" value={liveStats?.unique_capabilities ?? 0} />
        <Stat
          label="Collaborations"
          value={liveStats?.total_collaborations ?? 0}
          tone={(liveStats?.successful_collaborations ?? 0) > 0 ? "ok" : "default"}
        />
        <Stat label="Evolutions" value={liveStats?.evolution_recommendations ?? 0} />
        <Stat label="Avg Trust" value={((liveStats?.average_confidence ?? 0) * 100).toFixed(0) + "%"} />
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

      <Panel title="Ecosystem Health" subtitle={liveHealth?.level ?? "—"} className="lg:col-span-1">
        {!liveHealth ? (
          <Empty title="No health data" hint="Ecosystem not running yet." />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Badge tone={healthTone as "ok" | "warn" | "danger" | "default"}>{liveHealth.level}</Badge>
              <div className="flex-1">
                <div className="text-xs text-faint">Overall Health Score</div>
                <div className="beam mt-1 h-2 w-full overflow-hidden rounded-full bg-surface/40">
                  <div
                    className="h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-500 to-rose-500"
                    style={{ width: `${safeFixed((safeNum(liveHealth?.health_score) * 100), 0)}%` }}
                  />
                </div>
                <div className="mt-1 text-[11px] text-faint">{safeFixed((safeNum(liveHealth?.health_score) * 100), 1)}%</div>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
              <ScoreBar label="Availability" value={liveHealth.availability_score} />
              <ScoreBar label="Performance" value={liveHealth.performance_score} />
              <ScoreBar label="Collaboration" value={liveHealth.collaboration_score} />
              <ScoreBar label="Evolution" value={liveHealth.evolution_score} />
            </div>
            {(liveHealth?.issues ?? []).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-rose-400">Issues</div>
                <ul className="space-y-1 text-[11px] text-faint">
                  {(liveHealth?.issues ?? []).map((issue: string, i: number) => (
                    <li key={i}>• {issue}</li>
                  ))}
                </ul>
              </div>
            )}
            {(liveHealth?.recommendations ?? []).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-emerald-400">Recommendations</div>
                <ul className="space-y-1 text-[11px] text-faint">
                  {(liveHealth?.recommendations ?? []).map((rec: string, i: number) => (
                    <li key={i}>• {rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Runtime Distribution" subtitle="Health breakdown" className="lg:col-span-1">
        {!liveStats ? (
          <Empty title="No runtimes" hint="Discover runtimes to populate the ecosystem." />
        ) : (
          <div className="space-y-3">
            <RuntimeBar label="Healthy" count={liveStats.healthy_runtimes} total={liveStats.total_runtimes} tone="ok" />
            <RuntimeBar label="Degraded" count={liveStats.degraded_runtimes} total={liveStats.total_runtimes} tone="warn" />
            <RuntimeBar label="Unhealthy" count={liveStats.unhealthy_runtimes} total={liveStats.total_runtimes} tone="danger" />
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
              <div className="rounded-lg border border-border/60 p-2">
                <div className="text-faint">Avg Health</div>
                <div className="mt-0.5 text-sm font-medium">{safeFixed(liveStats?.average_health, 1)}</div>
              </div>
              <div className="rounded-lg border border-border/60 p-2">
                <div className="text-faint">Avg Latency</div>
                <div className="mt-0.5 text-sm font-medium">{safeFixed(liveStats?.average_latency, 0)}ms</div>
              </div>
              <div className="rounded-lg border border-border/60 p-2">
                <div className="text-faint">Active Swarms</div>
                <div className="mt-0.5 text-sm font-medium">{liveStats.active_swarms}</div>
              </div>
              <div className="rounded-lg border border-border/60 p-2">
                <div className="text-faint">Completed Missions</div>
                <div className="mt-0.5 text-sm font-medium">{liveStats.completed_missions}</div>
              </div>
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Ecosystem Actions" subtitle="Self-optimization controls" className="col-span-full">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <ActionButton label="Analyze" description="Run evolution analyzers" endpoint="/api/ecosystem/analyze" />
          <ActionButton label="Optimize" description="Continuous self-optimization" endpoint="/api/ecosystem/optimize" />
          <ActionButton label="Evolve" description="Force evolution cycle" endpoint="/api/ecosystem/evolve" />
          <ActionButton label="Rebuild" description="Rebuild graph from registry" endpoint="/api/ecosystem/rebuild" />
        </div>
      </Panel>
    </div>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-faint">{label}</span>
        <span className="text-text">{safeFixed((safeNum(value) * 100), 0)}%</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-surface/40">
        <div className="h-1.5 rounded-full bg-indigo-400" style={{ width: `${safeFixed((safeNum(value) * 100), 0)}%` }} />
      </div>
    </div>
  );
}

function RuntimeBar({
  label,
  count,
  total,
  tone,
}: {
  label: string;
  count: number;
  total: number;
  tone: "ok" | "warn" | "danger";
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  const color = tone === "ok" ? "bg-emerald-500" : tone === "warn" ? "bg-amber-500" : "bg-rose-500";
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs text-faint">{label}</span>
        <span className="text-xs text-text">{count} / {total}</span>
      </div>
      <div className="mt-1 h-2 w-full rounded-full bg-surface/40">
        <div className={`h-2 rounded-full ${color}`} style={{ width: `${safeFixed(pct, 0)}%` }} />
      </div>
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
      setResult(JSON.stringify(r).slice(0, 200));
    } catch (e) {
      setResult(String(e));
    } finally {
      setRunning(false);
    }
  }, [endpoint]);
  return (
    <div className="panel-glow rounded-xl border border-border/60 p-3">
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

// ── Capability Graph Tab ───────────────────────────────────────────────

function CapabilitiesTab() {
  const [graph, setGraph] = useState<{ nodes: unknown[]; edges: unknown[]; stats: GraphStats } | null>(null);

  const load = useCallback(async () => {
    try {
      const g = await api.get<{ nodes: unknown[]; edges: unknown[]; stats: GraphStats }>(
        "/api/ecosystem/capabilities"
      );
      setGraph(g);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const stats = graph?.stats;
  const nodes = (graph?.nodes ?? []) as Array<{ id: string; type: string; label: string; properties: Record<string, unknown> }>;
  const edges = (graph?.edges ?? []) as Array<{ source: string; target: string; type: string; weight: number }>;

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <Stat label="Nodes" value={stats?.total_nodes ?? 0} />
        <Stat label="Edges" value={stats?.total_edges ?? 0} />
        <Stat label="Brains" value={stats?.nodes_by_type?.brain ?? 0} tone="ok" />
        <Stat label="Capabilities" value={stats?.nodes_by_type?.capability ?? 0} />
        <Stat label="Missions" value={stats?.nodes_by_type?.mission ?? 0} />
        <Stat label="Swarms" value={stats?.nodes_by_type?.swarm ?? 0} />
        <Stat label="Updates" value={stats?.updates_count ?? 0} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Capability Coverage" subtitle="Capabilities → provider brains" className="lg:col-span-1">
        {nodes.length === 0 ? (
          <Empty title="No capabilities" hint="Discover runtimes with capabilities." />
        ) : (
          <div className="space-y-2 max-h-96 overflow-auto">
            {nodes
              .filter((n) => n.type === "capability")
              .map((cap) => {
                const providers = edges
                  .filter((e) => e.target === cap.id && e.type === "provides")
                  .map((e) => e.source);
                return (
                  <div key={cap.id} className="rounded-lg border border-border/60 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{cap.label}</span>
                      <Badge tone={providers.length > 1 ? "ok" : providers.length === 1 ? "warn" : "danger"}>
                        {providers.length} provider{providers.length === 1 ? "" : "s"}
                      </Badge>
                    </div>
                    {providers.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {providers.map((p) => (
                          <span key={p} className="rounded bg-surface/40 px-1.5 py-0.5 text-[10px] text-faint">{p}</span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </Panel>

      <Panel title="Edge Distribution" subtitle="By relationship type" className="lg:col-span-1">
        {!stats?.edges_by_type ? (
          <Empty title="No edges" hint="No capability relationships recorded." />
        ) : (
          <div className="space-y-2">
            {Object.entries(stats?.edges_by_type ?? {}).map(([type, count]) => (
              <div key={type} className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2">
                <span className="text-xs text-faint">{type}</span>
                <span className="text-sm font-medium">{count}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Collaborations Tab ─────────────────────────────────────────────────

function CollaborationsTab() {
  const [data, setData] = useState<{ links: unknown[]; runtime_stats: Record<string, unknown>; stats: NetworkStats } | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<{ links: unknown[]; runtime_stats: Record<string, unknown>; stats: NetworkStats }>(
        "/api/ecosystem/collaborations"
      );
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

  const stats = data?.stats;
  const links = (data?.links ?? []) as Array<{
    source: string;
    target: string;
    successful: number;
    failed: number;
    success_rate: number;
    trust_score: number;
    last_collaboration: string;
  }>;

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <Stat label="Links" value={stats?.total_links ?? 0} />
        <Stat label="Runtimes" value={stats?.unique_runtimes ?? 0} />
        <Stat label="Collaborations" value={stats?.total_collaborations ?? 0} />
        <Stat label="Successful" value={stats?.successful_collaborations ?? 0} tone="ok" />
        <Stat label="Failed" value={stats?.failed_collaborations ?? 0} tone={(stats?.failed_collaborations ?? 0) > 0 ? "danger" : "default"} />
        <Stat label="Avg Trust" value={((stats?.average_trust ?? 0) * 100).toFixed(0) + "%"} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Trust Links" subtitle="Pairwise collaboration history" className="lg:col-span-1">
        {links.length === 0 ? (
          <Empty title="No collaborations yet" hint="Run a mission with multiple members to populate." />
        ) : (
          <div className="space-y-2 max-h-96 overflow-auto">
            {links
              .slice()
              .sort((a, b) => b.trust_score - a.trust_score)
              .slice(0, 30)
              .map((link, i) => (
                <div key={i} className="rounded-lg border border-border/60 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">{link.source} → {link.target}</span>
                    <Badge tone={link.trust_score > 0.7 ? "ok" : link.trust_score > 0.4 ? "warn" : "danger"}>
                      trust {safeFixed((safeNum(link?.trust_score) * 100), 0)}%
                    </Badge>
                  </div>
                  <div className="mt-1 text-[11px] text-faint">
                    {link.successful} ok · {link.failed} fail · {safeFixed((safeNum(link?.success_rate) * 100), 0)}% success
                  </div>
                </div>
              ))}
          </div>
        )}
      </Panel>

      <Panel title="Runtime Trust Scores" subtitle="Average incoming trust" className="lg:col-span-1">
        {!data?.runtime_stats || Object.keys(data.runtime_stats).length === 0 ? (
          <Empty title="No runtimes" hint="Collaborations will populate trust scores." />
        ) : (
          <div className="space-y-2 max-h-96 overflow-auto">
            {Object.entries(data?.runtime_stats ?? {})
              .map(([rid, stats]) => ({
                rid,
                avg_trust: ((stats as Record<string, unknown>).average_trust as number) ?? 0,
                total: ((stats as Record<string, unknown>).total as number) ?? 0,
              }))
              .sort((a, b) => b.avg_trust - a.avg_trust)
              .map(({ rid, avg_trust, total }) => (
                <div key={rid} className="rounded-lg border border-border/60 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">{rid}</span>
                    <Badge tone={avg_trust > 0.7 ? "ok" : avg_trust > 0.4 ? "warn" : "danger"}>
                      {safeFixed((safeNum(avg_trust) * 100), 0)}%
                    </Badge>
                  </div>
                  <div className="mt-1 text-[11px] text-faint">{total} collaboration{total === 1 ? "" : "s"}</div>
                </div>
              ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Evolution Tab ──────────────────────────────────────────────────────

function EvolutionTab() {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [filter, setFilter] = useState<string>("all");

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ recommendations: Recommendation[] }>(
        filter === "all" ? "/api/ecosystem/evolution" : `/api/ecosystem/evolution?rec_type=${filter}`
      );
      setRecs(r.recommendations ?? []);
    } catch {
      // ignore
    }
  }, [filter]);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const typeOptions = ["all", "recommended_capability", "recommended_routing", "recommended_collaboration", "recommended_optimization"];

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <Stat label="Recommendations" value={recs.length} />
        <div className="ml-auto flex flex-wrap items-center gap-1">
          {typeOptions.map((t) => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              className={`rounded-lg px-3 py-1.5 text-[11px] transition ${
                filter === t ? "bg-indigo-500/30 text-text" : "border border-border/60 text-faint hover:bg-surface/20"
              }`}
            >
              {t === "all" ? "All" : t.replace("recommended_", "")}
            </button>
          ))}
          <button onClick={load} className="ml-2 rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Evolution Recommendations" subtitle="Self-improvement opportunities" className="col-span-full">
        {recs.length === 0 ? (
          <Empty title="No recommendations" hint="Run /api/ecosystem/analyze to generate recommendations." />
        ) : (
          <div className="space-y-3 overflow-hidden">
            {recs.map((rec) => (
              <div key={rec.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge tone={rec.priority > 0.7 ? "danger" : rec.priority > 0.5 ? "warn" : "default"}>
                        P{safeFixed((safeNum(rec?.priority) * 100), 0)}
                      </Badge>
                      <span className="text-sm font-medium">{rec.title}</span>
                    </div>
                    <div className="mt-1 text-[11px] text-faint">{rec.rationale}</div>
                  </div>
                  <div className="ml-3 text-right text-[11px] text-faint">
                    <div>conf: {safeFixed((safeNum(rec?.confidence) * 100), 0)}%</div>
                    <div>impact: {safeFixed((safeNum(rec?.expected_impact) * 100), 0)}%</div>
                  </div>
                </div>
                {rec.target_id && (
                  <div className="mt-2 text-[10px] text-faint">→ {rec.target_type}: {rec.target_id}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Marketplace Tab ────────────────────────────────────────────────────

function MarketplaceTab() {
  const [tasks, setTasks] = useState<MarketTask[]>([]);
  const [stats, setStats] = useState<MarketStats | null>(null);
  const [publishTitle, setPublishTitle] = useState("");
  const [publishCap, setPublishCap] = useState("");

  const load = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([
        api.get<MarketTask[]>("/api/ecosystem/marketplace/tasks?limit=50"),
        api.get<MarketStats>("/api/ecosystem/marketplace/stats"),
      ]);
      setTasks(Array.isArray(t) ? t : []);
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const publish = useCallback(async () => {
    if (!publishTitle.trim()) return;
    try {
      const caps = publishCap.split(",").map((c) => c.trim()).filter(Boolean);
      await api.post("/api/ecosystem/marketplace/publish", {
        title: publishTitle,
        required_capabilities: caps,
        priority: 0.5,
      });
      setPublishTitle("");
      setPublishCap("");
      await load();
    } catch (e) {
      // ignore
    }
  }, [publishTitle, publishCap, load]);

  return (
    <div className="grid h-full gap-4 p-4 grid-cols-1 lg:grid-cols-[1fr_1fr]">
      <div className="col-span-full flex flex-wrap items-center gap-3">
        <Stat label="Published" value={stats?.published ?? 0} />
        <Stat label="Awarded" value={stats?.awarded ?? 0} tone="ok" />
        <Stat label="Completed" value={stats?.completed ?? 0} tone="ok" />
        <Stat label="Failed" value={stats?.failed ?? 0} tone={(stats?.failed ?? 0) > 0 ? "danger" : "default"} />
        <Stat label="Active" value={stats?.active_tasks ?? 0} />
        <div className="ml-auto">
          <button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Publish Task" subtitle="Submit a task to the global marketplace" className="col-span-full">
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            type="text"
            value={publishTitle}
            onChange={(e) => setPublishTitle(e.target.value)}
            placeholder="Task title"
            className="w-full sm:flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text placeholder:text-faint"
          />
          <input
            type="text"
            value={publishCap}
            onChange={(e) => setPublishCap(e.target.value)}
            placeholder="capabilities (comma-separated)"
            className="w-full sm:w-64 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs text-text placeholder:text-faint"
          />
          <button
            onClick={publish}
            disabled={!publishTitle.trim()}
            className="rounded-lg bg-indigo-500/30 px-4 py-2 text-xs text-indigo-300 transition hover:bg-indigo-500/40 disabled:opacity-50"
          >
            Publish
          </button>
        </div>
      </Panel>

      <Panel title="Tasks" subtitle={`${tasks.length} total`} className="col-span-full">
        {tasks.length === 0 ? (
          <Empty title="No tasks" hint="Publish a task to begin." />
        ) : (
          <div className="space-y-2 overflow-hidden">
            {tasks.map((task) => (
              <div key={task.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-medium truncate">{task.title || task.id}</span>
                      <Badge tone={task.status === "completed" ? "ok" : task.status === "failed" ? "danger" : task.status === "awarded" ? "warn" : "default"}>
                        {task.status}
                      </Badge>
                    </div>
                    <div className="mt-1 truncate text-[11px] text-faint">
                      {task.required_capabilities.length > 0 ? task.required_capabilities.join(", ") : "no caps"} · {task.bids.length} bid(s)
                    </div>
                    {task.selected_bid && (
                      <div className="mt-1 text-[11px] text-emerald-400">
                        → {task.selected_bid.runtime_name} (score {safeFixed((safeNum(task?.selected_bid?.bid_score) * 100), 0)}%)
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
