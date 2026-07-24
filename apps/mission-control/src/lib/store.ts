"use client";

// Live event store. Consumes the backend /ws/dashboard stream and derives
// Mission Control state. ALL data originates from real EventBus events —
// nothing here is simulated.

import { create } from "zustand";
import { api } from "./api";
import type {
  AgentNode,
  AuditEntry,
  EventEnvelope,
  MemoryItem,
  ProviderHealthRecord,
  ProviderHealthStatus,
  SystemMetrics,
  TaskNode,
} from "./types";
import type { DesktopPerformanceMetrics } from "./desktop-types";
import type { MissionType } from "./types";

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
  performance: DesktopPerformanceMetrics | null;
  missions: Record<string, MissionType>;
  missionUpdates: number; // bump counter to trigger re-renders

  connect: () => void;
  disconnect: () => void;
  ingest: (e: EventEnvelope) => void;
  setMemory: (items: MemoryItem[]) => void;
  setAudit: (entries: AuditEntry[]) => void;
  setPerformance: (p: DesktopPerformanceMetrics) => void;
  setMissions: (items: MissionType[]) => void;
  updateMission: (m: MissionType) => void;
  clearNotifications: () => void;
}

const MAX_EVENTS = 400;
const MAX_NOTIFS = 60;

// WebSocket reconnection config
const WS_RECONNECT_BASE_DELAY = 3000; // 3s
const WS_RECONNECT_MAX_DELAY = 30000; // 30s
const WS_MAX_RETRIES = 999; // effectively unlimited for desktop runtime
const WS_HEARTBEAT_TIMEOUT = 90000; // 90s without heartbeat → reconnect


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
    "self_healing.issue": "Self-healing issue",
    "self_healing.action": "Self-healing action",
    "connection.lost": "Connection lost",
    "agent.composed": "Agent composed",
    "discovery.completed": "Discovery scan completed",
    "discovery.engine_found": "Engine discovered",
    "discovery.engine_lost": "Engine lost",
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
  performance: null,
  missions: {},
  missionUpdates: 0,
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

    // Start performance polling — every view benefits from live data.
    const pollPerf = () => {
      api.performance()
        .then((p) => { set({ performance: p }); })
        .catch(() => { /* backend may be offline */ });
    };
    pollPerf();
    const perfTimer = setInterval(pollPerf, 5000);

    let ws: WebSocket | null = null;
    let retryCount = 0;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let isIntentionalDisconnect = false;
    let lastHeartbeat = Date.now();
    let hbWatchdogTimer: ReturnType<typeof setInterval> | null = null;

    const connectImpl = () => {
      if (isIntentionalDisconnect) return;

      // Determine the WebSocket URL.
      // In a Tauri custom-protocol shell, location.protocol is "tauri:" — NOT
      // "http:" — so we cannot derive the ws:// scheme from the page origin.
      // We always connect directly to the embedded backend on 127.0.0.1:8000.
      // In a browser dev environment (npm run dev) location.protocol is "http:"
      // and the env-var base still resolves to localhost:8000, so this is safe.
      let url: string;
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const base = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
      if (location.protocol === "tauri:") {
        // Desktop runtime: always use the embedded backend address.
        url = "ws://127.0.0.1:8000/ws/dashboard";
      } else {
        url = `${proto}://${new URL(base).host}/ws/dashboard`;
      }

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
          // Track heartbeat timestamps for stale-connection detection.
          if (data.topic === "heartbeat") {
            lastHeartbeat = Date.now();
          }
          get().ingest(data);
        } catch {
          /* ignore malformed frames */
        }
      };

      // Start heartbeat watchdog — if no heartbeat within 90s, reconnect.
      const startWatchdog = () => {
        if (hbWatchdogTimer) clearInterval(hbWatchdogTimer);
        hbWatchdogTimer = setInterval(() => {
          if (Date.now() - lastHeartbeat > WS_HEARTBEAT_TIMEOUT) {
            console.warn("[WebSocket] No heartbeat for 90s — reconnecting");
            ws?.close();
            if (hbWatchdogTimer) clearInterval(hbWatchdogTimer);
            hbWatchdogTimer = null;
          }
        }, 30000);
      };
      startWatchdog();

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
      if (hbWatchdogTimer) clearInterval(hbWatchdogTimer);
      clearInterval(perfTimer);
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
    // Skip heartbeat messages — they are connection keep-alive only.
    if (e.topic === "heartbeat") {
      set((s) => {
        const telemetry = { ...s.telemetry };
        telemetry.pulses = [{ topic: e.topic, at: Date.now() }, ...telemetry.pulses].slice(0, 80);
        return { telemetry };
      });
      return;
    }

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
        case "mission.created":
        case "mission.planned":
        case "mission.started":
        case "mission.paused":
        case "mission.completed":
        case "mission.failed":
        case "mission.cancelled": {
          const m = p as unknown as MissionType;
          if (m?.id) {
            // Don't mutate — rely on the caller to do a full re-fetch
            // but update the status in-place so the UI stays live
            const existing = s.missions[m.id];
            if (existing) {
              return {
                events, notifications, agents, tasks, providers, telemetry,
                missions: {
                  ...s.missions,
                  [m.id]: { ...existing, status: m.status ?? existing.status, updated_at: new Date().toISOString() },
                },
                missionUpdates: Date.now(),
              };
            }
          }
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
  setPerformance: (p) => set({ performance: p }),
  setMissions: (items) => {
    const missions: Record<string, MissionType> = {};
    for (const m of items) missions[m.id] = m;
    set({ missions, missionUpdates: Date.now() });
  },
  updateMission: (m) =>
    set((s) => ({ missions: { ...s.missions, [m.id]: m }, missionUpdates: Date.now() })),
  clearNotifications: () => set({ notifications: [] }),
  hydrate: async () => {
    try {
      const [agents, tasks, providers, missions] = await Promise.all([
        api.get<unknown[]>("/api/agents"),
        api.get<unknown[]>("/api/tasks"),
        api.providers(),
        api.missions(),
      ]);
      set({
        agents: (agents as Array<{ id: string }>).reduce((acc, agent) => {
          acc[agent.id] = agent as unknown as AgentNode;
          return acc;
        }, {} as Record<string, AgentNode>),
        tasks: (tasks as Array<{ id: string }>).reduce((acc, task) => {
          acc[task.id] = task as unknown as TaskNode;
          return acc;
        }, {} as Record<string, TaskNode>),
        providers: (providers as Array<{ name: string; status?: string; latency?: number; lastSeen?: string }>).reduce((acc, provider) => {
          acc[provider.name] = {
            provider: provider.name,
            status: (provider.status as ProviderHealthStatus) || "unknown",
            latency_ms: provider.latency || 0,
            last_checked: provider.lastSeen || undefined,
          };
          return acc;
        }, {} as Record<string, ProviderHealthRecord>),
        missions: (missions as Array<{ id: string }>).reduce((acc, mission) => {
          acc[mission.id] = mission as unknown as MissionType;
          return acc;
        }, {} as Record<string, MissionType>),
      });
    } catch (e) {
      console.error("Failed to hydrate store:", e);
    }
  },
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
