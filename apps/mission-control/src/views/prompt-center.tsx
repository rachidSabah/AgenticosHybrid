"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  Suspense,
  type ChangeEvent,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  Handle,
  Position,
} from "reactflow";
import {
  Paperclip,
  Sparkles,
  Zap,
  Code,
  FileText,
  AlertCircle,
  Globe,
  Layers,
  X,
  History,
  ChevronDown,
  Folder,
  Brain,
  Activity,
  Radio,
  Rocket,
  Bot,
  Server,
  GitBranch,
  Network,
  Users,
  CheckCircle2,
  XCircle,
  Play,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────

interface PromptHistoryEntry {
  id: string;
  title: string;
  content: string;
  created_at: string;
  tokens: number;
}

interface Attachment {
  id: string;
  name: string;
  type: "image" | "document" | "code" | "archive" | "data" | "other";
  size: number;
  preview?: string;
}

type ExecNodeData = {
  label: string;
  status: string;
  type: "task" | "agent" | "system";
  startedAt?: number;
  duration?: number;
  tags?: (string | undefined)[];
};

type ExecNode = Node & { data: ExecNodeData };
type ExecEdge = Edge & { animated?: boolean; style?: Record<string, unknown> };

// ─────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────

const HISTORY_KEY = "mc.prompt.history";
const DRAFT_KEY = "mc.prompt.draft";
const MAX_HISTORY = 50;

const CLAUDE_STYLE_STARTERS = [
  {
    id: "architect",
    title: "Design a clean architecture",
    subtitle: "Component diagrams, system flow & data contracts",
    icon: Globe,
    prompt:
      "Design a clean system architecture for the following requirements. Include component diagrams, data contracts, and key design decisions.\n\n## Requirements\n",
  },
  {
    id: "code-gen",
    title: "Implement a production feature",
    subtitle: "Typescript, React, & Node.js clean implementation",
    icon: Code,
    prompt:
      "Implement a production-grade feature with full error handling and type safety.\n\n## Feature Description\n",
  },
  {
    id: "debug",
    title: "Debug & analyze root cause",
    subtitle: "Trace error stack & suggest precise fixes",
    icon: AlertCircle,
    prompt:
      "Analyze the root cause of this error and provide an authoritative fix.\n\n## Error Stack / Output\n",
  },
  {
    id: "refactor",
    title: "Refactor for performance & style",
    subtitle: "Optimize runtime efficiency & readability",
    icon: Layers,
    prompt:
      "Refactor this code to improve performance and maintainability while preserving exact behavior.\n\n## Code\n",
  },
];

interface AvailableModel {
  id: string;
  name: string;
  provider: string;
  tag: string;
}

// ─────────────────────────────────────────────────────────────
// Inline execution-graph nodes (mirroring execution-graph.tsx)
// ─────────────────────────────────────────────────────────────

const TASK_COLOR: Record<string, string> = {
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
const TASK_GLOW: Record<string, string> = {
  running: "rgba(16,185,129,0.25)",
  completed: "rgba(59,130,246,0.25)",
  failed: "rgba(239,68,68,0.25)",
  paused: "rgba(245,158,11,0.25)",
};

function MiniTaskNode({ data }: { data: ExecNodeData }) {
  const c = TASK_COLOR[data.status] ?? "#64748b";
  const g = TASK_GLOW[data.status] ?? "rgba(100,116,139,0.15)";
  const active = data.status === "running";
  return (
    <motion.div
      className="relative rounded-xl border px-3 py-2 min-w-[150px] backdrop-blur-sm text-xs"
      style={{ background: "rgba(12,14,22,0.92)", borderColor: c, boxShadow: `0 0 16px ${g}` }}
      initial={{ scale: 0.85, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.25 }}
    >
      {active && (
        <span
          className="absolute -inset-[1px] rounded-[11px] opacity-40 animate-pulse"
          style={{ border: `1px solid ${c}`, boxShadow: `0 0 20px ${c}` }}
        />
      )}
      <Handle type="target" position={Position.Left} style={{ background: c, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: c, width: 6, height: 6 }} />
      <div className="flex items-center gap-2">
        <span className="relative flex h-2 w-2 shrink-0">
          {active && (
            <span className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping" style={{ backgroundColor: c }} />
          )}
          <span className="relative inline-flex h-2 w-2 rounded-full" style={{ backgroundColor: c }} />
        </span>
        <span className="font-semibold truncate text-white/90">{data.label}</span>
        <span className="rounded px-1 py-0.5 text-[8px] uppercase tracking-wider" style={{ backgroundColor: `${c}22`, color: c }}>
          {data.status}
        </span>
      </div>
    </motion.div>
  );
}

function MiniAgentNode({ data }: { data: ExecNodeData }) {
  const colors: Record<string, string> = { running: "#8b5cf6", completed: "#10b981", failed: "#ef4444", idle: "#64748b" };
  const c = colors[data.status] ?? "#64748b";
  const active = data.status === "running";
  return (
    <motion.div
      className="relative rounded-xl border px-3 py-2 min-w-[150px] backdrop-blur-sm text-xs"
      style={{ background: "rgba(12,14,22,0.92)", borderColor: c, boxShadow: `0 0 16px rgba(139,92,246,0.2)` }}
      initial={{ scale: 0.85, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.25 }}
    >
      {active && (
        <span className="absolute -inset-[1px] rounded-[11px] opacity-40 animate-pulse" style={{ border: `1px solid ${c}` }} />
      )}
      <Handle type="target" position={Position.Left} style={{ background: c, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: c, width: 6, height: 6 }} />
      <div className="flex items-center gap-2">
        <Bot size={12} style={{ color: c }} />
        <span className="font-semibold truncate text-white/90">{data.label}</span>
        <span className="rounded px-1 py-0.5 text-[8px] uppercase tracking-wider" style={{ backgroundColor: `${c}22`, color: c }}>
          {data.status}
        </span>
      </div>
    </motion.div>
  );
}

function MiniSystemNode({ data }: { data: ExecNodeData }) {
  const c = "#06b6d4";
  const active = data.status === "running";
  return (
    <motion.div
      className="relative rounded-xl border px-3 py-2 min-w-[150px] backdrop-blur-sm text-xs"
      style={{ background: "rgba(12,14,22,0.92)", borderColor: c, boxShadow: `0 0 16px rgba(6,182,212,0.2)` }}
      initial={{ scale: 0.85, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ duration: 0.25 }}
    >
      {active && (
        <span className="absolute -inset-[1px] rounded-[11px] opacity-40 animate-pulse" style={{ border: `1px solid ${c}` }} />
      )}
      <Handle type="target" position={Position.Left} style={{ background: c, width: 6, height: 6 }} />
      <Handle type="source" position={Position.Right} style={{ background: c, width: 6, height: 6 }} />
      <div className="flex items-center gap-2">
        <Server size={12} style={{ color: c }} />
        <span className="font-semibold truncate text-white/90">{data.label}</span>
      </div>
    </motion.div>
  );
}

// Stable module-level node/edge types (React Flow requires stable identity)
const EXEC_NODE_TYPES: NodeTypes = {
  task: MiniTaskNode,
  agent: MiniAgentNode,
  system: MiniSystemNode,
};
const EXEC_EDGE_TYPES: EdgeTypes = {};

// ─────────────────────────────────────────────────────────────
// ExecutionGraphView — live ReactFlow panel shown post-dispatch
// ─────────────────────────────────────────────────────────────

function ExecutionGraphView({ missionId }: { missionId: string }) {
  const tasks = useStore((s) => s.tasks);
  const agents = useStore((s) => s.agents);

  const { nodes, edges } = useMemo(() => {
    const exNodes: ExecNode[] = [];
    const exEdges: ExecEdge[] = [];

    // System health root
    exNodes.push({
      id: "system-health",
      type: "system",
      position: { x: 0, y: 200 },
      data: { label: "Mission Control", status: "running", type: "system", tags: ["system"] },
    });

    // Task nodes (left-to-right layout)
    const taskArr = Object.values(tasks);
    taskArr.forEach((task, i) => {
      exNodes.push({
        id: `task-${task.id}`,
        type: "task",
        position: { x: 220 + (i % 3) * 230, y: 60 + Math.floor(i / 3) * 120 },
        data: {
          label: task.title || task.id,
          status: task.status,
          type: "task",
          tags: [task.role],
        },
      });
      exEdges.push({
        id: `edge-sys-t-${task.id}`,
        source: "system-health",
        target: `task-${task.id}`,
        animated: task.status === "running",
        style: { stroke: "#06b6d4", strokeOpacity: 0.3, strokeWidth: 1 },
      });
    });

    // Agent nodes
    const agentArr = Object.values(agents);
    agentArr.forEach((agent, i) => {
      exNodes.push({
        id: `agent-${agent.id}`,
        type: "agent",
        position: { x: 700 + (i % 2) * 220, y: 60 + Math.floor(i / 2) * 120 },
        data: {
          label: agent.role,
          status: agent.status,
          type: "agent",
          tags: [agent.provider],
        },
      });
      if (agent.current_task) {
        exEdges.push({
          id: `edge-a-t-${agent.id}`,
          source: `agent-${agent.id}`,
          target: `task-${agent.current_task}`,
          animated: agent.status === "running",
          style: { stroke: "#8b5cf6", strokeOpacity: 0.5, strokeWidth: 1.5 },
        });
      }
    });

    return { nodes: exNodes, edges: exEdges };
  }, [tasks, agents]);

  const taskCount = Object.values(tasks).length;
  const agentCount = Object.values(agents).length;
  const running = Object.values(tasks).filter((t) => t.status === "running").length;
  const done = Object.values(tasks).filter((t) => t.status === "completed").length;

  return (
    <div className="w-full rounded-2xl border border-cyan-400/20 bg-[#0a1020]/80 shadow-[0_0_40px_rgba(34,211,238,0.08)] backdrop-blur-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.25em] text-cyan-300/80">
          <Network size={12} />
          Live Execution Graph
          <span className="rounded bg-cyan-500/15 px-1.5 py-0.5 text-[8px] text-cyan-300">
            {missionId.slice(0, 8)}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[9px] font-mono uppercase tracking-widest text-white/40">
          <span className="flex items-center gap-1">
            <Play size={9} className="text-emerald-400" /> {running} running
          </span>
          <span className="flex items-center gap-1">
            <CheckCircle2 size={9} className="text-blue-400" /> {done} done
          </span>
          <span className="flex items-center gap-1">
            <GitBranch size={9} className="text-white/40" /> {taskCount} tasks
          </span>
          <span className="flex items-center gap-1">
            <Bot size={9} className="text-purple-400" /> {agentCount} agents
          </span>
        </div>
      </div>

      {/* Graph */}
      <div className="h-64 w-full">
        {nodes.length <= 1 ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center space-y-2">
              <div className="relative mx-auto h-8 w-8">
                <span className="absolute inset-0 rounded-full bg-cyan-400/20 animate-ping" />
                <span className="relative flex h-8 w-8 items-center justify-center rounded-full bg-cyan-400/10 border border-cyan-400/30">
                  <Network size={14} className="text-cyan-400" />
                </span>
              </div>
              <div className="font-mono text-[9px] uppercase tracking-widest text-white/30">
                Awaiting task graph…
              </div>
            </div>
          </div>
        ) : (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={EXEC_NODE_TYPES}
            edgeTypes={EXEC_EDGE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="rgba(34,211,238,0.04)" gap={24} />
            <Controls showInteractive={false} />
            <MiniMap
              maskColor="rgba(5,6,14,0.8)"
              style={{ background: "#080a10", border: "1px solid rgba(34,211,238,0.12)" }}
              nodeColor={(n: { data?: { status?: string } }) => {
                const s = n.data?.status;
                return { running: "#10b981", completed: "#3b82f6", failed: "#ef4444", paused: "#f59e0b" }[s ?? ""] ?? "#334155";
              }}
            />
          </ReactFlow>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Main PromptCenter component
// ─────────────────────────────────────────────────────────────

export function PromptCenter() {
  const [prompt, setPrompt] = useState<string>(() => {
    try {
      return localStorage.getItem(DRAFT_KEY) || "";
    } catch {
      return "";
    }
  });

  const [history, setHistory] = useState<PromptHistoryEntry[]>(() => {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  });

  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [selectedModel, setSelectedModel] = useState<AvailableModel | null>(null);
  const [workspacePath, setWorkspacePath] = useState<string>("");
  const [showWorkspacePicker, setShowWorkspacePicker] = useState(false);

  // Store — no agent targeting; always broadcast
  const providers = useStore((s) => s.providers);
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);
  const lastEvent = events.length > 0 ? events[0] : null;

  const connectedAgentCount = useMemo(
    () => Object.values(providers).filter((p) => p.provider && p.provider.toLowerCase() !== "mock").length,
    [providers],
  );

  const agentOptions = useMemo(() => {
    return Object.values(providers)
      .filter((p) => p.provider && p.provider.toLowerCase() !== "mock")
      .map((p) => ({
        id: (p.provider ?? "").toLowerCase().replace(/\s+/g, "-"),
        name: p.provider ?? "unknown",
        status: p.status ?? "unknown",
        latency: p.latency_ms ?? 0,
      }));
  }, [providers]);

  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [showAgentPicker, setShowAgentPicker] = useState(false);

  const toggleAgent = (name: string) => {
    setSelectedAgents((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
    );
  };

  const toggleAllAgents = () => {
    setSelectedAgents((prev) =>
      prev.length === agentOptions.length
        ? []
        : agentOptions.map((a) => a.name)
    );
  };

  const [statusLog, setStatusLog] = useState<string[]>([]);
  // Track the last dispatched mission id for graph display
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null);

  const pushStatus = useCallback((line: string) => {
    setStatusLog((prev) => [...prev.slice(-49), line]);
  }, []);

  // Track live task progress for the active mission
  useEffect(() => {
    if (!lastEvent || !activeMissionId) return;
    const p = lastEvent.payload as Record<string, any>;
    const isMission = p.mission_id === activeMissionId || p.id === activeMissionId || (lastEvent.topic.startsWith("mission.") && p.id === activeMissionId);
    if (isMission) {
      if (lastEvent.topic.startsWith("task.")) {
        const title = p.title || p.task_id || p.id || "Task";
        const status = lastEvent.topic.replace("task.", "");
        pushStatus(`Task ${title} → ${status}`);
      } else if (lastEvent.topic.startsWith("mission.")) {
        const status = lastEvent.topic.replace("mission.", "");
        pushStatus(`Mission → ${status}`);
      } else if (lastEvent.topic.startsWith("execution.")) {
        const status = lastEvent.topic.replace("execution.", "");
        const taskTitle = p.task_id || "Task";
        pushStatus(`Execution ${taskTitle} → ${status}`);
      }
    }
  }, [lastEvent, activeMissionId, pushStatus]);

  // Fetch current workspace on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.workspaceCurrent();
        if (!cancelled && res?.path) setWorkspacePath(res.path);
      } catch {
        // Backend may not support workspace yet
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fetch live models from the API Gateway
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.gatewayModels();
        if (cancelled) return;
        const models: AvailableModel[] = (res?.data ?? []).map((m: { id: string; owned_by?: string }) => ({
          id: m.id,
          name: m.id,
          provider: m.owned_by ?? "unknown",
          tag: "",
        }));
        setAvailableModels(models);
        setSelectedModel((prev) => prev && models.find((m) => m.id === prev.id) ? prev : (models[0] ?? null));
      } catch {
        // Keep empty — no fake fallback.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const [showModelPicker, setShowModelPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(true);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Revoke blob URLs on unmount
  useEffect(() => {
    return () => {
      for (const att of attachments) {
        if (att.preview) URL.revokeObjectURL(att.preview);
      }
    };
  }, [attachments]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 320)}px`;
    }
  }, [prompt]);

  // Draft auto-save
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(DRAFT_KEY, prompt);
      } catch {}
    }, 1000);
    return () => clearTimeout(timer);
  }, [prompt]);

  const saveToHistory = useCallback(() => {
    if (!prompt.trim()) return;
    const entry: PromptHistoryEntry = {
      id: `hist-${Date.now()}`,
      title: prompt.split("\n")[0]?.slice(0, 50) || "Untitled Prompt",
      content: prompt,
      created_at: new Date().toISOString(),
      tokens: Math.ceil(prompt.length / 4),
    };
    const updated = [entry, ...history.filter((h) => h.content !== prompt)].slice(0, MAX_HISTORY);
    setHistory(updated);
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    } catch {}
  }, [prompt, history]);

  const handleSubmit = async () => {
    if (!prompt.trim() || submitting) return;
    setSubmitting(true);
    setStatusLog([]);
    setActiveMissionId(null);
    saveToHistory();
    try {
      pushStatus("Creating mission…");
      const mission = await api.createMission({
        title: prompt.split("\n")[0]?.slice(0, 60) || "Prompt Mission",
        description: prompt,
        prompt,
        priority: "high",
        execution_mode: "hybrid",
        preferred_agents: selectedAgents,
      });

      if (mission?.id) {
        pushStatus("Mission planned → routing tasks…");
        await api.planMission(mission.id);
        const started = await api.startMission(mission.id);
        pushStatus(
          selectedAgents.length > 0
            ? `Dispatched → ${selectedAgents.length} selected agent${selectedAgents.length === 1 ? "" : "s"}`
            : "Dispatched → routed via default provider selection",
        );

        // Push into store so Mission Orchestrator + Swarm views pick it up live
        useStore.getState().updateMission(started ?? mission);
        setActiveMissionId(mission.id);

        // ── Auto-create swarm for this mission (real backend team) ──
        try {
          pushStatus("Initializing swarm orchestration…");
          const maxAgents = Math.max(3, connectedAgentCount);
          const swarm = await api.createSwarm({
            name: `mission-${mission.id}-swarm`,
            topology: "hierarchical",
            max_agents: maxAgents,
            timeout_seconds: 1800,
            tags: ["mission", "auto-generated", mission.id],
          });
          const agentCount = typeof swarm?.agent_count === "number" ? swarm.agent_count : 0;
          const swarmId = (swarm?.id as string | undefined) ?? "?";
          pushStatus(
            agentCount > 0
              ? `Swarm ${swarmId.slice(0, 8)} created → ${agentCount} real member(s)`
              : "Swarm created → no agents available to join",
          );

          // Analyze goal & create plan in parallel (report honestly)
          const [analyze, plan] = await Promise.allSettled([
            api.swarmAnalyzeGoal({ description: prompt }),
            api.swarmCreatePlan({ description: prompt }),
          ]);
          if (analyze.status === "fulfilled" && plan.status === "fulfilled") {
            pushStatus("Swarm plan generated");
          } else {
            pushStatus("Swarm planning incomplete — mission dispatch continues");
          }
        } catch (e) {
          console.warn("Swarm init failed:", e);
          pushStatus("Swarm init skipped — continuing with direct dispatch");
        }
      }

      setPrompt("");
      for (const att of attachments) {
        if (att.preview) URL.revokeObjectURL(att.preview);
      }
      setAttachments([]);
    } catch (e) {
      console.error("Submission failed:", e);
      pushStatus("Dispatch failed — check backend / agent health");
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleFilePick = (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    for (const file of files) {
      const id = `att-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setAttachments((prev) => [
        ...prev,
        {
          id,
          name: file.name,
          type: file.type.startsWith("image/") ? "image" : "document",
          size: file.size,
          preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
        },
      ]);
    }
    if (e.target) e.target.value = "";
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const target = prev.find((a) => a.id === id);
      if (target?.preview) URL.revokeObjectURL(target.preview);
      return prev.filter((a) => a.id !== id);
    });
  };

  return (
    <div className="relative flex h-full w-full flex-col items-center overflow-y-auto bg-[#05060e] px-4 py-8 text-[#c8d3e8]">
      {/* ── Ambient starfield layers ── */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(1px 1px at 15% 25%, rgba(148,190,255,0.40) 0, transparent 100%)," +
            "radial-gradient(1px 1px at 75% 15%, rgba(148,190,255,0.30) 0, transparent 100%)," +
            "radial-gradient(1.2px 1.2px at 38% 68%, rgba(103,232,249,0.55) 0, transparent 100%)," +
            "radial-gradient(1px 1px at 88% 55%, rgba(148,190,255,0.35) 0, transparent 100%)," +
            "radial-gradient(1.2px 1.2px at 8% 82%, rgba(103,232,249,0.45) 0, transparent 100%)," +
            "radial-gradient(1px 1px at 52% 42%, rgba(148,190,255,0.25) 0, transparent 100%)," +
            "radial-gradient(1px 1px at 93% 10%, rgba(148,190,255,0.20) 0, transparent 100%)," +
            "radial-gradient(1px 1px at 30% 95%, rgba(103,232,249,0.30) 0, transparent 100%)",
        }}
      />
      {/* Cyan aurora top */}
      <div className="pointer-events-none absolute -top-40 left-1/2 h-96 w-[65rem] -translate-x-1/2 rounded-full bg-cyan-500/10 blur-3xl" />
      {/* Indigo glow bottom */}
      <div className="pointer-events-none absolute bottom-0 left-1/4 h-72 w-[45rem] rounded-full bg-indigo-500/6 blur-3xl" />
      {/* Grid texture overlay */}
      <div className="pointer-events-none absolute inset-0 grid-texture opacity-25" />

      {/* ── Constellation connector lines (decorative SVG) ── */}
      <svg
        className="pointer-events-none absolute inset-0 h-full w-full opacity-[0.04]"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <line x1="20%" y1="15%" x2="50%" y2="45%" stroke="#22d3ee" strokeWidth="0.5" />
        <line x1="50%" y1="45%" x2="80%" y2="20%" stroke="#22d3ee" strokeWidth="0.5" />
        <line x1="80%" y1="20%" x2="95%" y2="60%" stroke="#22d3ee" strokeWidth="0.5" />
        <line x1="5%"  y1="70%" x2="30%" y2="50%" stroke="#818cf8" strokeWidth="0.5" />
        <line x1="30%" y1="50%" x2="50%" y2="45%" stroke="#818cf8" strokeWidth="0.5" />
        <circle cx="20%" cy="15%" r="2" fill="#22d3ee" />
        <circle cx="50%" cy="45%" r="2.5" fill="#22d3ee" />
        <circle cx="80%" cy="20%" r="2" fill="#22d3ee" />
        <circle cx="95%" cy="60%" r="1.5" fill="#818cf8" />
        <circle cx="5%"  cy="70%" r="1.5" fill="#818cf8" />
        <circle cx="30%" cy="50%" r="2" fill="#818cf8" />
      </svg>

      {/* ── Top Header Navigation ── */}
      <div className="relative z-30 w-full max-w-5xl flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="absolute inset-0 rounded-xl bg-cyan-400/30 blur-md" />
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-400/40 bg-[#0a1020] text-cyan-300">
              <Brain size={18} />
            </div>
          </div>
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.3em] text-cyan-300">
              AGENTIC OS
            </div>
            <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/40">
              PROMPT CENTER · MISSION UPLINK
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {/* Model Selector */}
          <div className="relative">
            <button
              onClick={() => setShowModelPicker(!showModelPicker)}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-semibold text-white backdrop-blur-lg hover:border-cyan-400/40 hover:bg-cyan-400/5 transition shadow-sm"
            >
              <Sparkles size={15} className="text-cyan-400" />
              <span>{selectedModel?.name ?? "No models available"}</span>
              {selectedModel?.tag && (
                <span className="rounded bg-cyan-500/20 px-1.5 py-0.5 text-[9px] text-cyan-300 font-mono">
                  {selectedModel.tag}
                </span>
              )}
              <ChevronDown size={14} className="text-white/50" />
            </button>

            <AnimatePresence>
              {showModelPicker && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 6 }}
                  className="absolute right-0 top-11 z-50 w-72 rounded-2xl border border-cyan-400/20 bg-[#0a1020]/95 p-2 shadow-2xl backdrop-blur-xl"
                >
                  {availableModels.length === 0 ? (
                    <div className="px-3 py-2.5 text-xs text-white/40">No models discovered</div>
                  ) : (
                    availableModels.map((m) => (
                      <button
                        key={m.id}
                        onClick={() => { setSelectedModel(m); setShowModelPicker(false); }}
                        className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-xs transition ${
                          selectedModel?.id === m.id ? "bg-cyan-500/15 text-cyan-200 font-medium" : "text-white/80 hover:bg-white/5"
                        }`}
                      >
                        <div>
                          <div className="font-semibold">{m.name}</div>
                          <div className="text-[10px] text-white/40">{m.provider}</div>
                        </div>
                        {m.tag && (
                          <span className="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-white/60">
                            {m.tag}
                          </span>
                        )}
                      </button>
                    ))
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Workspace Selector */}
          <div className="relative">
            <button
              onClick={() => setShowWorkspacePicker(!showWorkspacePicker)}
              className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-semibold text-white backdrop-blur-lg hover:border-cyan-400/40 hover:bg-cyan-400/5 transition shadow-sm"
              title="Select workspace directory"
            >
              <Folder size={15} className="text-emerald-400" />
              <span className="max-w-[110px] truncate">
                {workspacePath ? workspacePath.split("/").pop() || workspacePath : "No workspace"}
              </span>
              {workspacePath && (
                <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] text-emerald-300 font-mono">
                  active
                </span>
              )}
              <ChevronDown size={14} className="text-white/50" />
            </button>

            <AnimatePresence>
              {showWorkspacePicker && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 6 }}
                  className="absolute right-0 top-11 z-50 w-80 rounded-2xl border border-cyan-400/20 bg-[#0a1020]/95 p-3 shadow-2xl backdrop-blur-xl"
                >
                  <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-widest text-white/40">
                    Workspace Path
                  </div>
                  <input
                    type="text"
                    value={workspacePath}
                    onChange={(e) => setWorkspacePath(e.target.value)}
                    placeholder="/path/to/your/project"
                    className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white placeholder-white/30 outline-none focus:border-cyan-400/50"
                  />
                  <div className="mt-2 flex gap-2">
                    <button
                      onClick={async () => {
                        try {
                          await api.workspaceSelect(workspacePath);
                          setShowWorkspacePicker(false);
                        } catch {
                          // ignore
                        }
                      }}
                      className="flex-1 rounded-lg bg-cyan-500/20 px-3 py-1.5 text-xs font-medium text-cyan-300 hover:bg-cyan-500/30 transition"
                    >
                      Set Workspace
                    </button>
                    <button
                      onClick={async () => {
                        try {
                          const res = await api.workspaceCurrent();
                          if (res?.path) setWorkspacePath(res.path);
                        } catch {
                          // ignore
                        }
                      }}
                      className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/60 hover:bg-white/10 transition"
                    >
                      Refresh
                    </button>
                  </div>
                  <div className="mt-2 text-[9px] text-white/30">
                    The workspace path is injected into task prompts so AI agents can see your project files.
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Extended Thinking toggle */}
          <button
            onClick={() => setThinkingMode(!thinkingMode)}
            className={`flex items-center gap-1.5 rounded-xl border px-3 py-2 text-xs font-medium transition ${
              thinkingMode
                ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-300"
                : "border-white/10 bg-white/[0.03] text-white/60 hover:text-white"
            }`}
          >
            <Brain size={14} />
            <span>Extended Thinking</span>
          </button>

          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-medium text-white/80 hover:bg-white/10 hover:text-white transition"
          >
            <History size={14} />
            <span>History</span>
          </button>
        </div>
      </div>

      {/* ── Main Center Content ── */}
      <div className="relative z-10 my-auto w-full max-w-3xl flex flex-col items-center text-center space-y-6">
        {/* Welcome Greeting */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-2"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-1 text-xs font-medium text-cyan-300">
            <Sparkles size={13} />
            MISSION UPLINK · MULTI-AGENT ORCHESTRATION
          </div>
          <h1 className="text-3xl sm:text-4xl font-serif font-normal text-white tracking-tight">
            What can I help you build today?
          </h1>
          {/* Live broadcast status banner (replaces agent picker) */}
          <motion.div
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 }}
            className="inline-flex items-center gap-2.5 rounded-2xl border border-cyan-400/20 bg-cyan-400/5 px-4 py-2 text-xs text-cyan-300/80"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75 animate-ping" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400" />
            </span>
            <Radio size={12} />
            <span className="font-mono text-[10px] uppercase tracking-widest">
              {selectedAgents.length > 0
                ? `Targeting ${selectedAgents.length} selected agent${selectedAgents.length === 1 ? "" : "s"}`
                : connectedAgentCount > 0
                  ? `Routing through ${connectedAgentCount} discovered agent${connectedAgentCount === 1 ? "" : "s"}`
                  : "No agents discovered"}
            </span>
          </motion.div>
        </motion.div>

        {/* ── Prompt Input Container (Futuristic Glass Card) ── */}
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="relative z-20 w-full rounded-3xl border border-cyan-400/20 bg-[#0a1020]/80 p-4 shadow-[0_0_40px_rgba(34,211,238,0.08)] backdrop-blur-2xl transition-all focus-within:border-cyan-400/50 focus-within:ring-2 focus-within:ring-cyan-400/20"
        >
          {/* Attachments preview list */}
          {attachments.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-2 text-left">
              {attachments.map((att) => (
                <div key={att.id} className="group relative flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/90">
                  {att.preview ? (
                    // Blob URL preview — next/image optimization does not apply to
                    // ephemeral object URLs, so a plain <img> is the correct choice.
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={att.preview} alt="" className="h-6 w-6 rounded object-cover" />
                  ) : (
                    <FileText size={14} className="text-cyan-400" />
                  )}
                  <span className="truncate max-w-[140px] text-[11px] font-medium">{att.name}</span>
                  <button
                    onClick={() => removeAttachment(att.id)}
                    className="text-white/40 hover:text-red-400 ml-1"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Prompt Textarea */}
          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Reply to Mission Control or paste code..."
            rows={2}
            className="w-full resize-none bg-transparent px-2 py-1 text-sm sm:text-base text-white placeholder-white/40 outline-none font-sans leading-relaxed"
          />

          {/* Input Card Footer */}
          <div className="mt-3 flex items-center justify-between pt-2 border-t border-white/5 text-xs">
            <div className="flex items-center gap-2 text-white/50">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-1.5 rounded-xl px-2.5 py-1.5 hover:bg-white/10 hover:text-white transition"
              >
                <Paperclip size={16} />
                <span className="text-[11px]">Add content</span>
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={handleFilePick}
              />
            </div>

            <div className="flex items-center gap-3">
              {/* Target Agent Floating Popover Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowAgentPicker(!showAgentPicker)}
                  className={`hidden sm:flex items-center gap-1.5 rounded-xl border px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider transition ${
                    selectedAgents.length > 0
                      ? "border-cyan-400/50 bg-cyan-400/10 text-cyan-200 shadow-[0_0_12px_rgba(34,211,238,0.15)]"
                      : "border-white/10 bg-white/[0.03] text-cyan-300/70 hover:border-cyan-400/30 hover:bg-cyan-400/5"
                  }`}
                >
                  <Users size={12} className="text-cyan-400" />
                  <span>
                    {selectedAgents.length > 0
                      ? `${selectedAgents.length} AGENT${selectedAgents.length === 1 ? "" : "S"}`
                      : "ALL AGENTS"}
                  </span>
                  <ChevronDown size={12} className="text-white/40" />
                </button>

                <AnimatePresence>
                  {showAgentPicker && (
                    <motion.div
                      initial={{ opacity: 0, y: -8, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: -8, scale: 0.95 }}
                      className="absolute right-0 bottom-full mb-2 z-50 w-72 rounded-2xl border border-cyan-400/30 bg-[#0d1220]/95 p-3 shadow-[0_10px_40px_rgba(0,0,0,0.8),0_0_24px_rgba(34,211,238,0.15)] backdrop-blur-2xl text-left"
                    >
                      <div className="mb-2 flex items-center justify-between pb-2 border-b border-white/10">
                        <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-300 flex items-center gap-1.5">
                          <Users size={12} />
                          Target Agents
                        </div>
                        <button
                          type="button"
                          onClick={toggleAllAgents}
                          disabled={agentOptions.length === 0}
                          className="font-mono text-[9px] uppercase tracking-wider text-cyan-400/80 hover:text-cyan-200 disabled:opacity-30 transition"
                        >
                          {selectedAgents.length === agentOptions.length ? "CLEAR" : "SELECT ALL"}
                        </button>
                      </div>

                      <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
                        {agentOptions.length === 0 ? (
                          <div className="px-3 py-4 text-center font-mono text-[10px] uppercase text-white/40">
                            {connected ? "Runtime discovery pending…" : "No agents connected"}
                          </div>
                        ) : (
                          agentOptions.map((a) => {
                            const active = selectedAgents.includes(a.name);
                            return (
                              <button
                                key={a.id}
                                type="button"
                                onClick={() => toggleAgent(a.name)}
                                className={`flex w-full items-center gap-2 rounded-xl border px-2.5 py-2 text-left transition ${
                                  active
                                    ? "border-cyan-400/50 bg-cyan-400/15 text-cyan-200"
                                    : "border-white/5 bg-white/[0.02] text-white/70 hover:bg-white/5 hover:text-white"
                                }`}
                              >
                                <span className={`flex h-4 w-4 items-center justify-center rounded border transition shrink-0 ${
                                  active ? "border-cyan-400 bg-cyan-400/30 text-cyan-200" : "border-white/20 text-transparent"
                                }`}>
                                  <CheckCircle2 size={11} />
                                </span>
                                <span className="flex-1 truncate text-xs font-medium">
                                  {a.name}
                                </span>
                                <span className="text-[9px] font-mono text-white/35 uppercase">
                                  {a.status}
                                </span>
                              </button>
                            );
                          })
                        )}
                      </div>

                      <div className="mt-2 border-t border-white/10 pt-1.5 font-mono text-[9px] uppercase tracking-wider text-white/40 text-center">
                        {selectedAgents.length > 0
                          ? `→ ${selectedAgents.length} targeted agent${selectedAgents.length === 1 ? "" : "s"}`
                          : "→ Broadcast to ALL connected agents"}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              <span className="text-[10px] text-white/40 font-mono">
                {prompt.length} chars
              </span>

              {/* Submit Button — Rocket launch */}
              <button
                onClick={handleSubmit}
                disabled={!prompt.trim() || submitting}
                className="group relative flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-400 text-[#05060e] hover:bg-cyan-300 disabled:opacity-30 disabled:hover:bg-cyan-400 transition shadow-lg shadow-cyan-400/30"
                title="Dispatch as mission"
              >
                {submitting ? (
                  <span className="h-4 w-4 rounded-full border-2 border-black/30 border-t-black animate-spin" />
                ) : (
                  <Rocket size={17} strokeWidth={2.5} className="transition-transform group-hover:-translate-y-0.5 group-hover:scale-110" />
                )}
              </button>
            </div>
          </div>
        </motion.div>

        {/* ── Dispatch status pipeline ── */}
        <AnimatePresence>
          {statusLog.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              className="w-full rounded-2xl border border-cyan-400/15 bg-[#0a1020]/70 px-4 py-3 text-left backdrop-blur-xl"
            >
              <div className="mb-1.5 flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.25em] text-cyan-300/70">
                <Activity size={11} />
                Mission Pipeline
                {submitting && (
                  <span className="ml-auto flex items-center gap-1 text-cyan-400/60">
                    <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
                    Live
                  </span>
                )}
              </div>
              <div className="space-y-1 max-h-40 overflow-y-auto pr-2">
                {statusLog.map((line, i) => (
                  <div key={i} className="flex items-center gap-2 text-[11px] text-white/70">
                    <Zap size={10} className="text-cyan-400 shrink-0" />
                    <span className="font-mono text-[10px]">{line}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Live Execution Graph (shown after mission dispatch) ── */}
        <AnimatePresence>
          {activeMissionId && (
            <motion.div
              key={activeMissionId}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              transition={{ duration: 0.4 }}
              className="w-full"
            >
              <ExecutionGraphView missionId={activeMissionId} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Starter Prompt Cards ── */}
        <div className="grid w-full grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          {CLAUDE_STYLE_STARTERS.map((s) => {
            const Icon = s.icon;
            return (
              <button
                key={s.id}
                onClick={() => setPrompt(s.prompt)}
                className="group flex items-start gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-3.5 text-left hover:border-cyan-400/30 hover:bg-white/[0.05] transition-all"
              >
                <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/10 p-2 text-cyan-400 group-hover:scale-105 transition-transform">
                  <Icon size={16} />
                </div>
                <div>
                  <div className="text-xs font-semibold text-white/90 group-hover:text-cyan-300 transition-colors">
                    {s.title}
                  </div>
                  <div className="text-[11px] text-white/40 mt-0.5">
                    {s.subtitle}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── History Drawer Modal ── */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-md p-4"
          >
            <motion.div
              initial={{ x: 300 }}
              animate={{ x: 0 }}
              exit={{ x: 300 }}
              className="h-full w-full max-w-md rounded-3xl border border-white/10 bg-[#0a1020] p-6 shadow-2xl flex flex-col justify-between"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div className="flex items-center gap-2">
                  <History size={18} className="text-cyan-400" />
                  <h2 className="text-sm font-semibold text-white">Prompt History</h2>
                </div>
                <button onClick={() => setShowHistory(false)} className="text-white/40 hover:text-white">
                  <X size={16} />
                </button>
              </div>

              <div className="my-4 flex-1 overflow-y-auto space-y-2">
                {history.length === 0 ? (
                  <div className="py-12 text-center text-xs text-white/40">No prompts saved yet.</div>
                ) : (
                  history.map((h) => (
                    <button
                      key={h.id}
                      onClick={() => {
                        setPrompt(h.content);
                        setShowHistory(false);
                      }}
                      className="w-full rounded-2xl border border-white/5 bg-white/5 p-3 text-left hover:border-cyan-400/30 hover:bg-white/10 transition"
                    >
                      <div className="truncate text-xs font-semibold text-white">{h.title}</div>
                      <div className="text-[10px] text-white/40 mt-1 flex justify-between">
                        <span>{new Date(h.created_at).toLocaleDateString()}</span>
                        <span>~{h.tokens} tokens</span>
                      </div>
                    </button>
                  ))
                )}
              </div>

              <button
                onClick={() => {
                  setHistory([]);
                  localStorage.removeItem(HISTORY_KEY);
                }}
                className="w-full rounded-xl border border-red-500/30 bg-red-500/10 py-2.5 text-xs font-semibold text-red-400 hover:bg-red-500/20 transition"
              >
                Clear History
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Footer System Status ── */}
      <div className="relative z-10 w-full max-w-5xl flex items-center justify-between text-[11px] text-white/40 pt-4 border-t border-white/5">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-emerald-500"}`} />
          <span>{connected ? "EventBus Live" : "Mission Control Core Active"}</span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[9px] uppercase tracking-widest">
          <span className="flex items-center gap-1.5">
            <Users size={11} className="text-cyan-400/70" />
            {connectedAgentCount} AGENTS DISCOVERED
          </span>
          <span className="flex items-center gap-1.5 text-cyan-300/70">
            <Radio size={11} />
            BROADCAST DISPATCH
          </span>
          {activeMissionId && (
            <span className="flex items-center gap-1.5 text-emerald-400/70">
              <Network size={11} />
              SWARM ACTIVE · {activeMissionId.slice(0, 8)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
