"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";

/**
 * Phase 17 — Evolution Dashboard.
 *
 * Renders LIVE evolution state from /api/evolution/* endpoints and the
 * evolution.* WebSocket events ingested by the store. Shows the
 * improvement pipeline: proposals → validation → scheduling →
 * application → rollback.
 */

type EvoTab = "overview" | "improvements" | "safety" | "scheduler" | "plans" | "knowledge";

type EvolutionStats = {
  total_proposals: number;
  pending: number;
  validated: number;
  approved: number;
  applied: number;
  rejected: number;
  rolled_back: number;
  generation_plans: number;
  knowledge_syntheses: number;
  safety_pass_rate: number;
  average_impact: number;
  average_risk: number;
};

type SystemReadiness = {
  level: string;
  readiness_score: number;
  active_improvements: number;
  pending_validations: number;
  regression_risk: number;
  issues: string[];
};

type Improvement = {
  id: string;
  type: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  source: string;
  expected_impact: number;
  confidence: number;
  risk_score: number;
  created_at: string;
};

type SafetyHistory = {
  improvement_id: string;
  overall_result: string;
  overall_score: number;
  approved: boolean;
  blocking_issues: string[];
  warnings: string[];
}[];

type ScheduledItem = {
  id: string;
  title: string;
  priority: string;
  status: string;
  risk_score: number;
};

type GenerationPlan = {
  id: string;
  target_type: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
};

type KnowledgeSynthesis = {
  id: string;
  topic: string;
  summary: string;
  key_insights: string[];
  confidence: number;
  created_at: string;
};

export function EvolutionDashboard() {
  const [tab, setTab] = useState<EvoTab>("overview");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-1 border-b border-border/60 px-4 pt-2">
        {(["overview", "improvements", "safety", "scheduler", "plans", "knowledge"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t ? "bg-surface/40 text-text" : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "overview" ? "Overview" : t === "improvements" ? "Improvement Queue" : t === "safety" ? "Safety Status" : t === "scheduler" ? "Scheduler" : t === "plans" ? "Generated Plans" : "Knowledge"}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {tab === "overview" && <OverviewTab />}
        {tab === "improvements" && <ImprovementsTab />}
        {tab === "safety" && <SafetyTab />}
        {tab === "scheduler" && <SchedulerTab />}
        {tab === "plans" && <PlansTab />}
        {tab === "knowledge" && <KnowledgeTab />}
      </div>
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────────────────

function OverviewTab() {
  const [stats, setStats] = useState<EvolutionStats | null>(null);
  const [readiness, setReadiness] = useState<SystemReadiness | null>(null);
  const [loading, setLoading] = useState(false);
  const evoLive = useStore((s) => s.evolution);
  const connected = useStore((s) => s.connected);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, r] = await Promise.all([
        api.get<EvolutionStats>("/api/evolution/statistics"),
        api.get<SystemReadiness>("/api/evolution/readiness"),
      ]);
      setStats(s);
      setReadiness(r);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    void load();
    void useStore.getState().hydrateEvolution();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const liveStats = (evoLive?.statistics as EvolutionStats | null) ?? stats;
  const liveReadiness = (evoLive?.readiness as SystemReadiness | null) ?? readiness;

  const readinessTone =
    liveReadiness?.level === "ready" || liveReadiness?.level === "optimizing" ? "ok"
    : liveReadiness?.level === "cautious" ? "warn"
    : "danger";

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Proposals" value={liveStats?.total_proposals ?? 0} />
        <Stat label="Pending" value={liveStats?.pending ?? 0} />
        <Stat label="Applied" value={liveStats?.applied ?? 0} tone="ok" />
        <Stat label="Rejected" value={liveStats?.rejected ?? 0} tone={(liveStats?.rejected ?? 0) > 0 ? "danger" : "default"} />
        <Stat label="Rolled Back" value={liveStats?.rolled_back ?? 0} tone={(liveStats?.rolled_back ?? 0) > 0 ? "warn" : "default"} />
        <Stat label="Pass Rate" value={`${((liveStats?.safety_pass_rate ?? 0) * 100).toFixed(0)}%`} />
        <div className="ml-auto flex items-center gap-2">
          <Badge tone={connected ? "ok" : "default"}>{connected ? "LIVE" : "Local"}</Badge>
          <button onClick={load} disabled={loading} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20 disabled:opacity-50">{loading ? "Refreshing…" : "Refresh"}</button>
        </div>
      </div>

      <Panel title="System Readiness" subtitle={liveReadiness?.level ?? "—"} className="col-span-6">
        {!liveReadiness ? (
          <Empty title="No readiness data" hint="Run analysis to assess." />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Badge tone={readinessTone as "ok" | "warn" | "danger" | "default"}>{liveReadiness.level}</Badge>
              <div className="flex-1">
                <div className="text-xs text-faint">Readiness Score</div>
                <div className="mt-1 h-2 w-full rounded-full bg-surface/40">
                  <div className="h-2 rounded-full bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-500" style={{ width: `${(liveReadiness.readiness_score * 100).toFixed(0)}%` }} />
                </div>
                <div className="mt-1 text-[11px] text-faint">{(liveReadiness.readiness_score * 100).toFixed(1)}%</div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <Metric label="Active" value={String(liveReadiness.active_improvements)} />
              <Metric label="Pending" value={String(liveReadiness.pending_validations)} />
              <Metric label="Regression Risk" value={`${(liveReadiness.regression_risk * 100).toFixed(0)}%`} />
              <Metric label="Avg Impact" value={`${((liveStats?.average_impact ?? 0) * 100).toFixed(0)}%`} />
            </div>
            {liveReadiness.issues.length > 0 && (
              <div>
                <div className="mb-1 text-xs font-medium text-rose-400">Issues</div>
                <ul className="space-y-1 text-[11px] text-faint">
                  {liveReadiness.issues.map((issue, i) => <li key={i}>• {issue}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </Panel>

      <Panel title="Evolution Actions" subtitle="Self-improvement controls" className="col-span-6">
        <div className="grid grid-cols-2 gap-3">
          <ActionButton label="Analyze" description="Generate + validate proposals" endpoint="/api/evolution/analyze" />
          <ActionButton label="Schedule Next" description="Pick next improvement" endpoint="/api/evolution/schedule" />
          <ActionButton label="Assess Readiness" description="Recompute readiness" endpoint="/api/evolution/readiness/assess" />
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
    setRunning(true); setResult(null);
    try {
      const r = await api.post<Record<string, unknown>>(endpoint, {});
      setResult(JSON.stringify(r).slice(0, 150));
    } catch (e) { setResult(String(e)); }
    finally { setRunning(false); }
  }, [endpoint]);
  return (
    <div className="rounded-xl border border-border/60 p-3">
      <div className="text-xs font-medium">{label}</div>
      <div className="mt-0.5 text-[11px] text-faint">{description}</div>
      <button onClick={onClick} disabled={running} className="mt-2 w-full rounded-lg bg-indigo-500/20 px-3 py-1.5 text-[11px] text-indigo-300 transition hover:bg-indigo-500/30 disabled:opacity-50">{running ? "Running…" : "Run"}</button>
      {result && <div className="mt-2 truncate text-[10px] text-faint">{result}</div>}
    </div>
  );
}

// ── Improvements Tab ──────────────────────────────────────────────────

function ImprovementsTab() {
  const [improvements, setImprovements] = useState<Improvement[]>([]);
  const [filter, setFilter] = useState<string>("all");

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ improvements: Improvement[] }>("/api/evolution/improvements");
      setImprovements(r.improvements ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  const filtered = filter === "all" ? improvements : improvements.filter((i) => i.status === filter);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Total" value={improvements.length} />
        <Stat label="Pending" value={improvements.filter((i) => i.status === "proposed").length} />
        <Stat label="Applied" value={improvements.filter((i) => i.status === "applied").length} tone="ok" />
        <div className="ml-auto flex gap-1">
          {["all", "proposed", "validated", "approved", "applied", "rejected"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`rounded-lg px-3 py-1.5 text-[11px] transition ${filter === f ? "bg-indigo-500/30 text-text" : "border border-border/60 text-faint hover:bg-surface/20"}`}>{f}</button>
          ))}
          <button onClick={load} className="ml-2 rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button>
        </div>
      </div>

      <Panel title="Improvement Queue" subtitle={`${filtered.length} items`} className="col-span-12">
        {filtered.length === 0 ? (
          <Empty title="No improvements" hint="Run analysis to generate proposals." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {filtered.map((imp) => (
              <div key={imp.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <Badge tone={imp.priority === "critical" ? "danger" : imp.priority === "high" ? "warn" : "default"}>{imp.priority}</Badge>
                      <span className="text-sm font-medium">{imp.title}</span>
                    </div>
                    <div className="mt-1 text-[11px] text-faint">{imp.description}</div>
                    <div className="mt-1 text-[10px] text-faint">source: {imp.source} · type: {imp.type}</div>
                  </div>
                  <Badge tone={imp.status === "applied" ? "ok" : imp.status === "rejected" ? "danger" : imp.status === "validated" || imp.status === "approved" ? "warn" : "default"}>{imp.status}</Badge>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                  <Metric label="Impact" value={`${(imp.expected_impact * 100).toFixed(0)}%`} />
                  <Metric label="Confidence" value={`${(imp.confidence * 100).toFixed(0)}%`} />
                  <Metric label="Risk" value={`${(imp.risk_score * 100).toFixed(0)}%`} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Safety Tab ────────────────────────────────────────────────────────

function SafetyTab() {
  const [data, setData] = useState<{ validator: Record<string, unknown>; regression_guard: Record<string, unknown>; history: SafetyHistory } | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ validator: Record<string, unknown>; regression_guard: Record<string, unknown>; history: SafetyHistory }>("/api/evolution/safety");
      setData(r);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Validations" value={String(data?.validator?.total_validations ?? 0)} />
        <Stat label="Approved" value={String(data?.validator?.approved ?? 0)} tone="ok" />
        <Stat label="Rejected" value={String(data?.validator?.rejected ?? 0)} tone={(Number(data?.validator?.rejected ?? 0)) > 0 ? "danger" : "default"} />
        <Stat label="Pass Rate" value={`${(((data?.validator?.pass_rate as number) ?? 0) * 100).toFixed(0)}%`} />
        <div className="ml-auto"><button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button></div>
      </div>

      <Panel title="Safety Validation History" subtitle="Recent validation reports" className="col-span-12">
        {!data || !data.history || data.history.length === 0 ? (
          <Empty title="No validations yet" hint="Run analysis to trigger safety validation." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {data.history.map((h, i) => (
              <div key={i} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono">{h.improvement_id}</span>
                  <Badge tone={h.approved ? "ok" : "danger"}>{h.overall_result}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">Score: {(h.overall_score * 100).toFixed(0)}%</div>
                {h.blocking_issues.length > 0 && (
                  <div className="mt-1 text-[11px] text-rose-400">⚠ {h.blocking_issues.join("; ")}</div>
                )}
                {h.warnings.length > 0 && (
                  <div className="mt-1 text-[11px] text-amber-400">⚠ {h.warnings.join("; ")}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Scheduler Tab ─────────────────────────────────────────────────────

function SchedulerTab() {
  const [data, setData] = useState<{ stats: Record<string, unknown>; queue: ScheduledItem[]; scheduled: ScheduledItem[] } | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ stats: Record<string, unknown>; queue: ScheduledItem[]; scheduled: ScheduledItem[] }>("/api/evolution/scheduler");
      setData(r);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Queue" value={String(data?.stats?.queue_size ?? 0)} />
        <Stat label="Active" value={String(data?.stats?.active ?? 0)} tone="ok" />
        <Stat label="Scheduled" value={String(data?.stats?.total_scheduled ?? 0)} />
        <Stat label="Executed" value={String(data?.stats?.total_executed ?? 0)} tone="ok" />
        <div className="ml-auto"><button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button></div>
      </div>

      <Panel title="Execution Queue" subtitle="Pending improvements (ordered by priority + risk)" className="col-span-6">
        {!data || data.queue.length === 0 ? (
          <Empty title="Queue empty" hint="Validated improvements will appear here." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {data.queue.map((item) => (
              <div key={item.id} className="rounded-lg border border-border/60 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{item.title}</span>
                  <Badge tone={item.priority === "critical" ? "danger" : item.priority === "high" ? "warn" : "default"}>{item.priority}</Badge>
                </div>
                <div className="mt-1 text-[10px] text-faint">risk: {(item.risk_score * 100).toFixed(0)}%</div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Active Improvements" subtitle="Currently scheduled/executing" className="col-span-6">
        {!data || data.scheduled.length === 0 ? (
          <Empty title="No active improvements" hint="Schedule next to start execution." />
        ) : (
          <div className="space-y-2">
            {data.scheduled.map((item) => (
              <div key={item.id} className="rounded-lg border border-border/60 px-3 py-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{item.title}</span>
                  <Badge tone={item.status === "executing" ? "warn" : "ok"}>{item.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Plans Tab ─────────────────────────────────────────────────────────

function PlansTab() {
  const [plans, setPlans] = useState<GenerationPlan[]>([]);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ plans: GenerationPlan[] }>("/api/evolution/plans");
      setPlans(r.plans ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Plans" value={plans.length} />
        <div className="ml-auto"><button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button></div>
      </div>

      <Panel title="Generation Plans" subtitle="Blueprints for new artifacts" className="col-span-12">
        {plans.length === 0 ? (
          <Empty title="No plans" hint="Schedule improvements to generate plans." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {plans.map((plan) => (
              <div key={plan.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone="default">{plan.target_type}</Badge>
                    <span className="text-sm font-medium">{plan.name}</span>
                  </div>
                  <Badge tone={plan.status === "approved" ? "ok" : plan.status === "generated" ? "warn" : "default"}>{plan.status}</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">{plan.description}</div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Knowledge Tab ─────────────────────────────────────────────────────

function KnowledgeTab() {
  const [syntheses, setSyntheses] = useState<KnowledgeSynthesis[]>([]);

  const load = useCallback(async () => {
    try {
      const r = await api.get<{ syntheses: KnowledgeSynthesis[] }>("/api/evolution/knowledge");
      setSyntheses(r.syntheses ?? []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-12 flex items-center gap-3">
        <Stat label="Syntheses" value={syntheses.length} />
        <div className="ml-auto"><button onClick={load} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-faint transition hover:bg-surface/20">Refresh</button></div>
      </div>

      <Panel title="Knowledge Syntheses" subtitle="Extracted patterns + insights" className="col-span-12">
        {syntheses.length === 0 ? (
          <Empty title="No syntheses" hint="POST /api/evolution/synthesize to create." />
        ) : (
          <div className="space-y-2 max-h-[60vh] overflow-auto">
            {syntheses.map((s) => (
              <div key={s.id} className="rounded-xl border border-border/60 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{s.topic}</span>
                  <Badge tone={s.confidence > 0.6 ? "ok" : "warn"}>conf {(s.confidence * 100).toFixed(0)}%</Badge>
                </div>
                <div className="mt-1 text-[11px] text-faint">{s.summary}</div>
                {s.key_insights.length > 0 && (
                  <ul className="mt-2 space-y-1 text-[11px] text-faint">
                    {s.key_insights.slice(0, 5).map((insight, i) => <li key={i}>• {insight}</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
