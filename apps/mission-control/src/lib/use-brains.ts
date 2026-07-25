"use client";

// Brain Registry store. Consumes the backend /api/brains REST endpoints and
// an optional SSE stream (/api/brains/events) for live updates.
// This store is independent of the main useStore — brains are discovered
// runtime engines, not the same as agent nodes.

import { create } from "zustand";
import { api } from "./api";

// ── Domain types ────────────────────────────────────────────────────────────

export const BRAIN_STATUSES = [
  "discovered", "registered", "connected", "disconnected",
  "busy", "idle", "executing",
  "healthy", "unhealthy", "degraded", "failed",
  "removed", "paused", "resumed", "restarting", "shutdown", "recovering",
] as const;
export type BrainStatus = (typeof BRAIN_STATUSES)[number];

export const BRAIN_TYPES = ["local_cli", "cloud_api", "orchestrator", "mcp_server", "custom"] as const;
export type BrainType = (typeof BRAIN_TYPES)[number];

export const BRAIN_VENDORS = [
  "openai", "anthropic", "google", "mistral", "groq", "azure", "aws", "vertex",
  "openrouter", "cohere", "deepseek", "qwen", "moonshot", "together", "fireworks",
  "replicate", "ollama", "lm_studio", "vllm", "hermes", "claude_code", "gemini_cli",
  "codex", "opencode", "aider", "continue", "github_copilot", "cursor", "custom",
] as const;
export type BrainVendor = (typeof BRAIN_VENDORS)[number];

export const BRAIN_RUNTIMES = [
  "python", "node", "go", "rust", "container", "native", "cloud", "unknown", "bun", "deno",
] as const;
export type BrainRuntime = (typeof BRAIN_RUNTIMES)[number];

export const RELATIONSHIP_TYPES = [
  "parent", "child", "peer",
  "executor", "planner", "reviewer", "observer", "fallback",
  "shadow", "mirror", "consensus", "delegation", "communication",
  "routing", "tool_usage", "shared_context", "execution_chain", "mcp_connection",
] as const;
export type RelationshipType = (typeof RELATIONSHIP_TYPES)[number];

export interface BrainRecord {
  id: string;
  display_name: string;
  brain_type: BrainType;
  vendor: BrainVendor;
  runtime: BrainRuntime;
  version: string;
  status: BrainStatus;
  health: "healthy" | "degraded" | "unhealthy" | "unknown";

  capabilities: string[];
  supported_models: string[];
  supported_tools: string[];
  memory_usage: number;        // MB
  cpu_usage: number;           // percentage 0-100
  latency: number;             // ms
  throughput: number;          // req/s
  workspace: string;
  current_tasks: number;
  queue_depth: number;
  active_models: number;
  available_context: number;   // tokens
  connection_state: "connected" | "disconnected" | "reconnecting";
  uptime: number;              // seconds
  heartbeat: string;           // ISO timestamp
  tags: string[];
  priority: number;
  metadata: Record<string, unknown>;
  discovered_at: string;
  last_seen: string;
  session_count: number;
  error_count: number;
  last_error: string | null;
}

export interface BrainRelationship {
  id: string;
  source_id: string;
  target_id: string;
  relationship_type: RelationshipType;
  weight: number;               // 0.0 – 1.0
  active: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
  last_activity: string;
}

// ── SSE event types ─────────────────────────────────────────────────────────

interface BrainSSEEvent {
  type: "brain.registered" | "brain.updated" | "brain.removed" | "brain.heartbeat" | "brain.relationship_added" | "brain.relationship_removed";
  brain_id?: string;
  brain?: BrainRecord;
  relationship?: BrainRelationship;
  relationship_id?: string;
}

// ── Store state ─────────────────────────────────────────────────────────────

type ViewMode = "card" | "table" | "graph";
type SortField = "display_name" | "brain_type" | "vendor" | "status" | "health" | "cpu_usage" | "memory_usage" | "latency" | "uptime" | "discovered_at";
type SortDir = "asc" | "desc";

export interface BrainsFilter {
  search: string;
  status: BrainStatus[];
  health: ("healthy" | "degraded" | "unhealthy" | "unknown")[];
  type: BrainType[];
  vendor: BrainVendor[];
  runtime: BrainRuntime[];
  sort: SortField;
  sortDir: SortDir;
  groupBy: "none" | "type" | "vendor" | "status" | "health" | "runtime";
}

interface BrainsStoreState {
  brains: Record<string, BrainRecord>;
  relationships: BrainRelationship[];
  connected: boolean;
  loading: boolean;
  error: string | null;
  viewMode: ViewMode;
  selectedBrainId: string | null;
  filter: BrainsFilter;
  expandedBrains: Record<string, boolean>;

  // Actions
  setViewMode: (mode: ViewMode) => void;
  setSelectedBrain: (id: string | null) => void;
  setFilter: (f: Partial<BrainsFilter>) => void;
  resetFilter: () => void;
  toggleExpand: (id: string) => void;
  toggleStatusFilter: (status: BrainStatus) => void;
  toggleHealthFilter: (health: "healthy" | "degraded" | "unhealthy" | "unknown") => void;

  // Data actions
  fetchBrains: () => Promise<void>;
  fetchRelationships: () => Promise<void>;
  refreshBrain: (id: string) => Promise<BrainRecord | null>;
  rescan: () => Promise<{ discovered: number } | null>;
  removeBrain: (id: string) => Promise<boolean>;
  connectSSE: () => void;
  disconnectSSE: () => void;
  ingestSSE: (event: BrainSSEEvent) => void;

  // Selectors (computed)
  brainList: () => BrainRecord[];
  brainById: (id: string) => BrainRecord | undefined;
  connectionsForBrain: (id: string) => BrainRelationship[];
}

const DEFAULT_FILTER: BrainsFilter = {
  search: "",
  status: [],
  health: [],
  type: [],
  vendor: [],
  runtime: [],
  sort: "display_name",
  sortDir: "asc",
  groupBy: "none",
};

const SSE_RECONNECT_DELAY = 5000;

// ── API helpers ─────────────────────────────────────────────────────────────

function brainsApiBase(): string {
  if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).__TAURI__) {
    return "http://127.0.0.1:8000/api/brains";
  }
  const base = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
  return `${base}/api/brains`;
}

// ── Store ───────────────────────────────────────────────────────────────────

export const useBrainsStore = create<BrainsStoreState>((set, get) => ({
  brains: {},
  relationships: [],
  connected: false,
  loading: false,
  error: null,
  viewMode: "card",
  selectedBrainId: null,
  filter: { ...DEFAULT_FILTER },
  expandedBrains: {},

  // ── View actions ──

  setViewMode: (mode) => set({ viewMode: mode }),
  setSelectedBrain: (id) => set({ selectedBrainId: id }),
  setFilter: (partial) =>
    set((s) => ({ filter: { ...s.filter, ...partial } })),
  resetFilter: () => set({ filter: { ...DEFAULT_FILTER } }),
  toggleExpand: (id) =>
    set((s) => ({
      expandedBrains: {
        ...s.expandedBrains,
        [id]: !s.expandedBrains[id],
      },
    })),
  toggleStatusFilter: (status) =>
    set((s) => {
      const current = s.filter.status;
      const next = current.includes(status)
        ? current.filter((x) => x !== status)
        : [...current, status];
      return { filter: { ...s.filter, status: next } };
    }),
  toggleHealthFilter: (health) =>
    set((s) => {
      const current = s.filter.health;
      const next = current.includes(health)
        ? current.filter((x) => x !== health)
        : [...current, health];
      return { filter: { ...s.filter, health: next } };
    }),

  // ── Data actions ──

  fetchBrains: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${brainsApiBase()}`, {
        headers: { accept: "application/json" },
      });
      if (!res.ok) throw new Error(`fetchBrains -> ${res.status}`);
      const list = (await res.json()) as BrainRecord[];
      const brains: Record<string, BrainRecord> = {};
      for (const b of list) brains[b.id] = b;
      set({ brains, loading: false });
    } catch (e) {
      set({ error: String(e), loading: false });
    }
  },

  fetchRelationships: async () => {
    try {
      const res = await fetch(`${brainsApiBase()}/relationships`, {
        headers: { accept: "application/json" },
      });
      if (!res.ok) throw new Error(`fetchRelationships -> ${res.status}`);
      const list = (await res.json()) as BrainRelationship[];
      set({ relationships: list });
    } catch {
      // Non-critical; relationships may not be available yet
    }
  },

  refreshBrain: async (id) => {
    try {
      const res = await fetch(`${brainsApiBase()}/${encodeURIComponent(id)}`, {
        headers: { accept: "application/json" },
      });
      if (!res.ok) throw new Error(`refreshBrain -> ${res.status}`);
      const brain = (await res.json()) as BrainRecord;
      set((s) => ({
        brains: { ...s.brains, [brain.id]: brain },
        error: null,
      }));
      return brain;
    } catch (e) {
      set({ error: String(e) });
      return null;
    }
  },

  rescan: async () => {
    set({ loading: true, error: null });
    try {
      const res = await fetch(`${brainsApiBase()}/rescan`, {
        method: "POST",
        headers: { accept: "application/json" },
      });
      if (!res.ok) throw new Error(`rescan -> ${res.status}`);
      const result = await res.json() as { discovered: number };
      // Re-fetch full list after rescan
      await get().fetchBrains();
      return result;
    } catch (e) {
      set({ error: String(e), loading: false });
      return null;
    }
  },

  removeBrain: async (id) => {
    try {
      const res = await fetch(`${brainsApiBase()}/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error(`removeBrain -> ${res.status}`);
      set((s) => {
        const brains = { ...s.brains };
        delete brains[id];
        return { brains };
      });
      return true;
    } catch (e) {
      set({ error: String(e) });
      return false;
    }
  },

  // ── SSE connection ──

  connectSSE: () => {
    if (get().connected) return;

    const url = `${brainsApiBase()}/events`;
    let es: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      try {
        es = new EventSource(url);
      } catch {
        scheduleReconnect();
        return;
      }

      es.onopen = () => {
        set({ connected: true });
      };

      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as BrainSSEEvent;
          get().ingestSSE(data);
        } catch {
          // ignore malformed frames
        }
      };

      es.onerror = () => {
        set({ connected: false });
        es?.close();
        scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, SSE_RECONNECT_DELAY);
    };

    connect();

    // Store references for cleanup
    (get() as unknown as { _sse?: EventSource | null; _sseReconnectTimer?: ReturnType<typeof setTimeout> | null })._sse = es;
    (get() as unknown as { _sseReconnectTimer?: ReturnType<typeof setTimeout> | null })._sseReconnectTimer = reconnectTimer;
  },

  disconnectSSE: () => {
    const state = get() as unknown as {
      _sse?: EventSource;
      _sseReconnectTimer?: ReturnType<typeof setTimeout>;
    };
    state._sse?.close();
    if (state._sseReconnectTimer) clearTimeout(state._sseReconnectTimer);
    set({ connected: false });
  },

  ingestSSE: (event) => {
    set((s) => {
      switch (event.type) {
        case "brain.registered":
        case "brain.updated": {
          if (!event.brain) return s;
          return {
            brains: { ...s.brains, [event.brain.id]: event.brain },
            error: null,
          };
        }
        case "brain.removed": {
          if (!event.brain_id) return s;
          const brains = { ...s.brains };
          delete brains[event.brain_id];
          return { brains };
        }
        case "brain.heartbeat": {
          if (!event.brain) return s;
          return {
            brains: { ...s.brains, [event.brain.id]: event.brain },
          };
        }
        case "brain.relationship_added": {
          if (!event.relationship) return s;
          return {
            relationships: [...s.relationships, event.relationship],
          };
        }
        case "brain.relationship_removed": {
          if (!event.relationship_id) return s;
          return {
            relationships: s.relationships.filter(
              (r) => r.id !== event.relationship_id
            ),
          };
        }
        default:
          return s;
      }
    });
  },

  // ── Selectors ──

  brainList: () => Object.values(get().brains),

  brainById: (id) => get().brains[id],

  connectionsForBrain: (id) =>
    get().relationships.filter(
      (r) => r.source_id === id || r.target_id === id
    ),
}));

// ── Derived selectors (used outside hooks / in components) ──────────────────

export function selectBrainList(
  brains: Record<string, BrainRecord>
): BrainRecord[] {
  return Object.values(brains);
}

export function selectFilteredBrains(
  brains: Record<string, BrainRecord>,
  filter: BrainsFilter
): BrainRecord[] {
  let list = Object.values(brains);

  // Search
  if (filter.search) {
    const q = filter.search.toLowerCase();
    list = list.filter(
      (b) =>
        b.display_name.toLowerCase().includes(q) ||
        b.id.toLowerCase().includes(q) ||
        b.vendor.toLowerCase().includes(q) ||
        b.brain_type.toLowerCase().includes(q) ||
        b.tags.some((t) => t.toLowerCase().includes(q))
    );
  }

  // Status filter
  if (filter.status.length > 0) {
    list = list.filter((b) => filter.status.includes(b.status));
  }

  // Health filter
  if (filter.health.length > 0) {
    list = list.filter((b) => filter.health.includes(b.health));
  }

  // Type filter
  if (filter.type.length > 0) {
    list = list.filter((b) => filter.type.includes(b.brain_type));
  }

  // Vendor filter
  if (filter.vendor.length > 0) {
    list = list.filter((b) => filter.vendor.includes(b.vendor));
  }

  // Runtime filter
  if (filter.runtime.length > 0) {
    list = list.filter((b) => filter.runtime.includes(b.runtime));
  }

  // Sort
  const dir = filter.sortDir === "desc" ? -1 : 1;
  list.sort((a, b) => {
    let cmp = 0;
    switch (filter.sort) {
      case "display_name":
        cmp = a.display_name.localeCompare(b.display_name);
        break;
      case "brain_type":
        cmp = a.brain_type.localeCompare(b.brain_type);
        break;
      case "vendor":
        cmp = a.vendor.localeCompare(b.vendor);
        break;
      case "status":
        cmp = a.status.localeCompare(b.status);
        break;
      case "health":
        cmp = a.health.localeCompare(b.health);
        break;
      case "cpu_usage":
        cmp = a.cpu_usage - b.cpu_usage;
        break;
      case "memory_usage":
        cmp = a.memory_usage - b.memory_usage;
        break;
      case "latency":
        cmp = a.latency - b.latency;
        break;
      case "uptime":
        cmp = a.uptime - b.uptime;
        break;
      case "discovered_at":
        cmp = a.discovered_at.localeCompare(b.discovered_at);
        break;
    }
    return cmp * dir;
  });

  return list;
}

export function selectBrainsByGroup(
  brains: Record<string, BrainRecord>,
  filter: BrainsFilter
): Record<string, BrainRecord[]> {
  const list = selectFilteredBrains(brains, filter);
  const grouped: Record<string, BrainRecord[]> = {};

  if (filter.groupBy === "none") {
    grouped["All Brains"] = list;
    return grouped;
  }

  for (const brain of list) {
    let key = "";
    switch (filter.groupBy) {
      case "type":
        key = brain.brain_type;
        break;
      case "vendor":
        key = brain.vendor;
        break;
      case "status":
        key = brain.status;
        break;
      case "health":
        key = brain.health;
        break;
      case "runtime":
        key = brain.runtime;
        break;
    }
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(brain);
  }

  return grouped;
}

export function brainStatusToColor(status: BrainStatus): string {
  const map: Record<string, string> = {
    discovered: "#6366f1",
    registered: "#22d3ee",
    connected: "#22d3ee",
    disconnected: "#94a3b8",
    busy: "#f59e0b",
    idle: "#94a3b8",
    executing: "#10b981",
    healthy: "#10b981",
    unhealthy: "#ef4444",
    degraded: "#f97316",
    failed: "#ef4444",
    removed: "#64748b",
    paused: "#f59e0b",
    resumed: "#22d3ee",
    restarting: "#818cf8",
    shutdown: "#64748b",
    recovering: "#f97316",
  };
  return map[status] ?? "#94a3b8";
}

export function brainHealthToTone(health: string): "ok" | "warn" | "danger" | "default" {
  const map: Record<string, "ok" | "warn" | "danger" | "default"> = {
    healthy: "ok",
    degraded: "warn",
    unhealthy: "danger",
    unknown: "default",
  };
  return map[health] ?? "default";
}

// ── Vendor icon component lookup ────────────────────────────────────────────

export const VENDOR_ICON_MAP: Record<string, string> = {
  openai: "#00a67e",
  anthropic: "#d980ff",
  google: "#4285f4",
  mistral: "#ff9900",
  groq: "#f97316",
  azure: "#0078d4",
  aws: "#ff9900",
  vertex: "#4285f4",
  openrouter: "#8b5cf6",
  cohere: "#39594d",
  deepseek: "#4f6bff",
  qwen: "#6941c6",
  moonshot: "#06b6d4",
  together: "#7c3aed",
  fireworks: "#f43f5e",
  replicate: "#10b981",
  ollama: "#f97316",
  lm_studio: "#6366f1",
  vllm: "#06b6d4",
  hermes: "#00f0ff",
  claude_code: "#d980ff",
  gemini_cli: "#4285f4",
  codex: "#818cf8",
  opencode: "#38bdf8",
  aider: "#10b981",
  continue: "#6366f1",
  github_copilot: "#58a6ff",
  cursor: "#38bdf8",
  custom: "#94a3b8",
};
