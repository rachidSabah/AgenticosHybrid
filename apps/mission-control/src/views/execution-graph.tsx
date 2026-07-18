"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Node,
  type Edge,
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import { Panel, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";

const TASK_COLOR: Record<string, string> = {
  created: "#64748b",
  planned: "#6366f1",
  dispatched: "#f59e0b",
  assigned: "#f59e0b",
  completed: "#22c55e",
};

// Live execution graph. Task nodes are laid out left→right by status stage;
// agent nodes are pulled in from the live agent map. All data from EventBus.
export function ExecutionGraph() {
  const tasks = useStore((s) => s.tasks);
  const agents = useStore((s) => s.agents);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { setNodes, getNode, setCenter, fitView } = useReactFlow();

  const { nodes, edges } = useMemo(() => {
    const taskList = Object.values(tasks);
    const stageX: Record<string, number> = { created: 80, planned: 260, dispatched: 440, assigned: 440, completed: 660 };
    const taskNodes: Node[] = taskList.map((t, i) => ({
      id: t.id,
      position: { x: stageX[t.status] ?? 80, y: 80 + i * 90 },
      data: { label: t.title || t.id, status: t.status, role: t.role },
      style: {
        background: "rgba(15,18,28,0.85)",
        border: `1px solid ${TASK_COLOR[t.status] ?? "#64748b"}`,
        borderRadius: 10,
        color: "#e6e8ee",
        fontSize: 12,
        padding: "6px 10px",
        width: 150,
      },
      tabIndex: 0,
      "aria-label": `Task ${t.title || t.id}, ${t.status}${t.role ? `, ${t.role}` : ""}`,
    }));
    const agentNodes: Node[] = Object.values(agents).map((a, i) => ({
      id: `agent:${a.id}`,
      position: { x: 880, y: 80 + i * 90 },
      data: { label: `${a.role}`, status: a.status },
      style: {
        background: "rgba(15,18,28,0.85)",
        border: `1px solid ${TASK_COLOR[a.status] ?? "#64748b"}`,
        borderRadius: 10,
        color: "#e6e8ee",
        fontSize: 12,
        padding: "6px 10px",
        width: 150,
      },
      tabIndex: 0,
      "aria-label": `Agent ${a.role}, ${a.status}${a.provider ? `, ${a.provider}` : ""}`,
    }));
    const agentIds = Object.values(agents).map((a) => a.id);
    const edgeList: (Edge | null)[] = taskList
      .filter((t) => t.status === "assigned" || t.status === "dispatched")
      .map((t, i) => {
        const target = agentIds.length ? `agent:${agentIds[i % agentIds.length]}` : null;
        if (!target) return null;
        return {
          id: `${t.id}->${target}`,
          source: t.id,
          target,
          animated: true,
          style: { stroke: "#6366f1", strokeOpacity: 0.5 },
        };
      });
    const edges: Edge[] = edgeList.filter((e): e is Edge => e !== null);
    return { nodes: [...taskNodes, ...agentNodes], edges };
  }, [tasks, agents]);

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
      <div className="h-full p-4">
        <Panel title="Execution Graph" subtitle="Task lifecycle → dispatch">
          <Empty title="No tasks in flight" hint="Tasks appear here as they are created and dispatched." />
        </Panel>
      </div>
    );
  }

  return (
    <div className="h-full p-4">
      <Panel title="Execution Graph" subtitle="Live task lifecycle" contentClassName="p-0" className="h-full">
        <div ref={containerRef} className="h-full" role="application" aria-label="Execution graph: tasks and agents" tabIndex={0}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            proOptions={{ hideAttribution: true }}
            minZoom={0.2}
            onNodeClick={(_e, node) => setSelectedId(node.id)}
            aria-live="polite"
            aria-label="Execution graph: task lifecycle and agent assignments"
          >
            <Background color="#1f2633" gap={24} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      </Panel>
    </div>
  );
}