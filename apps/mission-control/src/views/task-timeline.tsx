"use client";

import React from "react";
import { useStore } from "@/lib/store";
import { Panel, StatusDot, Empty } from "@/components/ui/primitives";
import type { EventEnvelope } from "@/lib/types";

const TASK_TOPICS = new Set([
  "task.created",
  "task.planned",
  "task.dispatched",
  "task.assigned",
  "agent.started",
  "agent.completed",
  "agent.failed",
  "agent.recovered",
]);

// Chronological timeline of task/agent lifecycle events. Pure EventBus history.
export function TaskTimeline() {
  const events = useStore((s) => s.events);
  const ingest = useStore((s) => s.ingest);
  const items = events.filter((e) => TASK_TOPICS.has(e.topic));

  // Hydrate from REST on mount so the timeline shows past events
  React.useEffect(() => {
    fetch("/api/events/recent?limit=50")
      .then((r) => r.json())
      .then((list) => {
        if (!Array.isArray(list)) return;
        for (const ev of list) {
          if (TASK_TOPICS.has(ev.topic)) ingest(ev as EventEnvelope);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="scroll-page p-4">
      <Panel title="Task Timeline" subtitle="Lifecycle events in order" className="flex-1 min-h-0">
        <div className="relative space-y-0">
          <div className="absolute bottom-0 left-[7px] top-0 w-px bg-border/50" />
          {items.map((e) => (
            <Row key={e.id} e={e} />
          ))}
          {items.length === 0 && <Empty title="No task events" hint="Lifecycle events stream here in real time." />}
        </div>
      </Panel>
    </div>
  );
}

function Row({ e }: { e: EventEnvelope }) {
  const p = e.payload as Record<string, any>;
  const failed = e.topic.includes("failed") || e.topic.includes("denied");
  return (
    <div className="relative flex items-start gap-3 pb-4 pl-0">
      <span className="relative z-10 mt-1 grid h-4 w-4 place-items-center">
        <StatusDot status={failed ? "danger" : "healthy"} pulse={e.topic === "agent.started"} />
      </span>
      <div className="flex-1 rounded-xl border border-border/50 bg-surface/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{e.topic}</span>
          <span className="text-[11px] text-faint">{new Date(e.timestamp).toLocaleTimeString()}</span>
        </div>
        <div className="mt-0.5 text-xs text-muted">
          {[p.role, p.title, p.id, p.agent_id].filter(Boolean).slice(0, 2).join(" · ") || e.source}
        </div>
      </div>
    </div>
  );
}
