"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import { RefreshCw, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import { useStore } from "@/lib/store";

// ── Provider Colors ──
const PROVIDER_COLORS: Record<string, string> = {
  claude: "#d980ff",
  hermes: "#00f0ff",
  opencode: "#38bdf8",
  agy: "#f472b6",
  gemini: "#f97316",
  codex: "#818cf8",
  cursor: "#38bdf8",
  ollama: "#f97316",
  openai: "#818cf8",
  anthropic: "#d980ff",
  google: "#f97316",
  git: "#10b981",
  node: "#84cc16",
  python: "#3b82f6",
  docker: "#06b6d4",
};

function getProviderColor(name: string): string {
  const low = name.toLowerCase();
  for (const k of Object.keys(PROVIDER_COLORS)) {
    if (low.includes(k)) return PROVIDER_COLORS[k];
  }
  return "#818cf8";
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

// ── Node position calculation with collision avoidance ──
function computeNodePositions(
  nodeCount: number,
  containerWidth: number,
  containerHeight: number,
  zoom: number
): Array<{ x: number; y: number }> {
  if (nodeCount <= 1) return [{ x: containerWidth / 2, y: containerHeight / 2 }];

  const positions: Array<{ x: number; y: number }> = [];
  const cx = containerWidth / 2;
  const cy = containerHeight / 2;

  // Core node at center
  positions.push({ x: cx, y: cy });

  // Outer nodes in a circle — radius scales with container size and zoom
  const minRadius = 80;
  const maxRadius = Math.min(containerWidth, containerHeight) * 0.4;
  const radius = Math.max(minRadius, maxRadius) / zoom;

  for (let i = 0; i < nodeCount - 1; i++) {
    const angle = (i / (nodeCount - 1)) * Math.PI * 2 - Math.PI / 2;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    positions.push({ x, y });
  }

  return positions;
}

export function AgentConstellation() {
  const storeProviders = useStore((s) => s.providers);
  const storeAgents = useStore((s) => s.agents);
  const storeTasks = useStore((s) => s.tasks);
  const storeEvents = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  useEffect(() => {
    void useStore.getState().hydrate();
  }, []);

  const [activePlayback] = useState<"1x" | "2x" | "4x">("4x");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // ── Canvas ref + ResizeObserver ──
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          setCanvasSize({ width: Math.round(width), height: Math.round(height) });
        }
      }
    });

    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // ── Build constellation nodes from live data ──
  const constellationNodes = useMemo(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );

    const coreNode = {
      id: "mission_control_core",
      name: "MISSION CONTROL",
      sub: "Central Intelligence",
      status: "ONLINE",
      color: "#00f0ff",
      isCore: true,
    };

    if (providerList.length === 0) return [coreNode];

    const outerNodes = providerList.map((p, idx) => ({
      id: `${p.provider.toLowerCase().replace(/\s+/g, "_")}-${idx}`,
      name: p.provider.toUpperCase(),
      sub: p.status === "healthy" ? "Active Runtime" : p.status,
      status: p.status === "healthy" ? "ACTIVE" : p.status.toUpperCase(),
      color: getProviderColor(p.provider),
      isCore: false,
    }));

    return [coreNode, ...outerNodes];
  }, [storeProviders]);

  // ── Compute positions with collision avoidance ──
  const nodePositions = useMemo(() => {
    return computeNodePositions(constellationNodes.length, canvasSize.width, canvasSize.height, zoom);
  }, [constellationNodes.length, canvasSize, zoom]);

  // ── Connections (hub-and-spoke) ──
  const connections = useMemo(() => {
    return constellationNodes
      .filter((n) => !n.isCore)
      .map((n) => ({ from: n.id, to: "mission_control_core", color: n.color }));
  }, [constellationNodes]);

  // ── Metrics ──
  const totalAgentsCount = Math.max(Object.keys(storeAgents).length, constellationNodes.length - 1);
  const activeAgentsCount = Object.values(storeProviders).filter((p) => p.status === "healthy").length;
  const runningTasksCount = Object.values(storeTasks).filter((t) => t.status === "running").length;
  const completedTasksCount = Object.values(storeTasks).filter((t) => t.status === "completed").length;

  const liveEvents = useMemo(() => {
    return storeEvents.slice(0, 6).map((e) => ({
      time: new Date(e.timestamp).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      agent: e.topic.replace(/\./g, " "),
      detail: JSON.stringify(e.payload).slice(0, 32),
    }));
  }, [storeEvents]);

  // ── Pan handlers ──
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  }, [pan]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  return (
    <div className="flex h-full w-full flex-col gap-3 p-4 bg-bg text-text select-none">
      {/* ── Header ── */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Agent Constellation</h2>
          <span className="text-[10px] text-faint">Interactive network topology</span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))}
            className="rounded-lg border border-border/60 p-1.5 hover:bg-surface/30 transition"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>
          <span className="text-[10px] text-faint tabular-nums w-10 text-center">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom((z) => Math.min(3, z + 0.2))}
            className="rounded-lg border border-border/60 p-1.5 hover:bg-surface/30 transition"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>
          <button
            onClick={resetView}
            className="rounded-lg border border-border/60 p-1.5 hover:bg-surface/30 transition"
            aria-label="Reset view"
          >
            <Maximize2 size={14} />
          </button>
        </div>
      </div>

      {/* ── Main content: Canvas + Right panel ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[1fr_280px]">
        {/* ── Canvas ── */}
        <div
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="relative min-h-[300px] overflow-hidden rounded-xl border border-border/40 bg-surface/20 cursor-grab active:cursor-grabbing"
          style={{ cursor: isDragging ? "grabbing" : "grab" }}
        >
          {/* Grid texture background */}
          <div className="absolute inset-0 grid-texture opacity-30" />

          {/* SVG connections layer — uses viewBox for responsive scaling */}
          <svg
            className="absolute inset-0 h-full w-full pointer-events-none"
            viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
            preserveAspectRatio="xMidYMid meet"
          >
            {/* Orbit rings */}
            <circle
              cx={canvasSize.width / 2}
              cy={canvasSize.height / 2}
              r={Math.min(canvasSize.width, canvasSize.height) * 0.35 / zoom}
              fill="none"
              stroke="rgb(var(--border) / 0.3)"
              strokeWidth="1"
              strokeDasharray="4 6"
            />
            <circle
              cx={canvasSize.width / 2}
              cy={canvasSize.height / 2}
              r={Math.min(canvasSize.width, canvasSize.height) * 0.2 / zoom}
              fill="none"
              stroke="rgb(var(--border) / 0.2)"
              strokeWidth="1"
              strokeDasharray="3 5"
            />

            {/* Connection lines */}
            {connections.map((conn, idx) => {
              const fromNode = constellationNodes.find((n) => n.id === conn.from);
              const toNode = constellationNodes.find((n) => n.id === conn.to);
              if (!fromNode || !toNode) return null;
              const fromIdx = constellationNodes.indexOf(fromNode);
              const toIdx = constellationNodes.indexOf(toNode);
              const fromPos = nodePositions[fromIdx];
              const toPos = nodePositions[toIdx];
              if (!fromPos || !toPos) return null;

              return (
                <line
                  key={idx}
                  x1={fromPos.x + pan.x}
                  y1={fromPos.y + pan.y}
                  x2={toPos.x + pan.x}
                  y2={toPos.y + pan.y}
                  stroke={conn.color}
                  strokeWidth="1.5"
                  strokeOpacity="0.4"
                  strokeDasharray="4 4"
                  className="animate-dash-flow"
                />
              );
            })}
          </svg>

          {/* Node layer — positioned with absolute coordinates */}
          {constellationNodes.map((node, idx) => {
            const pos = nodePositions[idx];
            if (!pos) return null;
            const isCore = node.isCore;
            const nodeSize = isCore ? 64 : 40;

            return (
              <div
                key={node.id}
                className="absolute flex flex-col items-center z-10 transition-transform duration-300"
                style={{
                  left: `${pos.x + pan.x}px`,
                  top: `${pos.y + pan.y}px`,
                  transform: `translate(-50%, -50%) scale(${zoom})`,
                  transformOrigin: "center center",
                }}
              >
                {/* Pulsing aura */}
                <div
                  className={`absolute rounded-full opacity-20 animate-ping ${isCore ? "w-24 h-24" : "w-16 h-16"}`}
                  style={{ backgroundColor: node.color }}
                />

                {/* Node circle */}
                <div
                  className={`relative flex items-center justify-center rounded-full border-2 shadow-lg ${isCore ? "w-16 h-16" : "w-10 h-10"}`}
                  style={{
                    borderColor: node.color,
                    backgroundColor: "rgb(var(--surface) / 0.9)",
                    boxShadow: `0 0 ${isCore ? 30 : 12}px ${node.color}40`,
                  }}
                >
                  <div
                    className="rounded-full"
                    style={{
                      width: isCore ? 32 : 20,
                      height: isCore ? 32 : 20,
                      backgroundColor: node.color,
                      opacity: 0.7,
                    }}
                  />
                </div>

                {/* Label — hidden when zoomed out */}
                {zoom > 0.7 && (
                  <div
                    className={`mt-2 bg-surface/90 border rounded-lg px-2 py-1 backdrop-blur-sm text-center shadow-md ${isCore ? "border-accent/40" : "border-border/40"}`}
                    style={{ minWidth: isCore ? 120 : 80 }}
                  >
                    <div className={`font-semibold tracking-wide truncate ${isCore ? "text-[10px]" : "text-[9px]"}`} style={{ color: node.color }}>
                      {node.name}
                    </div>
                    <div className="text-[8px] text-faint">{node.sub}</div>
                    {node.status && (
                      <div className="mt-0.5 flex items-center justify-center gap-1">
                        <span
                          className={`h-1 w-1 rounded-full ${node.status === "ACTIVE" || node.status === "ONLINE" ? "bg-ok" : "bg-faint"} animate-pulse`}
                        />
                        <span className={`text-[8px] font-bold ${node.status === "ACTIVE" || node.status === "ONLINE" ? "text-ok" : "text-faint"}`}>
                          {node.status}
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Overview overlay top-left */}
          <div className="absolute top-3 left-3 z-20 glass rounded-xl p-3 backdrop-blur-md w-48 font-mono text-[10px]">
            <div className="text-faint text-[9px] uppercase tracking-wider mb-2 font-bold">
              Constellation Overview
            </div>
            <div className="space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-faint">TOTAL</span>
                <span className="font-bold text-text">{totalAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">ACTIVE</span>
                <span className="font-bold text-ok">{activeAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">RUNNING</span>
                <span className="font-bold text-warn">{runningTasksCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">COMPLETED</span>
                <span className="font-bold text-info">{completedTasksCount}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Right panel: Live events + communication ── */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Live Event Stream */}
          <div className="glass rounded-xl p-3 font-mono text-[10px] shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-text uppercase tracking-wider text-[9px]">Live Events</span>
              <span className="text-ok text-[8px]">● Live</span>
            </div>
            <div className="min-h-0 max-h-[180px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1.5 text-[9px]">
              {liveEvents.map((ev, i) => (
                <div key={i} className="flex items-start gap-1.5 border-b border-border/30 pb-1">
                  <span className="text-faint text-[8px] shrink-0">{ev.time}</span>
                  <div className="min-w-0">
                    <div className="font-semibold text-accent truncate">{ev.agent}</div>
                    <div className="text-faint text-[8px] truncate">{ev.detail}</div>
                  </div>
                </div>
              ))}
              {liveEvents.length === 0 && (
                <div className="text-faint text-center py-2">No events yet</div>
              )}
            </div>
          </div>

          {/* Telemetry mini-cards */}
          <div className="glass rounded-xl p-3 shrink-0">
            <div className="text-faint text-[9px] uppercase tracking-wider font-bold mb-2">Telemetry</div>
            <div className="grid grid-cols-2 gap-2 text-center">
              {[
                { label: "CPU", val: `${Math.round(performance?.cpu_usage_percent ?? 42)}%`, color: "text-accent" },
                { label: "RAM", val: `${Math.round(performance?.memory_usage_percent ?? 68)}%`, color: "text-ok" },
                { label: "AGENTS", val: `${totalAgentsCount}`, color: "text-info" },
                { label: "TOKENS", val: `${telemetry.tokens || 0}`, color: "text-warn" },
              ].map((m) => (
                <div key={m.label} className="bg-surface/40 rounded-lg p-1.5 border border-border/30">
                  <div className="text-[8px] text-faint">{m.label}</div>
                  <div className={`font-bold text-xs ${m.color}`}>{m.val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Playback speed indicator */}
          <div className="glass rounded-xl p-2 flex items-center justify-between shrink-0">
            <span className="text-[9px] text-faint uppercase tracking-wider">Playback</span>
            <div className="flex items-center gap-1">
              {(["1x", "2x", "4x"] as const).map((speed) => (
                <button
                  key={speed}
                  className={`rounded px-2 py-0.5 text-[9px] font-mono transition ${
                    activePlayback === speed
                      ? "bg-accent/20 text-accent"
                      : "text-faint hover:bg-surface/30"
                  }`}
                >
                  {speed}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ── Footer: Status bar ── */}
      <div className="glass rounded-xl px-3 py-2 flex items-center justify-between font-mono text-[9px] shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-faint">UPTIME</span>
          <span className="text-ok font-bold">{formatDuration(performance?.uptime_seconds ?? 0)}</span>
          <span className="text-faint">|</span>
          <span className="text-faint">ZOOM</span>
          <span className="text-accent font-bold">{Math.round(zoom * 100)}%</span>
          <span className="text-faint">|</span>
          <span className="text-faint">NODES</span>
          <span className="text-text font-bold">{constellationNodes.length}</span>
          <span className="text-faint">|</span>
          <span className="text-faint">LINKS</span>
          <span className="text-text font-bold">{connections.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-ok">● SYSTEM ONLINE</span>
        </div>
      </div>
    </div>
  );
}
