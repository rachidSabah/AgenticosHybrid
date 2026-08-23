"use client";

import { useEffect, useMemo, useState, useRef, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  Activity,
  Cpu,
  Zap,
  X,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  Clock,
  Radio,
  Layers,
  ArrowRight,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { useBrainsStore } from "@/lib/use-brains";
import type { EventEnvelope, ExecutionRecord, AgentNode, TaskNode } from "@/lib/types";

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
  deepseek: "#38bdf8",
  qwen: "#a855f7",
  mistral: "#f59e0b",
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

// ── Agent State Definitions ──
export type AgentLiveState =
  | "OFFLINE"
  | "UNKNOWN"
  | "IDLE"
  | "QUEUED"
  | "THINKING"
  | "EXECUTING"
  | "COMMUNICATING"
  | "WAITING"
  | "COMPLETED"
  | "FAILED"
  | "RETRYING";

export type ActivityIntensity = "NONE" | "LOW" | "MEDIUM" | "HIGH";

export interface ConstellationNodeData {
  id: string;
  name: string;
  rawName: string;
  sub: string;
  liveState: AgentLiveState;
  intensity: ActivityIntensity;
  color: string;
  isCore: boolean;
  runtime?: string;
  provider?: string;
  model?: string;
  currentTaskTitle?: string;
  currentOperation?: string;
  tokensCount?: number;
  toolCallsCount?: number;
  lastEventTime?: string;
  lastEventTopic?: string;
  error?: string;
  retryCount?: number;
  durationMs?: number;
  isParticipant: boolean;
}

export interface ConstellationConnectionData {
  id: string;
  from: string;
  to: string;
  color: string;
  state: "INACTIVE" | "ACTIVE" | "HIGH_ACTIVITY" | "COMMUNICATION" | "COMPLETED" | "ERROR";
  direction?: "forward" | "backward" | "bidirectional";
  particleCount: number;
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
  const minRadius = 90;
  const maxRadius = Math.min(containerWidth, containerHeight) * 0.38;
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
  const storeExecutions = useStore((s) => s.executions);
  const storeMissions = useStore((s) => s.missions);
  const telemetry = useStore((s) => s.telemetry);
  const performance = useStore((s) => s.performance);

  const brains = useBrainsStore((s) => s.brains);
  const brainRelationships = useBrainsStore((s) => s.relationships);

  useEffect(() => {
    void useStore.getState().hydrate();
    void useStore.getState().hydrateExecutions();
    void useBrainsStore.getState().fetchBrains();
    void useBrainsStore.getState().fetchRelationships();
  }, []);

  const [activePlayback, setActivePlayback] = useState<"1x" | "2x" | "4x">("1x");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

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

  // ── Active Mission Detection ──
  const activeMission = useMemo(() => {
    const missionList = Object.values(storeMissions);
    return (
      missionList.find((m) => m.status === "running" || m.status === "in_progress") ??
      missionList.find((m) => m.status === "planning") ??
      missionList[0] ??
      null
    );
  }, [storeMissions]);

  // ── Recent Event Analysis per Agent/Provider ──
  const recentEventMap = useMemo(() => {
    const map = new Map<string, EventEnvelope>();
    for (const ev of storeEvents) {
      const p = ev.payload as Record<string, any>;
      const candidates = [
        p.provider,
        p.agent_id,
        p.agent,
        p.source,
        p.principal,
        p.id,
        p.name,
      ].filter(Boolean).map(String);

      for (const cand of candidates) {
        const low = cand.toLowerCase();
        if (!map.has(low)) {
          map.set(low, ev);
        }
      }
    }
    return map;
  }, [storeEvents]);

  // ── Recent Active Executions per Provider/Agent ──
  const activeExecutionsMap = useMemo(() => {
    const map = new Map<string, ExecutionRecord>();
    for (const exec of Object.values(storeExecutions)) {
      const keys = [exec.provider, exec.agent_id, exec.runtime].filter(Boolean).map((s) => s.toLowerCase());
      for (const k of keys) {
        if (!map.has(k) || exec.status === "running") {
          map.set(k, exec);
        }
      }
    }
    return map;
  }, [storeExecutions]);

  // ── Build Constellation Nodes from Live Data ──
  const constellationNodes = useMemo<ConstellationNodeData[]>(() => {
    const providerList = Object.values(storeProviders).filter(
      (p) => p?.provider && !["mock", "Mock"].includes(p.provider)
    );

    const brainList = Object.values(brains);

    const agentMap = new Map<string, {
      name: string;
      providerKey: string;
      healthStatus: string;
      latencyMs: number;
      brainRecord?: any;
    }>();

    // Seed from providers
    for (const prov of providerList) {
      const key = prov.provider.toLowerCase().replace(/\s+/g, "_");
      agentMap.set(key, {
        name: prov.provider,
        providerKey: prov.provider,
        healthStatus: prov.status,
        latencyMs: prov.latency_ms ?? 0,
      });
    }

    // Seed/merge from discovered brains
    for (const br of brainList) {
      const key = (br.display_name || br.id || br.vendor).toLowerCase().replace(/\s+/g, "_");
      const existing = agentMap.get(key);
      if (existing) {
        existing.brainRecord = br;
        if (br.status) existing.healthStatus = br.status;
      } else {
        agentMap.set(key, {
          name: br.display_name || br.id || br.vendor,
          providerKey: br.vendor || br.id,
          healthStatus: br.status || br.health || "unknown",
          latencyMs: br.latency || 0,
          brainRecord: br,
        });
      }
    }

    // Also check agent nodes in store
    for (const ag of Object.values(storeAgents)) {
      const name = ag.provider || ag.role || ag.id;
      const key = name.toLowerCase().replace(/\s+/g, "_");
      if (!agentMap.has(key)) {
        agentMap.set(key, {
          name,
          providerKey: ag.provider || name,
          healthStatus: ag.health || "healthy",
          latencyMs: 0,
        });
      }
    }

    let runningCount = 0;

    const outerNodes: ConstellationNodeData[] = Array.from(agentMap.entries()).map(([key, item], idx) => {
      const provLow = item.providerKey.toLowerCase();
      const nameLow = item.name.toLowerCase();

      const exec = activeExecutionsMap.get(provLow) || activeExecutionsMap.get(nameLow);
      const recentEv = recentEventMap.get(provLow) || recentEventMap.get(nameLow);

      const agentStoreNode = Object.values(storeAgents).find(
        (a) => a.provider?.toLowerCase() === provLow || a.id.toLowerCase() === nameLow
      );

      let liveState: AgentLiveState = "IDLE";
      let intensity: ActivityIntensity = "NONE";
      let isParticipant = false;

      const isOffline = item.healthStatus === "down" || item.healthStatus === "disconnected" || item.healthStatus === "offline";
      const isUnhealthy = item.healthStatus === "unhealthy" || item.healthStatus === "failed";
      const isUnknown = item.healthStatus === "unknown";

      if (isOffline) {
        liveState = "OFFLINE";
        intensity = "NONE";
      } else if (isUnhealthy) {
        liveState = "FAILED";
        intensity = "LOW";
      } else if (isUnknown && !exec && !recentEv) {
        liveState = "UNKNOWN";
        intensity = "NONE";
      } else if (exec?.status === "running") {
        liveState = "EXECUTING";
        intensity = "HIGH";
        isParticipant = true;
        runningCount++;
      } else if (exec?.status === "completed") {
        liveState = "COMPLETED";
        intensity = "LOW";
        isParticipant = true;
      } else if (exec?.status === "failed") {
        liveState = "FAILED";
        intensity = "LOW";
        isParticipant = true;
      } else if (agentStoreNode?.status === "running") {
        liveState = "EXECUTING";
        intensity = "HIGH";
        isParticipant = true;
        runningCount++;
      } else if (recentEv) {
        const topic = recentEv.topic;
        if (topic.includes("started") || topic.includes("dispatched") || topic.includes("assigned")) {
          liveState = "THINKING";
          intensity = "MEDIUM";
          isParticipant = true;
        } else if (topic.includes("tool") || topic.includes("execute") || topic.includes("action")) {
          liveState = "EXECUTING";
          intensity = "HIGH";
          isParticipant = true;
        } else if (topic.includes("message") || topic.includes("collaboration") || topic.includes("delegate")) {
          liveState = "COMMUNICATING";
          intensity = "HIGH";
          isParticipant = true;
        } else if (topic.includes("completed")) {
          liveState = "COMPLETED";
          intensity = "LOW";
          isParticipant = true;
        } else if (topic.includes("failed") || topic.includes("denied")) {
          liveState = "FAILED";
          intensity = "LOW";
          isParticipant = true;
        } else if (topic.includes("retry") || topic.includes("recovered")) {
          liveState = "RETRYING";
          intensity = "MEDIUM";
          isParticipant = true;
        } else {
          liveState = item.healthStatus === "healthy" || item.healthStatus === "online" ? "IDLE" : "UNKNOWN";
          intensity = "NONE";
        }
      } else if (item.healthStatus === "healthy" || item.healthStatus === "online") {
        liveState = "IDLE";
        intensity = "NONE";
      }

      const taskNode = agentStoreNode?.current_task ? storeTasks[agentStoreNode.current_task] : undefined;
      const currentTaskTitle = taskNode?.title || (exec ? `Execution: ${exec.execution_id.slice(0, 8)}` : undefined);
      const currentOp = exec?.command || (recentEv ? recentEv.topic : undefined);

      const color = getProviderColor(item.name);

      return {
        id: `node-${key}-${idx}`,
        name: item.name.toUpperCase(),
        rawName: item.name,
        sub: liveState === "EXECUTING"
          ? "Executing Task"
          : liveState === "THINKING"
          ? "Reasoning / Processing"
          : liveState === "COMMUNICATING"
          ? "Collaborating"
          : liveState === "COMPLETED"
          ? "Task Complete"
          : liveState === "FAILED"
          ? "Execution Error"
          : item.healthStatus === "healthy" || item.healthStatus === "online"
          ? "Active Runtime"
          : item.healthStatus,
        liveState,
        intensity,
        color,
        isCore: false,
        runtime: item.brainRecord?.runtime || (exec?.runtime ? exec.runtime : "Native Engine"),
        provider: item.providerKey,
        model: item.brainRecord?.supported_models?.[0] || exec?.strategy || "Auto-routed",
        currentTaskTitle,
        currentOperation: currentOp,
        tokensCount: telemetry.tokens,
        toolCallsCount: recentEv?.topic.includes("tool") ? 1 : 0,
        lastEventTime: recentEv?.timestamp,
        lastEventTopic: recentEv?.topic,
        error: exec?.error || (item.healthStatus === "failed" ? "Agent unhealthy" : undefined),
        retryCount: exec?.retry_count,
        durationMs: exec?.duration_ms,
        isParticipant,
      };
    });

    // Core Mission Control Node
    const coreLiveState: AgentLiveState = runningCount > 0 ? "EXECUTING" : "IDLE";
    const coreIntensity: ActivityIntensity = runningCount > 0 ? "HIGH" : "LOW";

    const coreNode: ConstellationNodeData = {
      id: "mission_control_core",
      name: "MISSION CONTROL",
      rawName: "Mission Control",
      sub: runningCount > 0 ? `${runningCount} Brains Active` : "Central Orchestrator",
      liveState: coreLiveState,
      intensity: coreIntensity,
      color: "#00f0ff",
      isCore: true,
      currentTaskTitle: activeMission ? activeMission.title : "Fleet Standby",
      currentOperation: activeMission ? `Status: ${activeMission.status}` : "Awaiting Mission Directives",
      isParticipant: true,
    };

    return [coreNode, ...outerNodes];
  }, [
    storeProviders,
    storeAgents,
    storeTasks,
    brains,
    telemetry.tokens,
    activeExecutionsMap,
    recentEventMap,
    activeMission,
  ]);

  // ── Compute positions with collision avoidance ──
  const nodePositions = useMemo(() => {
    return computeNodePositions(constellationNodes.length, canvasSize.width, canvasSize.height, zoom);
  }, [constellationNodes.length, canvasSize, zoom]);

  // ── Intelligent Real Connections ──
  const connections = useMemo<ConstellationConnectionData[]>(() => {
    const list: ConstellationConnectionData[] = [];
    const coreNode = constellationNodes.find((n) => n.isCore);
    if (!coreNode) return list;

    // 1. Hub-and-spoke to core with dynamic execution state
    for (const node of constellationNodes) {
      if (node.isCore) continue;

      let state: ConstellationConnectionData["state"] = "INACTIVE";
      let particleCount = 0;

      if (node.liveState === "EXECUTING" || node.liveState === "COMMUNICATING") {
        state = "HIGH_ACTIVITY";
        particleCount = 3;
      } else if (node.liveState === "THINKING" || node.liveState === "RETRYING") {
        state = "ACTIVE";
        particleCount = 1;
      } else if (node.liveState === "COMPLETED") {
        state = "COMPLETED";
        particleCount = 0;
      } else if (node.liveState === "FAILED") {
        state = "ERROR";
        particleCount = 0;
      }

      list.push({
        id: `conn-core-${node.id}`,
        from: node.id,
        to: "mission_control_core",
        color: node.color,
        state,
        direction: "bidirectional",
        particleCount,
      });
    }

    // 2. Real inter-agent relationships from BrainRegistry
    for (const rel of brainRelationships) {
      const sourceNode = constellationNodes.find(
        (n) => n.rawName.toLowerCase() === rel.source_id.toLowerCase() || n.id.includes(rel.source_id.toLowerCase())
      );
      const targetNode = constellationNodes.find(
        (n) => n.rawName.toLowerCase() === rel.target_id.toLowerCase() || n.id.includes(rel.target_id.toLowerCase())
      );

      if (sourceNode && targetNode && sourceNode.id !== targetNode.id) {
        const isActive = rel.active || sourceNode.liveState === "EXECUTING" || targetNode.liveState === "EXECUTING";
        list.push({
          id: `conn-rel-${rel.id || rel.source_id}-${rel.target_id}`,
          from: sourceNode.id,
          to: targetNode.id,
          color: sourceNode.color,
          state: isActive ? "COMMUNICATION" : "INACTIVE",
          direction: "forward",
          particleCount: isActive ? 2 : 0,
        });
      }
    }

    return list;
  }, [constellationNodes, brainRelationships]);

  // ── Metrics (Truthful & Real) ──
  const totalAgentsCount = Math.max(Object.keys(storeAgents).length, constellationNodes.length - 1);
  const onlineAgentsCount = constellationNodes.filter(
    (n) => !n.isCore && n.liveState !== "OFFLINE" && n.liveState !== "UNKNOWN"
  ).length;
  const runningAgentsCount = constellationNodes.filter(
    (n) => !n.isCore && (n.liveState === "EXECUTING" || n.liveState === "THINKING" || n.liveState === "COMMUNICATING")
  ).length;
  const completedAgentsCount = constellationNodes.filter(
    (n) => !n.isCore && n.liveState === "COMPLETED"
  ).length;

  // ── Selected Node Details ──
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return constellationNodes.find((n) => n.id === selectedNodeId) || null;
  }, [selectedNodeId, constellationNodes]);

  // ── Live Events with Clickable Agent Highlighting ──
  const liveEvents = useMemo(() => {
    return storeEvents.slice(0, 8).map((e) => {
      const p = e.payload as Record<string, any>;
      const agentName = String(p.provider || p.agent_id || p.agent || p.source || e.topic.split(".")[0]);
      return {
        id: e.id,
        rawEvent: e,
        time: new Date(e.timestamp).toLocaleTimeString([], {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
        topic: e.topic,
        agent: agentName,
        detail: p.title || p.status_text || p.command || JSON.stringify(e.payload).slice(0, 38),
      };
    });
  }, [storeEvents]);

  // ── Pan Handlers ──
  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if ((e.target as HTMLElement).closest("button") || (e.target as HTMLElement).closest(".constellation-node")) {
        return;
      }
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    },
    [pan]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!isDragging) return;
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    },
    [isDragging, dragStart]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setSelectedNodeId(null);
  }, []);

  // ── Click on Event to Focus Node ──
  const handleEventClick = (agentName: string) => {
    const target = constellationNodes.find(
      (n) => n.rawName.toLowerCase().includes(agentName.toLowerCase()) || n.name.toLowerCase().includes(agentName.toLowerCase())
    );
    if (target) {
      setSelectedNodeId(target.id);
    }
  };

  return (
    <div className="flex h-full w-full flex-col gap-3 p-4 bg-bg text-text select-none">
      {/* ── Header ── */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Radio size={14} className="text-accent animate-pulse" />
            Agent Constellation
          </h2>
          <span className="text-[10px] text-faint">Live AI Neural Execution Map</span>
          {runningAgentsCount > 0 && (
            <span className="flex items-center gap-1 text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-mono animate-pulse">
              <Activity size={10} /> LIVE MISSION ACTIVE ({runningAgentsCount} RUNNING)
            </span>
          )}
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

      {/* ── Main Content: Canvas + Right Panel ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[1fr_300px]">
        {/* ── Canvas Viewport ── */}
        <div
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          className="relative min-h-[320px] overflow-hidden rounded-xl border border-border/40 bg-surface/20 cursor-grab active:cursor-grabbing corner-brackets"
          style={{ cursor: isDragging ? "grabbing" : "grab" }}
        >
          {/* Grid texture background */}
          <div className="absolute inset-0 grid-texture opacity-30" />
          <div className="scan-sweep pointer-events-none absolute inset-0" />

          {/* SVG Connections & Particle Stream Layer */}
          <svg
            className="absolute inset-0 h-full w-full pointer-events-none"
            viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
            preserveAspectRatio="xMidYMid meet"
          >
            <defs>
              <radialGradient id="core-glow-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.4" />
                <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
              </radialGradient>
            </defs>

            {/* Ambient Orbit Rings */}
            <circle
              cx={canvasSize.width / 2 + pan.x}
              cy={canvasSize.height / 2 + pan.y}
              r={(Math.min(canvasSize.width, canvasSize.height) * 0.38) / zoom}
              fill="none"
              stroke="rgb(var(--border) / 0.25)"
              strokeWidth="1"
              strokeDasharray="4 6"
            />
            <circle
              cx={canvasSize.width / 2 + pan.x}
              cy={canvasSize.height / 2 + pan.y}
              r={(Math.min(canvasSize.width, canvasSize.height) * 0.22) / zoom}
              fill="none"
              stroke="rgb(var(--border) / 0.18)"
              strokeWidth="1"
              strokeDasharray="3 5"
            />

            {/* Dynamic Real Connections */}
            {connections.map((conn) => {
              const fromNode = constellationNodes.find((n) => n.id === conn.from);
              const toNode = constellationNodes.find((n) => n.id === conn.to);
              if (!fromNode || !toNode) return null;
              const fromIdx = constellationNodes.indexOf(fromNode);
              const toIdx = constellationNodes.indexOf(toNode);
              const fromPos = nodePositions[fromIdx];
              const toPos = nodePositions[toIdx];
              if (!fromPos || !toPos) return null;

              const isConnActive = conn.state === "HIGH_ACTIVITY" || conn.state === "ACTIVE" || conn.state === "COMMUNICATION";
              const isConnError = conn.state === "ERROR";
              const isSelected = selectedNodeId && (conn.from === selectedNodeId || conn.to === selectedNodeId);

              const strokeColor = isConnError
                ? "#ef4444"
                : isConnActive
                ? conn.color
                : "rgb(var(--border) / 0.4)";

              const strokeWidth = isSelected ? 2.5 : isConnActive ? 2 : 1;
              const opacity = isSelected ? 0.9 : isConnActive ? 0.75 : 0.3;

              return (
                <g key={conn.id}>
                  {/* Connection Line */}
                  <line
                    x1={fromPos.x + pan.x}
                    y1={fromPos.y + pan.y}
                    x2={toPos.x + pan.x}
                    y2={toPos.y + pan.y}
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    strokeOpacity={opacity}
                    strokeDasharray={isConnActive ? "6 4" : "4 4"}
                    className={isConnActive ? "animate-dash-flow" : ""}
                  />

                  {/* Flowing Data Particles for Active Connections */}
                  {conn.particleCount > 0 && (
                    <>
                      <circle
                        r={conn.state === "HIGH_ACTIVITY" ? 3 : 2}
                        fill={conn.color}
                        className="animate-pulse"
                      >
                        <animateMotion
                          path={`M ${fromPos.x + pan.x} ${fromPos.y + pan.y} L ${toPos.x + pan.x} ${toPos.y + pan.y}`}
                          dur={activePlayback === "4x" ? "0.6s" : activePlayback === "2x" ? "1.2s" : "2.4s"}
                          repeatCount="indefinite"
                        />
                      </circle>
                      {conn.particleCount > 1 && (
                        <circle
                          r={2}
                          fill="#ffffff"
                          opacity={0.8}
                        >
                          <animateMotion
                            path={`M ${fromPos.x + pan.x} ${fromPos.y + pan.y} L ${toPos.x + pan.x} ${toPos.y + pan.y}`}
                            dur={activePlayback === "4x" ? "0.6s" : activePlayback === "2x" ? "1.2s" : "2.4s"}
                            begin="0.3s"
                            repeatCount="indefinite"
                          />
                        </circle>
                      )}
                    </>
                  )}
                </g>
              );
            })}
          </svg>

          {/* Node Layer (Interactive UI Elements) */}
          {constellationNodes.map((node, idx) => {
            const pos = nodePositions[idx];
            if (!pos) return null;
            const isCore = node.isCore;
            const isSelected = selectedNodeId === node.id;
            const isHovered = hoveredNodeId === node.id;
            const isExecuting = node.liveState === "EXECUTING";
            const isThinking = node.liveState === "THINKING";
            const isCommunicating = node.liveState === "COMMUNICATING";
            const isCompleted = node.liveState === "COMPLETED";
            const isFailed = node.liveState === "FAILED";
            const isOffline = node.liveState === "OFFLINE";

            return (
              <div
                key={node.id}
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedNodeId(node.id === selectedNodeId ? null : node.id);
                }}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
                className={`constellation-node absolute flex flex-col items-center z-10 transition-transform duration-200 cursor-pointer ${
                  isSelected ? "z-30" : ""
                }`}
                style={{
                  left: `${pos.x + pan.x}px`,
                  top: `${pos.y + pan.y}px`,
                  transform: `translate(-50%, -50%) scale(${zoom * (isSelected ? 1.15 : isHovered ? 1.08 : 1)})`,
                  transformOrigin: "center center",
                }}
              >
                {/* Outer Neural Pulse / Activity Ring */}
                {(isExecuting || isThinking || isCommunicating) && (
                  <div
                    className={`absolute rounded-full opacity-30 ${
                      isExecuting ? "animate-neural-fast" : "animate-ping"
                    } ${isCore ? "w-28 h-28" : "w-18 h-18"}`}
                    style={{
                      backgroundColor: node.color,
                      boxShadow: `0 0 24px ${node.color}`,
                    }}
                  />
                )}

                {/* Node Orb Container */}
                <div
                  className={`relative flex items-center justify-center rounded-full border-2 transition-all duration-300 ${
                    isCore ? "w-16 h-16" : "w-11 h-11"
                  } ${isOffline ? "opacity-40 grayscale" : ""}`}
                  style={{
                    borderColor: isSelected ? "#ffffff" : node.color,
                    backgroundColor: "rgb(var(--surface) / 0.95)",
                    boxShadow: isSelected
                      ? `0 0 24px ${node.color}, 0 0 8px #ffffff`
                      : isExecuting
                      ? `0 0 20px ${node.color}, inset 0 0 10px ${node.color}`
                      : `0 0 ${isCore ? 20 : 8}px ${node.color}30`,
                  }}
                >
                  {/* Internal Energy Center */}
                  <div
                    className={`rounded-full transition-all duration-300 ${
                      isExecuting ? "animate-pulse" : ""
                    }`}
                    style={{
                      width: isCore ? 32 : 18,
                      height: isCore ? 32 : 18,
                      backgroundColor: node.color,
                      opacity: isOffline ? 0.3 : isExecuting ? 1 : 0.75,
                    }}
                  />

                  {/* Core Icon or Status Glyph */}
                  {isCore ? (
                    <Cpu size={18} className="absolute text-background" />
                  ) : isExecuting ? (
                    <Activity size={12} className="absolute text-background animate-spin" />
                  ) : isCompleted ? (
                    <CheckCircle2 size={12} className="absolute text-emerald-400" />
                  ) : isFailed ? (
                    <AlertCircle size={12} className="absolute text-rose-400" />
                  ) : null}
                </div>

                {/* Node Card / Label */}
                {zoom > 0.65 && (
                  <div
                    className={`mt-1.5 bg-surface/95 border rounded-lg px-2 py-1 backdrop-blur-md text-center shadow-lg transition-all duration-200 ${
                      isSelected
                        ? "border-accent ring-1 ring-accent"
                        : isCore
                        ? "border-accent/50 bg-surface"
                        : isExecuting
                        ? "border-emerald-500/60 bg-emerald-950/20"
                        : "border-border/50"
                    }`}
                    style={{ minWidth: isCore ? 130 : 90 }}
                  >
                    <div
                      className={`font-semibold tracking-wide truncate ${isCore ? "text-[10px]" : "text-[9px]"}`}
                      style={{ color: node.color }}
                    >
                      {node.name}
                    </div>

                    <div className="text-[8px] text-faint truncate max-w-[120px]">{node.sub}</div>

                    {/* Live State Badge */}
                    <div className="mt-0.5 flex items-center justify-center gap-1">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          isExecuting
                            ? "bg-emerald-400 animate-ping"
                            : isThinking
                            ? "bg-purple-400 animate-pulse"
                            : isCompleted
                            ? "bg-cyan-400"
                            : isFailed
                            ? "bg-rose-500"
                            : isOffline
                            ? "bg-neutral-600"
                            : "bg-emerald-500"
                        }`}
                      />
                      <span
                        className={`text-[8px] font-bold ${
                          isExecuting
                            ? "text-emerald-400"
                            : isThinking
                            ? "text-purple-400"
                            : isCompleted
                            ? "text-cyan-400"
                            : isFailed
                            ? "text-rose-400"
                            : isOffline
                            ? "text-neutral-500"
                            : "text-ok"
                        }`}
                      >
                        {node.liveState}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {/* Constellation Metrics Overview Overlay (Top-Left) */}
          <div className="absolute top-3 left-3 z-20 glass rounded-xl p-3 backdrop-blur-md w-52 font-mono text-[10px]">
            <div className="text-faint text-[9px] uppercase tracking-wider mb-2 font-bold flex items-center justify-between">
              <span>Constellation Telemetry</span>
              <span className="text-accent text-[8px]">● Live</span>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between items-center">
                <span className="text-faint">TOTAL BRAINS</span>
                <span className="font-bold text-text">{totalAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">ONLINE RUNTIMES</span>
                <span className="font-bold text-ok">{onlineAgentsCount}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">RUNNING (ACTIVE)</span>
                <span className={`font-bold ${runningAgentsCount > 0 ? "text-emerald-400 animate-pulse" : "text-warn"}`}>
                  {runningAgentsCount}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-faint">COMPLETED TASKS</span>
                <span className="font-bold text-info">{completedAgentsCount}</span>
              </div>
            </div>

            {activeMission && (
              <div className="mt-2.5 pt-2 border-t border-border/40 text-[9px]">
                <div className="text-faint text-[8px] uppercase">Active Mission</div>
                <div className="font-semibold text-text truncate">{activeMission.title}</div>
                <div className="text-accent font-mono text-[8px] uppercase">{activeMission.status}</div>
              </div>
            )}
          </div>

          {/* Node Inspector Drawer (If Node is Selected) */}
          {selectedNode && (
            <div className="absolute bottom-3 left-3 right-3 lg:right-auto lg:w-96 z-20 glass rounded-xl p-3 backdrop-blur-md border border-accent/40 shadow-2xl font-mono text-xs animate-in fade-in slide-in-from-bottom-2">
              <div className="flex items-center justify-between pb-2 border-b border-border/40">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: selectedNode.color }}
                  />
                  <span className="font-bold text-text text-sm">{selectedNode.name}</span>
                </div>
                <button
                  onClick={() => setSelectedNodeId(null)}
                  className="text-faint hover:text-text p-1 rounded-md transition"
                >
                  <X size={14} />
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2 my-2 text-[10px]">
                <div className="bg-surface/50 p-2 rounded-lg border border-border/30">
                  <span className="text-faint block text-[8px]">LIVE STATE</span>
                  <span className="font-bold text-emerald-400">{selectedNode.liveState}</span>
                </div>
                <div className="bg-surface/50 p-2 rounded-lg border border-border/30">
                  <span className="text-faint block text-[8px]">INTENSITY</span>
                  <span className="font-bold text-accent">{selectedNode.intensity}</span>
                </div>
                <div className="bg-surface/50 p-2 rounded-lg border border-border/30">
                  <span className="text-faint block text-[8px]">RUNTIME</span>
                  <span className="font-semibold text-text truncate">{selectedNode.runtime}</span>
                </div>
                <div className="bg-surface/50 p-2 rounded-lg border border-border/30">
                  <span className="text-faint block text-[8px]">MODEL / STRATEGY</span>
                  <span className="font-semibold text-text truncate">{selectedNode.model}</span>
                </div>
              </div>

              {selectedNode.currentTaskTitle && (
                <div className="bg-surface/40 p-2 rounded-lg border border-border/30 mb-2 text-[10px]">
                  <span className="text-faint block text-[8px]">CURRENT MISSION TASK</span>
                  <div className="text-text font-medium truncate">{selectedNode.currentTaskTitle}</div>
                </div>
              )}

              {selectedNode.currentOperation && (
                <div className="bg-surface/40 p-2 rounded-lg border border-border/30 mb-2 text-[10px]">
                  <span className="text-faint block text-[8px]">ACTIVE OPERATION</span>
                  <div className="text-accent font-mono text-[9px] truncate">{selectedNode.currentOperation}</div>
                </div>
              )}

              {selectedNode.error && (
                <div className="bg-rose-500/10 p-2 rounded-lg border border-rose-500/30 text-rose-400 text-[10px]">
                  <span className="block font-bold text-[8px]">ERROR DIAGNOSTIC</span>
                  <div>{selectedNode.error}</div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Right Panel: Live Events + Telemetry + Playback ── */}
        <div className="flex flex-col gap-3 min-h-0">
          {/* Live Event Stream (Interactive) */}
          <div className="glass rounded-xl p-3 font-mono text-[10px] shrink-0">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-text uppercase tracking-wider text-[9px]">Live Event Stream</span>
              <span className="text-ok text-[8px] flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-ok animate-pulse" /> Live
              </span>
            </div>
            <div className="min-h-0 max-h-[190px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1.5 text-[9px]">
              {liveEvents.map((ev) => (
                <div
                  key={ev.id}
                  onClick={() => handleEventClick(ev.agent)}
                  className="flex items-start gap-1.5 border-b border-border/30 pb-1.5 cursor-pointer hover:bg-surface/40 p-1 rounded transition group"
                  title="Click to focus agent in constellation"
                >
                  <span className="text-faint text-[8px] shrink-0 mt-0.5">{ev.time}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-accent truncate group-hover:text-cyan-400">
                        {ev.agent}
                      </span>
                      <ArrowRight size={10} className="text-faint opacity-0 group-hover:opacity-100 transition" />
                    </div>
                    <div className="text-faint text-[8px] truncate">{ev.detail}</div>
                  </div>
                </div>
              ))}
              {liveEvents.length === 0 && (
                <div className="text-faint text-center py-2">No live execution events yet</div>
              )}
            </div>
          </div>

          {/* Telemetry Mini-Cards */}
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

          {/* Playback Speed Controller */}
          <div className="glass rounded-xl p-2 flex items-center justify-between shrink-0">
            <span className="text-[9px] text-faint uppercase tracking-wider flex items-center gap-1">
              <Play size={10} /> Playback Rate
            </span>
            <div className="flex items-center gap-1">
              {(["1x", "2x", "4x"] as const).map((speed) => (
                <button
                  key={speed}
                  onClick={() => setActivePlayback(speed)}
                  className={`rounded px-2 py-0.5 text-[9px] font-mono transition ${
                    activePlayback === speed
                      ? "bg-accent text-white font-bold"
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

      {/* ── Footer: Status Bar ── */}
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
          {runningAgentsCount > 0 ? (
            <span className="text-emerald-400 font-bold flex items-center gap-1 animate-pulse">
              ● NEURAL EXECUTION ACTIVE
            </span>
          ) : (
            <span className="text-ok">● SYSTEM ONLINE (STANDBY)</span>
          )}
        </div>
      </div>
    </div>
  );
}
