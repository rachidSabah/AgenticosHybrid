// Typed API client for all diagnostics endpoints
// BASE URL = same as api.ts

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
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return (await res.json()) as T;
  } catch (e) {
    if (fallback !== undefined) return fallback;
    throw e;
  }
}

async function post<T>(path: string, body?: unknown, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
    return (await res.json()) as T;
  } catch (e) {
    if (fallback !== undefined) return fallback;
    throw e;
  }
}

// ── Runtime & Health Types ──
// Backend returns: { hostname, os, os_version, python_version, cpu_count, cpu_percent, ... }
export interface DiagnosticsRuntime {
  hostname: string;
  os: string;
  os_version: string;
  python_version: string;
  cpu_count: number;
  cpu_percent: number;
  ram_total: number;
  ram_used: number;
  ram_percent: number;
  uptime_seconds: number;
  process_pid: number;
  process_memory_mb: number;
  gc_counts: number[];
  asyncio_tasks_count: number;
  version: string;
  git_commit: string;
  git_branch: string;
  build_timestamp: string;
  environment: string;
  workspace: string;
  platform_services: Record<string, boolean>;
}

// Backend health: { <subsystem>: { healthy, latency_ms, errors, warnings, restart_count, status, available }, _meta: {...} }
export interface DiagnosticsHealthSubsystem {
  healthy: boolean;
  latency_ms: number;
  errors: number;
  warnings: number;
  restart_count: number;
  status: string;
  available: boolean;
}

export interface DiagnosticsHealth {
  kernel: DiagnosticsHealthSubsystem;
  discovery: DiagnosticsHealthSubsystem;
  brain_registry: DiagnosticsHealthSubsystem;
  capability_registry: DiagnosticsHealthSubsystem;
  provider_registry: DiagnosticsHealthSubsystem;
  scheduler: DiagnosticsHealthSubsystem;
  executor: DiagnosticsHealthSubsystem;
  aggregation: DiagnosticsHealthSubsystem;
  learning: DiagnosticsHealthSubsystem;
  budget: DiagnosticsHealthSubsystem;
  rate_limiter: DiagnosticsHealthSubsystem;
  router: DiagnosticsHealthSubsystem;
  api: DiagnosticsHealthSubsystem;
  event_bus: DiagnosticsHealthSubsystem;
  sse: DiagnosticsHealthSubsystem;
  mission_control: DiagnosticsHealthSubsystem;
  mcp: DiagnosticsHealthSubsystem;
  memory: DiagnosticsHealthSubsystem;
  security: DiagnosticsHealthSubsystem;
  _meta: {
    health_score: number;
    healthy_count: number;
    total_subsystems: number;
    checked_at: string;
  };
}

// ── Discovery ──
// Backend: { providers: [...], scanner_stats, total_discovered, total_running, total_healthy, discovery_framework_available, local_discovery_available }
export interface DiagnosticsDiscoveryProvider {
  name: string;
  type: string;
  vendor: string;
  installed: boolean;
  running: boolean;
  version: string;
  pid: number | null;
  path: string;
  executable: string;
  last_seen: string;
  status: string;
  health: string;
  auto_bound: boolean;
  registration_state: string;
  errors: string[];
  support_windows: boolean;
  support_linux: boolean;
  support_macos: boolean;
}

export interface DiagnosticsDiscovery {
  providers: DiagnosticsDiscoveryProvider[];
  scanner_stats: Record<string, unknown>;
  total_discovered: number;
  total_running: number;
  total_healthy: number;
  discovery_framework_available: boolean;
  local_discovery_available: boolean;
}

// ── Brains ──
// Backend: { brains: [...], total_count, healthy_count, stats_available, health_monitor_available }
export interface DiagnosticsBrain {
  id: string;
  display_name: string;
  runtime: string;
  capabilities: string[];
  health: number;
  memory_mb: number;
  cpu_percent: number;
  task_count: number;
  current_model: string;
  connections: number;
  heartbeat: number;
  last_event: string;
  registration_source: string;
  status: string;
  latency: number;
}

export interface DiagnosticsBrains {
  brains: DiagnosticsBrain[];
  total_count: number;
  healthy_count: number;
  stats_available: boolean;
  health_monitor_available: boolean;
}

// ── Agents ──
// Backend: { agents: [...], total_count }
export interface DiagnosticsAgent {
  id: string;
  name: string;
  status: string;
  task_count: number;
  mission: string;
  workflow: string;
  execution_mode: string;
  provider: string;
  latency_ms: number;
  failures: number;
  retries: number;
  queue_depth: number;
  lifecycle: string;
}

export interface DiagnosticsAgents {
  agents: DiagnosticsAgent[];
  total_count: number;
}

// ── Capabilities ──
// Backend: { capabilities: [...], total_count }
export interface DiagnosticsCapability {
  name: string;
  provider: string;
  brain: string;
  priority: number;
  healthy: boolean;
  consumers: number;
  last_updated: string;
  dependencies: string[];
}

export interface DiagnosticsCapabilities {
  capabilities: DiagnosticsCapability[];
  total_count: number;
}

// ── Event Bus ──
// Backend: { topics: [...], total_topics, total_messages, bus_type, bus_available }
export interface DiagnosticsEventBusTopic {
  topic: string;
  publisher: string;
  subscriber_count: number;
  messages_per_sec: number;
  dropped: number;
  errors: number;
  avg_latency_ms: number;
  payload_size_bytes: number;
}

export interface DiagnosticsEventBus {
  topics: DiagnosticsEventBusTopic[];
  total_topics: number;
  total_messages: number;
  bus_type: string;
  bus_available: boolean;
}

// ── SSE Clients ──
// Backend: { clients: [...], total_count }
export interface DiagnosticsSSEClient {
  client_id: string;
  connected_at: string;
  duration_seconds: number;
  messages_per_sec: number;
  reconnects: number;
  dropped_frames: number;
  heartbeat: string;
  last_message: string;
  queue_size: number;
}

export interface DiagnosticsSSEClients {
  clients: DiagnosticsSSEClient[];
  total_count: number;
}

// ── APIs ──
// Backend: { endpoints: [...] }
export interface DiagnosticsAPIEndpoint {
  path: string;
  method: string;
  latency: number;
  calls: number;
  errors: number;
}

export interface DiagnosticsAPIs {
  endpoints: DiagnosticsAPIEndpoint[];
}

// ── Providers ──
// Backend: { providers: [...], count }
export interface DiagnosticsProvider {
  name: string;
  status: string;
  health: number;
  latency_ms: number;
  brain_id: string;
  bound: boolean;
}

export interface DiagnosticsProviders {
  providers: DiagnosticsProvider[];
  count: number;
}

// ── MCP ──
// Backend: { servers: [...] }
export interface DiagnosticsMCPServer {
  name: string;
  connected: boolean;
  capabilities: string[];
  ping: number;
  errors: number;
}

export interface DiagnosticsMCP {
  servers: DiagnosticsMCPServer[];
}

// ── Queues ──
// Backend: { queues: [...], total_queues }
export interface DiagnosticsQueue {
  name: string;
  depth: number;
  oldest_item_age_seconds: number;
  newest_item_age_seconds: number;
  wait_time_seconds: number;
  blocked: boolean;
  dead_letter_count: number;
}

export interface DiagnosticsQueues {
  queues: DiagnosticsQueue[];
  total_queues: number;
}

// ── Threads ──
// Backend: { tasks: [...], total_count, running_count, cancelled_count }
export interface DiagnosticsThread {
  id: string;
  name: string;
  status: string;
  duration_seconds: number;
  owner: string;
  coroutine: string;
  cancelled: boolean;
  waiting: boolean;
  blocked: boolean;
}

export interface DiagnosticsThreads {
  tasks: DiagnosticsThread[];
  total_count: number;
  running_count: number;
  cancelled_count: number;
}

// ── Resources ──
// Backend: { cpu_percent, cpu_per_core, ram_total, ram_used, ram_percent, disk_total, disk_used, disk_percent, net_bytes_sent, net_bytes_recv, thread_count, handle_count, open_files_count, gc_gen0..2, process_rss_mb, process_vms_mb, snapshot_at }
export interface DiagnosticsResources {
  cpu_percent: number;
  cpu_per_core: number[];
  ram_total: number;
  ram_used: number;
  ram_percent: number;
  disk_total: number;
  disk_used: number;
  disk_percent: number;
  net_bytes_sent: number;
  net_bytes_recv: number;
  thread_count: number;
  handle_count: number;
  open_files_count: number;
  gc_gen0: number;
  gc_gen1: number;
  gc_gen2: number;
  process_rss_mb: number;
  process_vms_mb: number;
  snapshot_at: string;
}

// ── Logs ──
// Backend: { logs: [...], total_count }
export interface DiagnosticsLog {
  timestamp: string;
  level: string;
  subsystem: string;
  message: string;
}

export interface DiagnosticsLogs {
  logs: DiagnosticsLog[];
  total_count: number;
}

// ── Self Test ──
export interface DiagnosticsSelfTestResult {
  results: {
    name: string;
    status: "PASS" | "WARNING" | "FAIL";
    message: string;
  }[];
}

// ── Report ──
export interface DiagnosticsReport {
  generatedAt: string;
}

// ── API functions ──

export async function fetchRuntime(): Promise<DiagnosticsRuntime> {
  return get<DiagnosticsRuntime>("/api/diagnostics/runtime", {} as DiagnosticsRuntime);
}

export async function fetchHealth(): Promise<DiagnosticsHealth> {
  return get<DiagnosticsHealth>("/api/diagnostics/health", {} as DiagnosticsHealth);
}

export async function fetchDiscovery(): Promise<DiagnosticsDiscovery> {
  return get<DiagnosticsDiscovery>("/api/diagnostics/discovery", {
    providers: [],
    scanner_stats: {},
    total_discovered: 0,
    total_running: 0,
    total_healthy: 0,
    discovery_framework_available: false,
    local_discovery_available: false,
  });
}

export async function fetchBrains(): Promise<DiagnosticsBrains> {
  return get<DiagnosticsBrains>("/api/diagnostics/brains", {
    brains: [],
    total_count: 0,
    healthy_count: 0,
    stats_available: false,
    health_monitor_available: false,
  });
}

export async function fetchAgents(): Promise<DiagnosticsAgents> {
  return get<DiagnosticsAgents>("/api/diagnostics/agents", { agents: [], total_count: 0 });
}

export async function fetchCapabilities(): Promise<DiagnosticsCapabilities> {
  return get<DiagnosticsCapabilities>("/api/diagnostics/capabilities", { capabilities: [], total_count: 0 });
}

export async function fetchEventBus(): Promise<DiagnosticsEventBus> {
  return get<DiagnosticsEventBus>("/api/diagnostics/eventbus", {
    topics: [],
    total_topics: 0,
    total_messages: 0,
    bus_type: "unknown",
    bus_available: false,
  });
}

export async function fetchSSE(): Promise<DiagnosticsSSEClients> {
  return get<DiagnosticsSSEClients>("/api/diagnostics/sse-clients", { clients: [], total_count: 0 });
}

export async function fetchAPIs(): Promise<DiagnosticsAPIs> {
  return get<DiagnosticsAPIs>("/api/diagnostics/apis", { endpoints: [] });
}

export async function fetchProviders(): Promise<DiagnosticsProviders> {
  return get<DiagnosticsProviders>("/api/diagnostics/providers", { providers: [], count: 0 });
}

export async function fetchMCP(): Promise<DiagnosticsMCP> {
  return get<DiagnosticsMCP>("/api/diagnostics/mcp", { servers: [] });
}

export async function fetchQueues(): Promise<DiagnosticsQueues> {
  return get<DiagnosticsQueues>("/api/diagnostics/queues", { queues: [], total_queues: 0 });
}

export async function fetchThreads(): Promise<DiagnosticsThreads> {
  return get<DiagnosticsThreads>("/api/diagnostics/threads", {
    tasks: [],
    total_count: 0,
    running_count: 0,
    cancelled_count: 0,
  });
}

export async function fetchResources(): Promise<DiagnosticsResources> {
  return get<DiagnosticsResources>("/api/diagnostics/resources", {} as DiagnosticsResources);
}

export async function fetchLogs(limit = 200): Promise<DiagnosticsLogs> {
  return get<DiagnosticsLogs>(`/api/diagnostics/logs?limit=${limit}`, { logs: [], total_count: 0 });
}

export async function runSelfTest(): Promise<DiagnosticsSelfTestResult> {
  return post<DiagnosticsSelfTestResult>("/api/diagnostics/self-test", undefined, { results: [] });
}

export function fetchDiagnosticsSSE(onEvent: (event: any) => void, onError: (err: any) => void): () => void {
  let source: EventSource | null = null;
  let isClosed = false;
  let retryTimer: NodeJS.Timeout | null = null;

  function connect() {
    if (isClosed) return;
    try {
      source = new EventSource(`${BASE}/api/diagnostics/events`);

      source.onopen = () => {
        onEvent({ type: "connected" });
      };

      source.addEventListener("connected", () => {
        onEvent({ type: "connected" });
      });

      source.addEventListener("DIAGNOSTICS_UPDATED", (event) => {
        try {
          const data = JSON.parse(event.data);
          onEvent(data);
        } catch (e) {
          console.error("Failed to parse SSE event", e);
        }
      });

      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          onEvent(data);
        } catch (e) {
          console.error("Failed to parse SSE event", e);
        }
      };

      source.onerror = (err) => {
        onError(err);
        if (source && source.readyState === EventSource.CLOSED) {
          source.close();
          source = null;
          if (!isClosed && !retryTimer) {
            retryTimer = setTimeout(() => {
              retryTimer = null;
              connect();
            }, 3000);
          }
        }
      };
    } catch (e) {
      onError(e);
    }
  }

  connect();

  return () => {
    isClosed = true;
    if (retryTimer) clearTimeout(retryTimer);
    if (source) {
      source.close();
      source = null;
    }
  };
}
