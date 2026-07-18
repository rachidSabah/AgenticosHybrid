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
};
