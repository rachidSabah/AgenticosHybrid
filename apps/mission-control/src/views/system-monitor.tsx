"use client";

import { useCallback, useEffect, useState, useRef } from "react";
import { Panel, Badge, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
import { safeFixed } from "@/lib/safe";
import type { DesktopPerformanceMetrics } from "@/lib/desktop-types";

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function KpiCard({ label, value, tone = "default" }: { label: string; value: string | number; tone?: "default" | "ok" | "warn" | "danger" | "accent" }) {
  const toneClass = { default: "text-text", ok: "text-ok", warn: "text-warn", danger: "text-danger", accent: "text-accent" }[tone];
  return (
    <div className="glass rounded-xl px-4 py-3 flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

function ProgressBar({ value, label, tone }: { value: number; label: string; tone?: "ok" | "warn" | "danger" | "accent" }) {
  const colorMap: Record<string, string> = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", accent: "bg-accent" };
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-faint">{label}</span>
        <span className="font-mono tabular-nums text-muted">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface/50">
        <div className={`h-full rounded-full ${colorMap[tone ?? "accent"] ?? "bg-accent"} transition-all`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}

export function SystemMonitor() {
  const m = useStore(useShallow(selectMetrics));
  const events = useStore((s) => s.events);
  const connected = useStore((s) => s.connected);

  const [perf, setPerf] = useState<DesktopPerformanceMetrics | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async () => {
    try {
      const p = await api.performance();
      setPerf(p);
      setPollError(null);
    } catch (err) {
      setPollError(String(err));
    }
  }, []);

  useEffect(() => {
    poll();
    timerRef.current = setInterval(poll, 5000);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [poll]);

  const rates = (() => {
    const now = Date.now();
    const recent = events.filter((e) => now - new Date(e.timestamp).getTime() < 60000);
    const perSec = recent.length / 60;
    const counts: Record<string, number> = {};
    for (const e of recent) counts[e.topic] = (counts[e.topic] ?? 0) + 1;
    const byTopic = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    return { perSec, byTopic };
  })();

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">System Monitor</h2>
          <span className={`inline-block h-2 w-2 rounded-full ${connected ? "bg-ok animate-pulse" : "bg-danger"}`} />
          <span className="text-[10px] text-faint">{connected ? "Live" : "Offline"}</span>
        </div>
        <button onClick={poll} className="rounded-lg border border-border/60 px-3 py-1.5 text-xs text-faint transition hover:bg-surface/30">Refresh</button>
      </div>

      {/* ── KPI Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <KpiCard label="Connection" value={connected ? "Live" : "Offline"} tone={connected ? "ok" : "danger"} />
        <KpiCard label="Throughput" value={`${rates.perSec.toFixed(1)}/s`} tone="accent" />
        <KpiCard label="Agents" value={m.agents} tone="default" />
        <KpiCard label="Errors" value={m.errors} tone={m.errors ? "danger" : "ok"} />
      </div>

      {/* ── Two-column content ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[1fr_1fr]">
        {/* Left: System Resources */}
        <Panel title="System Resources" subtitle={perf ? `${perf.process_count} processes · up ${formatUptime(perf.uptime_seconds)}` : "Loading…"}>
          {perf ? (
            <div className="space-y-4">
              <ProgressBar value={perf.cpu_usage_percent} label="CPU" tone={perf.cpu_usage_percent > 80 ? "danger" : perf.cpu_usage_percent > 60 ? "warn" : "accent"} />
              <ProgressBar value={perf.memory_usage_percent} label="Memory" tone={perf.memory_usage_percent > 80 ? "danger" : perf.memory_usage_percent > 60 ? "warn" : "accent"} />
              <ProgressBar value={perf.disk_usage_percent} label="Disk" tone={perf.disk_usage_percent > 90 ? "danger" : perf.disk_usage_percent > 75 ? "warn" : "accent"} />
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="rounded-lg border border-border/40 p-2">
                  <div className="text-[9px] uppercase text-faint">Memory</div>
                  <div className="text-sm font-bold tabular-nums">{safeFixed(perf.memory_used_mb, 0)}/{safeFixed(perf.memory_total_mb, 0)} MB</div>
                </div>
                <div className="rounded-lg border border-border/40 p-2">
                  <div className="text-[9px] uppercase text-faint">Disk Free</div>
                  <div className="text-sm font-bold tabular-nums">{safeFixed(perf.disk_free_gb, 1)} GB</div>
                </div>
              </div>
            </div>
          ) : (
            <Empty title="No performance data" hint={pollError ?? "Polling…"} />
          )}
        </Panel>

        {/* Right: Event Topics */}
        <Panel title="Event Topics" subtitle={`${rates.byTopic.length} active`}>
          <div className="min-h-0 max-h-[300px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1.5">
            {rates.byTopic.length === 0 ? (
              <Empty title="No events" hint="EventBus traffic appears here." />
            ) : (
              rates.byTopic.map(([topic, count]) => {
                const maxCount = rates.byTopic[0]?.[1] ?? 1;
                const pct = (count / maxCount) * 100;
                return (
                  <div key={topic} className="rounded-lg border border-border/40 p-2">
                    <div className="flex items-center justify-between text-[10px]">
                      <span className="truncate font-mono text-muted">{topic}</span>
                      <span className="text-faint tabular-nums">{count}</span>
                    </div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-surface/50">
                      <div className="h-full rounded-full bg-accent/60" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </Panel>
      </div>

      {/* ── Bottom stats row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <KpiCard label="Tasks" value={m.tasks} tone="default" />
        <KpiCard label="Providers" value={m.providers} tone="default" />
        <KpiCard label="Cost" value={`$${m.cost.toFixed(4)}`} tone="warn" />
        <KpiCard label="Latency" value={`${safeFixed(m?.latency, 0)}ms`} tone={m.latency > 1000 ? "warn" : "default"} />
      </div>
    </div>
  );
}
