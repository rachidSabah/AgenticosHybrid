"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  useReactFlow,
} from "reactflow";
import "reactflow/dist/style.css";
import { Panel, Badge, Empty } from "@/components/ui/primitives";
import Dynamic from "next/dynamic";
import { X } from "lucide-react";

const MonacoEditor = Dynamic(() => import("@/components/monaco-editor").then((m) => m.MonacoEditor), {
  ssr: false,
  loading: () => <div className="h-64 glass rounded-xl animate-pulse" />,
});

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

const NODE_TYPES: NodeTypes = {};

const STORAGE_KEY = "mc.workflow.draft";

// ── Workflow templates ──────────────────────────────────────────────

interface WorkflowTemplate {
  name: string;
  description: string;
  nodes: Node[];
  edges: Edge[];
}

function wfNode(id: string, step: Step, label: string, x: number, y: number): Node {
  return {
    id,
    position: { x, y },
    data: { label, step },
    style: {
      background: "rgba(15,18,28,0.85)",
      border: `1px solid ${NODE_COLOR[step]}`,
      borderRadius: 10,
      color: "#e6e8ee",
      fontSize: 12,
      padding: "6px 10px",
    },
  };
}

const WF_EDGE = (id: string, source: string, target: string): Edge => ({
  id,
  source,
  target,
  animated: true,
  style: { stroke: "#6366f1" },
});

const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    name: "CI/CD Pipeline",
    description: "trigger → plan → agent → gate → output",
    nodes: [
      wfNode("t1", "trigger", "trigger:git-push", 80, 200),
      wfNode("t2", "plan", "plan:build-steps", 280, 200),
      wfNode("t3", "agent", "agent:deploy-tool", 480, 200),
      wfNode("t4", "gate", "gate:quality-check", 680, 200),
      wfNode("t5", "output", "output:deployment", 880, 200),
    ],
    edges: [
      WF_EDGE("e1-2", "t1", "t2"),
      WF_EDGE("e2-3", "t2", "t3"),
      WF_EDGE("e3-4", "t3", "t4"),
      WF_EDGE("e4-5", "t4", "t5"),
    ],
  },
  {
    name: "Code Review",
    description: "trigger → plan → agent → agent → gate → output",
    nodes: [
      wfNode("c1", "trigger", "trigger:pr-opened", 80, 200),
      wfNode("c2", "plan", "plan:review-plan", 280, 200),
      wfNode("c3", "agent", "agent:code-review", 480, 200),
      wfNode("c4", "agent", "agent:security-scan", 680, 200),
      wfNode("c5", "gate", "gate:approval", 880, 200),
      wfNode("c6", "output", "output:report", 1080, 200),
    ],
    edges: [
      WF_EDGE("c1-2", "c1", "c2"),
      WF_EDGE("c2-3", "c2", "c3"),
      WF_EDGE("c3-4", "c3", "c4"),
      WF_EDGE("c4-5", "c4", "c5"),
      WF_EDGE("c5-6", "c5", "c6"),
    ],
  },
  {
    name: "Research Synthesis",
    description: "trigger → agent → agent → output",
    nodes: [
      wfNode("r1", "trigger", "trigger:query", 80, 200),
      wfNode("r2", "agent", "agent:research", 300, 200),
      wfNode("r3", "agent", "agent:summarize", 520, 200),
      wfNode("r4", "output", "output:synthesis", 740, 200),
    ],
    edges: [
      WF_EDGE("r1-2", "r1", "r2"),
      WF_EDGE("r2-3", "r2", "r3"),
      WF_EDGE("r3-4", "r3", "r4"),
    ],
  },
  {
    name: "Documentation",
    description: "trigger → agent → agent → gate → output",
    nodes: [
      wfNode("d1", "trigger", "trigger:source-change", 80, 200),
      wfNode("d2", "agent", "agent:analyze-code", 280, 200),
      wfNode("d3", "agent", "agent:write-docs", 480, 200),
      wfNode("d4", "gate", "gate:review", 680, 200),
      wfNode("d5", "output", "output:documentation", 880, 200),
    ],
    edges: [
      WF_EDGE("d1-2", "d1", "d2"),
      WF_EDGE("d2-3", "d2", "d3"),
      WF_EDGE("d3-4", "d3", "d4"),
      WF_EDGE("d4-5", "d4", "d5"),
    ],
  },
  {
    name: "Bug Fix",
    description: "trigger → plan → agent → agent → output",
    nodes: [
      wfNode("b1", "trigger", "trigger:bug-report", 80, 200),
      wfNode("b2", "plan", "plan:fix-plan", 280, 200),
      wfNode("b3", "agent", "agent:fix-code", 480, 200),
      wfNode("b4", "agent", "agent:run-tests", 680, 200),
      wfNode("b5", "output", "output:fix-applied", 880, 200),
    ],
    edges: [
      WF_EDGE("b1-2", "b1", "b2"),
      WF_EDGE("b2-3", "b2", "b3"),
      WF_EDGE("b3-4", "b3", "b4"),
      WF_EDGE("b4-5", "b4", "b5"),
    ],
  },
];

interface ValidationIssue {
  type: "error" | "warning";
  message: string;
  nodeId?: string;
}

function validateWorkflow(nodes: Node[], edges: Edge[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (nodes.length === 0) {
    issues.push({ type: "warning", message: "Workflow is empty — add at least one node" });
    return issues;
  }

  // Check for trigger node
  const hasTrigger = nodes.some((n) => (n.data as any).step === "trigger");
  if (!hasTrigger) {
    issues.push({ type: "error", message: "Workflow must have a trigger node (entry point)" });
  }

  // Check for output node
  const hasOutput = nodes.some((n) => (n.data as any).step === "output");
  if (!hasOutput) {
    issues.push({ type: "warning", message: "Consider adding an output node" });
  }

  // Check for orphaned nodes (no incoming/outgoing edges)
  const nodeIds = new Set(nodes.map((n) => n.id));
  const hasIncoming = new Set(edges.map((e) => e.target));
  const hasOutgoing = new Set(edges.map((e) => e.source));

  nodes.forEach((node) => {
    const isTrigger = (node.data as any).step === "trigger";
    const isOutput = (node.data as any).step === "output";

    if (!isTrigger && !hasIncoming.has(node.id)) {
      issues.push({ type: "warning", message: `Node "${(node.data as any).label || node.id}" has no incoming connections`, nodeId: node.id });
    }
    if (!isOutput && !hasOutgoing.has(node.id)) {
      issues.push({ type: "warning", message: `Node "${(node.data as any).label || node.id}" has no outgoing connections`, nodeId: node.id });
    }
  });

  // Check for cycles using DFS
  const adjacency = new Map<string, string[]>();
  edges.forEach((e) => {
    if (!adjacency.has(e.source)) adjacency.set(e.source, []);
    adjacency.get(e.source)!.push(e.target);
  });

  const visited = new Set<string>();
  const recStack = new Set<string>();

  function dfs(nodeId: string): boolean {
    visited.add(nodeId);
    recStack.add(nodeId);

    const neighbors = adjacency.get(nodeId) || [];
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        if (dfs(neighbor)) return true;
      } else if (recStack.has(neighbor)) {
        return true;
      }
    }

    recStack.delete(nodeId);
    return false;
  }

  nodes.forEach((node) => {
    if (!visited.has(node.id)) {
      if (dfs(node.id)) {
        issues.push({ type: "error", message: "Workflow contains a cycle — directed graphs must be acyclic" });
      }
    }
  });

  return issues;
}

// Workflow Studio — an interactive pipeline canvas. The editor builds a real,
// serializable graph (nodes + typed edges) that Phase 3B will persist to the
// backend workflow engine. Graph state is kept locally for 3A; the "Export"
// action produces the canonical JSON the engine will consume.
export function WorkflowStudio() {
  const [nodes, setNodes, onNodesChange] = useNodesState(load());
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [step, setStep] = useState<Step>("agent");
  const [showCode, setShowCode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { setNodes: setNodesRF, getNode, setCenter } = useReactFlow();

  const validationIssues = useMemo(() => validateWorkflow(nodes, edges), [nodes, edges]);
  const hasErrors = validationIssues.some((i) => i.type === "error");

  const applyTemplate = useCallback((template: WorkflowTemplate) => {
    setNodes(template.nodes);
    setEdges(template.edges);
    setSelectedId(null);
    setShowValidation(false);
  }, [setNodes, setEdges]);

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

  const runValidation = () => setShowValidation(true);

  const spec = {
    nodes: nodes.map((n) => ({ id: n.id, step: (n.data as any).step, label: (n.data as any).label })),
    edges: edges.map((e) => ({ from: e.source, to: e.target })),
  };

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
          setNodesRF((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[nextIndex] })));
          setSelectedId(nodeIds[nextIndex]);
          break;
        }
        case "ArrowLeft":
        case "ArrowUp": {
          e.preventDefault();
          const prevIndex = (currentIndex - 1 + nodeIds.length) % nodeIds.length;
          setNodesRF((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[prevIndex] })));
          setSelectedId(nodeIds[prevIndex]);
          break;
        }
        case "Home": {
          e.preventDefault();
          setNodesRF((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[0] })));
          setSelectedId(nodeIds[0]);
          break;
        }
        case "End": {
          e.preventDefault();
          setNodesRF((nds) => nds.map((n) => ({ ...n, selected: n.id === nodeIds[nodeIds.length - 1] })));
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
        case "Delete":
        case "Backspace": {
          if (selectedId) {
            e.preventDefault();
            setNodes((nds) => nds.filter((n) => n.id !== selectedId));
            setEdges((eds) => eds.filter((ed) => ed.source !== selectedId && ed.target !== selectedId));
            setSelectedId(null);
          }
          break;
        }
      }
    };

    container.addEventListener("keydown", handleKeyDown);
    return () => container.removeEventListener("keydown", handleKeyDown);
  }, [nodes, selectedId, setNodesRF, getNode, setCenter, setNodes, setEdges]);

  return (
    <div className="scroll-page p-4">
      <Panel
        title="Workflow Studio"
        subtitle="Compose an agentic pipeline"
        className="flex-1 min-h-0"
        contentClassName="p-0"
        actions={
          <div className="flex items-center gap-2">
            <select
              value={step}
              onChange={(e) => setStep(e.target.value as Step)}
              className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1 text-xs outline-none"
              aria-label="Node step type"
            >
              {STEPS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <button className="pill bg-accent/20 text-accent hover:bg-accent/30" onClick={addNode} aria-label="Add node">
              + Add
            </button>
            <button className="pill bg-surface/60 text-muted hover:bg-surface" onClick={exportJson} aria-label="Export to clipboard">
              Export
            </button>
            <button className="pill bg-surface/60 text-faint hover:text-danger" onClick={clear} aria-label="Clear canvas">
              Clear
            </button>
            <button
              className={`pill ${hasErrors ? "bg-danger/20 text-danger" : "bg-surface/60 text-muted"} hover:bg-surface`}
              onClick={runValidation}
              aria-label="Validate workflow"
            >
              Validate
            </button>
            <button
              className={`pill ${showCode ? "bg-accent/20 text-accent" : "bg-surface/60 text-muted"} hover:bg-surface`}
              onClick={() => setShowCode(!showCode)}
              aria-label={showCode ? "Switch to graph view" : "Switch to code view"}
              aria-pressed={showCode}
            >
              {showCode ? "Graph" : "Code"}
            </button>
          </div>
        }
      >
        <div className="h-full flex flex-col">
          {!showCode && (
            <div className="flex gap-2 px-4 py-2 overflow-x-auto border-b border-border/30 shrink-0">
              {WORKFLOW_TEMPLATES.map((t) => (
                <button
                  key={t.name}
                  onClick={() => applyTemplate(t)}
                  className="flex flex-col items-start gap-0.5 rounded-lg border border-border/40 bg-surface/30 px-3 py-1.5 text-left hover:bg-surface/60 hover:border-accent/40 transition-colors shrink-0 min-w-[130px]"
                >
                  <span className="text-xs font-medium text-foreground">{t.name}</span>
                  <span className="text-[10px] text-faint leading-tight">{t.description}</span>
                </button>
              ))}
            </div>
          )}
          {nodes.length === 0 && !showCode ? (
            <Empty title="Empty canvas" hint="Choose a template above, or add a step node to start building." />
          ) : showCode ? (
            <div className="h-full" role="region" aria-label="Workflow JSON code">
              <MonacoEditor value={JSON.stringify(spec, null, 2)} language="json" readOnly={false} onChange={handleCodeChange} />
            </div>
          ) : (
            <>
              <div ref={containerRef} className="flex-1 min-h-0" role="application" aria-label="Workflow graph editor" tabIndex={0}>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  onConnect={onConnect}
                  nodeTypes={NODE_TYPES}
                  fitView
                  proOptions={{ hideAttribution: true }}
                  minZoom={0.2}
                  onNodeClick={(_e, node) => setSelectedId(node.id)}
                  onPaneClick={() => setSelectedId(null)}
                  aria-live="polite"
                >
                  <Background color="#1f2633" gap={24} />
                  <Controls showInteractive={false} />
                  <MiniMap maskColor="rgba(8,10,16,0.7)" style={{ background: "#0b0e16" }} />
                </ReactFlow>
              </div>
              {showValidation && validationIssues.length > 0 && (
                <div className="fixed bottom-4 right-4 z-40 w-[360px] max-w-[90vw] glass-strong rounded-2xl shadow-depth p-4 animate-in slide-in-from-bottom-4 duration-300">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-semibold flex items-center gap-2">
                      {hasErrors ? (
                        <>
                          <span className="text-danger">●</span> Validation Failed
                        </>
                      ) : (
                        <>
                          <span className="text-warn">●</span> Validation Passed
                        </>
                      )}
                    </h3>
                    <button onClick={() => setShowValidation(false)} className="p-1 rounded hover:bg-surface/50" aria-label="Dismiss">
                      <X size={16} className="text-muted" />
                    </button>
                  </div>
                  <ul className="space-y-2 max-h-60 overflow-y-auto">
                    {validationIssues.map((issue, i) => (
                      <li
                        key={i}
                        className={`flex items-start gap-2 p-2 rounded-lg ${issue.type === "error" ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn"}`}
                      >
                        <span className="text-xs font-mono">{issue.type === "error" ? "!" : "⚠"}</span>
                        <span className="text-sm flex-1">{issue.message}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </Panel>
    </div>
  );
}

function handleCodeChange(value: string) {
  try {
    const parsed = JSON.parse(value);
    if (parsed.nodes && parsed.edges) {
      localStorage.setItem(STORAGE_KEY, value);
    }
  } catch {
    // Invalid JSON, ignore
  }
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