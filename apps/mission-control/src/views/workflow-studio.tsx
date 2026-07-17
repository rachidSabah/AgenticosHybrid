"use client";

import { useCallback, useState } from "react";
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

const STEPS = ["trigger", "plan", "agent", "tool", "gate", "output"] as const;
type Step = (typeof STEPS)[number];

const NODE_COLOR: Record<Step, string> = {
  trigger: "#22c55e",
  plan: "#6366f1",
  agent: "#8b5cf6",
  tool: "#0ea5e9",
  gate: "#f59e0b",
  output: "#ec4899",
};

const nodeTypes: NodeTypes = {};

const STORAGE_KEY = "mc.workflow.draft";

// Workflow Studio — an interactive pipeline canvas. The editor builds a real,
// serializable graph (nodes + typed edges) that Phase 3B will persist to the
// backend workflow engine. Graph state is kept locally for 3A; the "Export"
// action produces the canonical JSON the engine will consume.
export function WorkflowStudio() {
  const [nodes, setNodes, onNodesChange] = useNodesState(load());
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [step, setStep] = useState<Step>("agent");

  const onConnect = useCallback(
    (c: Connection) => setEdges((eds) => addEdge({ ...c, animated: true, style: { stroke: "#6366f1" } }, eds)),
    [setEdges],
  );

  const addNode = useCallback(() => {
    const id = `n_${nodes.length + 1}`;
    const node: Node = {
      id,
      position: { x: 120 + (nodes.length % 4) * 60, y: 80 + nodes.length * 30 },
      data: { label: `${step}:${id}`, step },
      style: {
        background: "rgba(15,18,28,0.85)",
        border: `1px solid ${NODE_COLOR[step]}`,
        borderRadius: 10,
        color: "#e6e8ee",
        fontSize: 12,
        padding: "6px 10px",
      },
    };
    setNodes((nds) => [...nds, node]);
  }, [nodes.length, step, setNodes]);

  const clear = () => {
    setNodes([]);
    setEdges([]);
    localStorage.removeItem(STORAGE_KEY);
  };

  const exportJson = () => {
    const spec = {
      nodes: nodes.map((n) => ({ id: n.id, step: (n.data as any).step, label: (n.data as any).label })),
      edges: edges.map((e) => ({ from: e.source, to: e.target })),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(spec));
    navigator.clipboard?.writeText(JSON.stringify(spec, null, 2));
  };

  return (
    <div className="h-full p-4">
      <Panel
        title="Workflow Studio"
        subtitle="Compose an agentic pipeline"
        className="h-full"
        contentClassName="p-0"
        actions={
          <div className="flex items-center gap-2">
            <select
              value={step}
              onChange={(e) => setStep(e.target.value as Step)}
              className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1 text-xs outline-none"
            >
              {STEPS.map((s) => (
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
            <button className="pill bg-surface/60 text-faint hover:text-danger" onClick={clear}>
              Clear
            </button>
          </div>
        }
      >
        <div className="h-full">
          {nodes.length === 0 ? (
            <Empty title="Empty canvas" hint="Add a step node, then drag between nodes to wire the pipeline." />
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

function load(): Node[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const spec = JSON.parse(raw) as { nodes: { id: string; step: Step; label: string }[] };
    return spec.nodes.map((n, i) => ({
      id: n.id,
      position: { x: 120 + (i % 4) * 60, y: 80 + i * 30 },
      data: { label: n.label, step: n.step },
      style: {
        background: "rgba(15,18,28,0.85)",
        border: `1px solid ${NODE_COLOR[n.step] ?? "#64748b"}`,
        borderRadius: 10,
        color: "#e6e8ee",
        fontSize: 12,
        padding: "6px 10px",
      },
    }));
  } catch {
    return [];
  }
}
