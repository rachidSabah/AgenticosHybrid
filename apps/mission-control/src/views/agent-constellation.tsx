"use client";

import { useMemo } from "react";
import ReactFlow, { Background, Controls, MiniMap, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import { Panel, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";

const STATUS_COLOR: Record<string, string> = {
  running: "#6366f1",
  completed: "#22c55e",
  failed: "#ef4444",
  recovered: "#f59e0b",
  idle: "#64748b",
};

// Live constellation of agents. Nodes are positioned on a ring; edges connect
// supervisors to their agents based on REAL agent.supervisor links from events.
export function AgentConstellation() {
  const agents = useStore((s) => s.agents);

  const { nodes, edges } = useMemo(() => {
    const list = Object.values(agents);
    const nodes: Node[] = list.map((a, i) => {
      const angle = (i / Math.max(1, list.length)) * Math.PI * 2;
      const r = list.length <= 1 ? 0 : 240;
      return {
        id: a.id,
        position: { x: 400 + Math.cos(angle) * r, y: 300 + Math.sin(angle) * r },
        data: { label: a.role, status: a.status, provider: a.provider, task: a.current_task },
        style: {
          background: "rgba(15,18,28,0.8)",
          border: `1px solid ${STATUS_COLOR[a.status] ?? "#64748b"}`,
          borderRadius: 12,
          color: "#e6e8ee",
          padding: "8px 12px",
          fontSize: 12,
        },
      };
    });
    const edges: Edge[] = list
      .filter((a) => a.supervisor && agents[a.supervisor])
      .map((a) => ({
        id: `${a.supervisor}->${a.id}`,
        source: a.supervisor!,
        target: a.id,
        animated: a.status === "running",
        style: { stroke: "#6366f1", strokeOpacity: 0.5 },
      }));
    return { nodes, edges };
  }, [agents]);

  if (nodes.length === 0) {
    return (
      <div className="h-full p-4">
        <Panel title="Agent Constellation" subtitle="Supervisor → agent topology">
          <Empty title="No agents in the constellation" hint="Compose or dispatch agents to populate the graph." />
        </Panel>
      </div>
    );
  }

  return (
    <div className="h-full p-4">
      <Panel title="Agent Constellation" subtitle="Live supervisor → agent topology" contentClassName="p-0" className="h-full">
        <div className="h-full">
          <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} minZoom={0.3}>
            <Background color="#1f2633" gap={24} />
            <Controls showInteractive={false} />
            <MiniMap
              maskColor="rgba(8,10,16,0.7)"
              style={{ background: "#0b0e16", border: "1px solid rgba(255,255,255,0.08)" }}
            />
          </ReactFlow>
        </div>
      </Panel>
    </div>
  );
}
