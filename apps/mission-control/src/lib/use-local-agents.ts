"use client";

// Zustand store for Phase 6.1 — Local Agent Discovery.
// Manages the list of discovered local AI agents, their health/status,
// SSE live updates, and agent control actions.

import { create } from "zustand";
import { api } from "./api";

// ── Types ──

export type AgentStatus =
  | "running"
  | "stopped"
  | "crashed"
  | "busy"
  | "idle"
  | "updating"
  | "restarting"
  | "unknown";

export interface LocalAgent {
  id: string;
  name: string;
  tool_type: string;
  version: string;
  status: AgentStatus;
  executable_path: string;
  working_directory: string;
  pid: number | null;
  capabilities: string[];
  supported_models: string[];
  supported_providers: string[];
  health_score: number;
  last_seen: string; // ISO
  discovered_at: string; // ISO
  latency_ms: number;
  memory_mb: number;
  cpu_percent: number;
  threads: number;
  uptime_seconds: number;
  restart_count: number;
  configuration: Record<string, unknown>;
  tags: string[];
  error: string;
}

// SSE event payloads
interface AgentDiscoveredEvent {
  agent: LocalAgent;
}
interface AgentUpdatedEvent {
  agent: LocalAgent;
}
interface AgentHealthChangedEvent {
  id: string;
  health_score: number;
  status: AgentStatus;
  latency_ms?: number;
  memory_mb?: number;
  cpu_percent?: number;
}
interface AgentRemovedEvent {
  id: string;
}

type SSEDiscoveryEvent =
  | { type: "agent-discovered"; data: AgentDiscoveredEvent }
  | { type: "agent-updated"; data: AgentUpdatedEvent }
  | { type: "agent-health-changed"; data: AgentHealthChangedEvent }
  | { type: "agent-removed"; data: AgentRemovedEvent }
  | { type: "discovery-completed"; data: Record<string, never> };

// ── Store State ──

interface LocalAgentsState {
  agents: LocalAgent[];
  loading: boolean;
  error: string | null;
  sseConnected: boolean;

  // Actions
  fetchAgents: () => Promise<void>;
  startSSE: () => void;
  stopSSE: () => void;
  startAgent: (id: string) => Promise<void>;
  stopAgent: (id: string) => Promise<void>;
  restartAgent: (id: string) => Promise<void>;
  forgetAgent: (id: string) => Promise<void>;
  refreshAgent: (id: string) => Promise<void>;
  rescan: () => Promise<void>;

  // Internal SSE state (not persisted to the store's surface)
  _sseRef: EventSource | null;
  _init: () => void;
}

const BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

// Helper to build the API base URL following the same pattern as lib/api.ts
function resolveSSEBase(): string {
  if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).__TAURI__) {
    return "http://127.0.0.1:8000";
  }
  return BASE;
}

export const useLocalAgentsStore = create<LocalAgentsState>((set, get) => ({
  agents: [],
  loading: false,
  error: null,
  sseConnected: false,
  _sseRef: null,

  // ── Initialise — call once from the view component on mount ──
  _init: () => {
    const { agents, loading } = get();
    // Only auto-fetch if we haven't loaded any agents yet
    if (agents.length === 0 && !loading) {
      get().fetchAgents();
    }
    get().startSSE();
  },

  // ── Fetch all agents from REST API ──
  fetchAgents: async () => {
    set({ loading: true, error: null });
    try {
      const data = await api.get<LocalAgent[]>("/api/agents");
      set({ agents: Array.isArray(data) ? data : [], loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message, loading: false });
    }
  },

  // ── Start SSE connection for live agent updates ──
  startSSE: () => {
    const existing = get()._sseRef;
    if (existing) {
      // Already connected or connecting
      return;
    }

    const sseBase = resolveSSEBase();
    const url = `${sseBase}/api/agents/sse`;
    let eventSource: EventSource;

    try {
      eventSource = new EventSource(url);
    } catch {
      // EventSource constructor can throw (e.g. blocked by CSP in Tauri)
      set({ error: "Failed to create SSE connection" });
      return;
    }

    eventSource.onopen = () => {
      set({ sseConnected: true, error: null });
    };

    // Generic message handler for all event types
    eventSource.onmessage = (ev) => {
      try {
        const event = JSON.parse(ev.data) as SSEDiscoveryEvent;
        handleSSEEvent(event);
      } catch {
        // Ignore malformed frames
      }
    };

    // Named event handlers (browser EventSource also supports them via addEventListener)
    const eventTypes = [
      "agent-discovered",
      "agent-updated",
      "agent-health-changed",
      "agent-removed",
      "discovery-completed",
    ] as const;

    for (const eventType of eventTypes) {
      eventSource.addEventListener(eventType, (ev: MessageEvent) => {
        try {
          const data = JSON.parse(ev.data) as Record<string, unknown>;
          const event: SSEDiscoveryEvent = { type: eventType, data } as SSEDiscoveryEvent;
          handleSSEEvent(event);
        } catch {
          // Ignore malformed frames
        }
      });
    }

    eventSource.onerror = () => {
      set({ sseConnected: false });
      // EventSource will automatically attempt reconnection — we
      // just update the connection indicator.
    };

    set({ _sseRef: eventSource });

    // ── SSE event dispatcher ──
    function handleSSEEvent(event: SSEDiscoveryEvent) {
      const state = get();
      let agents = [...state.agents];

      switch (event.type) {
        case "agent-discovered": {
          const { agent } = event.data as AgentDiscoveredEvent;
          const idx = agents.findIndex((a) => a.id === agent.id);
          if (idx >= 0) {
            agents[idx] = agent;
          } else {
            agents.push(agent);
          }
          break;
        }
        case "agent-updated": {
          const { agent } = event.data as AgentUpdatedEvent;
          const idx = agents.findIndex((a) => a.id === agent.id);
          if (idx >= 0) {
            agents[idx] = { ...agents[idx], ...agent };
          }
          break;
        }
        case "agent-health-changed": {
          const { id, health_score, status, latency_ms, memory_mb, cpu_percent } =
            event.data as AgentHealthChangedEvent;
          const idx = agents.findIndex((a) => a.id === id);
          if (idx >= 0) {
            agents[idx] = {
              ...agents[idx],
              health_score,
              status,
              ...(latency_ms !== undefined ? { latency_ms } : {}),
              ...(memory_mb !== undefined ? { memory_mb } : {}),
              ...(cpu_percent !== undefined ? { cpu_percent } : {}),
            };
          }
          break;
        }
        case "agent-removed": {
          const { id } = event.data as AgentRemovedEvent;
          agents = agents.filter((a) => a.id !== id);
          break;
        }
        case "discovery-completed": {
          // Optionally refresh the full list
          // get().fetchAgents();
          break;
        }
      }

      set({ agents });
    }
  },

  // ── Stop SSE connection ──
  stopSSE: () => {
    const es = get()._sseRef;
    if (es) {
      es.close();
      set({ _sseRef: null, sseConnected: false });
    }
  },

  // ── Agent control actions ──

  startAgent: async (id: string) => {
    try {
      await api.post<{ status: string }>(`/api/agents/${encodeURIComponent(id)}/start`);
      // Optimistically update local state
      const agents = get().agents.map((a) =>
        a.id === id ? { ...a, status: "running" as AgentStatus } : a
      );
      set({ agents });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  stopAgent: async (id: string) => {
    try {
      await api.post<{ status: string }>(`/api/agents/${encodeURIComponent(id)}/stop`);
      const agents = get().agents.map((a) =>
        a.id === id ? { ...a, status: "stopped" as AgentStatus } : a
      );
      set({ agents });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  restartAgent: async (id: string) => {
    try {
      // Optimistically mark as restarting
      const agents = get().agents.map((a) =>
        a.id === id ? { ...a, status: "restarting" as AgentStatus } : a
      );
      set({ agents });
      await api.post<{ status: string }>(`/api/agents/${encodeURIComponent(id)}/restart`);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  forgetAgent: async (id: string) => {
    try {
      // Optimistically remove from local state
      const agents = get().agents.filter((a) => a.id !== id);
      set({ agents });
      // If there's a delete/forget endpoint:
      // await api.del(`/api/agents/${encodeURIComponent(id)}`);
    } catch (err) {
      // Revert on error by re-fetching
      get().fetchAgents();
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  refreshAgent: async (id: string) => {
    try {
      const agent = await api.get<LocalAgent>(`/api/agents/${encodeURIComponent(id)}`);
      const agents = get().agents.map((a) =>
        a.id === id ? { ...a, ...agent } : a
      );
      set({ agents });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message });
    }
  },

  rescan: async () => {
    set({ loading: true, error: null });
    try {
      await api.post<{ status: string }>("/api/agents/rescan");
      // After triggering the scan, fetch the updated list
      await get().fetchAgents();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      set({ error: message, loading: false });
    }
  },
}));

// ── Selectors ──

/** Agents grouped by status category */
export function selectAgentsByStatus(state: LocalAgentsState) {
  return {
    running: state.agents.filter((a) => a.status === "running" || a.status === "busy"),
    idle: state.agents.filter((a) => a.status === "idle" || a.status === "updating" || a.status === "restarting"),
    stopped: state.agents.filter((a) => a.status === "stopped" || a.status === "crashed"),
    unknown: state.agents.filter((a) => a.status === "unknown"),
  };
}

/** Total health score average across all agents */
export function selectAverageHealth(state: LocalAgentsState): number {
  if (state.agents.length === 0) return 0;
  const total = state.agents.reduce((sum, a) => sum + a.health_score, 0);
  return Math.round(total / state.agents.length);
}

/** Number of agents online (running or busy) */
export function selectOnlineCount(state: LocalAgentsState): number {
  return state.agents.filter((a) => a.status === "running" || a.status === "busy").length;
}
