"use client";

import { useEffect, useState, useCallback } from "react";
import { safeFixed, safeNum } from "@/lib/safe";
import { motion, AnimatePresence } from "framer-motion";
import {
  Cpu,
  MemoryStick,
  Activity,
  Play,
  Square,
  RefreshCw,
  Eye,
  Settings,
  Trash2,
  List,
  Wifi,
  WifiOff,
  ChevronDown,
  ChevronUp,
  Clock,
} from "lucide-react";
import { clsx } from "clsx";
import { StatusDot } from "@/components/status-dot";
import { HealthBar } from "@/components/health-bar";
import { useLocalAgentsStore, type LocalAgent } from "@/lib/use-local-agents";

// ── Tool-type → emoji map ──

const TOOL_EMOJI: Record<string, string> = {
  hermes: "🤖",
  claude: "💬",
  codex: "◻",
  ollama: "🦙",
  docker: "🐳",
  python: "🐍",
  node: "⚡",
};

function getToolEmoji(toolType: string): string {
  const key = toolType.toLowerCase();
  return TOOL_EMOJI[key] ?? "🤖";
}

// ── Helpers ──

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function truncatePath(path: string, maxLen = 48): string {
  if (path.length <= maxLen) return path;
  return "…" + path.slice(-(maxLen - 1));
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

// ── Agent Card ──

function AgentCard({
  agent,
  onStart,
  onStop,
  onRestart,
  onRefresh,
  onForget,
}: {
  agent: LocalAgent;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
  onRestart: (id: string) => void;
  onRefresh: (id: string) => void;
  onForget: (id: string) => void;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const isRunning = agent.status === "running" || agent.status === "busy";
  const isStopped = agent.status === "stopped" || agent.status === "crashed";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.25 }}
      className="flex flex-col overflow-hidden rounded-xl border border-border/40 bg-surface/40 backdrop-blur-sm"
    >
      {/* ── Header row ── */}
      <div className="flex items-start gap-3 border-b border-border/30 px-4 py-3">
        <span className="mt-0.5 text-xl leading-none" role="img" aria-label={agent.tool_type}>
          {getToolEmoji(agent.tool_type)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-text">{agent.name}</h3>
            {agent.version && (
              <span className="shrink-0 rounded-md bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                v{agent.version}
              </span>
            )}
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            <StatusDot status={agent.status} label />
            {agent.pid != null && isRunning && (
              <span className="text-[11px] text-faint font-mono">PID {agent.pid}</span>
            )}
          </div>
        </div>
      </div>

      {/* ── Health bar ── */}
      <div className="border-b border-border/30 px-4 py-2">
        <div className="flex items-center justify-between text-[11px] text-faint mb-1">
          <span>Health</span>
        </div>
        <HealthBar score={agent.health_score} />
      </div>

      {/* ── Resource bars ── */}
      <div className="border-b border-border/30 px-4 py-2 space-y-2">
        {/* CPU */}
        <div className="flex items-center gap-2">
          <Cpu size={12} className="shrink-0 text-faint" />
          <div className="flex-1">
            <div className="flex items-center justify-between text-[10px] text-faint mb-0.5">
              <span>CPU</span>
              <span className="tabular-nums">{Math.round(agent.cpu_percent)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-surface/40">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent/60 to-accent transition-all duration-500"
                style={{ width: `${Math.min(100, agent.cpu_percent)}%` }}
              />
            </div>
          </div>
        </div>
        {/* RAM */}
        <div className="flex items-center gap-2">
          <MemoryStick size={12} className="shrink-0 text-faint" />
          <div className="flex-1">
            <div className="flex items-center justify-between text-[10px] text-faint mb-0.5">
              <span>RAM</span>
              <span className="tabular-nums">
                {agent.memory_mb > 1024
                  ? `${safeFixed((safeNum(agent?.memory_mb) / 1024), 1)} GB`
                  : `${Math.round(agent.memory_mb)} MB`}
              </span>
            </div>
            {/* Show a proportional bar — assume a typical ceiling of 16GB */}
            <div className="h-1.5 overflow-hidden rounded-full bg-surface/40">
              <div
                className="h-full rounded-full bg-gradient-to-r from-blue-500/60 to-blue-400 transition-all duration-500"
                style={{ width: `${Math.min(100, (agent.memory_mb / 16384) * 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Quick stats row ── */}
      <div className="flex flex-wrap items-center gap-3 border-b border-border/30 px-4 py-2 text-[11px] text-faint">
        <span className="inline-flex items-center gap-1">
          <Activity size={11} />
          {agent.latency_ms < 1000
            ? `${agent.latency_ms}ms`
            : `${safeFixed((safeNum(agent?.latency_ms) / 1000), 1)}s`}
        </span>
        {agent.uptime_seconds > 0 && (
          <span className="inline-flex items-center gap-1">
            <Clock size={11} />
            {formatUptime(agent.uptime_seconds)}
          </span>
        )}
        {agent.restart_count > 0 && (
          <span className="inline-flex items-center gap-1">
            {agent.restart_count} restarts
          </span>
        )}
        {agent.threads > 0 && (
          <span className="inline-flex items-center gap-1">
            {agent.threads} threads
          </span>
        )}
      </div>

      {/* ── Capabilities tags ── */}
      {agent.capabilities.length > 0 && (
        <div className="flex flex-wrap gap-1 border-b border-border/30 px-4 py-2">
          {agent.capabilities.map((cap) => (
            <span
              key={cap}
              className="rounded-md bg-accent/8 px-1.5 py-0.5 text-[10px] font-medium text-accent"
            >
              {cap}
            </span>
          ))}
        </div>
      )}

      {/* ── Supported models chip list ── */}
      {agent.supported_models.length > 0 && (
        <div className="border-b border-border/30 px-4 py-2">
          <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-faint">
            Models
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-thin">
            {agent.supported_models.map((model) => (
              <span
                key={model}
                className="shrink-0 rounded-md border border-border/40 bg-surface/20 px-2 py-0.5 text-[10px] text-muted whitespace-nowrap"
              >
                {model}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Working directory ── */}
      {agent.working_directory && (
        <div className="border-b border-border/30 px-4 py-1.5">
          <span className="text-[10px] font-mono text-faint" title={agent.working_directory}>
            {truncatePath(agent.working_directory)}
          </span>
        </div>
      )}

      {/* ── Error display ── */}
      {agent.error && (
        <div className="border-b border-border/30 bg-danger/5 px-4 py-1.5 text-[10px] text-danger">
          {agent.error}
        </div>
      )}

      {/* ── Action buttons ── */}
      <div className="flex items-center gap-1 border-b border-border/30 px-3 py-2">
        {isRunning ? (
          <button
            onClick={() => onStop(agent.id)}
            className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-warn hover:bg-warn/10 transition-colors"
            title="Stop"
          >
            <Square size={12} className="inline-block mr-1" />
            Stop
          </button>
        ) : isStopped ? (
          <button
            onClick={() => onStart(agent.id)}
            className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-ok hover:bg-ok/10 transition-colors"
            title="Start"
          >
            <Play size={12} className="inline-block mr-1" />
            Start
          </button>
        ) : (
          <button
            onClick={() => onStart(agent.id)}
            className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-muted hover:bg-surface/30 transition-colors"
            title="Start"
          >
            <Play size={12} className="inline-block mr-1" />
            Start
          </button>
        )}
        <button
          onClick={() => onRestart(agent.id)}
          className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-muted hover:bg-surface/30 transition-colors"
          title="Restart"
        >
          <RefreshCw size={12} className="inline-block mr-1" />
          Restart
        </button>
        <button
          onClick={() => onRefresh(agent.id)}
          className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-muted hover:bg-surface/30 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={11} className="inline-block" />
        </button>
        <button
          onClick={() => onForget(agent.id)}
          className="rounded-md border border-border/40 px-2 py-1 text-[10px] font-medium text-faint hover:text-danger hover:border-danger/40 transition-colors"
          title="Forget/Remove"
        >
          <Trash2 size={11} className="inline-block" />
        </button>
        <span className="flex-1" />
        <a
          href={`#logs/${agent.id}`}
          className="rounded-md px-2 py-1 text-[10px] font-medium text-faint hover:text-muted transition-colors"
          title="View logs"
        >
          <List size={11} className="inline-block mr-0.5" />
          Logs
        </a>
        <a
          href={`#settings/${agent.id}`}
          className="rounded-md px-2 py-1 text-[10px] font-medium text-faint hover:text-muted transition-colors"
          title="Settings"
        >
          <Settings size={11} className="inline-block" />
        </a>
        <button
          onClick={() => setDetailsOpen(!detailsOpen)}
          className="rounded-md px-2 py-1 text-[10px] font-medium text-faint hover:text-muted transition-colors"
          title="Toggle details"
        >
          {detailsOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* ── Collapsible details section ── */}
      <AnimatePresence>
        {detailsOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-1.5 border-t border-border/20 bg-surface/20 px-4 py-3 text-[11px] font-mono text-faint">
              <DetailRow label="ID" value={agent.id} />
              <DetailRow label="Tool Type" value={agent.tool_type} />
              <DetailRow label="Executable" value={agent.executable_path} />
              <DetailRow label="Working Dir" value={agent.working_directory} />
              <DetailRow label="PID" value={agent.pid != null ? String(agent.pid) : "—"} />
              <DetailRow label="Discovered" value={timeAgo(agent.discovered_at)} />
              <DetailRow label="Last Seen" value={timeAgo(agent.last_seen)} />
              <DetailRow label="Latency" value={`${agent.latency_ms}ms`} />
              <DetailRow label="CPU" value={`${safeFixed(agent?.cpu_percent, 1)}%`} />
              <DetailRow label="Memory" value={`${safeFixed(agent?.memory_mb, 0)} MB`} />
              <DetailRow label="Threads" value={String(agent.threads)} />
              <DetailRow label="Uptime" value={formatUptime(agent.uptime_seconds)} />
              <DetailRow label="Restarts" value={String(agent.restart_count)} />
              {agent.supported_providers.length > 0 && (
                <DetailRow label="Providers" value={agent.supported_providers.join(", ")} />
              )}
              {agent.tags.length > 0 && (
                <DetailRow label="Tags" value={agent.tags.join(", ")} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="shrink-0 w-20 text-[10px] uppercase tracking-wider text-faint/60">
        {label}
      </span>
      <span className="break-all text-[11px] text-muted">{value}</span>
    </div>
  );
}

// ── Skeleton card for loading state ──

function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-xl border border-border/40 bg-surface/20 p-4 space-y-3">
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 rounded-full bg-surface/40" />
        <div className="flex-1 space-y-1.5">
          <div className="h-3 w-1/2 rounded bg-surface/40" />
          <div className="h-2 w-1/3 rounded bg-surface/30" />
        </div>
      </div>
      <div className="h-2 w-full rounded bg-surface/30" />
      <div className="space-y-1.5">
        <div className="h-2 w-3/4 rounded bg-surface/30" />
        <div className="h-2 w-2/3 rounded bg-surface/30" />
      </div>
      <div className="flex gap-1.5">
        <div className="h-5 w-14 rounded bg-surface/30" />
        <div className="h-5 w-14 rounded bg-surface/30" />
        <div className="h-5 w-14 rounded bg-surface/30" />
      </div>
      <div className="flex gap-2">
        <div className="h-6 w-16 rounded bg-surface/30" />
        <div className="h-6 w-16 rounded bg-surface/30" />
        <div className="h-6 w-8 rounded bg-surface/30" />
      </div>
    </div>
  );
}

// ── Main Export: LocalAgents view ──

export function LocalAgents() {
  const {
    agents,
    loading,
    error,
    sseConnected,
    fetchAgents,
    startSSE,
    stopSSE,
    startAgent,
    stopAgent,
    restartAgent,
    refreshAgent,
    forgetAgent,
    rescan,
  } = useLocalAgentsStore();

  // Initialise store on mount (fetch + SSE)
  useEffect(() => {
    fetchAgents();
    startSSE();
    return () => stopSSE();
  }, [fetchAgents, startSSE, stopSSE]);

  const handleStart = useCallback((id: string) => startAgent(id), [startAgent]);
  const handleStop = useCallback((id: string) => stopAgent(id), [stopAgent]);
  const handleRestart = useCallback((id: string) => restartAgent(id), [restartAgent]);
  const handleRefresh = useCallback((id: string) => refreshAgent(id), [refreshAgent]);
  const handleForget = useCallback((id: string) => forgetAgent(id), [forgetAgent]);

  // ── Error state ──
  if (error && agents.length === 0 && !loading) {
    return (
      <div className="scroll-page">
        <Toolbar
          agentCount={0}
          sseConnected={sseConnected}
          onRescan={rescan}
          scanning={loading}
        />
        <div className="flex flex-col items-center justify-center gap-4 p-12">
          <div className="rounded-full bg-danger/10 p-3">
            <Activity size={24} className="text-danger" />
          </div>
          <p className="text-sm font-medium text-muted">Failed to load agents</p>
          <p className="max-w-xs text-center text-[11px] text-faint">{error}</p>
          <button
            onClick={fetchAgents}
            className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent/80 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ── Empty state ──
  if (!loading && agents.length === 0) {
    return (
      <div className="scroll-page">
        <Toolbar
          agentCount={0}
          sseConnected={sseConnected}
          onRescan={rescan}
          scanning={loading}
        />
        <div className="flex flex-col items-center justify-center gap-4 p-12">
          <span className="text-5xl">🔍</span>
          <p className="text-sm font-medium text-muted">
            No local agents detected
          </p>
          <p className="max-w-xs text-center text-[11px] text-faint">
            AI tools on your machine will appear here automatically.
            Run a scan or start an AI tool to discover it.
          </p>
          <button
            onClick={rescan}
            disabled={loading}
            className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent/80 disabled:opacity-50 transition-colors"
          >
            {loading ? "Scanning..." : "Scan Now"}
          </button>
        </div>
      </div>
    );
  }

  // ── Main content ──
  return (
    <div className="scroll-page">
      <Toolbar
        agentCount={agents.length}
        sseConnected={sseConnected}
        onRescan={rescan}
        scanning={loading}
      />

      {loading && agents.length === 0 ? (
        /* Loading skeleton */
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 p-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        /* Agent grid */
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 p-4">
          <AnimatePresence>
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onStart={handleStart}
                onStop={handleStop}
                onRestart={handleRestart}
                onRefresh={handleRefresh}
                onForget={handleForget}
              />
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

// ── Top Toolbar ──

function Toolbar({
  agentCount,
  sseConnected,
  onRescan,
  scanning,
}: {
  agentCount: number;
  sseConnected: boolean;
  onRescan: () => void;
  scanning: boolean;
}) {
  return (
    <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-border/60 bg-surface/60 px-4 py-2.5 backdrop-blur-md">
      <h1 className="text-sm font-semibold tracking-tight text-text">
        Local Agents
      </h1>
      <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium text-accent tabular-nums">
        {agentCount}
      </span>
      <div className="ml-auto flex items-center gap-3">
        {/* SSE connection indicator */}
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 text-[10px]",
            sseConnected ? "text-ok" : "text-faint"
          )}
          title={sseConnected ? "SSE Connected" : "SSE Disconnected"}
        >
          {sseConnected ? (
            <Wifi size={12} className="text-ok" />
          ) : (
            <WifiOff size={12} />
          )}
          <span className="hidden sm:inline">
            {sseConnected ? "Live" : "Offline"}
          </span>
        </span>

        <button
          onClick={onRescan}
          disabled={scanning}
          className={clsx(
            "inline-flex items-center gap-1.5 rounded-lg border border-border/40 px-3 py-1.5 text-[11px] font-medium transition-colors",
            scanning
              ? "cursor-not-allowed opacity-50"
              : "text-muted hover:bg-surface/30 hover:text-text"
          )}
        >
          <RefreshCw
            size={12}
            className={scanning ? "animate-spin" : ""}
          />
          {scanning ? "Scanning..." : "Re-scan"}
        </button>
      </div>
    </div>
  );
}
