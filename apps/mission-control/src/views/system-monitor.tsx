"use client";

import { useShallow } from "zustand/react/shallow";
import { Panel, Stat, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { api } from "@/lib/api";
import { safeFixed, safeNum, safeStr, safeArr, safeLen } from "@/lib/safe";
import { useMemo, useEffect, useCallback, useState, useRef } from "react";
import { List, type RowComponentProps } from "react-window";
import { AutoSizer } from "react-virtualized-auto-sizer";
import type { DesktopPerformanceMetrics } from "@/lib/desktop-types";

// ── Polling hook for live resource metrics ──
function usePerformancePoll(intervalMs = 5_000) {
  const setPerformance = useStore((s) => s.setPerformance);
  const connected = useStore((s) => s.connected);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    try {
      const p = await api.performance();
      setPerformance(p);
      setError(null);
    } catch {
      setError("Performance endpoint unreachable");
    }
  }, [setPerformance]);

  useEffect(() => {
    if (!connected) return;
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => clearInterval(id);
  }, [connected, intervalMs, fetch]);

  return error;
}

// ── Resource gauge ──
function Gauge({
  label,
  percent,
  used,
  total,
  unit = "%",
  tone = "accent",
}: {
  label: string;
  percent: number;
  used: number;
  total: number;
  unit?: string;
  tone?: string;
}) {
  const hue = percent > 90 ? "danger" : percent > 70 ? "warn" : tone;
  const barColor =
    hue === "danger"
      ? "bg-danger"
      : hue === "warn"
        ? "bg-warn"
        : "bg-accent";
  return (
    <div className="glass rounded-xl px-4 py-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wide text-faint">
          {label}
        </span>
        <span className="text-xs font-semibold tabular-nums text-text">
          {percent.toFixed(1)}
          {unit}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface/50">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-faint tabular-nums">
        <span>{used.toFixed(1)} used</span>
        <span>{total.toFixed(1)} total</span>
      </div>
    </div>
  );
}

// ── Virtualized Event Row ──

function EventRow({ index, style, events }: { index: number; style: React.CSSProperties; events: Array<{ id: string; topic: string; source: string; timestamp: string }> }) {
  const e = events[index];
  return (
    <div style={style} className="flex items-center gap-3 px-4 py-1.5">
      <StatusDot
        status={
          e.topic.includes("fail") || e.topic.includes("denied")
            ? "danger"
            : "healthy"
        }
      />
      <span className="w-44 shrink-0 truncate text-faint">{e.topic}</span>
      <span className="flex-1 truncate text-muted">{e.source}</span>
      <span className="text-faint">{new Date(e.timestamp).toLocaleTimeString()}</span>
    </div>
  );
}

// ── Main component ──
export function SystemMonitor() {
  const m = useStore(useShallow(selectMetrics));
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);
  const perf = useStore((s) => s.performance);
  const pollError = usePerformancePoll();

  // Reset pollError when it resolves so we don't show stale error on reconnect
  const rates = useMemo(() => {
    const now = Date.now();
    const windowMs = 60_000;
    const recent = events.filter(
      (e) => now - new Date(e.timestamp).getTime() < windowMs,
    );
    const buckets = new Array(60).fill(0);
    for (const e of recent) {
      const ts = new Date(e.timestamp).getTime();
      const idx = Math.min(
        59,
        Math.max(0, Math.floor((now - ts) / 1000)),
      );
      buckets[59 - idx] += 1;
    }
    const perSec = recent.length / 60;
    const counts: Record<string, number> = {};
    for (const e of recent) counts[e.topic] = (counts[e.topic] ?? 0) + 1;
    const byTopic = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12);
    const maxTopic = byTopic[0]?.[1] ?? 1;
    return { buckets, perSec, byTopic, maxTopic };
  }, [events]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* Top stats bar */}
      <div className="col-span-12 flex flex-wrap gap-3">
        <Stat
          label="Connection"
          value={connected ? "live" : "offline"}
          tone={connected ? "ok" : "danger"}
        />
        <Stat
          label="Throughput"
          value={`${rates.perSec.toFixed(1)}/s`}
          tone="accent"
        />
        <Stat label="Agents" value={m.agents} />
        <Stat label="Tasks" value={m.tasks} />
        <Stat label="Providers" value={m.providers} />
        <Stat
          label="Errors"
          value={m.errors}
          tone={m.errors ? "danger" : "ok"}
        />
        <Stat label="Cost" value={`$${m.cost.toFixed(4)}`} tone="warn" />
        <Stat
          label="Latency"
          value={`${safeFixed(m?.latency, 0)}ms`}
          tone={m.latency > 1000 ? "warn" : "default"}
        />
      </div>

      {/* System Resources — CPU, RAM, Disk */}
      <Panel
        title="System Resources"
        subtitle={
          perf
            ? `live · ${perf.process_count} processes · up ${formatUptime(perf.uptime_seconds)}`
            : pollError
              ? "unreachable"
              : "awaiting data…"
        }
        className="col-span-12 lg:col-span-4"
      >
        <div className="flex flex-col gap-3">
          {perf ? (
            <>
              <Gauge
                label="CPU"
                percent={perf.cpu_usage_percent}
                used={perf.cpu_usage_percent}
                total={100}
                tone="accent"
              />
              <Gauge
                label="Memory"
                percent={perf.memory_usage_percent}
                used={perf.memory_used_mb}
                total={perf.memory_total_mb}
                unit=" MB"
                tone="accent"
              />
              <Gauge
                label="Disk"
                percent={perf.disk_usage_percent}
                used={perf.disk_total_gb - perf.disk_free_gb}
                total={perf.disk_total_gb}
                unit=" GB"
                tone="accent"
              />
              <div className="mt-1 grid grid-cols-2 gap-2 text-[11px] text-faint tabular-nums">
                <span>Windows: {perf.window_count}</span>
              </div>
            </>
          ) : (
            <Empty
              title={
                pollError
                  ? "Backend performance API unreachable"
                  : "Waiting for backend…"
              }
              hint={
                pollError
                  ? "The system-monitor endpoint is not available. Check backend health."
                  : "System metrics appear on first successful poll."
              }
            />
          )}
        </div>
      </Panel>

      {/* Event Throughput chart */}
      <Panel
        title="Event Throughput"
        subtitle="Events per second (last 60s)"
        className="col-span-12 lg:col-span-8"
      >
        <ThroughputChart rates={rates.buckets} />
      </Panel>

      {/* Topic Breakdown */}
      <Panel
        title="Topic Breakdown"
        subtitle="By live event count"
        className="col-span-12 lg:col-span-4"
      >
        <div className="space-y-1.5">
          {rates.byTopic.map(([topic, count]) => (
            <div key={topic} className="flex items-center gap-2 text-xs">
              <span className="w-40 shrink-0 truncate font-mono text-faint">
                {topic}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface/50">
                <div
                  className="h-full bg-accent/70"
                  style={
                    {
                      width: `${(count / rates.maxTopic) * 100}%`,
                    }
                  }
                />
              </div>
              <span className="w-8 text-right tabular-nums text-muted">
                {count}
              </span>
            </div>
          ))}
          {rates.byTopic.length === 0 && <Empty title="No events yet" />}
        </div>
      </Panel>

      {/* Resource Usage Detail */}
      <Panel
        title="Resource Details"
        subtitle="Process-level snapshot from backend"
        className="col-span-12 lg:col-span-4"
      >
        {perf ? (
          <div className="grid grid-cols-2 gap-2 text-xs">
            <MetricTile label="Processes" value={perf.process_count} />
            <MetricTile label="Windows" value={perf.window_count} />
            <MetricTile
              label="Free Disk"
              value={`${(perf.disk_free_gb ?? 0).toFixed(1)} GB`}
            />
            <MetricTile
              label="Memory Used"
              value={`${(perf.memory_used_mb ?? 0).toFixed(0)} MB`}
            />
            <MetricTile
              label="Total Memory"
              value={`${(perf.memory_total_mb ?? 0).toFixed(0)} MB`}
            />
            <MetricTile
              label="Total Disk"
              value={`${(perf.disk_total_gb ?? 0).toFixed(1)} GB`}
            />
          </div>
        ) : (
          <Empty title="No details available" />
        )}
      </Panel>

      {/* Recent Events */}
      <Panel
        title="Recent Events"
        subtitle="Raw EventBus envelope stream"
        className="col-span-12 lg:col-span-8 min-h-0 flex-1"
        contentClassName="p-0"
      >
        {events.length === 0 ? (
          <div className="p-4">
            <Empty title="Awaiting stream…" />
          </div>
        ) : (
          <div className="h-full w-full">
            <AutoSizer
              renderProp={({ height, width }) => (
                <List<{ events: Array<{ id: string; topic: string; source: string; timestamp: string }> }>
                  style={{ height: height ?? 0, width: width ?? 0 }}
                  rowCount={events.length}
                  rowHeight={36}
                  rowProps={{ events }}
                  rowComponent={EventRow}
                  className="divide-y divide-border/40 font-mono text-xs"
                  overscanCount={20}
                />
              )}
            />
          </div>
        )}
      </Panel>
    </div>
  );
}

// ── Shared sub-components ──

function MetricTile({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="glass rounded-lg px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-faint">
        {label}
      </div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-text">
        {value}
      </div>
    </div>
  );
}

function ThroughputChart({ rates }: { rates: number[] }) {
  const max = Math.max(1, ...rates);
  return (
    <div className="flex h-full items-end gap-[2px]">
      {rates.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm bg-accent/70"
          style={{
            height: `${(v / max) * 100}%`,
            minHeight: v > 0 ? 2 : 1,
            opacity: 0.4 + (i / 60) * 0.6,
          }}
          title={`${v} evt/s`}
        />
      ))}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
