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
import { Play, Pause, StopCircle, CheckCircle2, XCircle, Clock, Search, Filter, ChevronDown, ChevronRight, GitBranch, GitCommit, GitPullRequest, AlertCircle, Zap, Bot, FileText, FileCode, File, Folder, Database, Server, Network, Wifi, Shield, Settings, RefreshCw, ListFilter, ListChecks, ListTodo, ListEnd, ListStart, List, Calendar, History, Tag, User, Users, Cpu, MemoryStick, HardDrive, Thermometer } from "lucide-react";

// ── Types ──

type ExecutionNode = Node & {
  data: {
    label: string;
    status: "created" | "planned" | "dispatched" | "assigned" | "running" | "in_progress" | "completed" | "failed" | "paused" | "cancelled" | "pending" | "recovered" | "idle" | "recovering";
    type: "task" | "agent" | "system";
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

// ── Custom Nodes ──

function TaskNode({ data }: { data: ExecutionNode["data"] }) {
  const color: Record<string, string> = {
    created: "#64748b",
    planned: "#64748b",
    dispatched: "#64748b",
    assigned: "#64748b",
    running: "#10b981",
    completed: "#3b82f6",
    failed: "#ef4444",
    paused: "#f59e0b",
    cancelled: "#64748b",
  };
  const nodeColor = color[data.status as string] || "#64748b";

  const glow: Record<string, string> = {
    created: "rgba(100,116,139,0.15)",
    planned: "rgba(100,116,139,0.15)",
    dispatched: "rgba(100,116,139,0.15)",
    assigned: "rgba(100,116,139,0.15)",
    running: "rgba(16,185,129,0.2)",
    completed: "rgba(59,130,246,0.2)",
    failed: "rgba(239,68,68,0.2)",
    paused: "rgba(245,158,11,0.2)",
    cancelled: "rgba(100,116,139,0.15)",
  };
  const nodeGlow = glow[data.status as string] || "rgba(100,116,139,0.15)";

  const isActive = data.status === "running";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[180px] backdrop-blur-sm"
      style={
        {
          background: "rgba(12,14,22,0.92)",
          borderColor: nodeColor,
          boxShadow: `0 0 20px ${nodeGlow}, inset 0 0 20px ${nodeGlow}`,
        }
      }
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Animated glow ring for active nodes */}
      {isActive && (
        <span
          className="absolute -inset-[2px] rounded-[14px] opacity-50 animate-pulse"
          style={{ border: `1px solid ${nodeColor}`, boxShadow: `0 0 30px ${nodeColor}` }}
        />
      )}

      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        {/* Status dot with pulse */}
        <span className="relative flex h-3 w-3 shrink-0">
          {isActive && (
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ backgroundColor: nodeColor }}
            />
          )}
          <span
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{ backgroundColor: nodeColor }}
          />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">{data.label}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
            >
              {data.status}
            </span>
          </div>
          {data.tags?.map((tag: string) => (
            <div key={tag} className="rounded-full bg-surface/20 px-2 py-0.5 text-[9px] text-faint mt-1">
              {tag}
            </div>
          ))}
        </div>
      </div>

      {/* Live metrics row */}
      <div className="mt-2 flex items-center gap-3 text-[9px] text-faint/60 border-t border-border/30 pt-2">
        {data.startedAt && (
          <span className="tabular-nums">{new Date(data.startedAt).toLocaleTimeString()}</span>
        )}
        {data.duration && (
          <span className="tabular-nums">{Math.round(data.duration / 1000)}s</span>
        )}
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
  const nodeColor = color[data.status as string] || "#64748b";

  const glow: Record<string, string> = {
    running: "rgba(139,92,246,0.2)",
    completed: "rgba(16,185,129,0.2)",
    failed: "rgba(239,68,68,0.2)",
    idle: "rgba(100,116,139,0.15)",
  };
  const nodeGlow = glow[data.status as string] || "rgba(100,116,139,0.15)";

  const isActive = data.status === "running";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[180px] backdrop-blur-sm"
      style={
        {
          background: "rgba(12,14,22,0.92)",
          borderColor: nodeColor,
          boxShadow: `0 0 20px ${nodeGlow}, inset 0 0 20px ${nodeGlow}`,
        }
      }
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Animated glow ring for active nodes */}
      {isActive && (
        <span
          className="absolute -inset-[2px] rounded-[14px] opacity-50 animate-pulse"
          style={{ border: `1px solid ${nodeColor}`, boxShadow: `0 0 30px ${nodeColor}` }}
        />
      )}

      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        {/* Status dot with pulse */}
        <span className="relative flex h-3 w-3 shrink-0">
          {isActive && (
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ backgroundColor: nodeColor }}
            />
          )}
          <span
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{ backgroundColor: nodeColor }}
          />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Bot size={16} className="text-accent" />
            <span className="text-sm font-semibold truncate">{data.label}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
            >
              {data.status}
            </span>
          </div>
          {data.tags?.map((tag: string) => (
            <div key={tag} className="rounded-full bg-surface/20 px-2 py-0.5 text-[9px] text-faint mt-1">
              {tag}
            </div>
          ))}
        </div>
      </div>

      {/* Live metrics row */}
      <div className="mt-2 flex items-center gap-3 text-[9px] text-faint/60 border-t border-border/30 pt-2">
        {data.startedAt && (
          <span className="tabular-nums">{new Date(data.startedAt).toLocaleTimeString()}</span>
        )}
        {data.duration && (
          <span className="tabular-nums">{Math.round(data.duration / 1000)}s</span>
        )}
      </div>
    </motion.div>
  );
}

function SystemNode({ data }: { data: ExecutionNode["data"] }) {
  const color: Record<string, string> = {
    running: "#06b6d4",
    completed: "#10b981",
    failed: "#ef4444",
    idle: "#64748b",
  };
  const nodeColor = color[data.status as string] || "#64748b";

  const glow: Record<string, string> = {
    running: "rgba(6,182,212,0.2)",
    completed: "rgba(16,185,129,0.2)",
    failed: "rgba(239,68,68,0.2)",
    idle: "rgba(100,116,139,0.15)",
  };
  const nodeGlow = glow[data.status as string] || "rgba(100,116,139,0.15)";

  const isActive = data.status === "running";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[180px] backdrop-blur-sm"
      style={
        {
          background: "rgba(12,14,22,0.92)",
          borderColor: nodeColor,
          boxShadow: `0 0 20px ${nodeGlow}, inset 0 0 20px ${nodeGlow}`,
        }
      }
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Animated glow ring for active nodes */}
      {isActive && (
        <span
          className="absolute -inset-[2px] rounded-[14px] opacity-50 animate-pulse"
          style={{ border: `1px solid ${nodeColor}`, boxShadow: `0 0 30px ${nodeColor}` }}
        />
      )}

      <Handle type="target" position={Position.Left} style={{ background: nodeColor, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: nodeColor, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        {/* Status dot with pulse */}
        <span className="relative flex h-3 w-3 shrink-0">
          {isActive && (
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ backgroundColor: nodeColor }}
            />
          )}
          <span
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{ backgroundColor: nodeColor }}
          />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Server size={16} className="text-accent" />
            <span className="text-sm font-semibold truncate">{data.label}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${nodeColor}22`, color: nodeColor }}
            >
              {data.status}
            </span>
          </div>
          {data.tags?.map((tag: string) => (
            <div key={tag} className="rounded-full bg-surface/20 px-2 py-0.5 text-[9px] text-faint mt-1">
              {tag}
            </div>
          ))}
        </div>
      </div>

      {/* Live metrics row */}
      <div className="mt-2 flex items-center gap-3 text-[9px] text-faint/60 border-t border-border/30 pt-2">
        {data.startedAt && (
          <span className="tabular-nums">{new Date(data.startedAt).toLocaleTimeString()}</span>
        )}
        {data.duration && (
          <span className="tabular-nums">{Math.round(data.duration / 1000)}s</span>
        )}
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
      strokeWidth={style?.strokeWidth || 1.5}
      strokeOpacity={style?.strokeOpacity || 0.5}
      className="react-flow__edge-path"
    />
  );
}

// ── Stable type references (module-level — React Flow requires a stable identity) ──

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
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<FilterState>({
    status: ["running", "completed", "failed", "paused", "cancelled", "idle", "healthy", "down", "degraded", "recovered", "in_progress", "planned", "created", "dispatched", "assigned"],
    type: ["task", "agent", "system"],
    search: "",
    sort: "newest",
    dimension: "2d",
  });

  const { nodes, edges } = useMemo(() => {
    const executionNodes: ExecutionNode[] = [];
    const executionEdges: ExecutionEdge[] = [];

    // Task nodes
    Object.values(tasks).forEach((task) => {
      executionNodes.push({
        id: `task-${task.id}`,
        type: "task",
        position: { x: Math.random() * 800, y: Math.random() * 600 },
        data: {
          label: task.title || task.id,
          status: task.status,
          type: "task",
          startedAt: Date.now() - 1000 * 60 * 5,
          duration: task.status === "completed" ? 60 * 1000 : undefined,
          tags: [task.role],
        },
      });
    });

    // Agent nodes
    Object.values(agents).forEach((agent) => {
      executionNodes.push({
        id: `agent-${agent.id}`,
        type: "agent",
        position: { x: Math.random() * 800, y: Math.random() * 600 },
        data: {
          label: agent.role,
          status: agent.status,
          type: "agent",
          startedAt: Date.now() - 1000 * 60 * 5,
          duration: agent.status === "completed" ? 60 * 1000 : undefined,
          tags: [agent.provider],
        },
      });

      // Agent-task edges
      if (agent.current_task) {
        executionEdges.push({
          id: `edge-${agent.id}-${agent.current_task}`,
          source: `agent-${agent.id}`,
          target: `task-${agent.current_task}`,
          animated: agent.status === "running",
          style: { stroke: "#6366f1", strokeOpacity: 0.5, strokeWidth: 1.5 },
        });
      }
      // Agent → system-health edge (live DAG connectivity)
      executionEdges.push({
        id: `edge-sys-${agent.id}`,
        source: `system-health`,
        target: `agent-${agent.id}`,
        animated: false,
        style: { stroke: "#10b981", strokeOpacity: 0.2, strokeWidth: 0.5 },
      });
    });

    // System nodes
    executionNodes.push({
      id: `system-health`,
      type: "system",
      position: { x: Math.random() * 800, y: Math.random() * 600 },
      data: {
        label: "System Health",
        status: "running",
        type: "system",
        startedAt: Date.now() - 1000 * 10,
        tags: ["health"],
      },
    });

    if (telemetry.errors > 0) {
      executionNodes.push({
        id: `system-error`,
        type: "system",
        position: { x: Math.random() * 800, y: Math.random() * 600 },
        data: {
          label: "System Error",
          status: "failed",
          type: "system",
          startedAt: Date.now() - 1000 * 5,
          tags: ["error"],
        },
      });
    }

    return { nodes: executionNodes, edges: executionEdges };
  }, [tasks, agents, telemetry]);

  const filteredNodes = useMemo(() => {
    return nodes.filter((node) => {
      const statusMatch = filters.status.includes(node.data.status);
      const typeMatch = filters.type.includes(node.data.type);
      const searchMatch = filters.search
        ? node.data.label.toLowerCase().includes(filters.search.toLowerCase()) ||
          node.data.tags?.some((t: string) => t.toLowerCase().includes(filters.search.toLowerCase()))
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

  // nodeTypes/edgeTypes are module-level constants (stable identity for React Flow)

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

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
      status: ["running", "completed", "failed", "paused", "cancelled"],
      type: ["task", "agent", "system"],
      search: "",
      sort: "newest",
      dimension: "3d",
    });
  };

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-12 gap-4 overflow-auto p-4">
      {/* Left: Filters */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-4">
        <Panel title="Filters" className="flex-shrink-0">
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
              <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {[
                  { id: "running", label: "Running", icon: <Play size={12} /> },
                  { id: "completed", label: "Completed", icon: <CheckCircle2 size={12} /> },
                  { id: "failed", label: "Failed", icon: <XCircle size={12} /> },
                  { id: "paused", label: "Paused", icon: <Pause size={12} /> },
                  { id: "cancelled", label: "Cancelled", icon: <StopCircle size={12} /> },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => toggleStatusFilter(item.id)}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.status.includes(item.id)
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Type</label>
              <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {[
                  { id: "task", label: "Task", icon: <GitBranch size={12} /> },
                  { id: "agent", label: "Agent", icon: <Bot size={12} /> },
                  { id: "system", label: "System", icon: <Server size={12} /> },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => toggleTypeFilter(item.id)}
                    className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.type.includes(item.id)
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
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
              <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1.5">
                {[
                  { id: "2d", label: "2D" },
                  { id: "3d", label: "3D" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilters((prev) => ({ ...prev, dimension: item.id as any }))}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filters.dimension === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <button
              onClick={clearFilters}
              className="mt-1 w-full rounded-lg px-2.5 py-1.5 text-[11px] font-medium text-faint hover:text-text hover:bg-surface/20 transition"
            >
              Clear filters
            </button>
          </div>
        </Panel>
        <Panel title="Stats" className="flex-shrink-0">
          <div className="space-y-2">
            <Stat label="Total Nodes" value={nodes.length} />
            <Stat label="Filtered Nodes" value={filteredNodes.length} />
            <Stat label="Total Edges" value={edges.length} />
            <Stat label="Filtered Edges" value={filteredEdges.length} />
            <Stat label="Errors" value={telemetry.errors} tone={telemetry.errors > 0 ? "danger" : undefined} />
          </div>
        </Panel>
        {selected && (
          <Panel title="Details" className="flex-shrink-0">
            <NodeDetails node={nodes.find((n) => n.id === selected)} />
          </Panel>
        )}
      </div>

      {/* Right: Graph */}
      <div className="col-span-12 lg:col-span-9 flex flex-col gap-4 h-full min-h-0">
        <Panel
          title="Execution Graph"
          subtitle="Live execution DAG"
          className="flex-1 min-h-0"
          contentClassName="p-0"
        >
          {filters.dimension === "2d" ? (
            <div className="h-full w-full">
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
                      cancelled: "#64748b",
                      created: "#64748b",
                      planned: "#64748b",
                      dispatched: "#64748b",
                      assigned: "#64748b",
                    };
                    return colorMap[status || ""] || "#64748b";
                  }}
                />
              </ReactFlow>
            </div>
          ) : (
            <div className="h-full w-full">
              <Suspense fallback={<LoadingScreen />}>
                <ThreeDGraph nodes={filteredNodes} edges={filteredEdges} onNodeClick={(id) => setSelected(id)} />
              </Suspense>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function NodeDetails({ node }: { node?: ExecutionNode }) {
  if (!node) return null;

  return (
    <div className="space-y-3 text-[10px] text-faint">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <div className="font-medium">Node ID</div>
          <div>{node.id}</div>
        </div>
        <div>
          <div className="font-medium">Type</div>
          <div className="flex items-center gap-1.5">
            {node.data.type === "task" && <GitBranch size={12} />}
            {node.data.type === "agent" && <Bot size={12} />}
            {node.data.type === "system" && <Server size={12} />}
            <span>{node.data.type}</span>
          </div>
        </div>
        <div>
          <div className="font-medium">Status</div>
          <div className="flex items-center gap-1.5">
            <StatusDot status={node.data.status} />
            <span>{node.data.status}</span>
          </div>
        </div>
        <div>
          <div className="font-medium">Started</div>
          <div>{node.data.startedAt ? new Date(node.data.startedAt).toLocaleString() : "—"}</div>
        </div>
        {node.data.duration && (
          <div>
            <div className="font-medium">Duration</div>
            <div>{Math.round(node.data.duration / 1000)}s</div>
          </div>
        )}
      </div>

      {node.data.tags && node.data.tags.length > 0 && (
        <div>
          <div className="font-medium">Tags</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {node.data.tags.map((tag: string) => (
              <div key={tag} className="rounded-full bg-surface/20 px-2 py-0.5 text-[9px] text-faint">
                {tag}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}