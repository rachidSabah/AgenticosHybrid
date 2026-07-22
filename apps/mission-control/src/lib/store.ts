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
  NeuralConnection,
  ProviderHealthRecord,
  RuntimeInfo,
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
  runtimes: Record<string, RuntimeInfo>;
  connections: Record<string, NeuralConnection>;

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

function mapRuntimeToActivity(status: string, eventTopic: string): RuntimeInfo['current_activity'] {
  if (status === 'lost' || status === 'disabled') return 'offline';
  if (status === 'unhealthy') return 'disconnected';
  if (eventTopic.includes('task.started')) return 'busy';
  if (eventTopic.includes('planning')) return 'planning';
  if (eventTopic.includes('reasoning')) return 'reasoning';
  if (eventTopic.includes('searching')) return 'searching';
  if (eventTopic.includes('coding')) return 'coding';
  return 'idle';
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
  runtimes: {},
  connections: {},
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
      let runtimes = s.runtimes;
      let connections = s.connections;

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
        case "runtime.discovery.engine_found": {
          runtimes = { ...s.runtimes };
          const rid = p.runtime_id;
          runtimes[rid] = {
            ...runtimes[rid],
            runtime_id: rid,
            runtime_type: p.runtime_type ?? runtimes[rid]?.runtime_type ?? 'custom',
            name: p.name ?? runtimes[rid]?.name ?? 'Unknown',
            display_name: p.display_name ?? runtimes[rid]?.display_name ?? 'Unknown',
            version: p.version ?? runtimes[rid]?.version ?? null,
            binary_path: p.binary_path ?? runtimes[rid]?.binary_path ?? null,
            status: p.status ?? runtimes[rid]?.status ?? 'discovered',
            health_status: p.health_status ?? runtimes[rid]?.health_status ?? 'unknown',
            capabilities: p.capabilities ?? runtimes[rid]?.capabilities ?? [],
            supports_streaming: p.supports_streaming ?? runtimes[rid]?.supports_streaming ?? false,
            supports_mcp: p.supports_mcp ?? runtimes[rid]?.supports_mcp ?? false,
            supports_tools: p.supports_tools ?? runtimes[rid]?.supports_tools ?? false,
            supports_vision: p.supports_vision ?? runtimes[rid]?.supports_vision ?? false,
            latency_ms: p.latency_ms ?? runtimes[rid]?.latency_ms ?? 0,
            cpu_percent: p.cpu_percent ?? runtimes[rid]?.cpu_percent ?? 0,
            memory_percent: p.memory_percent ?? runtimes[rid]?.memory_percent ?? 0,
            gpu_percent: p.gpu_percent ?? runtimes[rid]?.gpu_percent ?? 0,
            tasks_completed: p.tasks_completed ?? runtimes[rid]?.tasks_completed ?? 0,
            tasks_failed: p.tasks_failed ?? runtimes[rid]?.tasks_failed ?? 0,
            tasks_running: p.tasks_running ?? runtimes[rid]?.tasks_running ?? 0,
            current_model: p.current_model ?? runtimes[rid]?.current_model ?? null,
            current_activity: mapRuntimeToActivity(p.status ?? 'discovered', e.topic),
            discovered_at: p.discovered_at ?? runtimes[rid]?.discovered_at ?? new Date().toISOString(),
            last_seen_at: new Date().toISOString(),
            confidence: p.confidence ?? runtimes[rid]?.confidence ?? 1,
            tags: p.tags ?? runtimes[rid]?.tags ?? [],
            vendor: p.vendor ?? runtimes[rid]?.vendor ?? 'unknown',
          };
          break;
        }
        case "runtime.discovery.engine_lost": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], status: "lost", current_activity: "offline" };
          }
          break;
        }
        case "runtime.binding.completed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], status: "bound" };
          }
          break;
        }
        case "runtime.binding.failed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], status: "unbound", health_status: "unhealthy" };
          }
          break;
        }
        case "runtime.health.status_changed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], health_status: p.health_status };
          }
          break;
        }
        case "runtime.health.check_passed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], health_status: "healthy", latency_ms: p.latency_ms ?? runtimes[p.runtime_id].latency_ms };
          }
          break;
        }
        case "runtime.health.check_failed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], health_status: "unhealthy" };
          }
          break;
        }
        case "runtime.health.degraded": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], health_status: "degraded" };
          }
          break;
        }
        case "runtime.health.recovered": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], health_status: "healthy" };
          }
          break;
        }
        case "runtime.telemetry.recorded": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = {
              ...runtimes[p.runtime_id],
              cpu_percent: p.cpu_percent ?? runtimes[p.runtime_id].cpu_percent,
              memory_percent: p.memory_percent ?? runtimes[p.runtime_id].memory_percent,
              gpu_percent: p.gpu_percent ?? runtimes[p.runtime_id].gpu_percent,
              tasks_running: p.tasks_running ?? runtimes[p.runtime_id].tasks_running,
              tasks_completed: p.tasks_completed ?? runtimes[p.runtime_id].tasks_completed,
              tasks_failed: p.tasks_failed ?? runtimes[p.runtime_id].tasks_failed,
            };
          }
          break;
        }
        case "execution.task.dispatched": {
          connections = { ...s.connections };
          const connId = p.connection_id ?? `${p.source_id}-${p.target_id}`;
          connections[connId] = {
            id: connId,
            source_id: p.source_id ?? 'orchestrator',
            target_id: p.target_id ?? p.runtime_id,
            type: p.type ?? 'execution',
            active: true,
            message_count: p.message_count ?? 1,
            latency_ms: p.latency_ms ?? 0,
            bandwidth: p.bandwidth ?? 0,
            last_message_at: new Date().toISOString(),
            error_count: 0
          };
          break;
        }
        case "execution.task.started": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { ...runtimes[p.runtime_id], current_activity: "busy" };
          }
          break;
        }
        case "execution.task.completed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { 
              ...runtimes[p.runtime_id], 
              tasks_completed: runtimes[p.runtime_id].tasks_completed + 1,
              current_activity: "idle" 
            };
          }
          break;
        }
        case "execution.task.failed": {
          runtimes = { ...s.runtimes };
          if (runtimes[p.runtime_id]) {
            runtimes[p.runtime_id] = { 
              ...runtimes[p.runtime_id], 
              tasks_failed: runtimes[p.runtime_id].tasks_failed + 1,
              current_activity: "idle" 
            };
          }
          break;
        }
        case "runtime.discovery.scan_completed": {
          telemetry = { ...s.telemetry };
          telemetry.agents = Object.keys(runtimes).length;
          break;
        }
      }

      // Always clone telemetry to add the pulse
      if (telemetry === s.telemetry) {
        telemetry = { ...s.telemetry };
      }
      telemetry.pulses = [{ topic: e.topic, at: Date.now() }, ...telemetry.pulses].slice(0, 80);

      return { events, notifications, agents, tasks, providers, telemetry, runtimes, connections };
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
