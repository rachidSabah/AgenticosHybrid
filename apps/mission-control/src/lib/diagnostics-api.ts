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

export interface DiagnosticsRuntime {
  hostname: string;
  os: string;
  pythonVersion: string;
  nodeVersion: string;
  cpu: string;
  ram: string;
  uptime: number;
  version: string;
  gitCommit: string;
  gitBranch: string;
  healthScore: number;
}

export interface DiagnosticsHealth {
  status: string;
  subsystems: Record<string, {
    status: string;
    latency: number;
    errors: number;
    warnings: number;
    restartCount: number;
  }>;
}

export interface DiagnosticsDiscovery {
  tools: {
    name: string;
    type: string;
    vendor: string;
    installed: boolean;
    running: boolean;
    version: string;
    pid?: number;
    status: string;
    health: string;
  }[];
}

export interface DiagnosticsEventBus {
  topics: {
    name: string;
    messages: number;
    subscribers: number;
  }[];
}

export interface DiagnosticsBrains {
  brains: {
    id: string;
    runtime: string;
    capabilities: string[];
    health: string;
    memory: string;
    cpu: string;
    tasks: number;
    heartbeat: string;
  }[];
}

export interface DiagnosticsAgents {
  agents: {
    id: string;
    status: string;
    tasks: number;
    mission: string;
    provider: string;
    latency: number;
    failures: number;
    retries: number;
  }[];
}

export interface DiagnosticsCapabilities {
  capabilities: {
    capability: string;
    provider: string;
    brain: string;
    priority: number;
    healthy: boolean;
    consumers: number;
  }[];
}

export interface DiagnosticsThreads {
  tasks: {
    id: string;
    name: string;
    status: string;
    duration: string;
  }[];
}

export interface DiagnosticsResources {
  cpuPercent: number;
  ramUsed: number;
  ramTotal: number;
  diskUsed: number;
  diskTotal: number;
  netIo: string;
  threadCount: number;
  processMemory: string;
}

export interface DiagnosticsQueues {
  queues: {
    name: string;
    depth: number;
    capacity: number;
  }[];
}

export interface DiagnosticsLogs {
  logs: {
    timestamp: string;
    level: string;
    subsystem: string;
    message: string;
  }[];
}

export interface DiagnosticsMCP {
  servers: {
    name: string;
    connected: boolean;
    capabilities: string[];
    ping: number;
    errors: number;
  }[];
}

export interface DiagnosticsProviders {
  providers: {
    name: string;
    status: string;
    health: string;
    rateLimits: string;
    circuitBreaker: string;
  }[];
}

export interface DiagnosticsAPIs {
  endpoints: {
    path: string;
    method: string;
    latency: number;
    calls: number;
    errors: number;
  }[];
}

export interface DiagnosticsSSEClients {
  clients: {
    id: string;
    connectedAt: string;
    ip: string;
  }[];
}

export interface DiagnosticsSummary {
  status: string;
}

export interface DiagnosticsSelfTestResult {
  results: {
    name: string;
    status: "PASS" | "WARNING" | "FAIL";
    message: string;
  }[];
}

export interface DiagnosticsReport {
  generatedAt: string;
}

export async function fetchRuntime(): Promise<DiagnosticsRuntime> {
  return get<DiagnosticsRuntime>("/api/diagnostics/runtime", {} as DiagnosticsRuntime);
}

export async function fetchHealth(): Promise<DiagnosticsHealth> {
  return get<DiagnosticsHealth>("/api/diagnostics/health", { status: "offline", subsystems: {} });
}

export async function fetchDiscovery(): Promise<DiagnosticsDiscovery> {
  return get<DiagnosticsDiscovery>("/api/diagnostics/discovery", { tools: [] });
}

export async function fetchBrains(): Promise<DiagnosticsBrains> {
  return get<DiagnosticsBrains>("/api/diagnostics/brains", { brains: [] });
}

export async function fetchAgents(): Promise<DiagnosticsAgents> {
  return get<DiagnosticsAgents>("/api/diagnostics/agents", { agents: [] });
}

export async function fetchCapabilities(): Promise<DiagnosticsCapabilities> {
  return get<DiagnosticsCapabilities>("/api/diagnostics/capabilities", { capabilities: [] });
}

export async function fetchEventBus(): Promise<DiagnosticsEventBus> {
  return get<DiagnosticsEventBus>("/api/diagnostics/eventbus", { topics: [] });
}

export async function fetchSSE(): Promise<DiagnosticsSSEClients> {
  return get<DiagnosticsSSEClients>("/api/diagnostics/sse-clients", { clients: [] });
}

export async function fetchAPIs(): Promise<DiagnosticsAPIs> {
  return get<DiagnosticsAPIs>("/api/diagnostics/apis", { endpoints: [] });
}

export async function fetchProviders(): Promise<DiagnosticsProviders> {
  return get<DiagnosticsProviders>("/api/diagnostics/providers", { providers: [] });
}

export async function fetchMCP(): Promise<DiagnosticsMCP> {
  return get<DiagnosticsMCP>("/api/diagnostics/mcp", { servers: [] });
}

export async function fetchQueues(): Promise<DiagnosticsQueues> {
  return get<DiagnosticsQueues>("/api/diagnostics/queues", { queues: [] });
}

export async function fetchThreads(): Promise<DiagnosticsThreads> {
  return get<DiagnosticsThreads>("/api/diagnostics/threads", { tasks: [] });
}

export async function fetchResources(): Promise<DiagnosticsResources> {
  return get<DiagnosticsResources>("/api/diagnostics/resources", {} as DiagnosticsResources);
}

export async function fetchLogs(): Promise<DiagnosticsLogs> {
  return get<DiagnosticsLogs>("/api/diagnostics/logs", { logs: [] });
}

export async function runSelfTest(): Promise<DiagnosticsSelfTestResult> {
  return post<DiagnosticsSelfTestResult>("/api/diagnostics/self-test", undefined, { results: [] });
}

export function fetchDiagnosticsSSE(onEvent: (event: any) => void, onError: (err: any) => void): () => void {
  const source = new EventSource(`${BASE}/api/diagnostics/events`);
  
  source.addEventListener("connected", (event) => {
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
  };

  return () => {
    source.close();
  };
}
