"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useReactFlow,
  Handle,
  Position,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import { motion } from "framer-motion";
import { Panel, StatusDot, Empty } from "@/components/ui/primitives";
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

const nodeTypes = { agent: AgentNode };

// ── Main Component ──
export function AgentConstellation() {
  const agents = useStore((s) => s.agents);
  const providers = useStore((s) => s.providers);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { setNodes, getNode, setCenter } = useReactFlow();

  const { nodes, edges } = useMemo(() => {
    // Use providers as constellation nodes when agents are empty
    const provList = Object.values(providers);
    const agentList = Object.values(agents);
    const sources = agentList.length > 0 ? agentList.map(a => ({ ...a, label: a.role || a.provider || a.id })) : provList.map(p => ({
      id: p.provider,
      label: p.provider,
      status: p.status,
      provider: p.provider,
      current_task: null,
      role: p.provider,
      latency_ms: p.latency_ms,
    }));

    const constellationNodes: Node[] = sources.map((a, i) => {
      const angle = (i / Math.max(1, sources.length)) * Math.PI * 2;
      const r = sources.length <= 1 ? 0 : Math.min(280, 120 + sources.length * 20);
      return {
        id: a.id ?? a.provider ?? `agent-${i}`,
        type: "agent",
        position: { x: 400 + Math.cos(angle) * r, y: 300 + Math.sin(angle) * r },
        data: {
          label: a.label || a.provider,
          status: a.status || "idle",
          provider: a.provider || "unknown",
          task: "current_task" in a ? (a as any).current_task || "—" : "—",
          latency: "latency_ms" in a ? (a as any).latency_ms : undefined,
        },
      } as Node;
    });

    // Neural connections between ALL healthy agents (not just supervisor links)
    const edges: Edge[] = [];
    const healthyIds = constellationNodes.filter((n) => {
      const s = n.data?.status;
      return s === "running" || s === "healthy" || s === "thinking" || s === "coding";
    }).map((n) => n.id);

    for (let i = 0; i < healthyIds.length; i++) {
      for (let j = i + 1; j < healthyIds.length; j++) {
        edges.push({
          id: `${healthyIds[i]}->${healthyIds[j]}`,
          source: healthyIds[i],
          target: healthyIds[j],
          animated: true,
          style: { stroke: "#6366f1", strokeOpacity: 0.35, strokeWidth: 1.5 },
        });
      }
    }

    return { nodes: constellationNodes, edges };
  }, [agents, providers]);

  // Keyboard navigation
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const nodeIds = nodes.map((n) => n.id);
      if (nodeIds.length === 0) return;
      const currentIndex = selectedId ? nodeIds.indexOf(selectedId) : -1;

      switch (e.key) {
        case "ArrowRight":
        case "ArrowDown": {
          e.preventDefault();
          const nextIndex = (currentIndex + 1) % nodeIds.length;
          setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[nextIndex] })));
          setSelectedId(nodeIds[nextIndex]);
          break;
        }
        case "ArrowLeft":
        case "ArrowUp": {
          e.preventDefault();
          const prevIndex = (currentIndex - 1 + nodeIds.length) % nodeIds.length;
          setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[prevIndex] })));
          setSelectedId(nodeIds[prevIndex]);
          break;
        }
        case "Home": {
          e.preventDefault();
          setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[0] })));
          setSelectedId(nodeIds[0]);
          break;
        }
        case "End": {
          e.preventDefault();
          setNodes((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[nodeIds.length - 1] })));
          setSelectedId(nodeIds[nodeIds.length - 1]);
          break;
        }
        case "Enter":
        case " ": {
          if (selectedId) {
            e.preventDefault();
            const node = getNode(selectedId);
            if (node) setCenter(node.position.x, node.position.y, { zoom: 1.5, duration: 300 });
          }
          break;
        }
      }
    };

    container.addEventListener("keydown", handleKeyDown);
    return () => container.removeEventListener("keydown", handleKeyDown);
  }, [nodes, selectedId, setNodes, getNode, setCenter]);

  if (nodes.length === 0) {
    return (
      <div className="h-full p-4">
        <Panel title="Agent Constellation" subtitle="Neural agent topology">
          <Empty title="No agents in the constellation" hint="Compose or dispatch agents to populate the graph." />
        </Panel>
      </div>
    );
  }

  const healthy = nodes.filter((n) => {
    const s = n.data?.status;
    return s === "running" || s === "healthy" || s === "thinking" || s === "coding";
  }).length;

  return (
    <div className="h-full p-4">
      <Panel
        title="Agent Constellation"
        subtitle={`${nodes.length} agents · ${edges.length} neural links · ${healthy} active`}
        contentClassName="p-0"
        className="h-full"
        actions={
          <span className="inline-flex items-center gap-1.5 text-[10px]">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok animate-pulse" />
            LIVE
          </span>
        }
      >
        <div
          ref={containerRef}
          className="h-full"
          role="application"
          aria-label="Agent constellation graph"
          tabIndex={0}
        >
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            fitView
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            maxZoom={3}
            onNodeClick={(_e, node) => setSelectedId(node.id)}
            aria-live="polite"
            aria-label="Agent constellation: supervisors and agents"
          >
            <Background color="#1f2633" gap={24} />
            <Controls showInteractive={false} />
            <MiniMap
              maskColor="rgba(8,10,16,0.7)"
              style={{ background: "#0b0e16", border: "1px solid rgba(255,255,255,0.08)" }}
              nodeColor={(n) => STATUS_COLOR[n.data?.status as string] ?? "#64748b"}
            />
          </ReactFlow>
        </div>
      </Panel>
    </div>
  );
}
