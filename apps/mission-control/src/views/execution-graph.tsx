"use client";

import { useEffect, useMemo, useState, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, Empty, StatusDot, LoadingScreen } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { type TaskNode, type AgentNode } from "@/lib/types";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  useReactFlow,
  Handle,
  Position,
} from "reactflow";
import { ThreeDGraph } from "@/components/graphs/three-d-graph";
import { Play, Pause, StopCircle, CheckCircle2, XCircle, Search, GitBranch, Bot, Server, Activity, Gauge, Disc } from "lucide-react";

// ── Types ──

type ExecutionNode = Node & {
  data: {
    label: string;
    status: "created" | "planned" | "dispatched" | "assigned" | "running" | "in_progress" | "completed" | "failed" | "paused" | "cancelled" | "pending" | "recovered" | "idle" | "recovering";
    type: "task" | "agent" | "system";
    progressPct?: number;
    startedAt?: number;
    completedAt?: number;
    duration?: number;
    tags?: (string | undefined)[];
  };
}

type ExecutionEdge = Edge & {
  animated?: boolean;
  style?: {
    stroke?: string;
    strokeWidth?: number;
    strokeOpacity?: number;
  };
}

interface FilterState {
  status: string[];
  type: string[];
  search: string;
  sort: "newest" | "oldest" | "duration";
  dimension: "2d" | "3d";
}

// ── Futuristic Circular Gauge Component (Aircraft HUD Style) ──

function AircraftGauge({
  percentage,
  size = 72,
  strokeWidth = 6,
  label = "PROGRESS",
  color = "#10b981",
}: {
  percentage: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
  color?: string;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center justify-center">
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Outer subtle glow circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
          fill="transparent"
        />
        {/* Dynamic Progress Arc */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          fill="transparent"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 0.8, ease: "easeOut" }}
          style={{ filter: `drop-shadow(0 0 6px ${color}aa)` }}
        />
      </svg>
      {/* Center Percentage Text & Label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="font-mono text-xs font-bold tracking-tight text-white/95 tabular-nums">
          {percentage}%
        </span>
        <span className="text-[7px] font-semibold tracking-widest text-white/30 uppercase">
          {label}
        </span>
      </div>
    </div>
  );
}

// ── Custom Nodes ──

function TaskNode({ data }: { data: ExecutionNode["data"] }) {
  const color: Record<string, string> = {
    created: "#64748b",
    planned: "#06b6d4",
    dispatched: "#8b5cf6",
    assigned: "#3b82f6",
    running: "#10b981",
    in_progress: "#10b981",
    completed: "#22d3ee",
    failed: "#ef4444",
    paused: "#f59e0b",
    cancelled: "#64748b",
  };
  const nodeColor = color[data.status as string] || "#06b6d4";

  const glow: Record<string, string> = {
    created: "rgba(100,116,139,0.15)",
    planned: "rgba(6,182,212,0.2)",
    dispatched: "rgba(139,92,246,0.25)",
    assigned: "rgba(59,130,246,0.2)",
    running: "rgba(16,185,129,0.35)",
    in_progress: "rgba(16,185,129,0.35)",
    completed: "rgba(34,211,238,0.35)",
    failed: "rgba(239,68,68,0.3)",
    paused: "rgba(245,158,11,0.25)",
    cancelled: "rgba(100,116,139,0.15)",
  };
  const nodeGlow = glow[data.status as string] || "rgba(6,182,212,0.2)";

  const isActive = data.status === "running" || data.status === "in_progress" || data.status === "dispatched";

  // Calculate actual progress percentage or estimate from status
  const progressPct = data.progressPct !== undefined
    ? data.progressPct
    : data.status === "completed" ? 100
    : data.status === "running" || data.status === "in_progress" ? 65
    : data.status === "assigned" || data.status === "dispatched" ? 25
    : 0;

  const remainingPct = 100 - progressPct;

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[240px] backdrop-blur-xl shadow-2xl overflow-hidden"
      style={{
        background: "rgba(8,12,24,0.95)",
        borderColor: `${nodeColor}88`,
        boxShadow: `0 0 25px ${nodeGlow}, inset 0 0 15px ${nodeGlow}`,
      }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Sci-fi top bar */}
      <div
        className="absolute top-0 left-0 h-1 w-full"
        style={{ background: `linear-gradient(90deg, ${nodeColor}, transparent)` }}
      />

      {isActive && (
        <span
          className="absolute -inset-[2px] rounded-[16px] opacity-60 animate-pulse"
          style={{ border: `1px solid ${nodeColor}`, boxShadow: `0 0 30px ${nodeColor}` }}
        />
      )}

      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 9, height: 9, border: "2px solid #05060e" }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 9, height: 9, border: "2px solid #05060e" }} />

      <div className="flex items-center gap-3">
        {/* Aircraft Gauge Indicator */}
        <div className="shrink-0">
          <AircraftGauge percentage={progressPct} size={54} strokeWidth={4} color={nodeColor} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white/90 truncate">{data.label}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[8px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
            >
              {data.status}
            </span>
          </div>

          <div className="mt-1 flex items-center justify-between text-[9px] font-mono text-white/40">
            <span>Done: <strong className="text-white/80">{progressPct}%</strong></span>
            <span>Remain: <strong className="text-amber-400/80">{remainingPct}%</strong></span>
          </div>

          {/* Progress bar */}
          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/10">
            <motion.div
              className="h-full rounded-full"
              style={{ background: `linear-gradient(90deg, ${nodeColor}aa, ${nodeColor})` }}
              initial={{ width: 0 }}
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>

          {data.tags?.map((tag: string | undefined, idx: number) => tag && (
            <div key={idx} className="inline-block rounded bg-white/[0.05] px-1.5 py-0.5 text-[8px] text-white/40 mt-1 mr-1">
              {tag}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function AgentNode({ data }: { data: ExecutionNode["data"] }) {
  const color: Record<string, string> = {
    running: "#8b5cf6",
    completed: "#10b981",
    failed: "#ef4444",
    idle: "#64748b",
  };
  const nodeColor = color[data.status as string] || "#8b5cf6";
  const isActive = data.status === "running";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[200px] backdrop-blur-xl"
      style={{
        background: "rgba(12,14,22,0.95)",
        borderColor: `${nodeColor}88`,
        boxShadow: `0 0 20px ${nodeColor}33`,
      }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
    >
      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-500/20 border border-indigo-500/30 text-indigo-400">
          <Bot size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white/90 truncate">{data.label}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[8px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
            >
              {data.status}
            </span>
          </div>
          {data.tags?.map((tag: string | undefined, idx: number) => tag && (
            <div key={idx} className="inline-block rounded bg-white/[0.05] px-1.5 py-0.5 text-[8px] text-white/40 mt-1">
              {tag}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

function SystemNode({ data }: { data: ExecutionNode["data"] }) {
  const nodeColor = data.status === "failed" ? "#ef4444" : data.status === "running" ? "#06b6d4" : "#64748b";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[190px] backdrop-blur-xl"
      style={{
        background: "rgba(12,14,22,0.95)",
        borderColor: `${nodeColor}88`,
        boxShadow: `0 0 20px ${nodeColor}33`,
      }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
    >
      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-500/20 border border-cyan-500/30 text-cyan-400">
          <Server size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <span className="text-xs font-bold text-white/90 truncate block">{data.label}</span>
          <span
            className="mt-0.5 inline-block rounded px-1.5 py-0.5 text-[8px] font-medium uppercase tracking-wider"
            style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
          >
            {data.status}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function AnimatedEdge({ sourceX, sourceY, targetX, targetY, style }: any) {
  return (
    <path
      d={`M ${sourceX} ${sourceY} C ${sourceX + 50} ${sourceY}, ${targetX - 50} ${targetY}, ${targetX} ${targetY}`}
      fill="none"
      stroke={style?.stroke || "#6366f1"}
      strokeWidth={style?.strokeWidth || 2}
      strokeOpacity={style?.strokeOpacity || 0.6}
      className="react-flow__edge-path"
    />
  );
}

// ── Stable type references for React Flow ──

const nodeTypes: NodeTypes = {
  task: TaskNode,
  agent: AgentNode,
  system: SystemNode,
};

const edgeTypes: EdgeTypes = {
  default: AnimatedEdge,
};

// ── Main Component ──

export function ExecutionGraph() {
  const tasks = useStore((s) => s.tasks);
  const agents = useStore((s) => s.agents);
  const telemetry = useStore((s) => s.telemetry);
  const [selected, setSelected] = useState<string | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    status: ["running", "completed", "failed", "paused", "cancelled", "idle", "healthy", "down", "degraded", "recovered", "in_progress", "planned", "created", "dispatched", "assigned"],
    type: ["task", "agent", "system"],
    search: "",
    sort: "newest",
    dimension: "2d",
  });

  const { nodes, edges, hasActivity, overallMetrics } = useMemo(() => {
    const executionNodes: ExecutionNode[] = [];
    const executionEdges: ExecutionEdge[] = [];

    const taskList = Object.values(tasks);
    const agentList = Object.values(agents);
    const anyRunning =
      taskList.some(
        (t) => t.status === "running" || t.status === "in_progress" || t.status === "assigned" || t.status === "dispatched"
      ) || agentList.some((a) => a.status === "running");

    // Real task calculation
    let completedCount = 0;
    let runningCount = 0;

    taskList.forEach((task, i) => {
      const isDone = task.status === "completed";
      const isRun = task.status === "running" || task.status === "in_progress";
      if (isDone) completedCount++;
      if (isRun) runningCount++;

      const progressPct = isDone ? 100 : isRun ? 65 : task.status === "assigned" || task.status === "dispatched" ? 25 : 0;

      executionNodes.push({
        id: `task-${task.id}`,
        type: "task",
        position: { x: 300 + (i % 3) * 280, y: 80 + Math.floor(i / 3) * 160 },
        data: {
          label: task.title || task.id,
          status: task.status,
          type: "task",
          progressPct,
          tags: [task.role],
        },
      });
    });

    // Real agent calculation
    agentList.forEach((agent, i) => {
      executionNodes.push({
        id: `agent-${agent.id}`,
        type: "agent",
        position: { x: 50, y: 80 + i * 150 },
        data: {
          label: agent.role,
          status: agent.status,
          type: "agent",
          tags: [agent.provider],
        },
      });

      if (agent.current_task && taskList.some((t) => t.id === agent.current_task)) {
        executionEdges.push({
          id: `edge-${agent.id}-${agent.current_task}`,
          source: `agent-${agent.id}`,
          target: `task-${agent.current_task}`,
          animated: agent.status === "running",
          style: { stroke: "#22d3ee", strokeOpacity: 0.8, strokeWidth: 2 },
        });
      }
    });

    // System nodes based on live telemetry
    executionNodes.push({
      id: `system-health`,
      type: "system",
      position: { x: 300, y: 20 },
      data: {
        label: "System Health",
        status: telemetry.errors > 0 ? "failed" : anyRunning ? "running" : "idle",
        type: "system",
        tags: ["health"],
      },
    });

    if (telemetry.errors > 0) {
      executionNodes.push({
        id: `system-error`,
        type: "system",
        position: { x: 300, y: 500 },
        data: {
          label: `System Error (${telemetry.errors})`,
          status: "failed",
          type: "system",
          tags: ["error"],
        },
      });
    }

    const totalTaskCount = taskList.length;
    const overallProgressPct = totalTaskCount > 0 ? Math.round((completedCount / totalTaskCount) * 100) : (anyRunning ? 45 : 0);
    const overallRemainingPct = 100 - overallProgressPct;

    const hasActivity = taskList.length > 0 || agentList.length > 0 || telemetry.errors > 0;

    return {
      nodes: executionNodes,
      edges: executionEdges,
      hasActivity,
      overallMetrics: {
        totalTasks: totalTaskCount,
        completedTasks: completedCount,
        runningTasks: runningCount,
        overallProgressPct,
        overallRemainingPct,
      },
    };
  }, [tasks, agents, telemetry]);

  const filteredNodes = useMemo(() => {
    return nodes.filter((node) => {
      const statusMatch = filters.status.includes(node.data.status);
      const typeMatch = filters.type.includes(node.data.type);
      const searchMatch = filters.search
        ? node.data.label.toLowerCase().includes(filters.search.toLowerCase()) ||
          node.data.tags?.some((t: string | undefined) => t && t.toLowerCase().includes(filters.search.toLowerCase()))
        : true;
      return statusMatch && typeMatch && searchMatch;
    });
  }, [nodes, filters]);

  const filteredEdges = useMemo(() => {
    return edges.filter((edge) => {
      const sourceNode = nodes.find((n) => n.id === edge.source);
      const targetNode = nodes.find((n) => n.id === edge.target);
      return sourceNode && targetNode &&
             filteredNodes.some((n) => n.id === sourceNode.id) &&
             filteredNodes.some((n) => n.id === targetNode.id);
    });
  }, [edges, nodes, filteredNodes]);

  const toggleStatusFilter = (status: string) => {
    setFilters((prev) => ({
      ...prev,
      status: prev.status.includes(status)
        ? prev.status.filter((s) => s !== status)
        : [...prev.status, status],
    }));
  };

  const toggleTypeFilter = (type: string) => {
    setFilters((prev) => ({
      ...prev,
      type: prev.type.includes(type)
        ? prev.type.filter((t) => t !== type)
        : [...prev.type, type],
    }));
  };

  const clearFilters = () => {
    setFilters({
      status: ["running", "completed", "failed", "paused", "cancelled", "created", "planned", "dispatched", "assigned"],
      type: ["task", "agent", "system"],
      search: "",
      sort: "newest",
      dimension: "2d",
    });
  };

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto no-hscroll bg-[#080a10] p-4 pb-12 space-y-4">
      {/* ── Top Futuristic Aircraft Gauge HUD Header ── */}
      <div className="relative rounded-2xl border border-white/10 bg-[#121524]/80 p-4 sm:p-5 backdrop-blur-md shadow-2xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          {/* Aircraft Gauge indicator */}
          <AircraftGauge percentage={overallMetrics.overallProgressPct} size={80} strokeWidth={6} color="#10b981" />
          <div>
            <h1 className="text-lg font-bold text-white/95 tracking-wide flex items-center gap-2">
              <Gauge className="text-emerald-400" size={18} /> Execution Graph HUD
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-4 text-xs font-mono text-white/50">
              <span>Completed: <strong className="text-emerald-400">{overallMetrics.overallProgressPct}%</strong></span>
              <span>Remaining: <strong className="text-amber-400">{overallMetrics.overallRemainingPct}%</strong></span>
              <span>Active Tasks: <strong className="text-indigo-400">{overallMetrics.runningTasks}</strong></span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-center">
            <span className="block text-[9px] uppercase tracking-widest text-white/30">Total Nodes</span>
            <span className="text-sm font-bold font-mono text-white/90">{nodes.length}</span>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-center">
            <span className="block text-[9px] uppercase tracking-widest text-white/30">Total Edges</span>
            <span className="text-sm font-bold font-mono text-white/90">{edges.length}</span>
          </div>
        </div>
      </div>

      {/* ── Main Layout ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Column: Filters & Telemetry */}
        <div className="lg:col-span-3 flex flex-col gap-4">
          <Panel title="Filters" className="shrink-0">
            <div className="space-y-3">
              <div>
                <label className="text-[10px] font-medium text-faint">Search</label>
                <div className="mt-1 relative">
                  <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                  <input
                    type="text"
                    placeholder="Search nodes..."
                    value={filters.search}
                    onChange={(e) => setFilters((prev) => ({ ...prev, search: e.target.value }))}
                    className="w-full rounded-lg border border-border/40 bg-surface/10 pl-8 pr-2.5 py-1.5 text-[11px] focus:border-accent/50 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-medium text-faint">Status</label>
                <div className="mt-1 grid grid-cols-2 gap-1.5">
                  {[
                    { id: "running", label: "Running", icon: <Play size={10} /> },
                    { id: "completed", label: "Completed", icon: <CheckCircle2 size={10} /> },
                    { id: "failed", label: "Failed", icon: <XCircle size={10} /> },
                    { id: "paused", label: "Paused", icon: <Pause size={10} /> },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => toggleStatusFilter(item.id)}
                      className={`flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[10px] font-medium transition ${
                        filters.status.includes(item.id)
                          ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                          : "text-white/40 border border-white/[0.06] hover:bg-white/[0.04]"
                      }`}
                    >
                      {item.icon}
                      <span>{item.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] font-medium text-faint">Dimension</label>
                <div className="mt-1 grid grid-cols-2 gap-1.5">
                  {[
                    { id: "2d", label: "2D View" },
                    { id: "3d", label: "3D View" },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setFilters((prev) => ({ ...prev, dimension: item.id as any }))}
                      className={`rounded-lg px-2.5 py-1.5 text-[10px] font-medium transition ${
                        filters.dimension === item.id
                          ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
                          : "text-white/40 border border-white/[0.06] hover:bg-white/[0.04]"
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              <button
                onClick={clearFilters}
                className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-[10px] font-medium text-white/40 hover:bg-white/[0.04] transition"
              >
                Clear filters
              </button>
            </div>
          </Panel>

          {selected && (
            <Panel title="Node Details" className="shrink-0">
              <NodeDetails node={nodes.find((n) => n.id === selected)} />
            </Panel>
          )}
        </div>

        {/* Right Column: Execution Graph Canvas */}
        <div className="lg:col-span-9 flex flex-col min-h-[450px]">
          <Panel
            title="Execution Graph Canvas"
            subtitle={`Live DAG topology · ${filteredNodes.length} nodes visible`}
            className="flex-1 min-h-0"
            contentClassName="p-0"
          >
            {!hasActivity ? (
              <div className="flex h-full min-h-[400px] items-center justify-center">
                <Empty
                  title="No execution activity"
                  hint="Tasks and agents will render here when a mission starts."
                />
              </div>
            ) : filters.dimension === "2d" ? (
              <div className="h-full w-full min-h-[450px]">
                <ReactFlow
                  nodes={filteredNodes}
                  edges={filteredEdges}
                  nodeTypes={nodeTypes}
                  edgeTypes={edgeTypes}
                  fitView
                  onNodeClick={(_, node) => setSelected(node.id)}
                  onEdgeClick={(_, edge) => setSelected(edge.source)}
                >
                  <Background />
                  <Controls />
                  <MiniMap
                    maskColor="rgba(8,10,16,0.7)"
                    style={{ background: "#0b0e16", border: "1px solid rgba(255,255,255,0.08)" }}
                    nodeColor={(n: { data?: { status?: string } }) => {
                      const status = n.data?.status;
                      const colorMap: Record<string, string> = {
                        running: "#10b981",
                        completed: "#3b82f6",
                        failed: "#ef4444",
                        paused: "#f59e0b",
                      };
                      return colorMap[status || ""] || "#64748b";
                    }}
                  />
                </ReactFlow>
              </div>
            ) : (
              <div className="h-full w-full min-h-[450px]">
                <Suspense fallback={<LoadingScreen />}>
                  <ThreeDGraph nodes={filteredNodes} edges={filteredEdges} onNodeClick={(id) => setSelected(id)} />
                </Suspense>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function NodeDetails({ node }: { node?: ExecutionNode }) {
  if (!node) return null;

  return (
    <div className="space-y-2 text-[10px] text-white/60">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="font-medium text-white/30 uppercase text-[8px]">ID</div>
          <div className="font-mono text-white/80">{node.id}</div>
        </div>
        <div>
          <div className="font-medium text-white/30 uppercase text-[8px]">Type</div>
          <div className="text-white/80 capitalize">{node.data.type}</div>
        </div>
        <div>
          <div className="font-medium text-white/30 uppercase text-[8px]">Status</div>
          <div className="text-white/80 capitalize">{node.data.status}</div>
        </div>
        {node.data.progressPct !== undefined && (
          <div>
            <div className="font-medium text-white/30 uppercase text-[8px]">Progress</div>
            <div className="text-emerald-400 font-bold">{node.data.progressPct}%</div>
          </div>
        )}
      </div>
    </div>
  );
}