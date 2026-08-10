"use client";

import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { ExecutionRecord } from "@/lib/types";
import {
  Search, Activity, CheckCircle2, XCircle, Loader2, RefreshCw,
  Clock, Cpu, Server, Terminal, AlertTriangle, X, ChevronRight,
  History, Filter,
} from "lucide-react";

function StatusPill({ status }: { status: ExecutionRecord["status"] }) {
  const map: Record<string, { color: string; bg: string; icon: React.ReactNode; label: string }> = {
    running: { color: "text-sky-300", bg: "bg-sky-500/10 border-sky-500/30", icon: <Loader2 size={11} className="animate-spin" />, label: "Running" },
    completed: { color: "text-emerald-300", bg: "bg-emerald-500/10 border-emerald-500/30", icon: <CheckCircle2 size={11} />, label: "Completed" },
    failed: { color: "text-red-300", bg: "bg-red-500/10 border-red-500/30", icon: <XCircle size={11} />, label: "Failed" },
    retried: { color: "text-amber-300", bg: "bg-amber-500/10 border-amber-500/30", icon: <RefreshCw size={11} />, label: "Retried" },
    abandoned: { color: "text-rose-300", bg: "bg-rose-500/10 border-rose-500/30", icon: <AlertTriangle size={11} />, label: "Abandoned" },
  };
  const s = map[status] ?? map.running;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${s.color} ${s.bg}`}>
      {s.icon}{s.label}
    </span>
  );
}

interface Filters { mission_id: string; provider: string; status: string; search: string; }

export function ExecutionTimeline() {
  const executions = useStore((s) => s.executions);
  const executionOrder = useStore((s) => s.executionOrder);
  const executionUpdates = useStore((s) => s.executionUpdates);
  const hydrateExecutions = useStore((s) => s.hydrateExecutions);
  const tasks = useStore((s) => s.tasks);

  const [filters, setFilters] = useState<Filters>({ mission_id: "", provider: "", status: "", search: "" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, number>>({ total: 0 });

  useEffect(() => {
    void hydrateExecutions();
    let cancelled = false;
    const pollStats = async () => {
      try { const s = await api.executionStats(); if (!cancelled) setStats(s as Record<string, number>); } catch {}
    };
    void pollStats();
    const t = setInterval(pollStats, 10000);
    return () => { cancelled = true; clearInterval(t); };
  }, [hydrateExecutions]);

  useEffect(() => {
    void api.executionStats().then((s) => setStats(s as Record<string, number>)).catch(() => {});
  }, [executionUpdates]);

  const filtered = useMemo(() => {
    const list: ExecutionRecord[] = [];
    for (const id of executionOrder) {
      const rec = executions[id];
      if (!rec) continue;
      if (filters.provider && rec.provider !== filters.provider) continue;
      if (filters.status && rec.status !== filters.status) continue;
      if (filters.mission_id && !rec.mission_id.includes(filters.mission_id)) continue;
      if (filters.search) {
        const q = filters.search.toLowerCase();
        const hay = `${rec.task_id} ${rec.command} ${rec.prompt_preview} ${rec.provider} ${rec.runtime}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      list.push(rec);
    }
    return list;
  }, [executionOrder, executions, filters]);

  const providers = useMemo(() => {
    const set = new Set<string>();
    for (const id of executionOrder) { const r = executions[id]; if (r?.provider) set.add(r.provider); }
    return Array.from(set).sort();
  }, [executionOrder, executions]);

  const selected = selectedId ? executions[selectedId] ?? null : null;

  return (
    <div className="flex h-full w-full flex-col overflow-hidden bg-bg text-text">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface px-4 py-3">
        <div className="flex items-center gap-2">
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-1.5 text-amber-400">
            <History size={16} />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-text">Execution Timeline</h2>
            <p className="text-[10px] text-faint">{filtered.length} shown · updates via WebSocket</p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-border/40 bg-surface px-4 py-2.5">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-muted"><Filter size={13} /><span>Filters</span></div>
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint/60" />
          <input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            placeholder="Search task / command..." className="w-56 rounded-lg border border-border/60 bg-surface/60 py-1.5 pl-8 pr-3 text-xs text-text placeholder:text-faint outline-none focus:border-amber-500/40" />
        </div>
        <select value={filters.provider} onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
          className="rounded-lg border border-border/60 bg-surface/60 px-2.5 py-1.5 text-xs text-text outline-none">
          <option value="">All providers</option>
          {providers.map((p) => <option key={p} value={p} className="bg-elevated">{p}</option>)}
        </select>
        <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="rounded-lg border border-border/60 bg-surface/60 px-2.5 py-1.5 text-xs text-text outline-none">
          <option value="">All statuses</option>
          <option value="running" className="bg-elevated">Running</option>
          <option value="completed" className="bg-elevated">Completed</option>
          <option value="failed" className="bg-elevated">Failed</option>
          <option value="retried" className="bg-elevated">Retried</option>
          <option value="abandoned" className="bg-elevated">Abandoned</option>
        </select>
        <input value={filters.mission_id} onChange={(e) => setFilters({ ...filters, mission_id: e.target.value })}
          placeholder="Mission ID..." className="w-40 rounded-lg border border-border/60 bg-surface/60 px-2.5 py-1.5 text-xs text-text placeholder:text-faint outline-none" />
        <div className="ml-auto flex items-center gap-3 text-[10px] text-faint">
          <span>Total: <span className="font-mono text-muted/80">{stats.total ?? 0}</span></span>
          <span>✓ <span className="font-mono text-emerald-300/70">{stats.completed ?? 0}</span></span>
          <span>✗ <span className="font-mono text-red-300/70">{stats.failed ?? 0}</span></span>
          <button onClick={() => void hydrateExecutions()} className="rounded-md border border-border/60 bg-surface/60 px-2 py-1 text-[10px] text-muted hover:bg-surface/80"><RefreshCw size={11} /></button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {filtered.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-faint/60">
            <Terminal size={32} className="opacity-50" />
            <div className="text-xs">No executions yet</div>
            <div className="text-[10px]">Submit a mission from Prompt Center to see executions stream in live.</div>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-surface text-[10px] uppercase tracking-wider text-faint">
              <tr>
                <th className="px-4 py-2 font-medium">Execution</th>
                <th className="px-4 py-2 font-medium">Task</th>
                <th className="px-4 py-2 font-medium">Provider</th>
                <th className="px-4 py-2 font-medium">Runtime</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 text-right font-medium">Duration</th>
                <th className="px-4 py-2 text-right font-medium">Retry</th>
                <th className="px-4 py-2 font-medium">Started</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((rec) => {
                const task = rec.task_id ? tasks[rec.task_id] : null;
                const isSel = rec.execution_id === selectedId;
                return (
                  <tr key={rec.execution_id} onClick={() => setSelectedId(rec.execution_id)}
                    className={`cursor-pointer border-b border-border/40 transition ${isSel ? "bg-amber-500/10" : "hover:bg-surface/50"}`}>
                    <td className="px-4 py-2 font-mono text-[10px] text-faint/80">{rec.execution_id.slice(0, 8)}</td>
                    <td className="px-4 py-2 text-text/80">{task?.title ?? rec.task_id.slice(0, 8)}{rec.mission_id && <span className="ml-1.5 text-[9px] text-faint/60">m:{rec.mission_id.slice(0, 6)}</span>}</td>
                    <td className="px-4 py-2"><span className="inline-flex items-center gap-1 text-muted/80"><Server size={11} className="text-faint" />{rec.provider || "—"}</span></td>
                    <td className="px-4 py-2"><span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted"><Cpu size={11} className="text-faint/60" />{rec.runtime || "—"}</span></td>
                    <td className="px-4 py-2"><StatusPill status={rec.status} /></td>
                    <td className="px-4 py-2 text-right font-mono text-[10px] text-muted">{rec.duration_ms > 0 ? `${rec.duration_ms}ms` : "—"}</td>
                    <td className="px-4 py-2 text-right">{rec.retry_count > 0 ? <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">×{rec.retry_count}</span> : <span className="text-faint/40">—</span>}</td>
                    <td className="px-4 py-2 font-mono text-[10px] text-faint">{rec.started_at ? new Date(rec.started_at).toLocaleTimeString() : "—"}</td>
                    <td className="px-4 py-2 text-faint/60"><ChevronRight size={12} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <AnimatePresence>
        {selected && (
          <motion.div initial={{ x: 400, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 400, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            className="absolute right-0 top-0 z-30 flex h-full w-full max-w-md flex-col border-l border-border/60 bg-surface shadow-2xl">
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
              <div className="flex items-center gap-2"><Activity size={14} className="text-amber-400" /><h3 className="text-xs font-semibold text-text">Execution Detail</h3></div>
              <button onClick={() => setSelectedId(null)} className="rounded-md p-1 text-faint hover:bg-surface/80 hover:text-text"><X size={14} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 text-xs">
              <div className="mb-4 flex items-center gap-2"><StatusPill status={selected.status} /><span className="font-mono text-[10px] text-faint">{selected.execution_id}</span></div>
              <div className="mb-4 grid grid-cols-2 gap-2 text-[11px]">
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Provider</span><span className="text-text/80">{selected.provider}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Runtime</span><span className={`text-text/80 ${selected.runtime ? "" : "opacity-50"}`}>{selected.runtime || "—"}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Strategy</span><span className="text-text/80">{selected.strategy}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Retry count</span><span className="text-text/80">{selected.retry_count}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Duration</span><span className="text-text/80">{selected.duration_ms}ms</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Exit code</span><span className="text-text/80">{selected.exit_code === null ? "—" : String(selected.exit_code)}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Task ID</span><span className="text-text/80">{selected.task_id.slice(0, 12)}</span></div>
                <div className="flex flex-col gap-0.5 rounded-md border border-border/40 bg-surface/40 px-2 py-1.5"><span className="text-[9px] uppercase tracking-wider text-faint">Mission ID</span><span className="text-text/80">{selected.mission_id.slice(0, 12) || "—"}</span></div>
              </div>
              {selected.command && (
                <div className="mb-4"><div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint/80"><Terminal size={12} />CLI Command</div><pre className="max-h-32 overflow-auto rounded-md border border-border/60 bg-black/40 p-2 font-mono text-[10px] leading-relaxed text-emerald-300/80">{selected.command}</pre></div>
              )}
              {selected.prompt_preview && (
                <div className="mb-4"><div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint/80"><Terminal size={12} />Prompt Sent to CLI</div><pre className="max-h-48 overflow-auto rounded-md border border-amber-500/20 bg-amber-500/[0.03] p-2 font-mono text-[10px] leading-relaxed text-amber-100/80">{selected.prompt_preview}</pre><p className="mt-1 text-[9px] text-faint/60">The structured prompt above is what the CLI agent received. It contains the user&apos;s original mission request and the planner&apos;s task description.</p></div>
              )}
              {selected.stdout && (
                <div className="mb-4"><div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint/80"><CheckCircle2 size={12} />stdout</div><pre className="max-h-32 overflow-auto rounded-md border border-border/60 bg-black/40 p-2 font-mono text-[10px] leading-relaxed text-emerald-200/70">{selected.stdout}</pre></div>
              )}
              {selected.stderr && (
                <div className="mb-4"><div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint/80"><AlertTriangle size={12} />stderr</div><pre className="max-h-32 overflow-auto rounded-md border border-red-500/20 bg-red-500/[0.03] p-2 font-mono text-[10px] leading-relaxed text-red-200/80">{selected.stderr}</pre></div>
              )}
              {selected.error && (
                <div className="mb-4"><div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-faint/80"><XCircle size={12} />Error</div><pre className="max-h-32 overflow-auto rounded-md border border-red-500/30 bg-red-500/10 p-2 font-mono text-[10px] leading-relaxed text-red-200">{selected.error}</pre></div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
