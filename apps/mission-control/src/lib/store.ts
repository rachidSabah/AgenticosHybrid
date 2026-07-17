"use client";

// Live event store. Consumes the backend /ws/dashboard stream and derives
// Mission Control state. ALL data originates from real EventBus events —
// nothing here is simulated.

import { create } from "zustand";
import type {
  AgentNode,
  AuditEntry,
  EventEnvelope,
  MemoryItem,
  ProviderHealthRecord,
  SystemMetrics,
  TaskNode,
} from "./types";

export interface Notification {
  id: string;
  topic: string;
  title: string;
  detail: string;
  level: "info" | "ok" | "warn" | "danger";
  at: number;
}

interface Telemetry {
  // Rolling counters derived from events.
  tasks: number;
  agents: number;
  providers: number;
  pipelines: number;
  tokens: number;
  cost: number;
  latency: number;
  errors: number;
  // Recent activity ring for the AI Brain.
  pulses: { topic: string; at: number }[];
}

interface StoreState {
  connected: boolean;
  events: EventEnvelope[];
  agents: Record<string, AgentNode>;
  tasks: Record<string, TaskNode>;
  providers: Record<string, ProviderHealthRecord>;
  memory: MemoryItem[];
  audit: AuditEntry[];
  notifications: Notification[];
  telemetry: Telemetry;

  connect: () => void;
  disconnect: () => void;
  ingest: (e: EventEnvelope) => void;
  setMemory: (items: MemoryItem[]) => void;
  setAudit: (entries: AuditEntry[]) => void;
  clearNotifications: () => void;
}

const MAX_EVENTS = 400;
const MAX_NOTIFS = 60;

function pushUnique<T extends { id: string }>(map: Record<string, T>, items: T[]): Record<string, T> {
  const next = { ...map };
  for (const it of items) next[it.id] = it;
  return next;
}

function levelForTopic(topic: string): Notification["level"] {
  if (topic.includes("failed") || topic.includes("denied") || topic === "provider.down")
    return "danger";
  if (topic.includes("degraded") || topic.includes("recovered")) return "warn";
  if (topic.includes("completed") || topic.includes("registered") || topic.includes("granted"))
    return "ok";
  return "info";
}

function titleFor(topic: string, payload: Record<string, unknown>): string {
  const map: Record<string, string> = {
    "task.created": "Task created",
    "task.planned": "Task planned",
    "task.dispatched": "Task dispatched",
    "agent.started": "Agent started",
    "agent.completed": "Agent completed",
    "agent.failed": "Agent failed",
    "agent.recovered": "Agent recovered",
    "health.degraded": "Health degraded",
    "recovery.triggered": "Recovery triggered",
    "provider.health": "Provider health",
    "provider.registered": "Provider registered",
    "provider.failed": "Provider failed",
    "provider.failover": "Provider failover",
    "cost.recorded": "Cost recorded",
    "memory.written": "Memory written",
    "memory.evicted": "Memory evicted",
    "agent.composed": "Agent composed",
    "approval.requested": "Approval requested",
    "approval.decided": "Approval decided",
    "tool.denied": "Tool denied",
  };
  return map[topic] ?? topic;
}

export const useStore = create<StoreState>((set, get) => ({
  connected: false,
  events: [],
  agents: {},
  tasks: {},
  providers: {},
  memory: [],
  audit: [],
  notifications: [],
  telemetry: {
    tasks: 0,
    agents: 0,
    providers: 0,
    pipelines: 0,
    tokens: 0,
    cost: 0,
    latency: 0,
    errors: 0,
    pulses: [],
  },

  connect: () => {
    if (get().connected) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const base = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
    // Derive ws origin from the configured API base.
    const url = `${proto}://${new URL(base).host}/ws/dashboard`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
    } catch {
      return;
    }
    ws.onopen = () => set({ connected: true });
    ws.onclose = () => set({ connected: false });
    ws.onerror = () => set({ connected: false });
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as EventEnvelope;
        get().ingest(data);
      } catch {
        /* ignore malformed frames */
      }
    };
    (get() as unknown as { _ws?: WebSocket })._ws = ws;
  },

  disconnect: () => {
    const ws = (get() as unknown as { _ws?: WebSocket })._ws;
    ws?.close();
    set({ connected: false });
  },

  ingest: (e) => {
    set((s) => {
      const events = [e, ...s.events].slice(0, MAX_EVENTS);
      const notifications: Notification[] = [
        {
          id: e.id,
          topic: e.topic,
          title: titleFor(e.topic, e.payload),
          detail: JSON.stringify(e.payload).slice(0, 160),
          level: levelForTopic(e.topic),
          at: Date.now(),
        },
        ...s.notifications,
      ].slice(0, MAX_NOTIFS);

      const agents = { ...s.agents };
      const tasks = { ...s.tasks };
      const providers = { ...s.providers };
      const telemetry = { ...s.telemetry };
      telemetry.pulses = [{ topic: e.topic, at: Date.now() }, ...telemetry.pulses].slice(0, 80);

      const p = e.payload as Record<string, any>;
      switch (e.topic) {
        case "agent.started":
        case "agent.completed":
        case "agent.failed":
        case "agent.recovered": {
          const id = String(p.id ?? p.agent_id ?? "agent");
          const prev = agents[id] ?? {
            id,
            role: String(p.role ?? "agent"),
            capabilities: [],
            status: "idle",
            health: "unknown",
          };
          const statusMap: Record<string, AgentNode["status"]> = {
            "agent.started": "running",
            "agent.completed": "completed",
            "agent.failed": "failed",
            "agent.recovered": "recovered",
          };
          agents[id] = {
            ...prev,
            role: String(p.role ?? prev.role),
            provider: p.provider ?? prev.provider,
            current_task: p.task_id ?? prev.current_task,
            capabilities: (p.capabilities as string[]) ?? prev.capabilities,
            supervisor: p.supervisor ?? prev.supervisor,
            status: statusMap[e.topic] ?? prev.status,
            health: e.topic === "agent.failed" ? "down" : e.topic === "agent.recovered" ? "degraded" : "healthy",
          };
          telemetry.agents = Object.keys(agents).length;
          break;
        }
        case "task.created":
        case "task.planned":
        case "task.dispatched":
        case "task.assigned": {
          const id = String(p.id ?? "task");
          tasks[id] = {
            id,
            title: String(p.title ?? ""),
            role: String(p.role ?? ""),
            status: e.topic.replace("task.", "") as TaskNode["status"],
          };
          telemetry.tasks = Object.keys(tasks).length;
          break;
        }
        case "provider.health":
        case "provider.registered":
        case "provider.failed":
        case "provider.failover": {
          const name = String(p.name ?? p.provider ?? "provider");
          providers[name] = {
            provider: name,
            status: (p.status ?? providers[name]?.status ?? "unknown") as ProviderHealthRecord["status"],
            latency_ms: Number(p.latency_ms ?? providers[name]?.latency_ms ?? 0),
            error: p.error ?? providers[name]?.error,
          };
          telemetry.providers = Object.keys(providers).length;
          if (e.topic === "provider.failed") telemetry.errors += 1;
          break;
        }
        case "cost.recorded": {
          telemetry.cost += Number(p.amount ?? 0);
          break;
        }
        case "agent.composed": {
          telemetry.pipelines += 1;
          break;
        }
        case "tool.denied":
        case "agent.failed":
        case "provider.failed": {
          telemetry.errors += 1;
          break;
        }
      }

      return { events, notifications, agents, tasks, providers, telemetry };
    });
  },

  setMemory: (items) => set({ memory: items }),
  setAudit: (entries) => set({ audit: entries }),
  clearNotifications: () => set({ notifications: [] }),
}));

// Convenience selector for the System Monitor.
export function selectMetrics(s: StoreState): SystemMetrics {
  return {
    tasks: s.telemetry.tasks,
    agents: s.telemetry.agents,
    providers: s.telemetry.providers,
    pipelines: s.telemetry.pipelines,
    tokens: s.telemetry.tokens,
    cost: s.telemetry.cost,
    latency: s.telemetry.latency,
    errors: s.telemetry.errors,
  };
}
