"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  useReactFlow,
} from "reactflow";
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { setNodes, getNode, setCenter } = useReactFlow();

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
        tabIndex: 0,
        "aria-label": `${a.role}, ${a.status}${a.provider ? `, ${a.provider}` : ""}`,
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

  // Keyboard navigation for nodes
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
            if (node) {
              setCenter(node.position.x, node.position.y, { zoom: 1.5, duration: 300 });
            }
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
      <div className="scroll-page p-4 no-hscroll">
        <Panel title="Agent Constellation" subtitle="Supervisor → agent topology">
          <Empty title="No agents in the constellation" hint="Compose or dispatch agents to populate the graph." />
        </Panel>
      </div>
    );
  }

  return (
    <div className="scroll-page p-4 no-hscroll">
      <Panel title="Agent Constellation" subtitle="Live supervisor → agent topology" contentClassName="p-0">
        <div ref={containerRef} className="min-h-[400px]" role="application" aria-label="Agent constellation graph" tabIndex={0}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            onNodeClick={(_e, node) => setSelectedId(node.id)}
            aria-live="polite"
            aria-label="Agent constellation: supervisors and agents"
          >
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
