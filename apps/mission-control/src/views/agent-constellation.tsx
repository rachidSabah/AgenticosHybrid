"use client";

import { useEffect, useMemo, useRef, useState, Suspense } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useReactFlow,
  Handle,
  Position,
  getSmoothStepPath,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { Panel, Stat, StatusDot, Empty, LoadingScreen } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";

const STATUS_COLOR: Record<string, string> = {
  running: "#6366f1",
  completed: "#22c55e",
  failed: "#ef4444",
  recovered: "#f59e0b",
  idle: "#64748b",
  healthy: "#22c55e",
  thinking: "#d980ff",
  coding: "#38bdf8",
  testing: "#fbbf24",
  debugging: "#f97316",
  reviewing: "#8b5cf6",
  packaging: "#ec4899",
  waiting: "#64748b",
  offline: "#6b7280",
};

const AGENT_GLOW: Record<string, string> = {
  running: "rgba(99,102,241,0.3)",
  healthy: "rgba(34,197,94,0.3)",
  thinking: "rgba(217,128,255,0.3)",
};

// ── Custom Agent Node ──
function AgentNode({ data }: NodeProps) {
  const color = STATUS_COLOR[data.status] ?? "#64748b";
  const glow = AGENT_GLOW[data.status] ?? "rgba(100,116,139,0.15)";
  const isActive = data.status === "running" || data.status === "thinking" || data.status === "coding";

  return (
    <motion.div
      className="relative rounded-2xl border px-4 py-3 min-w-[180px] backdrop-blur-sm"
      style={{
        background: "rgba(12,14,22,0.92)",
        borderColor: color,
        boxShadow: `0 0 20px ${glow}, inset 0 0 20px ${glow}`,
      }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {/* Animated glow ring for active agents */}
      {isActive && (
        <span
          className="absolute -inset-[2px] rounded-[14px] opacity-50 animate-pulse"
          style={{ border: `1px solid ${color}`, boxShadow: `0 0 30px ${color}` }}
        />
      )}

      <Handle type="target" position={Position.Left} style={{ background: color, width: 8, height: 8 }} />
      <Handle type="source" position={Position.Right} style={{ background: color, width: 8, height: 8 }} />

      <div className="flex items-center gap-3">
        {/* Status dot with pulse */}
        <span className="relative flex h-3 w-3 shrink-0">
          {isActive && (
            <span
              className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
              style={{ backgroundColor: color }}
            />
          )}
          <span
            className="relative inline-flex h-3 w-3 rounded-full"
            style={{ backgroundColor: color }}
          />
        </span>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">{data.label || data.provider || "agent"}</span>
            <span
              className="rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider"
              style={{ backgroundColor: `${color}22`, color }}
            >
              {data.status}
            </span>
          </div>
          {data.provider && (
            <div className="text-[10px] text-faint/70 mt-0.5 flex items-center gap-2">
              <span>{data.provider}</span>
              <span>·</span>
              <span className="tabular-nums">{data.task || "idle"}</span>
            </div>
          )}
        </div>
      </div>

      {/* Live metrics row */}
      <div className="mt-2 flex items-center gap-3 text-[9px] text-faint/60 border-t border-border/30 pt-2">
        {data.latency !== undefined && (
          <span className="tabular-nums">{data.latency.toFixed(0)}ms</span>
        )}
        {data.cpu !== undefined && (
          <span className="tabular-nums">CPU {data.cpu}%</span>
        )}
        {data.memory !== undefined && (
          <span className="tabular-nums">RAM {data.memory}MB</span>
        )}
        {data.tokens !== undefined && (
          <span className="tabular-nums">{data.tokens} tok</span>
        )}
      </div>
    </motion.div>
  );
}

function TaskNode({ data }: NodeProps) {
  return (
    <motion.div
      className="relative rounded-xl border px-3 py-2 min-w-[140px] backdrop-blur-sm"
      style={{
        background: "rgba(12,14,22,0.92)",
        borderColor: STATUS_COLOR[data.status] ?? "#64748b",
      }}
      initial={{ scale: 0.9, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
    >
      <Handle type="target" position={Position.Left} style={{ width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ width: 6, height: 6 }} />
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full shrink-0"
          style={{ backgroundColor: STATUS_COLOR[data.status] ?? "#64748b" }}
        />
        <span className="text-xs font-medium truncate">{data.label || data.id || "task"}</span>
      </div>
      {data.description && (
        <div className="mt-1 text-[10px] text-faint/70 truncate">{data.description}</div>
      )}
    </motion.div>
  );
}

const nodeTypes = { agent: AgentNode, task: TaskNode };

function AnimatedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
}: {
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  sourcePosition: Position;
  targetPosition: Position;
}) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  return (
    <path
      id={id}
      className="react-flow__edge-path animate-dash"
      d={edgePath}
      stroke="#6366f1"
      strokeWidth={2}
      fill="none"
      strokeDasharray="5 5"
    />
  );
}

import { GalaxyConstellation } from "@/components/neural/galaxy-constellation";

// ── Main Component ──
function AgentDetails({ agent }: { agent: Record<string, unknown> }) {
  if (!agent) return null;
  return (
    <div className="space-y-2 text-xs">
      {Object.entries(agent)
        .filter(([k]) => !["id", "edges", "children"].includes(k))
        .slice(0, 8)
        .map(([key, val]) => (
          <div key={key} className="flex justify-between gap-2">
            <span className="text-faint capitalize">{key.replace(/_/g, " ")}</span>
            <span className="font-medium truncate max-w-[140px]">
              {typeof val === "object" ? JSON.stringify(val).slice(0, 40) : String(val)}
            </span>
          </div>
        ))}
    </div>
  );
}

export function AgentConstellation() {
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const telemetry = useStore((s) => s.telemetry);
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "running" | "idle" | "failed">("all");
  const [layout, setLayout] = useState<"force" | "hierarchy" | "circular">("force");
  const [dimension, setDimension] = useState<"2d" | "3d">("3d");

  const filteredAgents = useMemo(() => {
    return Object.values(agents).filter((agent) => {
      const searchMatch = search
        ? agent.id.toLowerCase().includes(search.toLowerCase()) ||
          agent.role.toLowerCase().includes(search.toLowerCase()) ||
          agent.provider?.toLowerCase().includes(search.toLowerCase())
        : true;
      const filterMatch =
        filter === "all" ||
        (filter === "running" && agent.status === "running") ||
        (filter === "idle" && agent.status === "idle") ||
        (filter === "failed" && agent.status === "failed");
      return searchMatch && filterMatch;
    });
  }, [agents, search, filter]);

  const { nodes, edges } = useMemo(() => {
    const agentNodes = filteredAgents.map((agent) => ({
      id: agent.id,
      type: "agent",
      data: agent,
    }));

    const taskNodes = Object.values(tasks)
      .filter((task) => task.status === "running" || task.status === "assigned")
      .map((task) => ({
        id: task.id,
        type: "task",
        data: task,
      }));

    const allNodes = [...agentNodes, ...taskNodes];

    const allEdges = filteredAgents.flatMap((agent) => {
      if (agent.current_task) {
        return [{
          id: `edge-${agent.id}-${agent.current_task}`,
          source: agent.id,
          target: agent.current_task,
          animated: agent.status === "running",
        }];
      }
      return [];
    });

    return { nodes: allNodes as import("reactflow").Node[], edges: allEdges };
  }, [filteredAgents, tasks]);

  const nodeTypes = useMemo(() => ({
    agent: AgentNode,
    task: TaskNode,
  }), []);

  const edgeTypes = useMemo(() => ({
    default: AnimatedEdge,
  }), []);

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* Left: Controls */}
      <div className="col-span-12 lg:col-span-3 flex flex-col gap-4">
        <Panel title="Filters" className="flex-shrink-0">
          <div className="space-y-3">
            <div>
              <label className="text-[10px] font-medium text-faint">Search</label>
              <div className="mt-1 relative">
                <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <input
                  type="text"
                  placeholder="Search agents..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full rounded-lg border border-border/40 bg-surface/10 pl-8 pr-2.5 py-1.5 text-[11px] focus:border-accent/50 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Status</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "all", label: "All" },
                  { id: "running", label: "Running" },
                  { id: "idle", label: "Idle" },
                  { id: "failed", label: "Failed" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setFilter(item.id as any)}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      filter === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Layout</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "force", label: "Force" },
                  { id: "hierarchy", label: "Hierarchy" },
                  { id: "circular", label: "Circular" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setLayout(item.id as any)}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      layout === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[10px] font-medium text-faint">Dimension</label>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                {[
                  { id: "2d", label: "2D" },
                  { id: "3d", label: "3D" },
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setDimension(item.id as any)}
                    className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition ${
                      dimension === item.id
                        ? "bg-accent/20 text-accent"
                        : "text-faint hover:text-text hover:bg-surface/20"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </Panel>
        <Panel title="Stats" className="flex-shrink-0">
          <div className="space-y-2">
            <Stat label="Total Agents" value={Object.keys(agents).length} />
            <Stat label="Filtered Agents" value={filteredAgents.length} />
            <Stat label="Running Tasks" value={Object.values(tasks).filter((t) => t.status === "running").length} />
            <Stat label="Active Edges" value={edges.length} />
            <Stat label="Errors" value={telemetry.errors} tone={telemetry.errors > 0 ? "danger" : undefined} />
          </div>
        </Panel>
        {selected && (
          <Panel title="Details" className="flex-shrink-0">
            <AgentDetails agent={((agents as Record<string, unknown>)[selected!] ?? (tasks as Record<string, unknown>)[selected!]) as unknown as Record<string, unknown>} />
          </Panel>
        )}
      </div>

      {/* Right: Graph */}
      <div className="col-span-12 lg:col-span-9 flex flex-col gap-4 h-full min-h-0">
        <Panel
          title="Agent Constellation"
          subtitle="Live agent-task network"
          className="flex-1 min-h-0"
          contentClassName="p-0"
        >
          {dimension === "2d" ? (
            <div className="h-full w-full">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                fitView
                onNodeClick={(_, node) => setSelected(node.id)}
                onEdgeClick={(_, edge) => setSelected(edge.source)}
              >
                <Background />
                <Controls />
              </ReactFlow>
            </div>
          ) : (
            <div className="h-full w-full">
              <Suspense fallback={<LoadingScreen />}>
                <GalaxyConstellation onSelectStar={(id) => setSelected(id)} />
              </Suspense>
            </div>

          )}
        </Panel>
      </div>
    </div>
  );
}
