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

// WebSocket reconnection config
const WS_RECONNECT_BASE_DELAY = 1000; // 1s
const WS_RECONNECT_MAX_DELAY = 30000; // 30s
const WS_MAX_RETRIES = 10;

function pushUnique<T extends { id: string }>(map: Record<string, T>, items: T[]): Record<string, T> {
  const next = { ...map };
  for (const it of items) next[it.id] = it;
  return next;
}

function levelForTopic(topic: string): Notification["level"] {
  if (topic.includes("failed") || topic.includes("denied") || topic === "provider.down") return "danger";
  if (topic.includes("degraded") || topic.includes("recovered")) return "warn";
  if (topic.includes("completed") || topic.includes("registered") || topic.includes("granted")) return "ok";
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

    let ws: WebSocket | null = null;
    let retryCount = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let isIntentionalDisconnect = false;

    const connectImpl = () => {
      if (isIntentionalDisconnect) return;

      const proto = location.protocol === "https:" ? "wss" : "ws";
      const base = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
      const url = `${proto}://${new URL(base).host}/ws/dashboard`;

      try {
        ws = new WebSocket(url);
      } catch {
        scheduleReconnect();
        return;
      }

      ws.onopen = () => {
        retryCount = 0;
        set({ connected: true });
      };

      ws.onclose = () => {
        set({ connected: false });
        if (!isIntentionalDisconnect) {
          scheduleReconnect();
        }
      };

      ws.onerror = () => {
        set({ connected: false });
        // onclose will handle reconnection
      };

      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as EventEnvelope;
          get().ingest(data);
        } catch {
          /* ignore malformed frames */
        }
      };

      (get() as unknown as { _ws?: WebSocket; _reconnectTimer?: ReturnType<typeof setTimeout>; _isIntentionalDisconnect?: boolean })._ws = ws;
    };

    const scheduleReconnect = () => {
      if (isIntentionalDisconnect) return;
      if (retryCount >= WS_MAX_RETRIES) {
        console.error("[WebSocket] Max retries reached, giving up");
        return;
      }

      const delay = Math.min(WS_RECONNECT_BASE_DELAY * Math.pow(2, retryCount), WS_RECONNECT_MAX_DELAY);
      // Add jitter (±10%)
      const jitter = delay * 0.1 * (Math.random() * 2 - 1);
      const finalDelay = Math.floor(delay + jitter);

      console.log(`[WebSocket] Reconnecting in ${finalDelay}ms (attempt ${retryCount + 1}/${WS_MAX_RETRIES})`);
      retryCount++;

      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connectImpl, finalDelay);

      (get() as unknown as { _reconnectTimer?: ReturnType<typeof setTimeout> })._reconnectTimer = reconnectTimer;
    };

    connectImpl();

    // Store cleanup functions for disconnect
    (get() as unknown as { _cleanup?: () => void })._cleanup = () => {
      isIntentionalDisconnect = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  },

  disconnect: () => {
    const state = get() as unknown as { _ws?: WebSocket; _reconnectTimer?: ReturnType<typeof setTimeout>; _cleanup?: () => void };
    state._cleanup?.();
    state._ws?.close();
    if (state._reconnectTimer) clearTimeout(state._reconnectTimer);
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

      let agents = s.agents;
      let tasks = s.tasks;
      let providers = s.providers;
      let telemetry = s.telemetry;

      const p = e.payload as Record<string, any>;
      switch (e.topic) {
        case "agent.started":
        case "agent.completed":
        case "agent.failed":
        case "agent.recovered": {
          const id = String(p.id ?? p.agent_id ?? "agent");
          agents = { ...s.agents };
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
          telemetry = { ...s.telemetry };
          telemetry.agents = Object.keys(agents).length;
          if (e.topic === "agent.failed") telemetry.errors += 1;
          break;
        }
        case "task.created":
        case "task.planned":
        case "task.dispatched":
        case "task.assigned": {
          const id = String(p.id ?? "task");
          tasks = { ...s.tasks };
          tasks[id] = {
            id,
            title: String(p.title ?? ""),
            role: String(p.role ?? ""),
            status: e.topic.replace("task.", "") as TaskNode["status"],
          };
          telemetry = { ...s.telemetry };
          telemetry.tasks = Object.keys(tasks).length;
          break;
        }
        case "provider.health":
        case "provider.registered":
        case "provider.failover": {
          const name = String(p.name ?? p.provider ?? "provider");
          providers = { ...s.providers };
          providers[name] = {
            provider: name,
            status: (p.status ?? providers[name]?.status ?? "unknown") as ProviderHealthRecord["status"],
            latency_ms: Number(p.latency_ms ?? providers[name]?.latency_ms ?? 0),
            error: p.error ?? providers[name]?.error,
          };
          telemetry = { ...s.telemetry };
          telemetry.providers = Object.keys(providers).length;
          break;
        }
        case "provider.failed": {
          const name = String(p.name ?? p.provider ?? "provider");
          providers = { ...s.providers };
          providers[name] = {
            provider: name,
            status: "down",
            latency_ms: 0,
            error: p.error,
          };
          telemetry = { ...s.telemetry };
          telemetry.providers = Object.keys(providers).length;
          telemetry.errors += 1;
          break;
        }
        case "cost.recorded": {
          telemetry = { ...s.telemetry };
          telemetry.cost += Number(p.amount ?? 0);
          break;
        }
        case "agent.composed": {
          telemetry = { ...s.telemetry };
          telemetry.pipelines += 1;
          break;
        }
        case "tool.denied": {
          telemetry = { ...s.telemetry };
          telemetry.errors += 1;
          break;
        }
      }

      // Always clone telemetry to add the pulse
      if (telemetry === s.telemetry) {
        telemetry = { ...s.telemetry };
      }
      telemetry.pulses = [{ topic: e.topic, at: Date.now() }, ...telemetry.pulses].slice(0, 80);

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
