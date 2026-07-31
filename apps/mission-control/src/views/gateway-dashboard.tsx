"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { safeFixed, safeNum } from "@/lib/safe";
import { motion } from "framer-motion";
import { Panel, Stat } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type {
  OpenAIModelType,
  GatewayHealth,
  GatewayConfig,
  GatewayStrategy,
  AgentRouteProfile,
} from "@/lib/types";
import {
  Terminal,
  Activity,
  Zap,
  Database,
  Server,
  Globe,
  Sliders,
  RefreshCw,
  Copy,
  Check,
  AlertTriangle,
  Boxes,
} from "lucide-react";
import { clsx } from "clsx";

const STRATEGY_META: Record<GatewayStrategy, { label: string; color: string; description: string }> = {
  fastest: { label: "Fastest", color: "#22c55e", description: "Minimise execution time" },
  cheapest: { label: "Cheapest", color: "#f59e0b", description: "Minimise token cost" },
  best_capability: { label: "Best Capability", color: "#8b5cf6", description: "Maximise capability match" },
  balanced: { label: "Balanced", color: "#3b82f6", description: "Weighted across all dimensions" },
  reliability_first: { label: "Reliability First", color: "#06b6d4", description: "Prefer proven, stable agents" },
  latency_first: { label: "Latency First", color: "#ec4899", description: "Minimise per-call latency" },
  custom: { label: "Custom", color: "#6b7280", description: "User-defined weights" },
};

const AGENT_COLORS: Record<string, string> = {
  claude: "#d97706",
  opencode: "#06b6d4",
  hermes: "#8b5cf6",
  gemini: "#4285f4",
  codex: "#10b981",
};

function getAgentColor(provider: string): string {
  const key = Object.keys(AGENT_COLORS).find((k) => provider.toLowerCase().includes(k));
  return key ? AGENT_COLORS[key] : "#6b7280";
}

// ── Sub-components ──

function QuickConnectSnippet() {
  const [copied, setCopied] = useState(false);
  const snippet = `export OPENAI_BASE_URL=http://localhost:8000/v1`;

  const copy = useCallback(() => {
    navigator.clipboard.writeText(snippet);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [snippet]);

  return (
    <div className="glass overflow-hidden rounded-xl">
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-2">
        <Terminal size={14} className="text-faint" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-faint">Quick Connect</span>
      </div>
      <div className="flex items-center gap-2 px-4 py-3">
        <code className="flex-1 rounded-lg bg-black/30 px-3 py-2 font-mono text-[13px] text-accent">
          {snippet}
        </code>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-medium text-faint transition-colors hover:bg-accent/10 hover:text-accent"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

function ModelBadge({ model }: { model: OpenAIModelType }) {
  const color = getAgentColor(model.owned_by);
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border/40 bg-black/20 px-3 py-2">
      <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      <div>
        <div className="text-[13px] font-medium">{model.id}</div>
        <div className="text-[10px] text-faint">{model.owned_by}</div>
      </div>
    </div>
  );
}

function AgentCard({ agent }: { agent: AgentRouteProfile }) {
  const color = getAgentColor(agent.provider);
  const capsObj = agent.capabilities || {};
  const topCaps = Object.entries(capsObj)
    .sort(([, a], [, b]) => (b as number) - (a as number))
    .slice(0, 4);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl p-3.5"
    >
      <div className="flex items-center gap-2.5">
        <div className="grid h-8 w-8 place-items-center rounded-lg" style={{ backgroundColor: `${color}20` }}>
          <Activity size={14} style={{ color }} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{agent.agent_name || agent.agent_id || "Agent"}</span>
            <span className="rounded bg-black/20 px-1.5 py-0.5 text-[10px] font-medium text-faint">
              {agent.provider}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {topCaps.map(([cap, score]) => (
              <span
                key={cap}
                className="rounded bg-black/20 px-1.5 py-0.5 text-[10px]"
                style={{ color: (score as number) > 0.7 ? "#22c55e" : (score as number) > 0.4 ? "#f59e0b" : "#ef4444" }}
              >
                {cap}: {safeFixed((safeNum(score) * 100), 0)}%
              </span>
            ))}
          </div>
        </div>
        <div className="text-right text-[11px] text-faint">
          <div>{agent.cost_per_1k > 0 ? `$${agent.cost_per_1k}/1k` : "Free"}</div>
          <div>{agent.latency_ms || 0}ms</div>
        </div>
      </div>
    </motion.div>
  );
}

function StrategySelector({
  active,
  onChange,
}: {
  active: GatewayStrategy;
  onChange: (s: GatewayStrategy) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {(Object.keys(STRATEGY_META) as GatewayStrategy[]).map((s) => {
        const meta = STRATEGY_META[s];
        const isActive = s === active;
        return (
          <button
            key={s}
            onClick={() => onChange(s)}
            className={clsx(
              "rounded-lg border px-3 py-2 text-[12px] font-medium transition-all",
              isActive
                ? "border-accent/40 bg-accent/10 text-accent shadow-sm"
                : "border-border/40 text-faint hover:border-border/80 hover:text-text",
            )}
          >
            <div className="flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: meta.color }} />
              {meta.label}
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── Main component ──

export function GatewayDashboard() {
  const [models, setModels] = useState<OpenAIModelType[]>([]);
  const [health, setHealth] = useState<GatewayHealth | null>(null);
  const [config, setConfig] = useState<GatewayConfig | null>(null);
  const [agents, setAgents] = useState<AgentRouteProfile[]>([]);
  const [activeStrategy, setActiveStrategy] = useState<GatewayStrategy>("balanced");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const connected = useStore((s) => s.connected);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mRes, hRes, cRes, aRes] = await Promise.allSettled([
        api.gatewayModels(),
        api.gatewayHealth(),
        api.getRouteConfig(),
        api.listRouteAgents(),
      ]);

      if (mRes.status === "fulfilled") setModels(mRes.value.data ?? []);
      if (hRes.status === "fulfilled") setHealth(hRes.value);
      if (cRes.status === "fulfilled") {
        setConfig(cRes.value);
        setActiveStrategy(cRes.value.default_strategy);
      }
      if (aRes.status === "fulfilled") setAgents(aRes.value);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load gateway data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 10_000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const strategyMeta = STRATEGY_META[activeStrategy];

  // Stats
  const stats = useMemo(() => ({
    models: models.length,
    agents: agents.length,
    freeAgents: agents.filter((a) => a.cost_per_1k === 0).length,
    avgReliability: agents.length > 0
      ? Math.round(agents.reduce((s, a) => s + a.reliability, 0) / agents.length * 100) / 100
      : 0,
  }), [models, agents]);

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight">Unified API Gateway</h1>
            <p className="text-[13px] text-faint">
              OpenAI-compatible /v1 endpoint — route missions across your agent swarm
            </p>
          </div>
          <button
            onClick={fetchAll}
            className="flex items-center gap-1.5 rounded-lg border border-border/40 px-3 py-2 text-[12px] font-medium text-faint transition-colors hover:border-accent/40 hover:text-accent"
          >
            <RefreshCw size={14} className={clsx(loading && "animate-spin")} />
            Refresh
          </button>
        </div>
      </motion.div>

      {/* Quick Connect */}
      <QuickConnectSnippet />

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-[13px] text-danger">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-4 gap-3">
        <Stat label="Available Models" value={stats.models} />
        <Stat label="Routed Agents" value={stats.agents} delta={`${stats.freeAgents} free`} />
        <Stat
          label="Avg Reliability"
          value={`${safeFixed((safeNum(stats?.avgReliability) * 100), 0)}%`}
          tone={stats.avgReliability > 0.9 ? "ok" : stats.avgReliability > 0.7 ? "warn" : "danger"}
        />
        <Stat
          label="Status"
          value={health?.status === "active" ? "Active" : "Inactive"}
          tone={health?.status === "active" ? "ok" : "warn"}
          delta={health ? `${health.uptime_seconds}s uptime` : undefined}
        />
      </div>

      {/* Strategy + Config */}
      <Panel title="Routing Strategy" subtitle={strategyMeta?.description ?? "Select a strategy"} className="flex-shrink-0">
        <div className="space-y-4">
          <StrategySelector active={activeStrategy} onChange={setActiveStrategy} />
          {config && (
            <div className="grid grid-cols-4 gap-3">
              <div className="glass rounded-lg px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-wide text-faint">Cost Weight</div>
                <div className="mt-0.5 text-lg font-semibold">{safeFixed((safeNum(config?.cost_weight) * 100), 0)}%</div>
              </div>
              <div className="glass rounded-lg px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-wide text-faint">Speed Weight</div>
                <div className="mt-0.5 text-lg font-semibold">{safeFixed((safeNum(config?.speed_weight) * 100), 0)}%</div>
              </div>
              <div className="glass rounded-lg px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-wide text-faint">Capability Weight</div>
                <div className="mt-0.5 text-lg font-semibold">{safeFixed((safeNum(config?.capability_weight) * 100), 0)}%</div>
              </div>
              <div className="glass rounded-lg px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-wide text-faint">Reliability Weight</div>
                <div className="mt-0.5 text-lg font-semibold">{safeFixed((safeNum(config?.reliability_weight) * 100), 0)}%</div>
              </div>
            </div>
          )}
        </div>
      </Panel>

      {/* Available Models */}
      <Panel title="Available Models" subtitle="Discovered via /v1/models">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-faint">Loading models...</div>
        ) : models.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-faint">
            <Database size={24} />
            <span className="text-[13px]">No models discovered. Start the backend to see available models.</span>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {models.map((m) => (
              <ModelBadge key={m.id} model={m} />
            ))}
          </div>
        )}
      </Panel>

      {/* Routed Agents */}
      <Panel title="Route Agents" subtitle={`${agents.length} agent(s) registered with OmniRoute`}>
        {agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-faint">
            <Boxes size={24} />
            <span className="text-[13px]">No agents registered for routing.</span>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {agents.map((a, idx) => (
              <AgentCard key={a.agent_id || `agent-${idx}`} agent={a} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
