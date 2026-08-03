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
  status: "pending" | "planned" | "dispatched" | "assigned" | "in_progress" | "running" | "completed" | "failed" | "recovered";
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

// Extended MCP types for Phase 4 Milestone 3

export interface MCPSession {
  id: string;
  server_id: string;
  transport: string;
  status: "active" | "idle" | "expired" | "closed";
  capabilities: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  metadata: Record<string, unknown>;
}

export interface MCPTelemetrySummary {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  error_rate: number;
  avg_latency_ms: number;
  active_servers: number;
  latency_distribution: {
    p50: number;
    p90: number;
    p95: number;
    p99: number;
    min: number;
    max: number;
  };
}

export interface MCPServerMetrics {
  server_id: string;
  server_name: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  total_latency_ms: number;
  avg_latency_ms: number;
  tool_invocations: Record<string, number>;
  resource_reads: number;
  prompt_calls: number;
}

export interface MCPResourceSubscription {
  id: string;
  server_id: string;
  resource_uri: string;
  created_at: string;
}

export interface MCPRegistryStats {
  total_servers: number;
  running: number;
  stopped: number;
  failed: number;
  enabled: number;
}

export interface MCPSessionStats {
  total: number;
  active: number;
  idle: number;
  expired: number;
  closed: number;
  expiring_soon: number;
  tracked_servers: number;
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

// ── MCP Version Management ──

export interface MCPVersionInfo {
  server_id: string;
  protocol_version: string | null;
  server_version: string | null;
  sdk_version: string | null;
  discovered_at: string | null;
  last_updated: string | null;
}

export interface MCPVersionDetail extends MCPVersionInfo {
  compatible: boolean;
}

export interface MCPVersionMatrix {
  supported_versions: string[];
  recommended_version: string;
  servers: Record<string, { protocol_version: string | null; server_version: string | null; compatible: boolean }>;
}

// ── MCP Capabilities ──

export interface MCPCapabilityView {
  server_id: string;
  tools_count: number;
  resources_count: number;
  prompts_count: number;
  sampling: boolean;
  roots: boolean;
  streaming: boolean;
  session_management: boolean;
  capability_negotiation: boolean;
  supported: string[];
}

export interface MCPNegotiateRequest {
  server_id: string;
  capabilities: string[];
}

export interface MCPNegotiateResult {
  server_id: string;
  agreed: string[];
  rejected: string[];
}

// ── MCP Registry Search ──

export interface MCPRegisteredTool {
  name: string;
  server_id: string;
  description: string;
  categories: string[];
  tags: string[];
  enabled: boolean;
}

export interface MCPRegisteredResource {
  uri: string;
  server_id: string;
  name: string;
  description: string;
  mime_type: string;
  enabled: boolean;
}

export interface MCPRegisteredPrompt {
  name: string;
  server_id: string;
  description: string;
  tags: string[];
  enabled: boolean;
}

// ── Swarm Orchestration (Phase 4, M4) ──

export interface SwarmProfile {
  name: string;
  topology: string;
  max_agents: number;
  timeout_seconds: number;
  tags: string[];
}

export interface SwarmSummary {
  id: string;
  name: string;
  topology: string;
  agent_count: number;
  status: string;
  created_at: string;
}

export interface SwarmDetail extends SwarmSummary {
  leader_id: string | null;
  goal: string | null;
  tags: string[];
  state: Record<string, string>;
}

export interface SwarmAgentInfo {
  agent_id: string;
  name: string;
  role: string;
  status: string;
  capabilities: string[];
  health: string;
}

export interface SwarmTaskSummary {
  id: string;
  goal: string;
  status: string;
  agent_id: string | null;
  pattern: string;
  created_at: string;
}

export interface SwarmPlanSummary {
  id: string;
  goal: string;
  task_count: number;
  status: string;
  created_at: string;
}

export interface SwarmConsensusSummary {
  round_id: string;
  topic: string;
  status: string;
  votes_cast: number;
  agents: number;
}

export interface SwarmMetricsSummary {
  total_swarms: number;
  active_swarms: number;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  total_cost: number;
  avg_latency_ms: number;
  agents_online: number;
}

// ── Mission Orchestrator types ──

export interface MissionType {
  id: string;
  title: string;
  description: string;
  prompt: string;
  objectives: string[];
  deliverables: string[];
  priority: string;
  execution_mode: string;
  constraints: string[];
  deadline?: string | null;
  tags: string[];
  attachments: MissionAttachment[];
  status: string;
  plan?: MissionPlanType | null;
  created_at: string;
  updated_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
}

export interface MissionAttachment {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  path: string;
  description: string;
}

export interface MissionTaskType {
  id: string;
  mission_id: string;
  title: string;
  description: string;
  status: string;
  assigned_role: string | null;
  assigned_provider: string;
  dependencies: string[];
  estimated_minutes: number;
  output: string;
  error: string;
  started_at: string | null;
  completed_at: string | null;
  attachments: string[];
}

export interface MissionPlanType {
  id: string;
  mission_id: string;
  summary: string;
  complexity: string;
  estimated_total_minutes: number;
  risk_level: string;
  tasks: MissionTaskType[];
  task_count: number;
}

// ── Gateway types ──────────────────────────────────────────────────────────

export type GatewayStrategy =
  | "fastest"
  | "cheapest"
  | "best_capability"
  | "balanced"
  | "reliability_first"
  | "latency_first"
  | "custom";

export interface GatewayConfig {
  default_strategy: GatewayStrategy;
  cost_weight: number;
  speed_weight: number;
  capability_weight: number;
  reliability_weight: number;
  max_fallback_depth: number;
  enable_parallel_routing: boolean;
  min_confidence_for_auto_route: number;
}

export interface AgentRouteProfile {
  agent_id: string;
  agent_name: string;
  provider: string;
  capabilities: Record<string, number>;
  cost_per_1k: number;
  latency_ms: number;
  reliability: number;
}

export interface TaskRouteAssignmentType {
  task_id: string;
  task_title: string;
  assigned_agent_id: string;
  assigned_agent_name: string;
  provider: string;
  strategy_used: GatewayStrategy;
  composite_score: number;
  cost_score: number;
  speed_score: number;
  capability_score: number;
  reliability_score: number;
  estimated_cost: number;
  estimated_duration_ms: number;
  status: string;
  fallback_agent_id: string | null;
  reasoning: string;
}

export interface MissionRoutePlanType {
  id: string;
  mission_id: string;
  strategy: GatewayStrategy;
  assignments: TaskRouteAssignmentType[];
  total_estimated_cost: number;
  total_estimated_duration_ms: number;
  average_composite_score: number;
  provider_usage: Record<string, number>;
  created_at: string;
}

export interface OpenAIModelType {
  id: string;
  object: string;
  created: number;
  owned_by: string;
}

export interface GatewayHealth {
  status: "active" | "inactive" | "error";
  uptime_seconds: number;
  requests_served: number;
  active_providers: number;
  active_models: number;
  last_request_at: string | null;
}

// ── Workspace ──
export interface WorkspaceEntry {
  name: string;
  path: string;
  type: "directory" | "file";
  size: number;
  children?: WorkspaceEntry[];
}

// ── Execution Log ──
export interface ExecutionRecord {
  execution_id: string;
  mission_id: string;
  task_id: string;
  agent_id: string;
  provider: string;
  runtime: string;
  strategy: string;
  status: "running" | "completed" | "failed" | "retried" | "abandoned";
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  retry_count: number;
  error: string;
  command: string;
  prompt_preview: string;
}

export interface ExecutionStats {
  total: number;
  completed?: number;
  failed?: number;
  running?: number;
  retried?: number;
  abandoned?: number;
  [key: string]: number | undefined;
}

// ── Worktree ──
export interface WorktreeEntry {
  branch: string;
  path: string;
  agent_id: string;
  task_id: string;
  status: "active" | "dirty" | "merged" | "removed";
  base_branch: string;
  created_at: string | null;
}

export interface WorktreeDiffFile {
  file: string;
  status: "added" | "modified" | "deleted" | "renamed";
  additions: number;
  deletions: number;
  diff: string;
}
