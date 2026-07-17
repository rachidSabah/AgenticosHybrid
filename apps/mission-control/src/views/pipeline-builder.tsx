"use client";

import { useCallback, useEffect, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  type Edge,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { Panel, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { ProviderInfo } from "@/lib/types";

const STAGES = ["input", "route", "provider", "reason", "memory", "output"] as const;
type Stage = (typeof STAGES)[number];

const STAGE_COLOR: Record<Stage, string> = {
  input: "#22c55e",
  route: "#6366f1",
  provider: "#8b5cf6",
  reason: "#0ea5e9",
  memory: "#f59e0b",
  output: "#ec4899",
};

const nodeTypes: NodeTypes = {};

// Pipeline Builder — composes a provider/model routing pipeline. Provider stage
// nodes are seeded from the real backend provider list so routing targets are
// genuine. The graph is edited locally in 3A; Phase 3B persists it to the engine.
export function PipelineBuilder() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  useEffect(() => {
    api.providers().then(setProviders).catch(() => {});
  }, []);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes(providers));
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [stage, setStage] = useState<Stage>("route");

  useEffect(() => {
    setNodes(initialNodes(providers));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers]);

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds) => addEdge({ ...c, animated: true, style: { stroke: "#6366f1" } }, eds)),
    [setEdges],
  );

  const addNode = useCallback(() => {
    const id = `s_${nodes.length + 1}`;
    const node: Node = {
      id,
      position: { x: 120 + (nodes.length % 4) * 60, y: 80 + nodes.length * 30 },
      data: { label: `${stage}:${id}`, stage },
      style: {
        background: "rgba(15,18,28,0.85)",
        border: `1px solid ${STAGE_COLOR[stage]}`,
        borderRadius: 10,
        color: "#e6e8ee",
        fontSize: 12,
        padding: "6px 10px",
      },
    };
    setNodes((nds) => [...nds, node]);
  }, [nodes.length, stage, setNodes]);

  const exportJson = () => {
    const spec = {
      stages: nodes.map((n) => ({ id: n.id, stage: (n.data as any).stage, label: (n.data as any).label })),
      edges: edges.map((e) => ({ from: e.source, to: e.target })),
    };
    navigator.clipboard?.writeText(JSON.stringify(spec, null, 2));
  };

  return (
    <div className="h-full p-4">
      <Panel
        title="Pipeline Builder"
        subtitle="Provider-aware routing pipeline"
        className="h-full"
        contentClassName="p-0"
        actions={
          <div className="flex items-center gap-2">
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value as Stage)}
              className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1 text-xs outline-none"
            >
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button className="pill bg-accent/20 text-accent hover:bg-accent/30" onClick={addNode}>
              + Add
            </button>
            <button className="pill bg-surface/60 text-muted hover:bg-surface" onClick={exportJson}>
              Export
            </button>
          </div>
        }
      >
        <div className="h-full">
          {nodes.length === 0 ? (
            <Empty title="Empty pipeline" hint="Add routing stages; connect them to define the flow." />
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              nodeTypes={nodeTypes}
              fitView
              proOptions={{ hideAttribution: true }}
              minZoom={0.2}
            >
              <Background color="#1f2633" gap={24} />
              <Controls showInteractive={false} />
              <MiniMap maskColor="rgba(8,10,16,0.7)" style={{ background: "#0b0e16" }} />
            </ReactFlow>
          )}
        </div>
      </Panel>
    </div>
  );
}

function initialNodes(providers: ProviderInfo[]): Node[] {
  const seeds: Node[] = [
    { id: "input", position: { x: 80, y: 200 }, data: { label: "input", stage: "input" }, style: stageStyle("input") },
    { id: "route", position: { x: 300, y: 200 }, data: { label: "route", stage: "route" }, style: stageStyle("route") },
  ];
  const provNodes: Node[] = providers.slice(0, 4).map((p, i) => ({
    id: `provider:${p.name}`,
    position: { x: 520, y: 80 + i * 80 },
    data: { label: `provider:${p.name}`, stage: "provider" },
    style: stageStyle("provider"),
  }));
  return [...seeds, ...provNodes];
}

function stageStyle(stage: Stage): React.CSSProperties {
  return {
    background: "rgba(15,18,28,0.85)",
    border: `1px solid ${STAGE_COLOR[stage]}`,
    borderRadius: 10,
    color: "#e6e8ee",
    fontSize: 12,
    padding: "6px 10px",
  };
}
