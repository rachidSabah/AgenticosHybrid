// Typed REST client over the AgenticOS FastAPI control plane.
// No duplicated business logic — it only maps HTTP responses to domain types.

import type {
  AgentSpec,
  AuditEntry,
  CapabilityInfo,
  CostRecord,
  MemoryItem,
  MemoryScope,
  MissionPlanType,
  MissionType,
  ModelInfo,
  ProviderConfig,
  ProviderHealthRecord,
  ProviderInfo,
} from "./types";

// Resolve the backend base URL.
// In Tauri's custom-protocol shell the page origin is tauri://localhost, so
// we cannot rely on a relative URL.  The embedded backend always runs on
// 127.0.0.1:8000.  We detect the Tauri context via window.__TAURI__ (injected
// by the Tauri runtime) and fall back to the build-time env var otherwise.
function resolveBase(): string {
  if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).__TAURI__) {
    return "http://127.0.0.1:8000";
  }
  return process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
}

const BASE = resolveBase();

async function get<T>(path: string, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, { headers: { accept: "application/json" } });
    if (!res.ok) {
      // HTTP error (4xx/5xx) — return safe default, never throw
      if (fallback !== undefined) return fallback;
      if (path.includes("health") || path.includes("status")) {
        return { status: "offline", healthy: false, state: "offline", bus: "offline" } as unknown as T;
      }
      return [] as unknown as T;
    }
    return (await res.json()) as T;
  } catch (err) {
    // Network error / JSON parse error — log + return safe default, never throw
    if (process.env.NODE_ENV !== "production") console.error(`[api.get] ${path}:`, err);
    if (fallback !== undefined) return fallback;
    if (path.includes("health") || path.includes("status")) {
      return { status: "offline", healthy: false, state: "offline", bus: "offline" } as unknown as T;
    }
    return [] as unknown as T;
  }
}

async function post<T>(path: string, body?: unknown, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      // HTTP error — return safe default, never throw
      if (fallback !== undefined) return fallback;
      return { success: false, status: "error", error: `HTTP ${res.status}` } as unknown as T;
    }
    return (await res.json()) as T;
  } catch (err) {
    // Network error — log + return safe default, never throw
    if (process.env.NODE_ENV !== "production") console.error(`[api.post] ${path}:`, err);
    if (fallback !== undefined) return fallback;
    return { success: false, status: "offline", error: "Control plane offline" } as unknown as T;
  }
}

async function put<T>(path: string, body?: unknown, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "PUT",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      if (fallback !== undefined) return fallback;
      return { success: false, status: "error", error: `HTTP ${res.status}` } as unknown as T;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`[api.put] ${path}:`, err);
    if (fallback !== undefined) return fallback;
    return { success: false, status: "offline", error: "Control plane offline" } as unknown as T;
  }
}

async function del<T>(path: string, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
    if (!res.ok) {
      if (fallback !== undefined) return fallback;
      return { deleted: false, success: false } as unknown as T;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`[api.del] ${path}:`, err);
    if (fallback !== undefined) return fallback;
    return { deleted: false, success: false } as unknown as T;
  }
}

export const api = {
  /** Generic request wrappers */
  get: <T>(path: string) => get<T>(path),
  post: <T>(path: string, body?: unknown) => post<T>(path, body),

  health: () => get<{ status: string; bus: string }>("/healthz"),
  eventsRecent: (limit = 100) => get<Array<Record<string, unknown>>>(`/api/events/recent?limit=${limit}`),


  providers: () => get<ProviderInfo[]>("/api/providers"),
  providerConfigs: () => get<ProviderConfig[]>("/api/provider-configs"),
  providerHealth: () => get<ProviderHealthRecord[]>("/api/provider-health"),
  upsertProvider: (cfg: ProviderConfig) => post<ProviderConfig>("/api/provider-configs", cfg),
  deleteProvider: (name: string) => del<{ deleted: string }>(`/api/provider-configs/${name}`),
  storeApiKey: (name: string, apiKey: string) =>
    post<{ stored: string }>(`/api/providers/${name}/api-key`, { api_key: apiKey }),
  apiKeyStatus: (name: string) =>
    get<{ provider: string; has_key: boolean }>(`/api/providers/${name}/api-key/status`),
  testProvider: (name: string) =>
    post<{ provider: string; healthy: boolean; status: string; latency_ms: number; error?: string }>(
      `/api/providers/${name}/test`,
    ),
  benchmarkProvider: (name: string, model = "") =>
    post<Record<string, unknown>>(`/api/providers/${name}/benchmark`, { model }),

  models: (provider?: string) =>
    get<ModelInfo[]>(`/api/models${provider ? `?provider=${encodeURIComponent(provider)}` : ""}`),

  cost: () => get<{ total: number; records: CostRecord[] }>("/api/cost"),
  rateLimits: () => get<Record<string, number>>("/api/rate-limits"),
  setRoutingPolicy: (policy: "latency" | "cost" | "round_robin") =>
    post<{ policy: string }>("/api/routing/policy", { policy }),

  capabilities: () => get<CapabilityInfo[]>("/api/capabilities"),

  composeAgent: (body: {
    name: string;
    capabilities: string[];
    provider: string;
    model: string;
  }) => post<AgentSpec>("/api/agents/compose", body),
  composeForTask: (body: { title: string; role: string }) =>
    post<AgentSpec>("/api/agents/compose-for-task", body),

  writeMemory: (body: {
    scope: MemoryScope;
    key: string;
    value: string;
    embedding?: number[];
    agent_id?: string;
    project_id?: string;
  }) => post<MemoryItem>("/api/memory", body),
  memoryScope: (scope: MemoryScope, agentId = "") =>
    get<MemoryItem[]>(`/api/memory/${scope}${agentId ? `?agent_id=${encodeURIComponent(agentId)}` : ""}`),
  recallMemory: (scope: MemoryScope, query: string, limit = 10, agentId = "") =>
    get<MemoryItem[]>(
      `/api/memory/${scope}/recall?query=${encodeURIComponent(query)}&limit=${limit}${agentId ? `&agent_id=${encodeURIComponent(agentId)}` : ""}`,
    ),
  forgetMemory: (id: string) => del<{ forgotten: boolean }>(`/api/memory/${id}`),
  enforceRetention: () => post<{ evicted: number }>("/api/memory/retention"),

  audit: (principal?: string) =>
    get<AuditEntry[]>(`/api/security/audit${principal ? `?principal=${encodeURIComponent(principal)}` : ""}`),
  authorize: (body: {
    principal: string;
    roles: string[];
    capability: string;
    requires_approval?: boolean;
  }) => post<{ allowed: boolean; reason: string; approved_by?: string }>("/api/security/authorize", body),
  decideApproval: (requestId: string, approved: boolean, by = "") =>
    post<{ decided: string }>(`/api/security/approval/${requestId}/decide`, { approved, by }),
  workspaceFor: (agentId: string) =>
    get<{ agent_id: string; workspace: string }>(`/api/security/workspace/${agentId}`),

  // ── Discovery API (Phase 4, M2) ──

  discoveryProviders: () => get<import("./types").DiscoveryProviderInfo[]>("/api/discovery/providers"),
  enableProvider: (name: string, body: { enabled: boolean }) =>
    put<import("./types").DiscoveryProviderInfo>(`/api/discovery/providers/${name}`, body),
  runDiscoveryScan: (profile?: string) =>
    post<{ profile: string; engines_found: number; engines_registered: number }>("/api/discovery/scan", profile ? { profile } : undefined),
  discoveryCache: () => get<import("./types").DiscoveryCacheEntry[]>("/api/discovery/cache"),
  clearDiscoveryCache: () => del<{ cleared: number }>("/api/discovery/cache"),
  discoveryHistory: (limit = 50) =>
    get<import("./types").DiscoveryHistoryEntry[]>(`/api/discovery/history?limit=${limit}`),
  discoveryStats: () => get<import("./types").DiscoveryStats>("/api/discovery/stats"),
  discoveryProfiles: () => get<import("./types").DiscoveryProfileEntry[]>("/api/discovery/profiles"),
  createDiscoveryProfile: (body: { name: string; description?: string; provider_configs?: import("./types").DiscoveryProviderConfig[] }) =>
    post<import("./types").DiscoveryProfileEntry>("/api/discovery/profiles", body),
  getDiscoveryProfile: (name: string) => get<import("./types").DiscoveryProfileEntry>(`/api/discovery/profiles/${encodeURIComponent(name)}`),
  deleteDiscoveryProfile: (name: string) => del<{ deleted: boolean }>(`/api/discovery/profiles/${encodeURIComponent(name)}`),
  activateDiscoveryProfile: (name: string) =>
    post<{ activated: string }>(`/api/discovery/profiles/${encodeURIComponent(name)}/activate`),
  validateEngine: (engineId: string) =>
    post<import("./types").DiscoveryValidationEntry[]>(`/api/discovery/engines/${encodeURIComponent(engineId)}/validate`),
  startHotReload: () => post<{ status: string }>("/api/discovery/hot-reload/start"),
  stopHotReload: () => post<{ status: string }>("/api/discovery/hot-reload/stop"),
  hotReloadStatus: () => get<import("./types").HotReloadStatus>("/api/discovery/hot-reload/status"),

  // ── MCP Runtime API (Phase 4, M3) ──

  mcpServers: (status?: string, enabledOnly?: boolean) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (enabledOnly) params.set("enabled_only", "true");
    const qs = params.toString();
    return get<import("./types").MCPServerDetail[]>(`/api/mcp/servers${qs ? `?${qs}` : ""}`);
  },
  mcpServer: (serverId: string) =>
    get<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}`),
  registerMcpServer: (body: Record<string, unknown>) =>
    post<import("./types").MCPServerDetail>("/api/mcp/servers", body),
  updateMcpServer: (serverId: string, body: Record<string, unknown>) =>
    put<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}`, body),
  deleteMcpServer: (serverId: string) =>
    del<{ deleted: string }>(`/api/mcp/servers/${encodeURIComponent(serverId)}`),

  mcpStartServer: (serverId: string) =>
    post<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}/start`),
  mcpStopServer: (serverId: string) =>
    post<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}/stop`),
  mcpRestartServer: (serverId: string) =>
    post<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}/restart`),
  mcpReloadServer: (serverId: string) =>
    post<import("./types").MCPServerDetail>(`/api/mcp/servers/${encodeURIComponent(serverId)}/reload`),

  mcpServerTools: (serverId: string) =>
    get<import("./types").MCPTool[]>(`/api/mcp/servers/${encodeURIComponent(serverId)}/tools`),
  mcpDiscoverTools: (serverId: string) =>
    post<import("./types").MCPTool[]>(`/api/mcp/servers/${encodeURIComponent(serverId)}/tools/discover`),
  mcpCallTool: (serverId: string, tool: string, args: Record<string, unknown>) =>
    post<import("./types").MCPToolResult>(`/api/mcp/servers/${encodeURIComponent(serverId)}/tools/call`, { tool, arguments: args }),

  mcpServerHealth: (serverId: string) =>
    get<{ server_id: string; health: string }>(`/api/mcp/servers/${encodeURIComponent(serverId)}/health`),
  mcpHealthSummary: () =>
    get<import("./types").MCPHealthSummary>("/api/mcp/health"),

  mcpSessions: () =>
    get<import("./types").MCPSessionMap>("/api/mcp/sessions"),

  mcpPermissions: (serverId: string) =>
    get<import("./types").MCPPermissionMapping[]>(`/api/mcp/servers/${encodeURIComponent(serverId)}/permissions`),
  mcpSetPermissions: (serverId: string, mappings: import("./types").MCPPermissionMapping[]) =>
    post<{ server_id: string; mappings_count: number }>(`/api/mcp/servers/${encodeURIComponent(serverId)}/permissions`, { mappings }),

  // Extended MCP API (Phase 4, M3)
  mcpServerResources: (serverId: string) =>
    get<import("./types").MCPResource[]>(`/api/mcp/servers/${encodeURIComponent(serverId)}/resources`),
  mcpServerPrompts: (serverId: string) =>
    get<import("./types").MCPPrompt[]>(`/api/mcp/servers/${encodeURIComponent(serverId)}/prompts`),
  mcpServerHealthCheck: (serverId: string) =>
    post<{ server_id: string; status: string; latency_ms: number }>(`/api/mcp/health/${encodeURIComponent(serverId)}/check`),
  mcpDegradedServers: () =>
    get<{ servers: string[] }>("/api/mcp/health/degraded"),
  mcpUnhealthyServers: () =>
    get<{ servers: string[] }>("/api/mcp/health/unhealthy"),

  mcpTelemetrySummary: () =>
    get<import("./types").MCPTelemetrySummary>("/api/mcp/telemetry/summary"),
  mcpLatencyDistribution: () =>
    get<{ p50: number; p90: number; p95: number; p99: number; min: number; max: number }>("/api/mcp/telemetry/latency"),
  mcpRecentErrors: (limit?: number) =>
    get<{ errors: Array<{ timestamp: string; server_id: string; method: string; error: string }> }>(`/api/mcp/telemetry/errors${limit ? `?limit=${limit}` : ""}`),
  mcpServerTelemetry: (serverId: string) =>
    get<import("./types").MCPServerMetrics>(`/api/mcp/telemetry/servers/${encodeURIComponent(serverId)}`),

  mcpRegistry: () =>
    get<{ servers: import("./types").MCPServerDetail[]; updated_at: string }>("/api/mcp/registry"),
  mcpRegistryStats: () =>
    get<import("./types").MCPRegistryStats>("/api/mcp/registry/stats"),

  mcpSessionsList: (serverId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (serverId) params.set("server_id", serverId);
    if (status) params.set("status", status);
    const qs = params.toString();
    return get<import("./types").MCPSession[]>(`/api/mcp/sessions${qs ? `?${qs}` : ""}`);
  },
  mcpSession: (sessionId: string) =>
    get<import("./types").MCPSession>(`/api/mcp/sessions/${encodeURIComponent(sessionId)}`),
  mcpCloseSession: (sessionId: string) =>
    del<{ closed: string }>(`/api/mcp/sessions/${encodeURIComponent(sessionId)}`),
  mcpSessionStats: () =>
    get<import("./types").MCPSessionStats>("/api/mcp/sessions/stats"),
  mcpCleanupSessions: () =>
    post<{ expired: number; closed_cleaned: number }>("/api/mcp/sessions/cleanup"),

  // ── MCP Version Management ──
  mcpVersions: () =>
    get<Record<string, import("./types").MCPVersionInfo>>("/api/mcp/versions"),
  mcpServerVersion: (serverId: string) =>
    get<import("./types").MCPVersionDetail>(`/api/mcp/versions/${encodeURIComponent(serverId)}`),
  mcpVersionMatrix: () =>
    get<import("./types").MCPVersionMatrix>("/api/mcp/versions/matrix"),

  // ── MCP Capabilities ──
  mcpCapabilities: () =>
    get<Record<string, string[]>>("/api/mcp/capabilities"),
  mcpServerCapabilities: (serverId: string) =>
    get<import("./types").MCPCapabilityView>(`/api/mcp/capabilities/${encodeURIComponent(serverId)}`),
  mcpNegotiateCapabilities: (body: import("./types").MCPNegotiateRequest) =>
    post<import("./types").MCPNegotiateResult>("/api/mcp/capabilities/negotiate", body),

  // ── MCP Registry Search ──
  mcpRegisteredTools: (serverId?: string) => {
    const qs = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
    return get<import("./types").MCPRegisteredTool[]>(`/api/mcp/tools/registry${qs}`);
  },
  mcpSearchTools: (query: string) =>
    get<import("./types").MCPRegisteredTool[]>(`/api/mcp/tools/registry/search?query=${encodeURIComponent(query)}`),
  mcpToolRegistryStats: () =>
    get<{ total_tools: number; total_servers: number }>("/api/mcp/tools/registry/stats"),

  mcpRegisteredResources: (serverId?: string) => {
    const qs = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
    return get<import("./types").MCPRegisteredResource[]>(`/api/mcp/resources/registry${qs}`);
  },
  mcpSearchResources: (query: string) =>
    get<import("./types").MCPRegisteredResource[]>(`/api/mcp/resources/registry/search?query=${encodeURIComponent(query)}`),

  mcpRegisteredPrompts: (serverId?: string) => {
    const qs = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
    return get<import("./types").MCPRegisteredPrompt[]>(`/api/mcp/prompts/registry${qs}`);
  },
  mcpSearchPrompts: (query: string) =>
    get<import("./types").MCPRegisteredPrompt[]>(`/api/mcp/prompts/registry/search?query=${encodeURIComponent(query)}`),

  // ── Swarm Orchestration (Phase 4, M4) ──

  swarmProfiles: () =>
    get<import("./types").SwarmProfile[]>("/api/swarm/profiles"),
  createSwarmProfile: (body: Record<string, unknown>) =>
    post<import("./types").SwarmProfile>("/api/swarm/profiles", body),
  deleteSwarmProfile: (name: string) =>
    del<{ deleted: string }>(`/api/swarm/profiles/${encodeURIComponent(name)}`),

  swarmList: () =>
    get<import("./types").SwarmSummary[]>("/api/swarm/swarms"),
  createSwarm: (body: Record<string, unknown>) =>
    post<import("./types").SwarmDetail>("/api/swarm/swarms", body),
  swarmDetail: (swarmId: string) =>
    get<import("./types").SwarmDetail>(`/api/swarm/swarms/${encodeURIComponent(swarmId)}`),
  deleteSwarm: (swarmId: string) =>
    del<{ deleted: string }>(`/api/swarm/swarms/${encodeURIComponent(swarmId)}`),

  swarmAgents: () =>
    get<import("./types").SwarmAgentInfo[]>("/api/swarm/agents"),
  swarmAgentDetail: (agentId: string) =>
    get<import("./types").SwarmAgentInfo>(`/api/swarm/agents/${encodeURIComponent(agentId)}`),

  swarmGoals: () =>
    get<{ goals: Array<{ id: string; description: string; status: string }> }>("/api/swarm/goals"),
  createSwarmGoal: (body: { description: string; swarm_id?: string }) =>
    post<import("./types").SwarmTaskSummary>("/api/swarm/goals", body),

  swarmPlans: (planId?: string) => {
    const path = planId ? `/api/swarm/plans/${encodeURIComponent(planId)}` : "/api/swarm/plans";
    return get<import("./types").SwarmPlanSummary | import("./types").SwarmPlanSummary[]>(path);
  },
  swarmTasks: () =>
    get<import("./types").SwarmTaskSummary[]>("/api/swarm/tasks"),

  swarmConsensus: (roundId?: string) => {
    const path = roundId ? `/api/consensus/${encodeURIComponent(roundId)}` : "/api/consensus";
    return get(path);
  },

  swarmMetrics: () =>
    get<import("./types").SwarmMetricsSummary>("/api/swarm/metrics"),
  swarmTimeline: (planId: string) =>
    get<{ timeline: Array<{ timestamp: string; event: string }> }>(`/api/swarm/metrics/timeline/${encodeURIComponent(planId)}`),
  swarmCost: (planId: string) =>
    get<Record<string, unknown>>(`/api/swarm/cost/${encodeURIComponent(planId)}`),
  swarmPerformance: (planId: string) =>
    get<Record<string, unknown>>(`/api/swarm/performance/${encodeURIComponent(planId)}`),

  swarmAnalyzeGoal: (body: { description: string }) =>
    post<{ analysis: Record<string, unknown> }>("/api/swarm/planner/analyze", body),
  swarmCreatePlan: (body: { goal: string }) =>
    post<{ plan: Record<string, unknown> }>("/api/swarm/planner/plan", body),

  swarmSupervisorMonitor: (planId: string) =>
    post<{ status: string }>(`/api/swarm/supervisor/monitor`, { plan_id: planId }),
  swarmValidateOutput: (body: Record<string, unknown>) =>
    post<{ valid: boolean; score: number }>("/api/swarm/validate/output", body),
  swarmMerge: (body: Record<string, unknown>) =>
    post<{ merged: Record<string, unknown> }>("/api/swarm/merge", body),
  swarmRecover: (taskId: string) =>
    post<{ recovered: string }>(`/api/swarm/recovery/task/${encodeURIComponent(taskId)}`),
  swarmRetry: (taskId: string) =>
    post<{ retry: boolean; delay: number }>(`/api/swarm/retry/should`, { task_id: taskId }),

  // ── Desktop Runtime (Phase 4, M6) ──

  desktopState: () => get<import("./desktop-types").DesktopRuntimeState>("/api/desktop/state"),
  desktopStatus: () => get<{ status: string }>("/api/desktop/status"),
  desktopConfig: () => get<import("./desktop-types").DesktopConfig>("/api/desktop/config"),
  updateDesktopConfig: (body: Partial<import("./desktop-types").DesktopConfig>) =>
    put<import("./desktop-types").DesktopConfig>("/api/desktop/config", body),

  // Windows
  listWindows: () => get<import("./desktop-types").WindowInfo[]>("/api/desktop/windows"),

  // Workspaces
  listWorkspaces: () => get<import("./desktop-types").Workspace[]>("/api/desktop/workspaces"),
  createWorkspace: (body: { name: string }) =>
    post<import("./desktop-types").Workspace>("/api/desktop/workspaces", body),
  getWorkspace: (id: string) =>
    get<import("./desktop-types").Workspace>(`/api/desktop/workspaces/${encodeURIComponent(id)}`),
  switchWorkspace: (id: string) =>
    post<{ switched: string }>(`/api/desktop/workspaces/${encodeURIComponent(id)}/switch`),

  // Notifications
  listNotifications: () =>
    get<import("./desktop-types").DesktopNotification[]>("/api/desktop/notifications"),
  dismissNotification: (id: string) =>
    del<{ dismissed: string }>(`/api/desktop/notifications/${encodeURIComponent(id)}`),

  // Diagnostics & Performance
  diagnostics: () => get<import("./desktop-types").DesktopDiagnosticsInfo>("/api/desktop/diagnostics"),
  performance: () =>
    get<import("./desktop-types").DesktopPerformanceMetrics>("/api/desktop/performance"),

  // Runtime Discovery
  runtimes: () =>
    get<import("./desktop-types").RuntimeInfo[]>("/api/desktop/runtimes"),
  runtimeEngines: () =>
    get<{engines: Record<string, unknown>[]; total: number}>("/api/runtime/engines"),
  discoverRuntimes: () =>
    post<import("./desktop-types").RuntimeDiscoveryResult>("/api/desktop/runtimes/discover"),
  getRuntime: (rt: string) =>
    get<import("./desktop-types").RuntimeInfo | null>(`/api/desktop/runtimes/${encodeURIComponent(rt)}`),

  // Updates
  updateStatus: () => get<{ version: string; status: string }>("/api/desktop/updates/status"),
  checkUpdates: (channel?: string) =>
    get<import("./desktop-types").ReleaseInfo[]>(
      `/api/desktop/updates/check${channel ? `?channel=${encodeURIComponent(channel)}` : ""}`,
    ),
  updateHistory: () =>
    get<import("./desktop-types").UpdateHistoryRecord[]>("/api/desktop/updates/history"),
  pendingUpdate: () => get<import("./desktop-types").UpdateManifest | null>("/api/desktop/updates/pending"),
  downloadUpdate: (body: import("./desktop-types").UpdateManifest) =>
    post<{ success: boolean }>("/api/desktop/updates/download", body),
  installUpdate: (body: import("./desktop-types").UpdateManifest) =>
    post<import("./desktop-types").UpdateResult>("/api/desktop/updates/install", body),

  // Channels
  channels: () => get<string[]>("/api/desktop/channels"),
  currentChannel: () => get<{ channel: string }>("/api/desktop/channels/current"),
  setChannel: (channel: string) =>
    put<{ channel: string }>("/api/desktop/channels", { channel }),

  // Rollback
  rollbackAvailable: () =>
    get<string[]>("/api/desktop/rollback/available"),
  rollback: () => post<import("./desktop-types").UpdateResult>("/api/desktop/rollback"),

  // ── Dev-Mode Git Updates (works on localhost:3000 + any checkout) ──
  // These endpoints check whether the local git checkout is behind
  // origin/main and let the user pull + restart. Useful when running
  // `npm run dev` on localhost:3000 + uvicorn on localhost:8000.
  devUpdateStatus: () =>
    get<{
      local_commit: string;
      local_short: string;
      branch: string;
      remote_commit: string;
      remote_short: string;
      behind: number;
      up_to_date: boolean;
      has_remote: boolean;
      error?: string;
    }>("/api/dev/updates/status"),
  devUpdateCommits: (limit = 50) =>
    get<
      Array<{
        hash: string;
        short_hash: string;
        author: string;
        date: string;
        subject: string;
      }>
    >(`/api/dev/updates/commits?limit=${limit}`),
  devUpdatePull: () =>
    post<{
      success: boolean;
      stdout?: string;
      stderr?: string;
      new_head?: string;
      error?: string;
      returncode?: number;
    }>("/api/dev/updates/pull"),
  devUpdateRestart: () =>
    post<{ scheduled: boolean; message: string }>("/api/dev/updates/restart"),

  // ── Workspace + File Context ──
  workspaceList: (path?: string, depth?: number) =>
    get<{ root: string; file_count: number; children: import("./types").WorkspaceEntry[] }>(
      `/api/workspace/list${path ? `?path=${encodeURIComponent(path)}` : ""}${depth ? `${path ? "&" : "?"}depth=${depth}` : ""}`,
    ),
  workspaceFiles: (path: string) =>
    get<{ path: string; content: string; size: number; truncated: boolean; lines: number }>(
      `/api/workspace/files?path=${encodeURIComponent(path)}`,
    ),
  workspaceSelect: (path: string) =>
    post<{ path: string }>("/api/workspace/select", { path }),
  workspaceCurrent: () => get<{ path: string }>("/api/workspace/current"),
  workspaceContext: () =>
    get<{ root: string; files: Record<string, string>; file_tree: string; total_chars: number }>(
      "/api/workspace/context",
    ),

  // ── Mission Orchestrator API ──
  missions: () => get<MissionType[]>("/api/missions"),

  // ── Execution Log ──
  executions: (params?: {
    mission_id?: string;
    task_id?: string;
    provider?: string;
    status?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.mission_id) qs.set("mission_id", params.mission_id);
    if (params?.task_id) qs.set("task_id", params.task_id);
    if (params?.provider) qs.set("provider", params.provider);
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return get<import("./types").ExecutionRecord[]>(`/api/executions${q ? `?${q}` : ""}`);
  },
  execution: (executionId: string) =>
    get<import("./types").ExecutionRecord>(`/api/executions/${encodeURIComponent(executionId)}`),
  executionStats: () => get<import("./types").ExecutionStats>("/api/executions/stats"),

  // ── Worktree Management ──
  worktreeCreate: (body: { branch_name?: string; base_branch?: string; agent_id?: string; task_id?: string }) =>
    post<import("./types").WorktreeEntry>("/api/worktrees/create", body),
  worktreeList: () => get<import("./types").WorktreeEntry[]>("/api/worktrees/list"),
  worktreeRemove: (branchName: string) =>
    del<{ removed: string }>(`/api/worktrees/${encodeURIComponent(branchName)}`),
  worktreeForAgent: (agentId: string) =>
    get<{ agent_id: string; path: string }>(`/api/worktrees/for-agent/${encodeURIComponent(agentId)}`),
  worktreeDiff: (branchName: string) =>
    get<import("./types").WorktreeDiffFile[]>(`/api/worktrees/${encodeURIComponent(branchName)}/diff`),
  worktreeFile: (branchName: string, path: string) =>
    get<{ path: string; content: string; truncated: boolean }>(
      `/api/worktrees/${encodeURIComponent(branchName)}/file?path=${encodeURIComponent(path)}`,
    ),
  worktreeMerge: (branchName: string) =>
    post<{ merged: boolean; branch: string; base: string; message?: string; error?: string; conflicts?: boolean }>(
      `/api/worktrees/${encodeURIComponent(branchName)}/merge`,
    ),

  // ── Messaging Gateways ──
  telegramStatus: () => get<{ running: boolean; username: string; recent_messages: unknown[]; allowed_users: number[] | null }>("/api/gateway/telegram/status"),
  telegramConnect: (body: { bot_token: string; allowed_users?: number[] }) =>
    post<{ status: string; username: string }>("/api/gateway/telegram/connect", body),
  telegramDisconnect: () => post<{ status: string }>("/api/gateway/telegram/disconnect"),
  telegramSend: (body: { chat_id: number | string; text: string }) =>
    post<{ sent: boolean }>("/api/gateway/telegram/send", body),
  telegramChats: () => get<Array<{ chat_id: number; last_message: string; timestamp: string }>>("/api/gateway/telegram/chats"),
  whatsappStatus: () => get<{ running: boolean; connection_status: string; qr_code: string; has_qr: boolean; recent_messages: unknown[] }>("/api/gateway/whatsapp/status"),
  whatsappConnect: (body?: { session_path?: string }) =>
    post<{ status: string }>("/api/gateway/whatsapp/connect", body ?? {}),
  whatsappDisconnect: () => post<{ status: string }>("/api/gateway/whatsapp/disconnect"),
  whatsappSend: (body: { to: string; text: string }) =>
    post<{ sent: boolean }>("/api/gateway/whatsapp/send", body),
  createMission: (body: Record<string, unknown>) =>
    post<MissionType>("/api/missions", body),
  getMission: (id: string) => get<MissionType>(`/api/missions/${id}`),
  updateMission: (id: string, body: Record<string, unknown>) =>
    put<MissionType>(`/api/missions/${id}`, body),
  deleteMission: (id: string) => del<{ deleted: string }>(`/api/missions/${id}`),
  planMission: (id: string) => post<MissionPlanType>(`/api/missions/${id}/plan`),
  startMission: (id: string) => post<MissionType>(`/api/missions/${id}/start`),
  pauseMission: (id: string) => post<MissionType>(`/api/missions/${id}/pause`),
  cancelMission: (id: string) => post<MissionType>(`/api/missions/${id}/cancel`),

  // ── Exports for mission types ──
  createBackup: (body?: import("./desktop-types").BackupConfig) =>
    post<import("./desktop-types").BackupResult>("/api/desktop/backup", body ?? {}),
  listBackups: () =>
    get<import("./desktop-types").BackupResult[]>("/api/desktop/backups"),
  restorePoints: () =>
    get<{ points: Array<Record<string, unknown>> }>("/api/desktop/restore/points"),

  // Offline
  offlineState: () => get<{ state: string }>("/api/desktop/offline"),
  enableOffline: () => post<{ state: string }>("/api/desktop/offline/enable"),
  disableOffline: () => post<{ state: string }>("/api/desktop/offline/disable"),
  offlineEvents: () =>
    get<import("./desktop-types").OfflineEvent[]>("/api/desktop/offline/events"),
  syncOffline: () => post<{ synced: number }>("/api/desktop/offline/sync"),

  // First Run
  firstRunState: () =>
    get<import("./desktop-types").FirstRunState>("/api/desktop/first-run"),
  runFirstRunStep: (step: string) =>
    post<{ success: boolean }>("/api/desktop/first-run/step", { step }),

  // Hardening
  hardeningConfig: () =>
    get<import("./desktop-types").HardeningConfig>("/api/desktop/hardening/config"),
  updateHardeningConfig: (body: Partial<import("./desktop-types").HardeningConfig>) =>
    put<import("./desktop-types").HardeningConfig>("/api/desktop/hardening/config", body),
  validateStartup: () =>
    post<{ success: boolean; checks: Array<Record<string, unknown>> }>(
      "/api/desktop/hardening/validate",
    ),
  integrityCheck: () =>
    post<import("./desktop-types").IntegrityCheckResult>("/api/desktop/hardening/integrity"),
  runDiagnostics: () =>
    post<import("./desktop-types").SelfDiagnosticsReport>("/api/desktop/hardening/diagnostics"),
  checkMemory: () =>
    post<import("./desktop-types").MemoryLeakReport>("/api/desktop/hardening/memory"),
  checkThreads: () =>
    post<import("./desktop-types").ThreadReport>("/api/desktop/hardening/threads"),
  cleanupResources: () =>
    post<import("./desktop-types").CleanupResult>("/api/desktop/hardening/cleanup"),
  repairSystem: (targets?: string[]) =>
    post<import("./desktop-types").RepairResult>("/api/desktop/hardening/repair", targets ? { targets } : undefined),
  recoveryStatus: () =>
    get<{ in_recovery: boolean }>("/api/desktop/hardening/recovery"),
  enterRecovery: () =>
    post<{ success: boolean }>("/api/desktop/hardening/recovery/enter"),
  exitRecovery: () =>
    post<{ success: boolean }>("/api/desktop/hardening/recovery/exit"),
  recover: () =>
    post<import("./desktop-types").RepairResult>("/api/desktop/hardening/recover"),
  resourceUsage: () =>
    get<import("./desktop-types").ResourceUsageSummary>("/api/desktop/hardening/resources"),
  planShutdown: (force?: boolean) =>
    post<{ steps: Array<Record<string, unknown>> }>(
      "/api/desktop/hardening/shutdown", force ? { force } : undefined,
    ),

  // Menus
  listMenus: () => get<unknown[]>("/api/desktop/menus"),

  // Shortcuts
  listShortcuts: () =>
    get<import("./desktop-types").KeyboardShortcut[]>("/api/desktop/shortcuts"),

  // Command Palette
  commandPalette: () =>
    get<import("./desktop-types").CommandPaletteItem[]>("/api/desktop/command-palette"),

  // Search
  globalSearch: (query: string) =>
    get<import("./desktop-types").SearchResult[]>(
      `/api/desktop/search?q=${encodeURIComponent(query)}`,
    ),

  // ── Gateway / OmniRoute ──

  /** List models via the /v1 gateway */
  gatewayModels: () => get<{ object: string; data: import("./types").OpenAIModelType[] }>("/v1/models"),

  /** Get gateway health / status */
  gatewayHealth: () => get<import("./types").GatewayHealth>("/api/v1/gateway/health"),

  /** Get OmniRoute engine config */
  getRouteConfig: () => get<import("./types").GatewayConfig>("/api/v1/routing/config"),

  /** Update OmniRoute engine config */
  updateRouteConfig: (cfg: Partial<import("./types").GatewayConfig>) =>
    post<import("./types").GatewayConfig>("/api/v1/routing/config", cfg),

  /** List registered routing agents */
  listRouteAgents: () => get<import("./types").AgentRouteProfile[]>("/api/v1/routing/agents"),

  /** Compare routing strategies for a mission plan */
  compareStrategies: (missionId: string) =>
    get<Record<string, import("./types").MissionRoutePlanType>>(
      `/api/v1/routing/compare/${missionId}`,
    ),
  // ── AI Agent Binding Center API ──
  bindingDiscover: (mode: "surface" | "deep" = "surface") =>
    post<{ total_found: number; providers: Array<Record<string, unknown>> }>("/binding/discover", { mode }),
  bindingDeepScan: () =>
    post<{ total_found: number; sources_scanned: number; providers: Array<Record<string, unknown>> }>("/binding/deep-scan"),
  bindingManual: (body: Record<string, unknown>) =>
    post<{ id: string; provider: string; bound: boolean }>("/binding/manual", body),
  bindingValidate: (providerId: string) =>
    post<{ provider_id: string; healthy: boolean; details: Record<string, unknown> }>(`/binding/validate`, { provider_id: providerId }),
  bindingRepair: (providerId: string) =>
    post<{ provider_id: string; repaired: boolean; action_taken: string }>(`/binding/repair`, { provider_id: providerId }),
  bindingRebind: (providerId: string, newPath: string) =>
    post<{ provider_id: string; rebound: boolean }>(`/binding/rebind`, { provider_id: providerId, executable_path: newPath }),
  bindingUnbind: (providerId: string) =>
    post<{ provider_id: string; unbound: boolean }>(`/binding/unbind`, { provider_id: providerId }),
  bindingProviders: () =>
    get<Array<Record<string, unknown>>>("/binding/providers"),
  bindingLogs: (limit = 100) =>
    get<Array<{ timestamp: string; level: string; message: string }>>(`/binding/logs?limit=${limit}`),
  bindingHistory: () =>
    get<Array<{ id: string; event: string; timestamp: string; provider: string }>>("/binding/history"),
  // ── OmniRoute AI Networking Engine API ──
  omnirouteStatus: () => get<{ status: string; version: string; uptime_seconds: number; requests_processed: number }>("/omniroute/status"),
  omnirouteRoutes: () => get<Array<Record<string, unknown>>>("/omniroute/routes"),
  omnirouteProviders: () => get<Array<Record<string, unknown>>>("/omniroute/providers"),
  omniroutePolicies: () => get<Array<Record<string, unknown>>>("/omniroute/policies"),
  omnirouteBudget: () => get<{ today_cost: number; monthly_cost: number; saved_cost: number; local_ratio: number }>("/omniroute/budget"),
  omnirouteCompression: () => get<{ original_tokens: number; compressed_tokens: number; savings_pct: number }>("/omniroute/compression"),
  omnirouteFailover: () => get<Array<{ timestamp: string; from_provider: string; to_provider: string; reason: string }>>("/omniroute/failover"),
  omnirouteTelemetry: () => get<Record<string, number>>("/omniroute/telemetry"),
  omnirouteReload: () => post<{ reloaded: boolean }>("/omniroute/reload"),
  omnirouteRoute: (prompt: string, policy?: string) => post<{ target_provider: string; model: string; latency_ms: number }>("/omniroute/route", { prompt, policy }),
  omnirouteCompress: (text: string) => post<{ original_tokens: number; compressed_tokens: number; compressed_text: string }>("/omniroute/compress", { text }),
};
