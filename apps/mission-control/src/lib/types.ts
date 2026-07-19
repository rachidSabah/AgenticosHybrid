// Frontend domain types mirroring the AgenticOS backend ports exactly.
// Source of truth: src/agentic_os/domain/** — no business logic here.

export type Topic =
  | "task.created"
  | "task.planned"
  | "task.dispatched"
  | "task.assigned"
  | "agent.started"
  | "agent.heartbeat"
  | "agent.completed"
  | "agent.failed"
  | "agent.recovered"
  | "health.check"
  | "health.degraded"
  | "recovery.triggered"
  | "dashboard.event"
  | "provider.health"
  | "provider.registered"
  | "provider.failed"
  | "provider.failover"
  | "cost.recorded"
  | "memory.written"
  | "memory.evicted"
  | "agent.composed"
  | "approval.requested"
  | "approval.decided"
  | "audit.event"
  | "tool.denied";

export interface EventEnvelope {
  id: string;
  type: string;
  source: string;
  topic: Topic | string;
  timestamp: string; // ISO-8601 from backend datetime
  payload: Record<string, unknown>;
}

export interface ProviderInfo {
  name: string;
  kind: string;
  supports_streaming?: boolean;
  supports_tools?: boolean;
}

export interface ProviderConfig {
  name: string;
  kind: string;
  base_url?: string;
  default_model?: string;
  api_key_ref?: string;
  enabled?: boolean;
  rate_limit?: number;
  notes?: string;
}

export type ProviderHealthStatus = "unknown" | "healthy" | "degraded" | "down";

// NOTE: backend field is `provider` (not `name`) — kept as `provider` here.
export interface ProviderHealthRecord {
  provider: string;
  status: ProviderHealthStatus;
  latency_ms: number;
  last_checked?: string;
  error?: string | null;
}

export interface ModelInfo {
  id: string;
  provider: string;
  context_window?: number;
  input_cost_per_1k?: number;
  output_cost_per_1k?: number;
  capabilities?: string[];
}

export interface CostRecord {
  id?: string;
  provider: string;
  model?: string;
  task_id?: string;
  input_tokens?: number;
  output_tokens?: number;
  cost: number;
  at?: string;
}

export interface CapabilityInfo {
  name: string;
  description: string;
  requires_approval: boolean;
}

export interface AgentSpec {
  id?: string;
  name: string;
  capabilities: string[];
  provider: string;
  model: string;
  system_prompt?: string;
  requires_approval?: boolean;
}

export type MemoryScope =
  | "working"
  | "conversation"
  | "project"
  | "shared"
  | "long_term";

export interface MemoryItem {
  id: string;
  scope: MemoryScope;
  key: string;
  value: string;
  embedding?: number[];
  agent_id?: string;
  project_id?: string;
  created_at?: string;
  expires_at?: string | null;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  principal: string;
  action: string;
  target: string;
  outcome: string;
  meta?: Record<string, unknown>;
}

export interface AgentNode {
  id: string;
  role: string;
  provider?: string;
  status: "idle" | "running" | "completed" | "failed" | "recovered" | "recovering";
  health: "healthy" | "degraded" | "down" | "unknown";
  current_task?: string;
  capabilities: string[];
  supervisor?: string;
}

export interface TaskNode {
  id: string;
  title: string;
  role: string;
  status: "pending" | "planned" | "dispatched" | "assigned" | "in_progress" | "completed" | "failed" | "recovered";
}

// ── Discovery types (Phase 4, M2) ──

export interface DiscoveryProviderInfo {
  name: string;
  provider_type: string;
  enabled: boolean;
  interval_seconds: number;
  timeout_seconds: number;
  confidence_override: number | null;
}

export interface DiscoveryCacheEntry {
  key: string;
  provider_name: string;
  confidence: number;
  discovered_at: string;
  expires_at: string;
  hit_count: number;
  expired: boolean;
}

export interface DiscoveryHistoryEntry {
  id: string;
  profile_name: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number;
  providers_run: number;
  providers_failed: number;
  engines_found: number;
  errors: string[];
}

export interface DiscoveryStats {
  total_scans: number;
  total_engines_found: number;
  avg_duration_ms: number;
  failure_rate: number;
  cache_hit_rate: number;
  active_providers: number;
}

export interface DiscoveryProfileEntry {
  name: string;
  description: string;
  provider_configs: DiscoveryProviderConfig[];
  auto_register: boolean;
  validate_after_discovery: boolean;
  interval_seconds: number;
  tags: string[];
}

export interface DiscoveryProviderConfig {
  name: string;
  provider_type: string;
  enabled: boolean;
  interval_seconds: number;
}

export interface DiscoveryValidationEntry {
  engine_id: string;
  engine_name: string;
  valid: boolean;
  errors: string[];
  warnings: string[];
  validated_at: string;
}

export interface HotReloadStatus {
  running: boolean;
}

// ── MCP types (Phase 4, M3) ──

export interface MCPServerConfig {
  id: string;
  name: string;
  transport: string;
  command?: string;
  args: string[];
  env: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  server_type?: string;
  description?: string;
  enabled: boolean;
  sandbox?: boolean;
  sandbox_config?: Record<string, unknown>;
  health_check_interval_seconds: number;
  health_check_timeout_seconds: number;
  version?: string;
  author?: string;
  homepage?: string;
  repository?: string;
  tags: string[];
  created_by?: string;
}

export interface MCPServerDetail {
  config: MCPServerConfig;
  status: MCPStatus;
  health: MCPHealth;
  tools: MCPTool[];
  resources: MCPResource[];
  prompts: MCPPrompt[];
  restart_count: number;
  error?: string;
  process_id?: number;
  last_health_check?: string;
  last_error_at?: string;
}

export type MCPStatus = "stopped" | "starting" | "running" | "stopping" | "failed";
export type MCPHealth = "healthy" | "degraded" | "unhealthy" | "unknown";

export interface MCPTool {
  name: string;
  description: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
}

export interface MCPToolResult {
  content: string;
  is_error: boolean;
}

export interface MCPPermissionMapping {
  tool_name: string;
  capability: string;
  description?: string;
}

export interface MCPResource {
  uri: string;
  name: string;
  description?: string;
  mime_type?: string;
}

export interface MCPPrompt {
  name: string;
  description: string;
  arguments?: Record<string, unknown>;
}

export interface MCPHealthSummary {
  total: number;
  running: number;
  servers: Record<string, { name: string; status: MCPStatus; health: MCPHealth; tools: number }>;
}

export interface MCPSessionMap {
  sessions: Record<string, string>;
  total: number;
}

export interface SystemMetrics {
  tasks: number;
  agents: number;
  providers: number;
  pipelines: number;
  tokens: number;
  cost: number;
  latency: number;
  errors: number;
}
