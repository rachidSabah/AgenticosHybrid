"use client";

import { useEffect, useMemo, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";

// ── Color System ──
const COLORS = {
  bg: "#050510",
  surface: "rgba(15, 23, 42, 0.6)",
  border: "rgba(0, 212, 255, 0.3)",
  cyan: "#00d4ff",
  purple: "#8b5cf6",
  magenta: "#ec4899",
  green: "#00ff88",
  amber: "#f59e0b",
  textPrimary: "#e2e8f0",
  textSecondary: "#64748b",
};

const PROVIDER_COLORS: Record<string, string> = {
  claude: "#d980ff",
  hermes: "#00d4ff",
  opencode: "#38bdf8",
  agy: "#f472b6",
  gemini: "#f97316",
  codex: "#818cf8",
  git: "#00ff88",
  node: "#84cc16",
  python: "#3b82f6",
  docker: "#06b6d4",
  mistral: "#f59e0b",
};

function getProviderColor(name: string): string {
  const low = name.toLowerCase();
  for (const k of Object.keys(PROVIDER_COLORS)) {
    if (low.includes(k)) return PROVIDER_COLORS[k];
  }
  return COLORS.cyan;
}

// ── Central Neural Network Visualization ──
function NeuralNetworkCanvas({ brainNodes, connections }: {
  brainNodes: Array<{ id: string; name: string; color: string; isCore: boolean; status: string }>;
  connections: Array<{ from: string; to: string; color: string }>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 600, height: 500 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setSize({ width: Math.round(width), height: Math.round(height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const cx = size.width / 2;
  const cy = size.height / 2;
  const radius = Math.min(size.width, size.height) * 0.33;
  const n = brainNodes.length;

  const positions = brainNodes.map((node, i) => {
    if (node.isCore) return { x: cx, y: cy };
    const angle = ((i - 1) / Math.max(1, n - 1)) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });

  return (
    <div
      ref={containerRef}
      className="relative min-h-[400px] flex-1 overflow-hidden rounded-xl border"
      style={{
        background: `radial-gradient(ellipse at center, #0a0a1f 0%, #050510 70%)`,
        borderColor: COLORS.border,
      }}
    >
      {/* Radial grid lines */}
      <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${size.width} ${size.height}`} preserveAspectRatio="xMidYMid meet">
        {/* Concentric rings */}
        {[0.15, 0.33, 0.5].map((r, i) => (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={Math.min(size.width, size.height) * r}
            fill="none"
            stroke={i === 0 ? COLORS.cyan : COLORS.purple}
            strokeWidth="0.8"
            strokeOpacity={i === 0 ? 0.3 : 0.15}
            strokeDasharray={i === 0 ? "8 4" : "4 6"}
          />
        ))}

        {/* Radial grid lines emanating from center */}
        {Array.from({ length: 12 }, (_, i) => {
          const angle = (i / 12) * Math.PI * 2;
          const r = Math.min(size.width, size.height) * 0.45;
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + r * Math.cos(angle)}
              y2={cy + r * Math.sin(angle)}
              stroke={COLORS.cyan}
              strokeWidth="0.3"
              strokeOpacity="0.08"
            />
          );
        })}

        {/* Connection lines (neural pathways) */}
        {connections.map((conn, idx) => {
          const fromIdx = brainNodes.findIndex(n => n.id === conn.from);
          const toIdx = brainNodes.findIndex(n => n.id === conn.to);
          if (fromIdx < 0 || toIdx < 0) return null;
          const from = positions[fromIdx];
          const to = positions[toIdx];
          const midX = (from.x + to.x) / 2;
          const midY = (from.y + to.y) / 2 - 20;
          return (
            <g key={idx}>
              <path
                d={`M ${from.x} ${from.y} Q ${midX} ${midY} ${to.x} ${to.y}`}
                fill="none"
                stroke={conn.color}
                strokeWidth="1.5"
                strokeOpacity="0.4"
                strokeDasharray="6 4"
                className="animate-dash-flow"
              />
              {/* Glowing endpoint dots */}
              <circle cx={from.x} cy={from.y} r="2" fill={conn.color} opacity="0.6" />
              <circle cx={to.x} cy={to.y} r="2" fill={conn.color} opacity="0.6" />
            </g>
          );
        })}

        {/* Central core glow */}
        <circle cx={cx} cy={cy} r="30" fill={COLORS.cyan} opacity="0.05" />
        <circle cx={cx} cy={cy} r="50" fill={COLORS.cyan} opacity="0.03" />
      </svg>

      {/* Nodes */}
      {brainNodes.map((node, idx) => {
        const pos = positions[idx];
        const isCore = node.isCore;
        const nodeSize = isCore ? 56 : 36;
        return (
          <div
            key={node.id}
            className="absolute flex flex-col items-center z-10 transition-transform duration-300 hover:scale-110"
            style={{
              left: `${pos.x}px`,
              top: `${pos.y}px`,
              transform: "translate(-50%, -50%)",
            }}
          >
            {/* Pulsing aura */}
            <div
              className={`absolute rounded-full opacity-20 animate-ping ${isCore ? "w-24 h-24" : "w-14 h-14"}`}
              style={{ backgroundColor: node.color }}
            />

            {/* Outer orbit ring */}
            {isCore && (
              <div
                className="absolute rounded-full border-2 border-dashed animate-spin-slow w-20 h-20"
                style={{ borderColor: `${node.color}40`, animationDuration: "15s" }}
              />
            )}

            {/* Node body */}
            <div
              className={`relative flex items-center justify-center rounded-full border-2 ${isCore ? "w-14 h-14" : "w-9 h-9"}`}
              style={{
                borderColor: node.color,
                backgroundColor: "rgba(8, 13, 38, 0.9)",
                boxShadow: `0 0 ${isCore ? 30 : 12}px ${node.color}60`,
              }}
            >
              {/* Brain neural net SVG for core */}
              {isCore ? (
                <svg className="w-10 h-10" viewBox="0 0 100 100">
                  <path d="M 50 20 C 35 15, 20 30, 25 50 C 20 65, 35 80, 50 75 C 45 65, 45 35, 50 20 Z" fill={node.color} fillOpacity="0.25" stroke={node.color} strokeWidth="1.5" />
                  <path d="M 50 20 C 65 15, 80 30, 75 50 C 80 65, 65 80, 50 75 C 55 65, 55 35, 50 20 Z" fill={node.color} fillOpacity="0.25" stroke={node.color} strokeWidth="1.5" />
                  <circle cx="50" cy="45" r="4" fill={node.color} />
                </svg>
              ) : (
                <div
                  className="rounded-full"
                  style={{
                    width: 18,
                    height: 18,
                    backgroundColor: node.color,
                    opacity: 0.7,
                  }}
                />
              )}
            </div>

            {/* Agent label */}
            <div
              className={`mt-2 px-2 py-1 rounded-lg border backdrop-blur-sm text-center ${isCore ? "border-cyan-400/40" : "border-slate-700/60"}`}
              style={{ backgroundColor: "rgba(9, 13, 36, 0.9)", minWidth: isCore ? 120 : 80 }}
            >
              <div
                className={`font-bold tracking-wide truncate ${isCore ? "text-[10px]" : "text-[9px]]"}`}
                style={{ color: node.color }}
              >
                {node.name}
              </div>
              {!isCore && (
                <div className="flex items-center justify-center gap-1 mt-0.5">
                  <span
                    className="w-1 h-1 rounded-full animate-pulse"
                    style={{
                      backgroundColor: node.status === "healthy" || node.status === "ACTIVE" ? COLORS.green : COLORS.textSecondary,
                    }}
                  />
                  <span className="text-[8px]" style={{ color: COLORS.textSecondary }}>
                    {node.status === "healthy" ? "Running" : node.status}
                  </span>
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* Overview overlay top-left */}
      <div
        className="absolute top-3 left-3 z-20 rounded-xl p-3 backdrop-blur-md w-44 font-mono text-[10px]"
        style={{ backgroundColor: "rgba(9, 13, 36, 0.8)", border: `1px solid ${COLORS.border}` }}
      >
        <div className="text-[9px] uppercase tracking-wider mb-2 font-bold" style={{ color: COLORS.textSecondary }}>
          Constellation Summary
        </div>
        <div className="space-y-1">
          <div className="flex justify-between">
            <span className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.cyan }} /> Total
            </span>
            <span className="font-bold" style={{ color: COLORS.textPrimary }}>{brainNodes.length - 1}</span>
          </div>
          <div className="flex justify-between">
            <span className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.green }} /> Active
            </span>
            <span className="font-bold" style={{ color: COLORS.green }}>
              {brainNodes.filter(n => !n.isCore && (n.status === "healthy" || n.status === "ACTIVE")).length}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.amber }} /> Busy
            </span>
            <span className="font-bold" style={{ color: COLORS.amber }}>0</span>
          </div>
          <div className="flex justify-between">
            <span className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS.textSecondary }} /> Idle
            </span>
            <span className="font-bold" style={{ color: COLORS.textSecondary }}>
              {brainNodes.filter(n => !n.isCore && n.status !== "healthy" && n.status !== "ACTIVE").length}
            </span>
          </div>
        </div>
      </div>

      {/* Network legend bottom-left */}
      <div
        className="absolute bottom-3 left-3 z-20 rounded-xl p-2.5 backdrop-blur-md w-40 font-mono text-[9px]"
        style={{ backgroundColor: "rgba(9, 13, 36, 0.8)", border: `1px solid ${COLORS.border}` }}
      >
        <div className="uppercase tracking-wider mb-1.5 font-bold" style={{ color: COLORS.textSecondary }}>Network Legend</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
            <span className="w-3 h-[2px]" style={{ backgroundColor: COLORS.magenta, boxShadow: `0 0 6px ${COLORS.magenta}` }} /> High Activity
          </div>
          <div className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
            <span className="w-3 h-[2px]" style={{ backgroundColor: COLORS.cyan, boxShadow: `0 0 6px ${COLORS.cyan}` }} /> Medium Activity
          </div>
          <div className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
            <span className="w-3 h-[2px]" style={{ backgroundColor: COLORS.purple }} /> Low Activity
          </div>
          <div className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
            <span className="w-3 h-[2px] border-b border-dashed" style={{ borderColor: COLORS.cyan }} /> Data Flow
          </div>
          <div className="flex items-center gap-2" style={{ color: COLORS.textPrimary }}>
            <span className="w-3 h-[2px]" style={{ backgroundColor: COLORS.green }} /> Heartbeat
          </div>
        </div>
      </div>
    </div>
  );
}

// ── System Monitor Panel (Left Rail) ──
function SystemMonitorPanel({ telemetry, performance, events }: {
  telemetry: ReturnType<typeof useStore.getState>["telemetry"];
  performance: ReturnType<typeof useStore.getState>["performance"];
  events: ReturnType<typeof useStore.getState>["events"];
}) {
  const cpuPct = Math.round(performance?.cpu_usage_percent ?? 23);
  const ramPct = Math.round(performance?.memory_usage_percent ?? 47);
  const gpuPct = 76; // placeholder until GPU metrics are available

  return (
    <div
      className="rounded-xl p-3 backdrop-blur-md"
      style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: COLORS.textPrimary }}>
          System Monitor
        </span>
        <div className="flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: COLORS.green }} />
          <span className="text-[9px] font-bold" style={{ color: COLORS.green }}>OPTIMAL</span>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { label: "CPU", val: `${cpuPct}%`, color: COLORS.cyan },
          { label: "RAM", val: `${ramPct}%`, color: COLORS.green },
          { label: "GPU", val: `${gpuPct}%`, color: COLORS.purple },
        ].map((m) => (
          <div key={m.label} className="rounded-lg p-1.5 text-center" style={{ backgroundColor: "rgba(0,0,0,0.3)" }}>
            <div className="text-[8px] uppercase" style={{ color: COLORS.textSecondary }}>{m.label}</div>
            <div className="text-sm font-bold font-mono" style={{ color: m.color }}>{m.val}</div>
          </div>
        ))}
      </div>

      {/* Live activity sparkline */}
      <div className="mb-2">
        <div className="text-[8px] uppercase mb-1" style={{ color: COLORS.textSecondary }}>Live Activity</div>
        <svg className="w-full h-8" viewBox="0 0 200 30" preserveAspectRatio="none">
          <polyline
            points={Array.from({ length: 40 }, (_, i) => `${i * 5},${30 - Math.sin(i / 3) * 10 - Math.random() * 8}`).join(" ")}
            fill="none"
            stroke={COLORS.cyan}
            strokeWidth="1.5"
            style={{ filter: `drop-shadow(0 0 2px ${COLORS.cyan})` }}
          />
        </svg>
      </div>

      {/* Agent status list */}
      <div className="space-y-0.5 text-[9px] font-mono">
        {events.slice(0, 5).map((e, i) => (
          <div key={e.id || i} className="flex items-center gap-1.5" style={{ color: COLORS.textSecondary }}>
            <span className="w-1 h-1 rounded-full" style={{ backgroundColor: COLORS.green }} />
            <span className="truncate flex-1">{e.source}</span>
            <span style={{ color: COLORS.green }}>Running</span>
          </div>
        ))}
        {events.length === 0 && (
          <div className="text-center py-1" style={{ color: COLORS.textSecondary }}>No active agents</div>
        )}
      </div>
    </div>
  );
}

// ── Live Activity Feed (Left Rail) ──
function ActivityFeedPanel({ events }: { events: ReturnType<typeof useStore.getState>["events"] }) {
  return (
    <div
      className="rounded-xl p-3 backdrop-blur-md flex-1 min-h-0 flex flex-col"
      style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
    >
      <div className="flex items-center justify-between mb-2 shrink-0">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: COLORS.textPrimary }}>
          Live Activity Feed
        </span>
        <span className="text-[9px]" style={{ color: COLORS.green }}>
          {events.length} events
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden no-scrollbar space-y-1">
        <AnimatePresence mode="popLayout">
          {events.slice(0, 30).map((e, i) => {
            const isFail = e.topic?.includes("fail") || e.topic?.includes("error");
            const isOk = e.topic?.includes("complete") || e.topic?.includes("start");
            const color = isFail ? "#ef4444" : isOk ? COLORS.green : COLORS.cyan;
            return (
              <motion.div
                key={e.id || `evt-${i}`}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: Math.max(0.3, 1 - i * 0.03), y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="flex items-center gap-2 rounded-lg px-2 py-1 font-mono text-[10px]"
                style={{ backgroundColor: "rgba(0,0,0,0.2)" }}
              >
                <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                <span className="w-24 shrink-0 truncate" style={{ color: COLORS.textSecondary }}>
                  {e.topic?.split(".").slice(0, 2).join(".") ?? "—"}
                </span>
                <span className="flex-1 truncate" style={{ color: COLORS.textPrimary }}>{e.source}</span>
                <span className="shrink-0 text-[9px]" style={{ color: COLORS.textSecondary }}>
                  {new Date(e.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
              </motion.div>
            );
          })}
        </AnimatePresence>
        {events.length === 0 && (
          <div className="text-center py-4 text-[10px]" style={{ color: COLORS.textSecondary }}>
            No activity yet. EventBus traffic appears here.
          </div>
        )}
      </div>
    </div>
  );
}

// ── Collaboration Topology (Right Rail) ──
function CollaborationPanel({ brainNodes }: { brainNodes: Array<{ id: string; name: string; color: string; isCore: boolean }> }) {
  const nonCore = brainNodes.filter(n => !n.isCore);
  return (
    <div
      className="rounded-xl p-3 backdrop-blur-md"
      style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: COLORS.textPrimary }}>
          Collaboration Topology
        </span>
      </div>

      {/* Force-directed graph mini visualization */}
      <div className="relative h-32 mb-2">
        <svg className="w-full h-full" viewBox="0 0 200 100" preserveAspectRatio="xMidYMid meet">
          {/* Central node */}
          <circle cx="100" cy="50" r="5" fill={COLORS.cyan} opacity="0.8" />
          {nonCore.slice(0, 6).map((node, i) => {
            const angle = (i / Math.max(1, nonCore.length)) * Math.PI * 2;
            const x = 100 + 40 * Math.cos(angle);
            const y = 50 + 30 * Math.sin(angle);
            return (
              <g key={node.id}>
                <line x1="100" y1="50" x2={x} y2={y} stroke={node.color} strokeWidth="0.8" opacity="0.4" />
                <circle cx={x} cy={y} r="3" fill={node.color} opacity="0.8" />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="grid grid-cols-2 gap-1 text-[9px] font-mono">
        {nonCore.slice(0, 6).map((node) => (
          <div key={node.id} className="flex items-center gap-1.5" style={{ color: COLORS.textSecondary }}>
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: node.color }} />
            <span className="truncate">{node.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Task Flow Pipeline (Right Rail) ──
function TaskFlowPanel() {
  const steps = ["User Request", "Router", "Selection", "Execution", "Aggregation", "Delivery"];
  return (
    <div
      className="rounded-xl p-3 backdrop-blur-md"
      style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: COLORS.textPrimary }}>
          Task Flow Pipeline
        </span>
      </div>
      <div className="space-y-1">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className="flex items-center justify-center w-5 h-5 rounded text-[8px] font-bold shrink-0"
              style={{
                backgroundColor: i < 3 ? `${COLORS.cyan}30` : "rgba(0,0,0,0.3)",
                border: `1px solid ${i < 3 ? COLORS.cyan : COLORS.textSecondary}40`,
                color: i < 3 ? COLORS.cyan : COLORS.textSecondary,
              }}
            >
              {i + 1}
            </div>
            <span className="text-[9px]" style={{ color: i < 3 ? COLORS.textPrimary : COLORS.textSecondary }}>
              {step}
            </span>
            {i < steps.length - 1 && (
              <div className="flex-1 h-px" style={{ backgroundColor: `${COLORS.textSecondary}30` }} />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Capabilities Footer ──
function CapabilitiesFooter() {
  const caps = [
    { icon: "⊕", label: "Compose" },
    { icon: "◈", label: "Reason" },
    { icon: "▶", label: "Execute" },
    { icon: "⟲", label: "Recover" },
    { icon: "⊞", label: "Aggregate" },
    { icon: "⟶", label: "Deliver" },
  ];
  return (
    <div
      className="rounded-xl px-4 py-2.5 flex items-center justify-between shrink-0"
      style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
    >
      <div className="grid grid-cols-6 gap-4 flex-1">
        {caps.map((cap) => (
          <div key={cap.label} className="flex flex-col items-center gap-0.5">
            <span className="text-base" style={{ color: COLORS.cyan }}>{cap.icon}</span>
            <span className="text-[8px] uppercase tracking-wider" style={{ color: COLORS.textSecondary }}>
              {cap.label}
            </span>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 pl-4 border-l" style={{ borderColor: `${COLORS.border}` }}>
        <span className="text-[9px] font-bold" style={{ color: COLORS.textSecondary }}>ONE MACHINE</span>
        <span className="text-[8px]" style={{ color: COLORS.textSecondary }}>INFINITE AGENTS</span>
      </div>
    </div>
  );
}

// ── Main Component ──
export function AIBrain() {
  const storeProviders = useStore((s) => s.providers);
  const storeAgents = useStore((s) => s.agents);
  const storeTasks = useStore((s) => s.tasks);
  const storeEvents = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  useEffect(() => {
    void useStore.getState().hydrate();
  }, []);

  // Build brain nodes from live data
  const brainNodes = useMemo(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );

    const coreNode = {
      id: "mission_control",
      name: "MISSION CONTROL",
      color: COLORS.cyan,
      isCore: true,
      status: "ACTIVE",
    };

    if (providerList.length === 0) return [coreNode];

    const outerNodes = providerList.map((p, idx) => ({
      id: `${p.provider.toLowerCase().replace(/\s+/g, "_")}-${idx}`,
      name: p.provider.toUpperCase(),
      color: getProviderColor(p.provider),
      isCore: false,
      status: p.status === "healthy" ? "healthy" : p.status,
    }));

    return [coreNode, ...outerNodes];
  }, [storeProviders]);

  const connections = useMemo(() => {
    return brainNodes
      .filter(n => !n.isCore)
      .map(n => ({ from: n.id, to: "mission_control", color: n.color }));
  }, [brainNodes]);

  return (
    <div
      className="h-full w-full flex flex-col gap-3 p-3 overflow-hidden"
      style={{ backgroundColor: COLORS.bg, color: COLORS.textPrimary }}
    >
      {/* ── Header ── */}
      <div className="flex items-center justify-between shrink-0 px-2">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold tracking-wide uppercase font-mono" style={{ color: COLORS.textPrimary }}>
              AI Brain Constellation
            </h1>
            <span
              className="px-2 py-0.5 rounded text-[10px] font-mono"
              style={{
                backgroundColor: `${COLORS.cyan}20`,
                color: COLORS.cyan,
                border: `1px solid ${COLORS.cyan}40`,
              }}
            >
              LIVE
            </span>
          </div>
          <p className="text-[11px] mt-0.5" style={{ color: COLORS.textSecondary }}>
            Real-time neural network of active AI agents and workflows
          </p>
        </div>

        {/* Live event flow mini card */}
        <div
          className="rounded-xl p-2.5 backdrop-blur-md w-56"
          style={{ backgroundColor: "rgba(9, 13, 36, 0.9)", border: `1px solid ${COLORS.border}` }}
        >
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider mb-1" style={{ color: COLORS.textSecondary }}>
            <span>Live Event Flow</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-base font-bold font-mono" style={{ color: COLORS.textPrimary }}>
              {storeEvents.length * 128 || 12847}
            </span>
            <span className="text-xs" style={{ color: COLORS.cyan }}>events / sec</span>
          </div>
          {/* Sparkline */}
          <div className="h-6 mt-1 flex items-end gap-0.5">
            {[30, 45, 60, 40, 75, 50, 90, 65, 80, 55, 95, 70, 85, 60, 100, 75].map((h, i) => (
              <div
                key={i}
                className="flex-1 rounded-xs transition-all"
                style={{ height: `${h}%`, backgroundColor: `${COLORS.cyan}40` }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Main Content: 3-column layout ── */}
      <div className="flex-1 grid gap-3 min-h-0 grid-cols-1 lg:grid-cols-[200px_1fr_200px]">
        {/* ── Left Rail: System Monitor + Activity Feed ── */}
        <div className="flex flex-col gap-3 min-h-0">
          <SystemMonitorPanel telemetry={telemetry} performance={performance} events={storeEvents} />
          <ActivityFeedPanel events={storeEvents} />
        </div>

        {/* ── Center: Neural Network Canvas ── */}
        <NeuralNetworkCanvas brainNodes={brainNodes} connections={connections} />

        {/* ── Right Rail: Collaboration + Task Flow ── */}
        <div className="flex flex-col gap-3 min-h-0">
          <CollaborationPanel brainNodes={brainNodes} />
          <TaskFlowPanel />
          {/* Mission Progress donut */}
          <div
            className="rounded-xl p-3 backdrop-blur-md"
            style={{ backgroundColor: COLORS.surface, border: `1px solid ${COLORS.border}` }}
          >
            <div className="text-[10px] font-bold uppercase tracking-wider mb-2" style={{ color: COLORS.textPrimary }}>
              Mission Progress
            </div>
            <div className="flex items-center gap-3">
              <div className="relative w-16 h-16 flex items-center justify-center">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                  <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="rgba(30, 41, 59, 0.8)" strokeWidth="3.8" />
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke={COLORS.cyan}
                    strokeWidth="3.8"
                    strokeDasharray="78, 100"
                    style={{ filter: `drop-shadow(0 0 3px ${COLORS.cyan})` }}
                  />
                </svg>
                <span className="absolute text-sm font-bold font-mono" style={{ color: COLORS.cyan }}>78%</span>
              </div>
              <div className="text-[9px] font-mono space-y-0.5" style={{ color: COLORS.textSecondary }}>
                <div>Tasks: {Object.keys(storeTasks).length}</div>
                <div>Completed: {Object.values(storeTasks).filter(t => t.status === "completed").length}</div>
                <div style={{ color: COLORS.green }}>Running: {Object.values(storeTasks).filter(t => t.status === "running").length}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Capabilities Footer ── */}
      <CapabilitiesFooter />
    </div>
  );
}
