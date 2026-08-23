"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { safeFixed, safeNum, safeStr } from "@/lib/safe";
import { clsx } from "clsx";
import {
  Play,
  Square,
  RefreshCw,
  Terminal,
  Activity,
  Server,
  X,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Search,
  Filter,
  RotateCw,
  Skull,
  Clock,
  Cpu,
  MemoryStick,
  DollarSign,
  Zap,
  Loader2,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────

interface RuntimeCapability {
  name: string;
  version: string | null;
  enabled: boolean;
}

interface RuntimeMetrics {
  cpu_percent: number;
  memory_mb: number;
  threads: number;
  tokens_used: number;
  cost: number;
  latency_ms: number;
  queue_depth: number;
  active_tasks: number;
  restart_count: number;
  crash_count: number;
  uptime_seconds: number;
}

interface RuntimeLog {
  timestamp: string;
  stream: string;
  text: string;
  level: string;
}

interface Runtime {
  id: string;
  name: string;
  brain_id: string | null;
  provider: string;
  type: string;
  version: string | null;
  pid: number | null;
  status: string;
  health: string;
  started_at: string | null;
  uptime: number;
  cpu: number;
  memory: number;
  threads: number;
  command: string;
  arguments: string[];
  working_directory: string | null;
  environment: Record<string, string>;
  terminal: string | null;
  session_id: string | null;
  active_session: Record<string, unknown> | null;
  restart_count: number;
  crash_count: number;
  last_error: string | null;
  last_exit_code: number | null;
  last_seen: string | null;
  heartbeat: string | null;
  capabilities: RuntimeCapability[];
  supported_models: string[];
  active_tasks: number;
  queue_depth: number;
  tokens_used: number;
  cost: number;
  latency: number;
  streaming: boolean;
  binary_path: string | null;
  executable: string | null;
  executable_path: string | null;
  source: string;
  discovered: boolean;
  metadata: Record<string, unknown>;
}

interface RuntimeListResponse extends Array<Runtime> {}

interface ExecuteResponse {
  output: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

// Resolve the backend base URL. Mirrors lib/api.ts resolveBase() so the
// dashboard honours NEXT_PUBLIC_API_BASE (e.g. when the backend runs on a
// non-default port such as 8080) instead of hardcoding localhost:8000.
function resolveRuntimeApiBase(): string {
  if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).__TAURI__) {
    return "http://127.0.0.1:8000";
  }
  return process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8000";
}

const API_BASE = resolveRuntimeApiBase();

const STATUS_COLORS: Record<string, string> = {
  discovered: "bg-gray-500 text-gray-100",
  registered: "bg-blue-600 text-blue-100",
  initializing: "bg-blue-500 text-blue-100",
  starting: "bg-yellow-500 text-yellow-100",
  ready: "bg-green-600 text-green-100",
  busy: "bg-orange-500 text-orange-100",
  idle: "bg-teal-500 text-teal-100",
  streaming: "bg-cyan-500 text-cyan-100",
  waiting: "bg-amber-500 text-amber-100",
  stopping: "bg-yellow-600 text-yellow-100",
  stopped: "bg-red-600 text-red-100",
  crashed: "bg-red-700 text-red-100",
  failed: "bg-red-900 text-red-100",
  restarting: "bg-yellow-500 text-yellow-100",
  updating: "bg-purple-500 text-purple-100",
  disconnected: "bg-gray-600 text-gray-100",
  unknown: "bg-gray-500 text-gray-100",
};

const TYPE_COLORS: Record<string, string> = {
  claude_code: "bg-violet-500/20 text-violet-300",
  opencode: "bg-emerald-500/20 text-emerald-300",
  gemini_cli: "bg-blue-500/20 text-blue-300",
  hermes: "bg-amber-500/20 text-amber-300",
  custom: "bg-gray-500/20 text-gray-300",
  wsl: "bg-cyan-500/20 text-cyan-300",
  generic: "bg-slate-500/20 text-slate-300",
};

const HEALTH_COLORS: Record<string, string> = {
  healthy: "bg-green-500",
  degraded: "bg-yellow-500",
  unhealthy: "bg-red-500",
  unknown: "bg-gray-500",
  starting: "bg-blue-400",
  stopped: "bg-gray-400",
};

const LOG_LEVEL_COLORS: Record<string, string> = {
  info: "text-blue-400",
  warn: "text-yellow-400",
  warning: "text-yellow-400",
  error: "text-red-400",
  debug: "text-gray-500",
};

const LOG_LEVEL_BG: Record<string, string> = {
  info: "bg-blue-500/10",
  warn: "bg-yellow-500/10",
  warning: "bg-yellow-500/10",
  error: "bg-red-500/10",
  debug: "bg-gray-500/10",
};

// ── Helpers ────────────────────────────────────────────────────────────────

function formatUptime(seconds: number): string {
  const s = safeNum(seconds);
  if (s < 0) return "—";
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const sec = Math.round(s % 60);
    return `${m}m ${sec}s`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  try {
    const ms = Date.now() - new Date(iso).getTime();
    const sec = Math.floor(ms / 1000);
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
    return `${Math.floor(sec / 86400)}d ago`;
  } catch {
    return iso;
  }
}

// ── Status Badge ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status.toLowerCase()] ?? STATUS_COLORS.unknown;
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider",
        color,
      )}
    >
      {status}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const color = TYPE_COLORS[type.toLowerCase()] ?? TYPE_COLORS.generic;
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium",
        color,
      )}
    >
      {type}
    </span>
  );
}

function CapabilityBadge({ name }: { name: string }) {
  return (
    <span className="rounded-md bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
      {name}
    </span>
  );
}

// ── Health Bar ─────────────────────────────────────────────────────────────

function HealthBar({ value, max = 100, color }: { value?: number; max?: number; color?: string }) {
  const v = safeNum(value);
  const pct = Math.min(Math.max((v / max) * 100, 0), 100);
  const barColor =
    color ??
    (pct > 80 ? "bg-green-500" : pct > 50 ? "bg-yellow-500" : pct > 20 ? "bg-orange-500" : "bg-red-500");
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-700">
        <div className={clsx("h-full rounded-full transition-all duration-500", barColor)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-gray-400">{v.toFixed(1)}%</span>
    </div>
  );
}

function MemoryBar({ usedMb }: { usedMb?: number }) {
  const mb = safeNum(usedMb);
  const maxDisplay = Math.max(mb, 100);
  const pct = Math.min((mb / 4096) * 100, 100);
  const barColor = pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-blue-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-700">
        <div className={clsx("h-full rounded-full transition-all duration-500", barColor)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-gray-400">
        {mb < 1 ? "<1" : mb.toFixed(0)} MB
      </span>
    </div>
  );
}

// ── Metric Gauge ───────────────────────────────────────────────────────────

function MetricGauge({
  label,
  value,
  suffix = "",
  max = 100,
  color,
}: {
  label: string;
  value?: number;
  suffix?: string;
  max?: number;
  color?: string;
}) {
  const v = safeNum(value);
  const pct = Math.min(Math.max((v / max) * 100, 0), 100);
  const barColor =
    color ??
    (pct > 80 ? "bg-red-500" : pct > 50 ? "bg-yellow-500" : "bg-green-500");
  return (
    <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-3">
      <div className="text-[10px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums text-gray-100">
        {v.toFixed(1)}
        <span className="ml-0.5 text-xs text-gray-500">{suffix}</span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-700">
        <div
          className={clsx("h-full rounded-full transition-all duration-500", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Loading Skeleton ───────────────────────────────────────────────────────

function TableSkeleton() {
  return (
    <div className="animate-pulse space-y-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 rounded-lg bg-gray-800/30 p-3">
          <div className="h-4 w-32 rounded bg-gray-700" />
          <div className="h-4 w-20 rounded bg-gray-700" />
          <div className="h-4 w-20 rounded bg-gray-700" />
          <div className="h-4 w-12 rounded bg-gray-700" />
          <div className="ml-auto h-4 w-16 rounded bg-gray-700" />
        </div>
      ))}
    </div>
  );
}

// ── API Helpers ────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { accept: "application/json", "content-type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  return (await res.json()) as T;
}

async function fetchRuntimes(): Promise<Runtime[]> {
  return apiFetch<RuntimeListResponse>("/api/runtimes");
}

async function fetchRuntime(id: string): Promise<Runtime> {
  return apiFetch<Runtime>(`/api/runtimes/${encodeURIComponent(id)}`);
}

async function startRuntime(id: string): Promise<Runtime> {
  return apiFetch<Runtime>(`/api/runtimes/${encodeURIComponent(id)}/start`, { method: "POST" });
}

async function stopRuntime(id: string, force = false): Promise<Runtime | { status: string }> {
  return apiFetch<Runtime | { status: string }>(
    `/api/runtimes/${encodeURIComponent(id)}/stop`,
    { method: "POST", body: JSON.stringify({ force }) },
  );
}

async function restartRuntime(id: string): Promise<Runtime | { status: string }> {
  return apiFetch<Runtime | { status: string }>(
    `/api/runtimes/${encodeURIComponent(id)}/restart`,
    { method: "POST" },
  );
}

async function killRuntime(id: string): Promise<Runtime | { status: string }> {
  return apiFetch<Runtime | { status: string }>(
    `/api/runtimes/${encodeURIComponent(id)}/kill`,
    { method: "POST" },
  );
}

async function fetchLogs(
  id: string,
  limit = 100,
  level?: string,
  search?: string,
): Promise<RuntimeLog[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (level) params.set("level", level);
  if (search) params.set("search", search);
  return apiFetch<RuntimeLog[]>(
    `/api/runtimes/${encodeURIComponent(id)}/logs?${params.toString()}`,
  );
}

async function fetchMetrics(id: string): Promise<RuntimeMetrics> {
  return apiFetch<RuntimeMetrics>(
    `/api/runtimes/${encodeURIComponent(id)}/metrics`,
  );
}

async function executeCommand(id: string, command: string): Promise<ExecuteResponse> {
  return apiFetch<ExecuteResponse>(
    `/api/runtimes/${encodeURIComponent(id)}/execute`,
    { method: "POST", body: JSON.stringify({ command }) },
  );
}

async function discoverRuntimes(): Promise<Runtime[]> {
  return apiFetch<RuntimeListResponse>("/api/runtimes/discover", { method: "POST" });
}

// ── Detail Panel Sub-Views ─────────────────────────────────────────────────

function LogsTab({ runtimeId }: { runtimeId: string }) {
  const [logs, setLogs] = useState<RuntimeLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const loadLogs = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchLogs(
        runtimeId,
        100,
        levelFilter || undefined,
        searchFilter || undefined,
      );
      setLogs(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [runtimeId, levelFilter, searchFilter]);

  useEffect(() => {
    loadLogs();
    const interval = setInterval(loadLogs, 3000);
    return () => clearInterval(interval);
  }, [loadLogs]);

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const filteredLogs = useMemo(() => {
    return logs;
  }, [logs]);

  return (
    <div className="flex flex-col gap-3">
      {/* Filter controls */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="Search logs..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            className="w-full rounded-lg border border-gray-700/50 bg-gray-800/60 py-1.5 pl-7 pr-3 text-xs text-gray-200 placeholder-gray-500 focus:border-accent/50 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-gray-700/50 bg-gray-800/60 p-0.5">
          {["", "info", "warn", "error", "debug"].map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl === levelFilter ? "" : lvl)}
              className={clsx(
                "rounded-md px-2 py-1 text-[10px] font-medium uppercase tracking-wider transition-colors",
                levelFilter === lvl || (lvl === "" && levelFilter === "")
                  ? "bg-accent/20 text-accent"
                  : "text-gray-500 hover:text-gray-300",
              )}
            >
              {lvl || "All"}
            </button>
          ))}
        </div>
        <button
          onClick={loadLogs}
          className="rounded-lg border border-gray-700/50 bg-gray-800/60 p-1.5 text-gray-400 hover:text-gray-200"
          title="Refresh logs"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={clsx(
            "rounded-lg border border-gray-700/50 p-1.5 text-xs",
            autoScroll ? "bg-accent/20 text-accent" : "bg-gray-800/60 text-gray-400 hover:text-gray-200",
          )}
          title="Auto-scroll"
        >
          Auto
        </button>
      </div>

      {/* Log entries */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={loadLogs} className="ml-auto text-red-300 hover:text-red-200">
            Retry
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-8 text-xs text-gray-500">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading logs...
        </div>
      ) : filteredLogs.length === 0 ? (
        <div className="py-8 text-center text-xs text-gray-500">No log entries found.</div>
      ) : (
        <div
          ref={scrollRef}
          className="max-h-80 overflow-y-auto rounded-lg border border-gray-700/30 bg-gray-900/80 font-mono text-[11px] leading-relaxed"
        >
          {filteredLogs.map((log, i) => (
            <div
              key={`${log.timestamp}-${i}`}
              className={clsx(
                "flex gap-3 border-b border-gray-800/50 px-3 py-1.5 transition-colors hover:bg-gray-800/40",
                LOG_LEVEL_BG[log.level] ?? "",
              )}
            >
              <span className="w-20 flex-shrink-0 text-gray-500">
                {formatTimestamp(log.timestamp)}
              </span>
              <span
                className={clsx(
                  "w-12 flex-shrink-0 font-semibold uppercase",
                  LOG_LEVEL_COLORS[log.level] ?? "text-gray-400",
                )}
              >
                {log.level}
              </span>
              <span className="text-gray-300">{log.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TerminalTab({ runtimeId }: { runtimeId: string }) {
  const [command, setCommand] = useState("");
  const [output, setOutput] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const outputRef = useRef<HTMLPreElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleExecute = useCallback(async () => {
    if (!command.trim()) return;
    const cmd = command.trim();
    setOutput((prev) => [...prev, `$ ${cmd}`]);
    setCommand("");
    setHistory((prev) => [...prev, cmd]);
    setHistoryIdx(-1);
    setLoading(true);
    setError(null);
    try {
      const result = await executeCommand(runtimeId, cmd);
      setOutput((prev) => [...prev, result.output || "(empty output)"]);
    } catch (err) {
      const msg = String(err);
      setError(msg);
      setOutput((prev) => [...prev, `Error: ${msg}`]);
    } finally {
      setLoading(false);
    }
  }, [command, runtimeId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleExecute();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (history.length > 0) {
        const newIdx = historyIdx === -1 ? history.length - 1 : Math.max(0, historyIdx - 1);
        setHistoryIdx(newIdx);
        setCommand(history[newIdx]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIdx >= 0) {
        const newIdx = historyIdx + 1;
        if (newIdx >= history.length) {
          setHistoryIdx(-1);
          setCommand("");
        } else {
          setHistoryIdx(newIdx);
          setCommand(history[newIdx]);
        }
      }
    }
  };

  const clearOutput = () => {
    setOutput([]);
    setError(null);
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Command Input */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-green-400">$</span>
          <input
            ref={inputRef}
            type="text"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter command..."
            disabled={loading}
            className="w-full rounded-lg border border-gray-700/50 bg-gray-900/80 py-2 pl-7 pr-3 font-mono text-xs text-gray-200 placeholder-gray-500 focus:border-accent/50 focus:outline-none disabled:opacity-50"
          />
        </div>
        <button
          onClick={handleExecute}
          disabled={loading || !command.trim()}
          className="flex items-center gap-1.5 rounded-lg bg-accent/80 px-3 py-2 text-xs font-medium text-white transition hover:bg-accent disabled:opacity-40"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Run
        </button>
        <button
          onClick={clearOutput}
          className="flex items-center gap-1.5 rounded-lg border border-gray-700/50 bg-gray-800/60 px-3 py-2 text-xs text-gray-400 hover:text-gray-200"
        >
          <X className="h-3.5 w-3.5" />
          Clear
        </button>
      </div>

      {/* Output */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
          {error}
        </div>
      )}

      <pre
        ref={outputRef}
        className="max-h-80 min-h-[120px] overflow-auto rounded-lg border border-gray-700/30 bg-gray-950 p-3 font-mono text-[11px] leading-relaxed text-gray-300"
      >
        {output.length === 0 ? (
          <span className="text-gray-600">Enter a command above and press Enter or click Run.</span>
        ) : (
          output.map((line, i) => {
            const isCmd = line.startsWith("$ ");
            const isErr = line.startsWith("Error:");
            return (
              <div
                key={i}
                className={clsx(
                  "whitespace-pre-wrap break-all",
                  isCmd && "text-green-400",
                  isErr && "text-red-400",
                )}
              >
                {line}
              </div>
            );
          })
        )}
      </pre>
    </div>
  );
}

function MetricsTab({ runtimeId }: { runtimeId: string }) {
  const [metrics, setMetrics] = useState<RuntimeMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchMetrics(runtimeId);
      setMetrics(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [runtimeId]);

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-xs text-gray-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Loading metrics...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs text-red-400">
        <AlertCircle className="h-4 w-4 flex-shrink-0" />
        <span>{error}</span>
        <button onClick={load} className="ml-auto text-red-300 hover:text-red-200">
          Retry
        </button>
      </div>
    );
  }

  if (!metrics) {
    return <div className="py-8 text-center text-xs text-gray-500">No metrics available.</div>;
  }

  return (
    <div className="space-y-6">
      {/* CPU + Memory Gauges */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <MetricGauge
          label="CPU Usage"
          value={metrics.cpu_percent}
          suffix="%"
          max={100}
        />
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-3">
          <div className="text-[10px] uppercase tracking-wide text-gray-500">Memory</div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-gray-100">
            {safeFixed(metrics?.memory_mb, 0)}
            <span className="ml-0.5 text-xs text-gray-500">MB</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-gray-700">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${Math.min((metrics.memory_mb / 4096) * 100, 100)}%` }}
            />
          </div>
        </div>
      </div>

      {/* Latency (only the value the backend actually reports — no invented percentiles) */}
      <div>
        <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500">
          Latency (ms)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-gray-500">reported</div>
            <div className="text-base font-semibold tabular-nums text-gray-100">
              {safeNum(metrics.latency_ms).toFixed(0)}
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-gray-700">
              <div
                className={clsx(
                  "h-full rounded-full transition-all duration-500",
                  metrics.latency_ms > 1000 ? "bg-red-500" : metrics.latency_ms > 500 ? "bg-yellow-500" : "bg-green-500",
                )}
                style={{ width: `${Math.min((safeNum(metrics.latency_ms) / 1000) * 100, 100)}%` }}
              />
            </div>
          </div>
          <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-gray-500">p50</div>
            <div className="text-base font-semibold tabular-nums text-gray-100">—</div>
            <div className="mt-1.5 text-[10px] text-gray-500">not measured by backend</div>
          </div>
          <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-gray-500">p99</div>
            <div className="text-base font-semibold tabular-nums text-gray-100">—</div>
            <div className="mt-1.5 text-[10px] text-gray-500">not measured by backend</div>
          </div>
        </div>
      </div>

      {/* Tokens & Cost */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-3">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-gray-500">
            <Zap className="h-3 w-3" />
            Tokens Used
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-gray-100">
            {metrics.tokens_used.toLocaleString()}
          </div>
        </div>
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-3">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-gray-500">
            <DollarSign className="h-3 w-3" />
            Cost
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-gray-100">
            ${safeFixed(metrics?.cost, 4)}
          </div>
        </div>
      </div>

      {/* Threads, Tasks, Queue */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
          <div className="text-[10px] uppercase tracking-wide text-gray-500">Threads</div>
          <div className="text-base font-semibold tabular-nums text-gray-100">{metrics.threads}</div>
        </div>
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
          <div className="text-[10px] uppercase tracking-wide text-gray-500">Tasks</div>
          <div className="text-base font-semibold tabular-nums text-gray-100">{metrics.active_tasks}</div>
        </div>
        <div className="rounded-lg border border-gray-700/50 bg-gray-800/40 p-2.5 text-center">
          <div className="text-[10px] uppercase tracking-wide text-gray-500">Queue</div>
          <div className="text-base font-semibold tabular-nums text-gray-100">{metrics.queue_depth}</div>
        </div>
      </div>

      {/* Restart / Crash counts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-gray-700/50 bg-gray-800/40 px-3 py-2">
          <RotateCw className="h-3.5 w-3.5 text-yellow-400" />
          <span className="text-xs text-gray-400">
            Restarts: <span className="font-semibold text-gray-200">{metrics.restart_count}</span>
          </span>
        </div>
        <div className="flex items-center gap-2 rounded-lg border border-gray-700/50 bg-gray-800/40 px-3 py-2">
          <Skull className="h-3.5 w-3.5 text-red-400" />
          <span className="text-xs text-gray-400">
            Crashes: <span className="font-semibold text-gray-200">{metrics.crash_count}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ── Detail Panel ───────────────────────────────────────────────────────────

function RuntimeDetailPanel({
  runtime,
  onClose,
  onRefresh,
}: {
  runtime: Runtime;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [activeTab, setActiveTab] = useState<"logs" | "terminal" | "metrics">("logs");

  return (
    <div className="mt-4 overflow-hidden rounded-xl border border-gray-700/40 bg-gray-800/30">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-gray-700/30 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-100">{runtime.name}</h3>
            <StatusBadge status={runtime.status} />
            <TypeBadge type={runtime.type} />
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-gray-500">
            {runtime.version && <span>v{runtime.version}</span>}
            <span>ID: {runtime.id}</span>
            {runtime.provider && <span>Provider: {runtime.provider}</span>}
            {runtime.pid != null && <span>PID: {runtime.pid}</span>}
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-700/50 hover:text-gray-200"
          title="Close detail panel"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Metadata grid */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 border-b border-gray-700/30 px-4 py-3 text-[11px] sm:grid-cols-3">
        <div>
          <span className="text-gray-500">Started:</span>{" "}
          <span className="text-gray-300">{formatDate(runtime.started_at)}</span>
        </div>
        <div>
          <span className="text-gray-500">Uptime:</span>{" "}
          <span className="text-gray-300">{formatUptime(runtime.uptime)}</span>
        </div>
        <div>
          <span className="text-gray-500">Health:</span>{" "}
          <span className="inline-flex items-center gap-1 text-gray-300">
            <span
              className={clsx(
                "inline-block h-2 w-2 rounded-full",
                HEALTH_COLORS[safeStr(runtime?.health).toLowerCase()] ?? "bg-gray-500",
              )}
            />
            {runtime.health}
          </span>
        </div>
        <div>
          <span className="text-gray-500">Restarts:</span>{" "}
          <span className="text-gray-300">{runtime.restart_count}</span>
        </div>
        <div>
          <span className="text-gray-500">Crashes:</span>{" "}
          <span className="text-gray-300">{runtime.crash_count}</span>
        </div>
        <div>
          <span className="text-gray-500">Source:</span>{" "}
          <span className="text-gray-300">{runtime.source}</span>
        </div>
        {runtime.last_error && (
          <div className="col-span-full">
            <span className="text-red-400">Last Error:</span>{" "}
            <span className="text-red-300">{runtime.last_error}</span>
          </div>
        )}
        {runtime.last_exit_code != null && (
          <div>
            <span className="text-gray-500">Last Exit Code:</span>{" "}
            <span className="text-gray-300">{runtime.last_exit_code}</span>
          </div>
        )}
        {runtime.working_directory && (
          <div className="col-span-full">
            <span className="text-gray-500">Working Dir:</span>{" "}
            <span className="text-gray-300 font-mono">{runtime.working_directory}</span>
          </div>
        )}
        {runtime.command && (
          <div className="col-span-full">
            <span className="text-gray-500">Command:</span>{" "}
            <span className="text-gray-300 font-mono">{runtime.command} {runtime.arguments?.join(" ")}</span>
          </div>
        )}
      </div>

      {/* Capabilities */}
      {runtime.capabilities && runtime.capabilities.length > 0 && (
        <div className="flex flex-wrap gap-1 border-b border-gray-700/30 px-4 py-2">
          {runtime.capabilities.map((cap, idx) => (
            <CapabilityBadge key={`${cap.name}-${idx}`} name={cap.name} />
          ))}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-gray-700/30">
        {(["logs", "terminal", "metrics"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={clsx(
              "flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider transition-colors",
              activeTab === tab
                ? "border-b-2 border-accent text-accent"
                : "text-gray-500 hover:text-gray-300",
            )}
          >
            {tab === "logs" && <Activity className="h-3.5 w-3.5" />}
            {tab === "terminal" && <Terminal className="h-3.5 w-3.5" />}
            {tab === "metrics" && <Cpu className="h-3.5 w-3.5" />}
            {tab}
          </button>
        ))}
        <button
          onClick={onRefresh}
          className="ml-auto flex items-center gap-1 px-4 text-[11px] text-gray-500 hover:text-gray-300"
          title="Refresh runtime"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Tab content */}
      <div className="p-4">
        {activeTab === "logs" && <LogsTab runtimeId={runtime.id} />}
        {activeTab === "terminal" && <TerminalTab runtimeId={runtime.id} />}
        {activeTab === "metrics" && <MetricsTab runtimeId={runtime.id} />}
      </div>
    </div>
  );
}

// ── Main Runtime Dashboard Component ───────────────────────────────────────

export default function RuntimeDashboard() {
  const [runtimes, setRuntimes] = useState<Runtime[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchRuntimes();
      setRuntimes(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + poll every 5s
  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, [load]);

  // Re-fetch when selectedId changes so the detail panel is fresh
  useEffect(() => {
    if (selectedId) {
      const interval = setInterval(load, 5000);
      return () => clearInterval(interval);
    }
  }, [selectedId, load]);

  const handleDiscover = async () => {
    setDiscovering(true);
    try {
      await discoverRuntimes();
      await load();
    } catch (err) {
      setError(`Discovery failed: ${err}`);
    } finally {
      setDiscovering(false);
    }
  };

  const handleAction = async (
    action: "start" | "stop" | "restart" | "kill",
    runtimeId: string,
  ) => {
    setActionLoading(`${action}-${runtimeId}`);
    try {
      switch (action) {
        case "start":
          await startRuntime(runtimeId);
          break;
        case "stop":
          await stopRuntime(runtimeId);
          break;
        case "restart":
          await restartRuntime(runtimeId);
          break;
        case "kill":
          await killRuntime(runtimeId);
          break;
      }
      await load();
    } catch (err) {
      setError(`${action} failed: ${err}`);
    } finally {
      setActionLoading(null);
    }
  };

  const selectedRuntime = useMemo(
    () => runtimes.find((r) => r.id === selectedId) ?? null,
    [runtimes, selectedId],
  );

  const counters = useMemo(() => {
    const total = runtimes.length;
    const running = runtimes.filter((r) =>
      ["running", "ready", "busy", "streaming", "starting"].includes(r.status),
    ).length;
    const stopped = runtimes.filter((r) =>
      ["stopped", "crashed", "failed"].includes(r.status),
    ).length;
    return { total, running, stopped };
  }, [runtimes]);

  // ── Render ──

  return (
    <div className="flex h-full flex-col p-4" role="region" aria-label="Runtime Dashboard">
      {/* ── Header ── */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-base font-semibold text-gray-100">Runtime Dashboard</h1>
          <p className="text-[11px] text-gray-500">
            Manage and monitor AI runtime processes
          </p>
        </div>

        {/* Counters */}
        <div className="ml-auto flex items-center gap-2">
          <div className="rounded-lg border border-gray-700/30 bg-gray-800/40 px-3 py-1.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-gray-500">Total</div>
            <div className="text-sm font-semibold tabular-nums text-gray-200">{counters.total}</div>
          </div>
          <div className="rounded-lg border border-green-700/30 bg-green-900/20 px-3 py-1.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-green-400">Running</div>
            <div className="text-sm font-semibold tabular-nums text-green-300">{counters.running}</div>
          </div>
          <div className="rounded-lg border border-red-700/30 bg-red-900/20 px-3 py-1.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-red-400">Stopped</div>
            <div className="text-sm font-semibold tabular-nums text-red-300">{counters.stopped}</div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleDiscover}
            disabled={discovering}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700/50 bg-gray-800/60 px-3 py-1.5 text-xs text-gray-300 transition hover:bg-gray-700/60 hover:text-gray-100 disabled:opacity-50"
          >
            <Search className="h-3.5 w-3.5" />
            {discovering ? "Discovering…" : "Discover Runtimes"}
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg border border-gray-700/50 bg-gray-800/60 px-3 py-1.5 text-xs text-gray-300 transition hover:bg-gray-700/60 hover:text-gray-100 disabled:opacity-50"
            title="Refresh list"
          >
            <RefreshCw className={clsx("h-3.5 w-3.5", loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Error Banner ── */}
      {error && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-xs text-red-400">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
          <button onClick={load} className="ml-auto text-red-300 hover:text-red-200">
            Retry
          </button>
        </div>
      )}

      {/* ── Runtime Table ── */}
      <div className="min-h-0 flex-1 overflow-auto">
        {loading && runtimes.length === 0 ? (
          <TableSkeleton />
        ) : runtimes.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <Server className="mx-auto h-10 w-10 text-gray-600" />
              <p className="mt-2 text-sm text-gray-500">No runtimes found</p>
              <p className="mt-1 text-xs text-gray-600">
                Click &quot;Discover Runtimes&quot; to scan for available runtimes.
              </p>
              <button
                onClick={handleDiscover}
                disabled={discovering}
                className="mt-3 rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
              >
                {discovering ? "Discovering…" : "Discover Runtimes"}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Table header */}
            <div className="flex items-center gap-2 rounded-lg bg-gray-800/40 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              <span className="w-48">Name</span>
              <span className="w-20">Type</span>
              <span className="w-24">Status</span>
              <span className="w-16">PID</span>
              <span className="w-24">Health</span>
              <span className="w-24">Uptime</span>
              <span className="w-24">CPU</span>
              <span className="w-28">Memory</span>
              <span className="ml-auto w-40 text-right">Actions</span>
            </div>

            {/* Table rows */}
            {runtimes.map((rt) => {
              const isExpanded = expandedId === rt.id;
              const hlValue = safeNum(rt?.health);
              const hlColor =
                hlValue >= 80 ? "bg-green-500" : hlValue >= 50 ? "bg-yellow-500" : hlValue > 0 ? "bg-orange-500" : "bg-gray-500";
              const isActionLoading = actionLoading && actionLoading.endsWith(rt.id);

              return (
                <div key={rt.id}>
                  <div
                    className={clsx(
                      "flex cursor-pointer items-center gap-2 rounded-lg px-4 py-2.5 transition-colors hover:bg-gray-800/40",
                      isExpanded && "bg-gray-800/50",
                    )}
                    onClick={() => setExpandedId(isExpanded ? null : rt.id)}
                  >
                    {/* Expand indicator + Name */}
                    <span className="flex w-48 items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown className="h-3.5 w-3.5 flex-shrink-0 text-gray-500" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 flex-shrink-0 text-gray-500" />
                      )}
                      <span className="truncate text-sm font-medium text-gray-200">{rt.name}</span>
                    </span>

                    {/* Type */}
                    <span className="w-20">
                      <TypeBadge type={rt.type} />
                    </span>

                    {/* Status */}
                    <span className="w-24">
                      <StatusBadge status={rt.status} />
                    </span>

                    {/* PID */}
                    <span className="w-16 font-mono text-xs text-gray-400">
                      {rt.pid ?? "—"}
                    </span>

                    {/* Health dot */}
                    <span className="flex w-24 items-center gap-1.5">
                      <span className={clsx("inline-block h-2 w-2 rounded-full", hlColor)} />
                      <span className="text-xs text-gray-400">{rt.health}</span>
                    </span>

                    {/* Uptime */}
                    <span className="flex w-24 items-center gap-1 text-xs text-gray-400">
                      <Clock className="h-3 w-3" />
                      {formatUptime(rt.uptime)}
                    </span>

                    {/* CPU */}
                    <span className="w-24">
                      <HealthBar value={rt.cpu} color={rt.cpu > 80 ? undefined : "bg-blue-500"} />
                    </span>

                    {/* Memory */}
                    <span className="w-28">
                      <MemoryBar usedMb={rt.memory} />
                    </span>

                    {/* Actions */}
                    <span
                      className="ml-auto flex w-40 items-center justify-end gap-1"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {/* Every runtime is a real, controllable process, so all
                          four controls are always shown. Start appears only when
                          the runtime is not currently running. */}
                      <>
                        <button
                          onClick={() => handleAction("stop", rt.id)}
                          disabled={!!actionLoading}
                          className="rounded-md border border-yellow-700/40 bg-yellow-900/20 p-1.5 text-yellow-400 hover:bg-yellow-900/40 disabled:opacity-40"
                          title="Stop"
                        >
                          {isActionLoading && actionLoading?.startsWith("stop") ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Square className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleAction("restart", rt.id)}
                          disabled={!!actionLoading}
                          className="rounded-md border border-blue-700/40 bg-blue-900/20 p-1.5 text-blue-400 hover:bg-blue-900/40 disabled:opacity-40"
                          title="Restart"
                        >
                          {isActionLoading && actionLoading?.startsWith("restart") ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RotateCw className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleAction("kill", rt.id)}
                          disabled={!!actionLoading}
                          className="rounded-md border border-red-700/40 bg-red-900/20 p-1.5 text-red-400 hover:bg-red-900/40 disabled:opacity-40"
                          title="Kill"
                        >
                          {isActionLoading && actionLoading?.startsWith("kill") ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Skull className="h-3.5 w-3.5" />
                          )}
                        </button>
                        {rt.pid == null && (
                          <button
                            onClick={() => handleAction("start", rt.id)}
                            disabled={!!actionLoading}
                            className="rounded-md border border-green-700/40 bg-green-900/20 p-1.5 text-green-400 hover:bg-green-900/40 disabled:opacity-40"
                            title="Start"
                          >
                            {isActionLoading && actionLoading?.startsWith("start") ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Play className="h-3.5 w-3.5" />
                            )}
                          </button>
                        )}
                      </>
                    </span>
                  </div>

                  {/* Expanded Detail Panel */}
                  {isExpanded && (
                    <div className="px-2 pb-2">
                      <RuntimeDetailPanel
                        runtime={rt}
                        onClose={() => setExpandedId(null)}
                        onRefresh={load}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
