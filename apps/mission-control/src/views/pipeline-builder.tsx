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
import { api } from "@/lib/api";
import type { ProviderInfo } from "@/lib/types";
import Dynamic from "next/dynamic";
import { X } from "lucide-react";

const MonacoEditor = Dynamic(() => import("@/components/monaco-editor").then((m) => m.MonacoEditor), {
  ssr: false,
  loading: () => <div className="h-64 glass rounded-xl animate-pulse" />,
});

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

const STORAGE_KEY = "mc.pipeline.draft";

// ── Pipeline templates ──────────────────────────────────────────────

interface PipelineTemplate {
  name: string;
  description: string;
  nodes: Node[];
  edges: Edge[];
}

function pipeNode(id: string, stage: Stage, label: string, x: number, y: number): Node {
  return {
    id,
    position: { x, y },
    data: { label, stage },
    style: {
      background: "rgba(15,18,28,0.85)",
      border: `1px solid ${STAGE_COLOR[stage]}`,
      borderRadius: 10,
      color: "#e6e8ee",
      fontSize: 12,
      padding: "6px 10px",
    },
  };
}

const PIPE_EDGE = (id: string, source: string, target: string): Edge => ({
  id,
  source,
  target,
  animated: true,
  style: { stroke: "#6366f1" },
});

const PIPELINE_TEMPLATES: PipelineTemplate[] = [
  {
    name: "Basic LLM Call",
    description: "input → route → provider → output",
    nodes: [
      pipeNode("p1", "input", "input:user-prompt", 80, 200),
      pipeNode("p2", "route", "route:llm-route", 280, 200),
      pipeNode("p3", "provider", "provider:gpt-4o", 480, 200),
      pipeNode("p4", "output", "output:response", 680, 200),
    ],
    edges: [
      PIPE_EDGE("p1-2", "p1", "p2"),
      PIPE_EDGE("p2-3", "p2", "p3"),
      PIPE_EDGE("p3-4", "p3", "p4"),
    ],
  },
  {
    name: "Multi-Model",
    description: "input → route → dual providers → output",
    nodes: [
      pipeNode("m1", "input", "input:prompt", 80, 200),
      pipeNode("m2", "route", "route:split", 280, 200),
      pipeNode("m3", "provider", "provider:reasoning-model", 500, 120),
      pipeNode("m4", "provider", "provider:coding-model", 500, 280),
      pipeNode("m5", "output", "output:merged-result", 720, 200),
    ],
    edges: [
      PIPE_EDGE("m1-2", "m1", "m2"),
      PIPE_EDGE("m2-3", "m2", "m3"),
      PIPE_EDGE("m2-4", "m2", "m4"),
      PIPE_EDGE("m3-5", "m3", "m5"),
      PIPE_EDGE("m4-5", "m4", "m5"),
    ],
  },
  {
    name: "Secure Pipeline",
    description: "input → route → provider → memory → output",
    nodes: [
      pipeNode("s1", "input", "input:request", 80, 200),
      pipeNode("s2", "route", "route:secure-route", 260, 200),
      pipeNode("s3", "provider", "provider:gpt-4o", 440, 200),
      pipeNode("s4", "memory", "memory:context-store", 620, 200),
      pipeNode("s5", "output", "output:response", 800, 200),
    ],
    edges: [
      PIPE_EDGE("s1-2", "s1", "s2"),
      PIPE_EDGE("s2-3", "s2", "s3"),
      PIPE_EDGE("s3-4", "s3", "s4"),
      PIPE_EDGE("s4-5", "s4", "s5"),
    ],
  },
];

interface ValidationIssue {
  type: "error" | "warning";
  message: string;
  nodeId?: string;
}

function validatePipeline(nodes: Node[], edges: Edge[], providers: ProviderInfo[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (nodes.length === 0) {
    issues.push({ type: "warning", message: "Pipeline is empty — add at least one stage" });
    return issues;
  }

  // Check for required input stage
  const hasInput = nodes.some((n) => (n.data as any).stage === "input");
  if (!hasInput) {
    issues.push({ type: "error", message: "Pipeline must have an input stage (entry point)" });
  }

  // Check for required output stage
  const hasOutput = nodes.some((n) => (n.data as any).stage === "output");
  if (!hasOutput) {
    issues.push({ type: "warning", message: "Consider adding an output stage" });
  }

  // Check for orphaned nodes
  const nodeIds = new Set(nodes.map((n) => n.id));
  const hasIncoming = new Set(edges.map((e) => e.target));
  const hasOutgoing = new Set(edges.map((e) => e.source));

  nodes.forEach((node) => {
    const isInput = (node.data as any).stage === "input";
    const isOutput = (node.data as any).stage === "output";
    const isProvider = (node.data as any).stage === "provider";

    if (!isInput && !hasIncoming.has(node.id)) {
      issues.push({
        type: "warning",
        message: `Stage "${(node.data as any).label || node.id}" has no incoming connections`,
        nodeId: node.id,
      });
    }
    if (!isOutput && !hasOutgoing.has(node.id) && !isProvider) {
      issues.push({
        type: "warning",
        message: `Stage "${(node.data as any).label || node.id}" has no outgoing connections`,
        nodeId: node.id,
      });
    }
  });

  // Check for cycles
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
        issues.push({ type: "error", message: "Pipeline contains a cycle — directed graphs must be acyclic" });
      }
    }
  });

  return issues;
}

// Pipeline Builder — composes a provider/model routing pipeline. Provider stage
// nodes are seeded from the real backend provider list so routing targets are
// genuine. The graph is edited locally in 3A; Phase 3B persists it to the engine.
export function PipelineBuilder() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.providers().then(setProviders).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  const [nodes, setNodes, onNodesChange] = useNodesState(PIPELINE_TEMPLATES[0].nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(PIPELINE_TEMPLATES[0].edges);
  const [stage, setStage] = useState<Stage>("route");
  const [showCode, setShowCode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { setNodes: setNodesRF, getNode, setCenter } = useReactFlow();

  const validationIssues = useMemo(() => validatePipeline(nodes, edges, providers), [nodes, edges, providers]);
  const hasErrors = validationIssues.some((i) => i.type === "error");

  const applyTemplate = useCallback((template: PipelineTemplate) => {
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

  const runValidation = () => setShowValidation(true);

  const spec = {
    stages: nodes.map((n) => ({ id: n.id, stage: (n.data as any).stage, label: (n.data as any).label })),
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
    <div className="flex h-full flex-col gap-3 p-4 bg-background text-text overflow-hidden">
      <Panel
        title="Pipeline Builder"
        subtitle="Visual routing & execution pipeline composer"
        className="flex-1 flex flex-col min-h-0 border-indigo-500/20 bg-surface/30 backdrop-blur-xl shadow-2xl"
        contentClassName="p-0 flex-1 flex flex-col min-h-0 overflow-hidden"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value as Stage)}
              className="rounded-lg border border-indigo-500/40 bg-black/60 px-2.5 py-1 text-xs text-text outline-none focus:border-indigo-400 font-mono"
              aria-label="Pipeline stage type"
            >
              {STAGES.map((s) => (
                <option key={s} value={s}>
                  + {s}
                </option>
              ))}
            </select>
            <button className="rounded-lg bg-indigo-500/20 border border-indigo-500/40 px-3 py-1 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/30 transition-all shadow-[0_0_12px_rgba(99,102,241,0.2)]" onClick={addNode} aria-label="Add node">
              + Add Stage
            </button>
            <button className="rounded-lg bg-surface/60 border border-border/60 px-3 py-1 text-xs text-muted hover:bg-surface hover:text-text transition-all" onClick={exportJson} aria-label="Export to clipboard">
              Export JSON
            </button>
            <button className="rounded-lg bg-surface/60 border border-border/60 px-3 py-1 text-xs text-faint hover:text-danger hover:border-danger/40 transition-all" onClick={runValidation} aria-label="Clear canvas">
              Clear
            </button>
            <button
              className={`rounded-lg border px-3 py-1 text-xs font-medium transition-all ${showCode ? "bg-cyan-500/20 border-cyan-400 text-cyan-300 shadow-[0_0_10px_rgba(34,211,238,0.3)]" : "bg-surface/60 border-border/60 text-muted hover:text-text"}`}
              onClick={() => setShowCode(!showCode)}
              aria-label={showCode ? "Switch to graph view" : "Switch to code view"}
              aria-pressed={showCode}
            >
              {showCode ? "Graph View" : "Code View"}
            </button>
          </div>
        }
      >
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {!showCode && (
            <div className="flex gap-2 px-4 py-2.5 overflow-x-auto border-b border-border/40 bg-surface/20 shrink-0 no-scrollbar">
              {PIPELINE_TEMPLATES.map((t) => (
                <button
                  key={t.name}
                  onClick={() => applyTemplate(t)}
                  className="flex flex-col items-start gap-1 rounded-xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/20 to-purple-950/20 px-3.5 py-2 text-left hover:border-indigo-400/70 hover:from-indigo-950/40 hover:to-purple-950/40 transition-all shrink-0 min-w-[150px] shadow-sm group"
                >
                  <div className="flex items-center gap-1.5 w-full">
                    <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 group-hover:animate-ping" />
                    <span className="text-xs font-bold text-indigo-200 truncate">{t.name}</span>
                  </div>
                  <span className="text-[10px] font-mono text-faint leading-tight group-hover:text-muted truncate max-w-[200px]">{t.description}</span>
                </button>
              ))}
            </div>
          )}
          {nodes.length === 0 && !showCode ? (
            <Empty title="Empty pipeline canvas" hint="Choose a pipeline template above or click '+ Add Stage' to build a execution topology." />
          ) : showCode ? (
            <div className="flex-1 h-full min-h-0" role="region" aria-label="Pipeline JSON code">
              <MonacoEditor value={JSON.stringify(spec, null, 2)} language="json" readOnly={false} onChange={handleCodeChange} />
            </div>
          ) : (
            <>
              <div ref={containerRef} className="flex-1 h-full w-full relative min-h-[350px]" role="application" aria-label="Pipeline graph editor" tabIndex={0}>
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
                  onNodeClick={(_e, node) => setSelectedId(node.id)}
                  onPaneClick={() => setSelectedId(null)}
                  aria-live="polite"
                >
                  <Background color="#1e1b4b" gap={20} size={1} />
                  <Controls showInteractive={false} className="bg-black/60 border border-border/40 rounded-xl overflow-hidden text-white" />
                  <MiniMap maskColor="rgba(8,10,16,0.85)" style={{ background: "#090d16", borderRadius: "12px", border: "1px solid rgba(255,255,255,0.1)" }} />
                </ReactFlow>
              </div>
              {showValidation && validationIssues.length > 0 && (
                <div className="fixed bottom-6 right-6 z-50 w-full md:w-[380px] max-w-[92vw] glass-strong rounded-2xl border border-border/80 shadow-2xl p-4 backdrop-blur-2xl animate-in slide-in-from-bottom-4 duration-300">
                  <div className="flex items-center justify-between mb-3 border-b border-border/40 pb-2">
                    <h3 className="font-semibold text-xs uppercase tracking-wider flex items-center gap-2">
                      {hasErrors ? (
                        <>
                          <span className="h-2 w-2 rounded-full bg-danger animate-pulse" /> Validation Failed
                        </>
                      ) : (
                        <>
                          <span className="h-2 w-2 rounded-full bg-warn animate-pulse" /> Validation Warnings
                        </>
                      )}
                    </h3>
                    <button onClick={() => setShowValidation(false)} className="p-1 rounded-lg hover:bg-surface/50 transition" aria-label="Dismiss">
                      <X size={16} className="text-faint hover:text-text" />
                    </button>
                  </div>
                  <ul className="space-y-2 max-h-60 overflow-y-auto no-scrollbar">
                    {validationIssues.map((issue, i) => (
                      <li
                        key={i}
                        className={`flex items-start gap-2 p-2.5 rounded-xl border text-xs ${issue.type === "error" ? "border-danger/30 bg-danger/10 text-danger" : "border-warn/30 bg-warn/10 text-warn"}`}
                      >
                        <span className="font-mono font-bold shrink-0">{issue.type === "error" ? "[ERR]" : "[WARN]"}</span>
                        <span className="flex-1 leading-relaxed">{issue.message}</span>
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

function handleCodeChange(value: string) {
  try {
    const parsed = JSON.parse(value);
    if (parsed.stages && parsed.edges) {
      localStorage.setItem(STORAGE_KEY, value);
    }
  } catch {
    // Invalid JSON, ignore
  }
}