// Typed REST client over the AgenticOS FastAPI control plane.
// No duplicated business logic — it only maps HTTP responses to domain types.

import type {
  AgentSpec,
  AuditEntry,
  CapabilityInfo,
  CostRecord,
  MemoryItem,
  MemoryScope,
  ModelInfo,
  ProviderConfig,
  ProviderHealthRecord,
  ProviderInfo,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { accept: "application/json" } });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

async function put<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PUT ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  health: () => get<{ status: string; bus: string }>("/healthz"),

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
};
