"use client";

import { Panel, Stat, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";

export function SystemMonitor() {
  const m = useStore(selectMetrics);
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);
  const rates = useRates(events);

  return (
    <div className="grid h-full grid-cols-12 grid-rows-6 gap-4 p-4">
      <div className="col-span-12 row-span-1 flex flex-wrap gap-3">
        <Stat label="Connection" value={connected ? "live" : "offline"} tone={connected ? "ok" : "danger"} />
        <Stat label="Throughput" value={`${rates.perSec.toFixed(1)}/s`} tone="accent" />
        <Stat label="Agents" value={m.agents} />
        <Stat label="Tasks" value={m.tasks} />
        <Stat label="Providers" value={m.providers} />
        <Stat label="Errors" value={m.errors} tone={m.errors ? "danger" : "ok"} />
        <Stat label="Cost" value={`$${m.cost.toFixed(4)}`} tone="warn" />
      </div>

      <Panel title="Event Throughput" subtitle="Events per second (last 60s)" className="col-span-8 row-span-3">
        <ThroughputChart rates={rates.buckets} />
      </Panel>

      <Panel title="Topic Breakdown" subtitle="By live event count" className="col-span-4 row-span-3">
        <div className="space-y-1.5">
          {rates.byTopic.map(([topic, count]) => (
            <div key={topic} className="flex items-center gap-2 text-xs">
              <span className="w-40 shrink-0 truncate font-mono text-faint">{topic}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface/50">
                <div className="h-full bg-accent/70" style={{ width: `${(count / rates.maxTopic) * 100}%` }} />
              </div>
              <span className="w-8 text-right tabular-nums text-muted">{count}</span>
            </div>
          ))}
          {rates.byTopic.length === 0 && <Empty title="No events yet" />}
        </div>
      </Panel>

      <Panel title="Recent Events" subtitle="Raw EventBus envelope stream" className="col-span-12 row-span-2" contentClassName="p-0">
        <div className="divide-y divide-border/40 font-mono text-xs">
          {events.slice(0, 30).map((e) => (
            <div key={e.id} className="flex items-center gap-3 px-4 py-1.5">
              <StatusDot status={e.topic.includes("fail") || e.topic.includes("denied") ? "danger" : "healthy"} />
              <span className="w-44 shrink-0 truncate text-faint">{e.topic}</span>
              <span className="flex-1 truncate text-muted">{e.source}</span>
              <span className="text-faint">{new Date(e.timestamp).toLocaleTimeString()}</span>
            </div>
          ))}
          {events.length === 0 && <Empty title="Awaiting stream…" />}
        </div>
      </Panel>
    </div>
  );
}

function useRates(events: { topic: string; timestamp: string }[]) {
  const now = Date.now();
  const windowMs = 60_000;
  const recent = events.filter((e) => now - new Date(e.timestamp).getTime() < windowMs);
  const buckets = new Array(60).fill(0);
  for (const e of recent) {
    const ts = new Date(e.timestamp).getTime();
    const idx = Math.min(59, Math.max(0, Math.floor((now - ts) / 1000)));
    buckets[59 - idx] += 1;
  }
  const perSec = recent.length / 60;
  const counts: Record<string, number> = {};
  for (const e of recent) counts[e.topic] = (counts[e.topic] ?? 0) + 1;
  const byTopic = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 12);
  const maxTopic = byTopic[0]?.[1] ?? 1;
  return { buckets, perSec, byTopic, maxTopic };
}

function ThroughputChart({ rates }: { rates: number[] }) {
  const max = Math.max(1, ...rates);
  return (
    <div className="flex h-full items-end gap-[2px]">
      {rates.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-sm bg-accent/70"
          style={{ height: `${(v / max) * 100}%`, minHeight: v > 0 ? 2 : 1, opacity: 0.4 + (i / 60) * 0.6 }}
          title={`${v} evt/s`}
        />
      ))}
    </div>
  );
}
