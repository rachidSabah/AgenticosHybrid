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
  // Phase 15: Ecosystem snapshot — derived entirely from ecosystem.* events
  // and the /api/ecosystem/dashboard REST endpoint. No mock data.
  ecosystem: {
    stats: Record<string, unknown> | null;
    health: Record<string, unknown> | null;
    graphStats: Record<string, unknown> | null;
    networkStats: Record<string, unknown> | null;
    marketplaceStats: Record<string, unknown> | null;
    evolutionStats: Record<string, unknown> | null;
    lastEventAt: number;
  } | null;
  // Phase 16: Cluster federation snapshot — derived from cluster.* events
  // and the /api/cluster/dashboard REST endpoint.
  cluster: {
    status: Record<string, unknown> | null;
    topology: Record<string, unknown> | null;
    statistics: Record<string, unknown> | null;
    lastEventAt: number;
  } | null;
  // Phase 17: Evolution snapshot — derived from evolution.* events
  // and the /api/evolution/dashboard REST endpoint.
  evolution: {
    statistics: Record<string, unknown> | null;
    readiness: Record<string, unknown> | null;
    lastEventAt: number;
  } | null;

  connect: () => void;
  disconnect: () => void;
  ingest: (e: EventEnvelope) => void;
  setMemory: (items: MemoryItem[]) => void;
  setAudit: (entries: AuditEntry[]) => void;
  setPerformance: (p: DesktopPerformanceMetrics) => void;
  setMissions: (items: MissionType[]) => void;
  updateMission: (m: MissionType) => void;
  clearNotifications: () => void;
  /** Fetch initial snapshot from REST and seed the store (agents, providers, brains). */
  hydrate: () => Promise<void>;
  /** Phase 15: Fetch the ecosystem dashboard snapshot from REST. */
  hydrateEcosystem: () => Promise<void>;
  /** Phase 16: Fetch the cluster dashboard snapshot from REST. */
  hydrateCluster: () => Promise<void>;
  /** Phase 17: Fetch the evolution dashboard snapshot from REST. */
  hydrateEvolution: () => Promise<void>;
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
  // Initial agent/provider maps are empty — populated exclusively from live
  // backend data via hydrate() + WebSocket events. Hardcoded seed data was
  // removed so that counts on Mission Overview / Fleet / Constellation match
  // the real BrainRegistry / RuntimeRegistry counts exactly.
  agents: {},
  tasks: {},
  providers: {},
  memory: [],
  audit: [],
  notifications: [],
  performance: null,
  missions: {},
  missionUpdates: 0,
  // Phase 15: ecosystem snapshot — null until hydrateEcosystem() or the
  // first ecosystem.* WebSocket event populates it.
  ecosystem: null,
  // Phase 16: cluster snapshot — null until hydrateCluster() or the
  // first cluster.* WebSocket event populates it.
  cluster: null,
  // Phase 17: evolution snapshot — null until hydrateEvolution() or the
  // first evolution.* WebSocket event populates it.
  evolution: null,
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
            // Silent reconnect — no console.warn to avoid spam
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
        // Silent — no console.error to avoid spam
        return;
      }

      const delay = Math.min(WS_RECONNECT_BASE_DELAY * Math.pow(2, retryCount), WS_RECONNECT_MAX_DELAY);
      // Add jitter (±10%)
      const jitter = delay * 0.1 * (Math.random() * 2 - 1);
      const finalDelay = Math.floor(delay + jitter);

      // Silent reconnect — no console.log to avoid spam
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
        case "task.assigned":
        case "task.started":
        case "task.completed":
        case "task.failed": {
          const id = String(p.task_id ?? p.taskId ?? p.id ?? "task");
          tasks = { ...s.tasks };
          const prev = tasks[id] ?? {
            id,
            title: String(p.title ?? ""),
            role: String(p.role ?? ""),
            status: "pending" as TaskNode["status"],
          };
          tasks[id] = {
            id,
            title: String(p.title ?? prev.title ?? ""),
            role: String(p.role ?? prev.role ?? ""),
            status: (
              e.topic === "task.started" ? "in_progress" :
              e.topic === "task.completed" ? "completed" :
              e.topic === "task.failed" ? "failed" :
              e.topic.replace("task.", "")
            ) as TaskNode["status"],
          };
          telemetry = { ...s.telemetry };
          telemetry.tasks = Object.keys(tasks).length;
          if (e.topic === "task.failed") telemetry.errors += 1;
          break;
        }
        case "task.output": {
          const tid = String(p.task_id ?? p.taskId ?? p.id ?? "");
          if (tid) {
            const outputKey = `__output__${tid}`;
            const sAny = s as unknown as Record<string, unknown>;
            const prevLines = sAny[outputKey] as string[] | undefined;
            const newLine = `[${p.timestamp ?? ""}] ${p.stream === "stderr" ? "✗" : "›"} ${p.line ?? ""}`;
            sAny[outputKey] = [...(prevLines ?? []), newLine].slice(-500);
          }
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
        case "brain.registered":
        case "brain.discovered":
        case "brain.updated":
        case "brain.health_changed": {
          const name = String(p.display_name ?? p.name ?? p.id ?? "brain");
          providers = { ...s.providers };
          const healthNum = Number(p.health ?? 100);
          const statusStr = healthNum >= 80 ? "healthy" : healthNum >= 50 ? "degraded" : "unknown";
          providers[name] = {
            provider: name,
            status: statusStr,
            latency_ms: Number(p.latency ?? 0),
          };
          const id = String(p.id ?? name);
          agents = { ...s.agents };
          agents[id] = {
            id,
            role: "assistant",
            capabilities: (p.capabilities as string[]) ?? [],
            status: statusStr === "healthy" ? "running" : "idle",
            health: statusStr as AgentNode["health"],
            provider: name,
          };
          telemetry = { ...s.telemetry };
          telemetry.providers = Object.keys(providers).length;
          telemetry.agents = Object.keys(agents).length;
          break;
        }
        case "brain.removed": {
          // When a brain is unregistered (runtime disappears), remove its
          // entries from both the agents and providers maps so the UI
          // reflects the removal immediately — without waiting for the next
          // 30s hydrate() to correct the stale state.
          const name = String(p.display_name ?? p.name ?? p.id ?? "brain");
          const id = String(p.id ?? name);
          providers = { ...s.providers };
          agents = { ...s.agents };
          delete providers[name];
          delete agents[id];
          telemetry = { ...s.telemetry };
          telemetry.providers = Object.keys(providers).length;
          telemetry.agents = Object.keys(agents).length;
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
            // Upsert: if the mission is new (e.g. just created from Prompt Center),
            // insert it into the store. If it already exists, update its status
            // in-place. Either way, bump missionUpdates so subscribers re-render.
            const existing = s.missions[m.id];
            const merged = existing
              ? { ...existing, ...m, status: m.status ?? existing.status, updated_at: new Date().toISOString() }
              : { ...m, updated_at: new Date().toISOString() };
            return {
              events, notifications, agents, tasks, providers, telemetry,
              missions: {
                ...s.missions,
                [m.id]: merged,
              },
              missionUpdates: Date.now(),
            };
          }
          break;
        }
        // ── Phase 15: Ecosystem events ───────────────────────────────
        // Every ecosystem.* event updates the local ecosystem snapshot so
        // the Mission Overview / AI Brain / AI Constellation / Fleet views
        // can render live state without polling.
        case "ecosystem.started":
        case "ecosystem.updated":
        case "ecosystem.health.updated":
        case "ecosystem.capability.updated":
        case "ecosystem.collaboration.updated":
        case "ecosystem.statistics.updated":
        case "ecosystem.analysis.completed":
        case "ecosystem.evolution.generated":
        case "ecosystem.optimization.started":
        case "ecosystem.optimization.completed":
        case "ecosystem.task.published":
        case "ecosystem.task.bids_collected":
        case "ecosystem.task.awarded":
        case "ecosystem.task.completed":
        case "ecosystem.task.failed":
        case "ecosystem.task.cancelled": {
          // Merge the event payload into the ecosystem snapshot. The
          // payload shape varies by topic — we keep a per-topic reducer
          // so each event updates exactly the slice it owns.
          const prevEco = s.ecosystem ?? {
            stats: null,
            health: null,
            graphStats: null,
            networkStats: null,
            marketplaceStats: null,
            evolutionStats: null,
            lastEventAt: 0,
          };
          const next = { ...prevEco, lastEventAt: Date.now() };
          if (e.topic === "ecosystem.updated" || e.topic === "ecosystem.statistics.updated") {
            next.stats = p as Record<string, unknown>;
          } else if (e.topic === "ecosystem.health.updated") {
            next.health = p as Record<string, unknown>;
          } else if (e.topic === "ecosystem.capability.updated") {
            next.graphStats = p as Record<string, unknown>;
          } else if (e.topic === "ecosystem.collaboration.updated") {
            next.networkStats = p as Record<string, unknown>;
          } else if (e.topic === "ecosystem.analysis.completed") {
            next.evolutionStats = p as Record<string, unknown>;
          } else if (e.topic === "ecosystem.optimization.completed") {
            next.evolutionStats = p as Record<string, unknown>;
          }
          return {
            events, notifications, agents, tasks, providers, telemetry,
            ecosystem: next,
          };
        }
        // ── Phase 16: Cluster federation events ─────────────────────
        case "cluster.started":
        case "cluster.updated":
        case "cluster.node.joined":
        case "cluster.node.left":
        case "cluster.node.updated":
        case "cluster.brain.discovered":
        case "cluster.brain.removed":
        case "cluster.scheduler.started":
        case "cluster.scheduler.completed":
        case "cluster.failover.started":
        case "cluster.failover.completed":
        case "cluster.consensus.completed":
        case "cluster.topology.updated":
        case "cluster.statistics.updated": {
          const prevCluster = s.cluster ?? {
            status: null,
            topology: null,
            statistics: null,
            lastEventAt: 0,
          };
          const nextCluster = { ...prevCluster, lastEventAt: Date.now() };
          if (e.topic === "cluster.started" || e.topic === "cluster.updated") {
            nextCluster.status = p as Record<string, unknown>;
          } else if (e.topic === "cluster.topology.updated") {
            nextCluster.topology = p as Record<string, unknown>;
          } else if (
            e.topic === "cluster.statistics.updated"
            || e.topic === "cluster.node.joined"
            || e.topic === "cluster.node.left"
            || e.topic === "cluster.node.updated"
          ) {
            // Node events include the node payload — keep topology slice fresh
            nextCluster.status = p as Record<string, unknown>;
          }
          return {
            events, notifications, agents, tasks, providers, telemetry,
            cluster: nextCluster,
          };
        }
        // ── Phase 17: Evolution events ───────────────────────────────
        case "evolution.started":
        case "evolution.stopped":
        case "evolution.analysis.completed":
        case "evolution.improvement.scheduled":
        case "evolution.improvement.applied":
        case "evolution.improvement.rolled_back":
        case "evolution.knowledge.synthesized":
        case "evolution.readiness.updated":
        case "evolution.statistics.updated": {
          const prevEvo = s.evolution ?? {
            statistics: null,
            readiness: null,
            lastEventAt: 0,
          };
          const nextEvo = { ...prevEvo, lastEventAt: Date.now() };
          if (e.topic === "evolution.statistics.updated") {
            nextEvo.statistics = p as Record<string, unknown>;
          } else if (e.topic === "evolution.readiness.updated") {
            nextEvo.readiness = p as Record<string, unknown>;
          } else if (e.topic === "evolution.analysis.completed") {
            nextEvo.statistics = p as Record<string, unknown>;
          }
          return {
            events, notifications, agents, tasks, providers, telemetry,
            evolution: nextEvo,
          };
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
      // Fetch all snapshot sources in parallel — never block on any single failure.
      const [rawAgents, rawProviders, rawBrains, rawLocalAgents] = await Promise.allSettled([
        api.get<Array<Record<string, unknown>>>("/api/agents"),
        api.providerHealth(),
        api.get<Array<Record<string, unknown>>>("/api/brains"),
        api.get<Array<Record<string, unknown>>>("/api/local-agents"),
      ]);

      // ── Agents ──────────────────────────────────────────────────────────────
      const agentsMap: Record<string, AgentNode> = {};
      if (rawAgents.status === "fulfilled" && Array.isArray(rawAgents.value)) {
        for (const a of rawAgents.value) {
          const id = String(a.id ?? a.name ?? "");
          if (!id) continue;
          agentsMap[id] = {
            id,
            role: String(a.role ?? "agent"),
            capabilities: (a.capabilities as string[]) ?? [],
            status: (a.status as AgentNode["status"]) ?? "idle",
            health: (a.health as AgentNode["health"]) ?? "unknown",
            provider: a.provider as string | undefined,
          };
        }
      }

      // ── Providers (from health endpoint — has .provider field) ────────────
      let providersMap: Record<string, ProviderHealthRecord> = {};
      if (rawProviders.status === "fulfilled" && Array.isArray(rawProviders.value)) {
        for (const p of rawProviders.value) {
          const name = String(p.provider ?? "");
          if (!name || ["mock", "Mock"].includes(name)) continue;
          providersMap[name] = {
            provider: name,
            status: (p.status as ProviderHealthStatus) ?? "unknown",
            latency_ms: Number(p.latency_ms ?? 0),
            error: p.error as string | undefined,
          };
        }
      }

      // ── Brains → also surface as provider entries so AI Brain shows them ──
      if (rawBrains.status === "fulfilled" && Array.isArray(rawBrains.value)) {
        for (const b of rawBrains.value) {
          const name = String(b.display_name ?? b.id ?? "");
          if (!name) continue;
          // Add as provider entry so AI Brain / Agent Constellation renders them
          if (!providersMap[name]) {
            providersMap[name] = {
              provider: name,
              status: b.health != null && Number(b.health) >= 80 ? "healthy"
                : b.health != null && Number(b.health) >= 50 ? "degraded" : "unknown",
              latency_ms: Number(b.latency ?? 0),
            };
          }
          // Also add as agent entry
          const id = String(b.id ?? b.display_name ?? "");
          if (id && !agentsMap[id]) {
            agentsMap[id] = {
              id,
              role: "assistant",
              capabilities: (b.capabilities as string[]) ?? [],
              status: providersMap[name].status === "healthy" ? "running" : "idle",
              health: providersMap[name].status as AgentNode["health"] ?? "unknown",
              provider: name,
            };
          }
        }
      }

      // ── Local Agents → surface as providers + agents ──────────────────────
      if (rawLocalAgents.status === "fulfilled" && Array.isArray(rawLocalAgents.value)) {
        for (const a of rawLocalAgents.value) {
          // LocalAgent.to_dict() exposes `status` (not `running`). Include
          // every discovered agent — "discovered" means "installed on this
          // machine", which is exactly what the Fleet/Constellation/Binding
          // views need to display. The previous `!a.running` check was always
          // false (no such field) so local agents never appeared in the store.
          const name = String(a.name ?? "");
          if (!name) continue;
          const status = String(a.status ?? "unknown");
          const isHealthy = status === "running" || status === "idle" || status === "busy";
          if (!providersMap[name]) {
            providersMap[name] = {
              provider: name,
              status: isHealthy ? "healthy" : "degraded",
              latency_ms: Number(a.latency_ms ?? 0),
            };
          }
          const id = String(a.id ?? a.name ?? "");
          if (id && !agentsMap[id]) {
            agentsMap[id] = {
              id,
              role: String(a.engine_type ?? "agent"),
              capabilities: (a.capabilities as string[]) ?? [],
              status: a.running ? "running" : "idle",
              health: a.health === "healthy" ? "healthy" : "degraded",
              provider: name,
            };
          }
        }
      }

      // ── Commit snapshot + update telemetry counters ───────────────────────
      // Dedupe providers by normalized id: /api/providers/health may return
      // "hermes" while /api/brains uses display_name "Hermes" — both slugify
      // to the same key, and views use that slug as a React key (duplicate
      // key error). Keep the healthiest entry per slug.
      const providersBySlug: Record<string, ProviderHealthRecord> = {};
      for (const p of Object.values(providersMap)) {
        const slug = (p.provider ?? "").toLowerCase().replace(/\s+/g, "-");
        if (!slug) continue;
        const prev = providersBySlug[slug];
        const rank = (s?: string) =>
          s === "healthy" ? 3 : s === "degraded" ? 2 : s === "unknown" ? 1 : 0;
        if (!prev || rank(p.status) > rank(prev.status)) {
          providersBySlug[slug] = p;
        }
      }
      providersMap = providersBySlug;

      // Replace (not merge) agents/providers so that runtimes which disappeared
      // from the backend are also removed from the store. The previous merge
      // logic (`{ ...s.agents, ...agentsMap }`) kept stale entries forever.
      // Preserve the rest of telemetry (tasks/tokens/cost/pulses) which is
      // accumulated from WebSocket events and must not be reset on every hydrate.
      set((s) => ({
        agents: agentsMap,
        providers: providersMap,
        telemetry: {
          ...s.telemetry,
          agents: Object.keys(agentsMap).length,
          providers: Object.keys(providersMap).length,
        },
      }));
    } catch (e) {
      console.warn("[store] hydrate failed:", e);
    }
  },
  // Phase 15: Pull the live ecosystem snapshot from /api/ecosystem/dashboard.
  // The backend derives every field from BrainRegistry + EventBus — no mock.
  hydrateEcosystem: async () => {
    try {
      const dash = await api.get<Record<string, unknown>>("/api/ecosystem/dashboard");
      set({
        ecosystem: {
          stats: (dash.stats as Record<string, unknown>) ?? null,
          health: (dash.health as Record<string, unknown>) ?? null,
          graphStats: (dash.graph_stats as Record<string, unknown>) ?? null,
          networkStats: (dash.network_stats as Record<string, unknown>) ?? null,
          marketplaceStats: (dash.marketplace_stats as Record<string, unknown>) ?? null,
          evolutionStats: (dash.evolution_stats as Record<string, unknown>) ?? null,
          lastEventAt: Date.now(),
        },
      });
    } catch (e) {
      // EcosystemController may not be running yet — that's fine, the UI
      // will retry on the next hydrate cycle. Don't log warn to avoid
      // spamming the console when the ecosystem is intentionally disabled.
      if (get().ecosystem === null) {
        set({ ecosystem: null });
      }
    }
  },
  // Phase 16: Pull the live cluster snapshot from /api/cluster/dashboard.
  hydrateCluster: async () => {
    try {
      const [dash, stats] = await Promise.all([
        api.get<Record<string, unknown>>("/api/cluster/dashboard"),
        api.get<Record<string, unknown>>("/api/cluster/statistics"),
      ]);
      set({
        cluster: {
          status: (dash.federation as Record<string, unknown>) ?? null,
          topology: (dash.topology as Record<string, unknown>) ?? null,
          statistics: stats ?? null,
          lastEventAt: Date.now(),
        },
      });
    } catch (e) {
      // ClusterController may not be running (single-node deployment
      // without federation). Silently leave cluster state as-is.
      if (get().cluster === null) {
        set({ cluster: null });
      }
    }
  },
  // Phase 17: Pull the live evolution snapshot from /api/evolution/dashboard.
  hydrateEvolution: async () => {
    try {
      const [dash, readiness] = await Promise.all([
        api.get<Record<string, unknown>>("/api/evolution/dashboard"),
        api.get<Record<string, unknown>>("/api/evolution/readiness"),
      ]);
      set({
        evolution: {
          statistics: (dash.statistics as Record<string, unknown>) ?? null,
          readiness: readiness ?? null,
          lastEventAt: Date.now(),
        },
      });
    } catch (e) {
      // EvolutionController may not be running. Silently leave state as-is.
      if (get().evolution === null) {
        set({ evolution: null });
      }
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
