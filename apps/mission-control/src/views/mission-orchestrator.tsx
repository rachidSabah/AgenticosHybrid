"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type {
  MissionType, MissionPlanType, MissionTaskType, EventEnvelope,
  MemoryItem, ProviderHealthRecord, MissionAttachment,
  GatewayStrategy, MissionRoutePlanType, TaskRouteAssignmentType,
} from "@/lib/types";
import {
  Plus, X, Check, Play, Pause, Trash2, FileText, Target, ListTodo, Tag, Clock,
  ChevronDown, ChevronUp, RefreshCw, RotateCcw, UserPlus, AlertCircle,
  Upload, Paperclip, Download, GripVertical, BrainCircuit, MessageCircle,
  GitMerge, Kanban, CheckCircle2, XCircle, Loader2, Layers, Workflow,
  Activity, Server, Route,
} from "lucide-react";

const PRIORITIES = ["low", "medium", "high", "critical"];
const MODES = ["sequential", "parallel", "hybrid"];

const STATUS_COLORS: Record<string, string> = {
  draft: "#6b7280", planning: "#f59e0b", planned: "#6366f1",
  executing: "#22c55e", paused: "#f59e0b", completed: "#22c55e",
  failed: "#ef4444", cancelled: "#6b7280",
};
const TASK_COLORS: Record<string, string> = {
  pending: "#6b7280", planned: "#6366f1", assigned: "#8b5cf6",
  running: "#22c55e", completed: "#22c55e", failed: "#ef4444",
  blocked: "#ef4444", skipped: "#6b7280",
};

// ── Agent provider definitions ──
const AGENT_PROVIDERS = [
  { id: "claude", label: "Claude Code", color: "#d97706", role: "Architecture, Refactoring, Reasoning" },
  { id: "hermes", label: "Hermes", color: "#8b5cf6", role: "Analysis, Debugging, Validation, Security" },
  { id: "opencode", label: "OpenCode", color: "#06b6d4", role: "Implementation, Feature Completion, Tests" },
  { id: "codex", label: "Codex CLI", color: "#10b981", role: "Code Generation, API Implementation" },
  { id: "gemini", label: "Gemini CLI", color: "#4285f4", role: "Research, Documentation, Alternatives" },
  { id: "ollama", label: "Ollama", color: "#f97316", role: "Offline Assistance, Local Execution" },
];

// ── Events relevant for inter-agent comms ──
const COMMS_TOPICS = new Set([
  "task.dispatched", "task.planned", "task.created",
  "agent.started", "agent.completed", "agent.failed", "agent.recovered",
  "approval.requested", "approval.decided",
  "memory.written", "memory.evicted",
]);

// ── Merge validation stages ──
const MERGE_STAGES = [
  { id: "conflicts", label: "Conflict Detection", icon: GitMerge },
  { id: "merge", label: "Merge Changes", icon: Layers },
  { id: "format", label: "Formatting", icon: FileText },
  { id: "lint", label: "Linting", icon: CheckCircle2 },
  { id: "tests", label: "Tests", icon: Activity },
  { id: "security", label: "Security Scan", icon: AlertCircle },
  { id: "regression", label: "Regression", icon: RotateCcw },
  { id: "documentation", label: "Documentation", icon: FileText },
] as const;

// ── OmniRoute strategy labels ──
const ROUTING_STRATEGIES: { id: GatewayStrategy; label: string; desc: string; icon: string }[] = [
  { id: "balanced", label: "Balanced", desc: "Equal weight across all dimensions", icon: "⚖️" },
  { id: "fastest", label: "Fastest", desc: "Minimize response latency", icon: "⚡" },
  { id: "cheapest", label: "Cheapest", desc: "Minimize cost per token", icon: "💰" },
  { id: "best_capability", label: "Best Capability", desc: "Maximize model capability score", icon: "🧠" },
  { id: "reliability_first", label: "Reliability First", desc: "Least error-prone providers", icon: "🛡️" },
  { id: "latency_first", label: "Latency First", desc: "Lowest latency providers", icon: "🏎️" },
  { id: "custom", label: "Custom", desc: "Manual assignment", icon: "🎛️" },
];

// ── Main Component ──
export function MissionOrchestrator() {
  const [missions, setMissions] = useState<MissionType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedMission, setSelectedMission] = useState<MissionType | null>(null);
  const [planning, setPlanning] = useState<string | null>(null);
  const [rightTab, setRightTab] = useState<string>("detail");

  // Live mission updates from EventBus
  const missionStore = useStore((s) => s.missions);
  const missionUpdates = useStore((s) => s.missionUpdates);

  const loadMissions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.missions();
      setMissions(data);
      useStore.getState().setMissions(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMissions(); }, [loadMissions]);

  // Merge live store updates
  useEffect(() => {
    if (missionUpdates && Object.keys(missionStore).length > 0) {
      setMissions((prev) =>
        prev.map((m) => missionStore[m.id] ? { ...m, ...missionStore[m.id] } : m),
      );
      if (selectedMission && missionStore[selectedMission.id]) {
        setSelectedMission((prev) =>
          prev ? { ...prev, ...missionStore[prev.id] } : prev,
        );
      }
    }
  }, [missionUpdates, missionStore, selectedMission]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      {/* Left column */}
      <div className="col-span-12 lg:col-span-4 flex flex-col gap-4">
        <AgentStatusList />
        <Panel
          title="Missions"
          subtitle={`${missions.length} total`}
          actions={
            <div className="flex items-center gap-1">
              <button className="pill bg-surface/60 text-faint hover:text-text" onClick={loadMissions} title="Refresh">
                <RefreshCw size={12} />
              </button>
              <button
                className="pill bg-accent/20 text-accent hover:bg-accent/30"
                onClick={() => setShowCreate(!showCreate)}
              >
                {showCreate ? <X size={14} /> : <Plus size={14} />}
                {showCreate ? "Close" : "New"}
              </button>
            </div>
          }
          className="flex-1 min-h-0"
        >
          {showCreate ? (
            <MissionForm
              onSubmit={async (data) => {
                await api.createMission(data);
                setShowCreate(false);
                loadMissions();
              }}
              onCancel={() => setShowCreate(false)}
            />
          ) : loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="h-16 glass rounded-xl animate-pulse" />)}
            </div>
          ) : error ? (
            <div className="text-sm text-danger p-3 glass rounded-xl">{error}</div>
          ) : missions.length === 0 ? (
            <Empty title="No missions yet" hint="Click 'New' to create your first mission." />
          ) : (
            <div className="space-y-2 h-full overflow-y-auto">
              {missions.map((m) => (
                <MissionCard
                  key={`${m.id}-${m.status}-${m.updated_at}`}
                  mission={m}
                  selected={selectedMission?.id === m.id}
                  onClick={() => { setSelectedMission(m); setRightTab("detail"); }}
                  onPlan={async () => {
                    setPlanning(m.id);
                    try { await api.planMission(m.id); await loadMissions(); }
                    finally { setPlanning(null); }
                  }}
                  onStart={async () => { await api.startMission(m.id); loadMissions(); }}
                  onPause={async () => { await api.pauseMission(m.id); loadMissions(); }}
                  onCancel={async () => { await api.cancelMission(m.id); loadMissions(); }}
                  onDelete={async () => {
                    await api.deleteMission(m.id);
                    if (selectedMission?.id === m.id) setSelectedMission(null);
                    loadMissions();
                  }}
                  planning={planning === m.id}
                />
              ))}
            </div>
          )}
        </Panel>
      </div>

      {/* Right column */}
      <div className="col-span-12 lg:col-span-8 flex flex-col gap-4">
        {selectedMission ? (
          <>
            <MissionDetail mission={selectedMission} onRefresh={loadMissions} />

            {/* Tab bar for additional panels */}
            <div className="flex items-center gap-1 rounded-xl bg-surface/20 p-0.5 shrink-0 overflow-x-auto">
              {[
                { id: "detail", label: "Plan & Tasks", icon: ListTodo },
                { id: "timeline", label: "Timeline", icon: Kanban },
                { id: "memory", label: "Shared Memory", icon: BrainCircuit },
                { id: "comms", label: "Agent Comms", icon: MessageCircle },
                { id: "merge", label: "Merge & Validate", icon: GitMerge },
                { id: "validation", label: "Final Validation", icon: CheckCircle2 },
              ].map((tab) => (
                <button
                  key={tab.id}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium transition-colors whitespace-nowrap ${
                    rightTab === tab.id
                      ? "bg-accent/15 text-accent"
                      : "text-faint hover:text-text hover:bg-surface/30"
                  }`}
                  onClick={() => setRightTab(tab.id)}
                >
                  <tab.icon size={12} />
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={rightTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.15 }}
                className="flex-1 min-h-0"
              >
                {rightTab === "detail" && selectedMission.plan && (
                  <MissionPlanView plan={selectedMission.plan} mission={selectedMission} />
                )}
                {rightTab === "detail" && !selectedMission.plan && (
                  <Panel title="Execution Plan" subtitle="Not yet planned" className="h-full">
                    <Empty title="No plan yet" hint="Click the Plan button on the mission card." />
                  </Panel>
                )}
                {rightTab === "timeline" && <ExecutionTimeline plan={selectedMission.plan} />}
                {rightTab === "memory" && <SharedMemoryPanel />}
                {rightTab === "comms" && <AgentCommsLog missionId={selectedMission.id} />}
                {rightTab === "merge" && <MergePipelinePanel />}
                {rightTab === "validation" && <FinalValidationPanel mission={selectedMission} />}
              </motion.div>
            </AnimatePresence>
          </>
        ) : (
          <Panel title="Mission Detail" subtitle="Select a mission to view" className="flex-1 min-h-0">
            <Empty title="No mission selected" hint="Select a mission from the left panel." />
          </Panel>
        )}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  EXTENDED AGENT STATUS LIST
// ══════════════════════════════════════════════════════════════

function AgentStatusList() {
  const providers = useStore((s) => s.providers);
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);

  // Compute queue depth per provider from recent events
  const queueDepth = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events.slice(0, 100)) {
      const p = e.payload as Record<string, any>;
      if (e.topic === "task.dispatched" && p?.assigned_provider) {
        counts[p.assigned_provider] = (counts[p.assigned_provider] ?? 0) + 1;
      }
    }
    return counts;
  }, [events]);

  const agents = AGENT_PROVIDERS.map((ap) => {
    const live: ProviderHealthRecord | undefined = providers[ap.id];
    const status = live?.status ?? (connected ? ("idle" as any) : ("offline" as any));
    const q = queueDepth[ap.id] ?? 0;
    return {
      ...ap,
      status,
      latency: live?.latency_ms ?? 0,
      queue: q,
      model: "",  // Not in current ProviderHealthRecord — pending backend extension
    };
  });

  const online = agents.filter((a) => a.status === "healthy").length;
  const busy = agents.filter((a) => a.queue > 0).length;

  return (
    <Panel title="Connected Agents" subtitle={`${online} online · ${busy} active`} className="shrink-0">
      <div className="space-y-1">
        {agents.map((a) => (
          <motion.div
            key={a.id}
            layout
            className="flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 hover:bg-surface/20 transition-colors"
          >
            <StatusDot status={a.status} pulse={a.status === "healthy"} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium truncate">{a.label}</span>
                {a.status === "healthy" && (
                  <span className="text-[9px] text-faint tabular-nums">{a.latency.toFixed(0)}ms</span>
                )}
              </div>
              <div className="text-[9px] text-faint truncate">{a.role}</div>
            </div>
            <div className="flex flex-col items-end gap-0.5 shrink-0">
              {a.queue > 0 && (
                <span className="px-1.5 py-0.5 rounded bg-accent/10 text-[9px] text-accent tabular-nums">
                  {a.queue} queued
                </span>
              )}
              <span className={`text-[9px] capitalize ${
                String(a.status) === "healthy" || String(a.status) === "executing" ? "text-ok" :
                String(a.status) === "idle" ? "text-faint" : String(a.status) === "offline" ? "text-danger" : "text-warn"
              }`}>
                {a.status}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
      <div className="mt-1.5 text-[9px] text-center text-faint">
        {connected ? "· EventBus live · Provider Framework" : "· Disconnected"}
      </div>
    </Panel>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION CARD
// ══════════════════════════════════════════════════════════════

function MissionCard({
  mission, selected, onClick, onPlan, onStart, onPause, onCancel, onDelete, planning,
}: {
  mission: MissionType; selected: boolean; onClick: () => void;
  onPlan: () => void; onStart: () => void; onPause: () => void;
  onCancel: () => void; onDelete: () => void; planning: boolean;
}) {
  const statusColor = STATUS_COLORS[mission.status] ?? "#6b7280";
  const taskCount = mission.plan?.task_count ?? 0;
  const completed = mission.plan?.tasks?.filter((t) => t.status === "completed").length ?? 0;
  const progress = taskCount > 0 ? Math.round((completed / taskCount) * 100) : 0;

  return (
    <motion.div
      layout
      className={`glass rounded-xl p-3 cursor-pointer border transition-colors ${
        selected ? "border-accent/50" : "border-transparent hover:border-border/40"
      }`}
      onClick={onClick}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StatusDot status={mission.status} pulse={mission.status === "executing"} />
            <span className="text-sm font-medium truncate">{mission.title}</span>
            <Badge tone={mission.priority === "critical" ? "danger" : mission.priority === "high" ? "warn" : "info"}>
              {mission.priority}
            </Badge>
          </div>
          <div className="mt-1 flex items-center gap-3 text-[11px] text-faint">
            <span style={{ color: statusColor }}>{mission.status}</span>
            {taskCount > 0 && <span>{taskCount} tasks</span>}
            {progress > 0 && <span>{progress}%</span>}
            {mission.deadline && <span>Due {new Date(mission.deadline).toLocaleDateString()}</span>}
          </div>
          {(mission.status === "executing" || mission.status === "paused") && taskCount > 0 && (
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface/50">
              <div className="h-full rounded-full bg-accent/60 transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {mission.status === "planned" && (
            <button className="pill bg-green-500/15 text-green-400 hover:bg-green-500/25 text-[10px]" onClick={(e) => { e.stopPropagation(); onStart(); }} title="Start">
              <Play size={12} />
            </button>
          )}
          {mission.status === "executing" && (
            <button className="pill bg-yellow-500/15 text-yellow-400 hover:bg-yellow-500/25 text-[10px]" onClick={(e) => { e.stopPropagation(); onPause(); }} title="Pause">
              <Pause size={12} />
            </button>
          )}
          {mission.status === "draft" && (
            <button className="pill bg-accent/15 text-accent hover:bg-accent/25 text-[10px]" onClick={(e) => { e.stopPropagation(); onPlan(); }} disabled={planning} title="Plan">
              {planning ? "..." : <FileText size={12} />}
            </button>
          )}
          {(mission.status === "draft" || mission.status === "planned" || mission.status === "paused") && (
            <button className="pill bg-surface/80 text-faint hover:text-danger text-[10px]" onClick={(e) => { e.stopPropagation(); onDelete(); }} title="Delete">
              <Trash2 size={12} />
            </button>
          )}
          {(mission.status === "executing" || mission.status === "paused") && (
            <button className="pill bg-red-500/15 text-red-400 hover:bg-red-500/25 text-[10px]" onClick={(e) => { e.stopPropagation(); onCancel(); }} title="Cancel">
              <X size={12} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION FORM
// ══════════════════════════════════════════════════════════════

function MissionForm({
  onSubmit, onCancel,
}: {
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    title: "", description: "", prompt: "",
    objectives: [""], deliverables: [""],
    priority: "medium", execution_mode: "hybrid",
    constraints: [] as string[], deadline: "", tags: [] as string[],
  });
  const [attachments, setAttachments] = useState<File[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const update = <K extends keyof typeof form>(key: K, val: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [key]: val }));

  const handleSubmit = async () => {
    if (!form.title.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({
        ...form,
        objectives: form.objectives.filter(Boolean),
        deliverables: form.deliverables.filter(Boolean),
        constraints: form.constraints.filter(Boolean),
        tags: form.tags.filter(Boolean),
        deadline: form.deadline || null,
        attachment_count: attachments.length,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setAttachments((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setAttachments((prev) => [...prev, ...Array.from(e.target.files!)]);
  };

  const removeAttachment = (i: number) => setAttachments((prev) => prev.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-3">
      <input className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
        placeholder="Mission title *" value={form.title}
        onChange={(e) => update("title", e.target.value)} />
      <textarea className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60 resize-none"
        placeholder="Mission description" rows={2} value={form.description}
        onChange={(e) => update("description", e.target.value)} />
      <textarea className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60 resize-none font-mono text-[11px]"
        placeholder="Prompt (full instruction for AI agents)" rows={3} value={form.prompt}
        onChange={(e) => update("prompt", e.target.value)} />
      <div className="grid grid-cols-2 gap-2">
        <select className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none"
          value={form.priority} onChange={(e) => update("priority", e.target.value)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none"
          value={form.execution_mode} onChange={(e) => update("execution_mode", e.target.value)}>
          {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <ArrayInput label="Objectives" values={form.objectives} onChange={(v) => update("objectives", v)}
        placeholder="e.g. Implement update mechanism" icon={<Target size={12} />} />
      <ArrayInput label="Deliverables" values={form.deliverables} onChange={(v) => update("deliverables", v)}
        placeholder="e.g. Design document" icon={<ListTodo size={12} />} />
      <div className="grid grid-cols-2 gap-2">
        <input className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-xs outline-none focus:border-accent/60"
          placeholder="Tags (comma-separated)" value={form.tags.join(", ")}
          onChange={(e) => update("tags", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
        <input type="date" className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-xs outline-none focus:border-accent/60"
          value={form.deadline} onChange={(e) => update("deadline", e.target.value)} />
      </div>
      {/* Drag-and-drop attachment zone */}
      <div className={`rounded-lg border-2 border-dashed p-3 text-center transition-colors ${
        dragOver ? "border-accent/60 bg-accent/5" : "border-border/40 hover:border-border/60"
      }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input ref={fileRef} type="file" multiple className="hidden" onChange={handleFilePick} />
        <button type="button" className="flex items-center justify-center gap-2 w-full text-xs text-faint hover:text-text transition-colors"
          onClick={() => fileRef.current?.click()}>
          <Upload size={14} />
          <span>{dragOver ? "Drop files here" : "Drag & drop or click to add attachments"}</span>
        </button>
        {attachments.length > 0 && (
          <div className="mt-2 space-y-1 text-left">
            {attachments.map((f, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg bg-surface/40 px-2 py-1 text-[11px]">
                <FileText size={10} className="text-accent shrink-0" />
                <span className="flex-1 truncate">{f.name}</span>
                <span className="text-faint shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
                <button className="text-faint hover:text-danger" onClick={() => removeAttachment(i)}><X size={10} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex gap-2 pt-1">
        <button className="flex-1 pill bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-40"
          onClick={handleSubmit} disabled={!form.title.trim() || submitting}>
          {submitting ? "Creating..." : "Create Mission"}
        </button>
        <button className="pill bg-surface/60 text-muted hover:bg-surface" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// ── Array Input ──
function ArrayInput({ label, values, onChange, placeholder, icon }: {
  label: string; values: string[]; onChange: (v: string[]) => void;
  placeholder: string; icon: React.ReactNode;
}) {
  const add = () => onChange([...values, ""]);
  const set = (i: number, v: string) => { const n = [...values]; n[i] = v; onChange(n); };
  const remove = (i: number) => onChange(values.filter((_, idx) => idx !== i));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-[10px] uppercase tracking-wider text-faint flex items-center gap-1">{icon} {label}</label>
        <button className="text-[10px] text-accent hover:text-accent/80" onClick={add}>+ Add</button>
      </div>
      {values.map((v, i) => (
        <div key={i} className="flex gap-1">
          <input className="flex-1 rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none"
            placeholder={placeholder} value={v} onChange={(e) => set(i, e.target.value)} />
          <button className="text-faint hover:text-danger p-1" onClick={() => remove(i)}><X size={12} /></button>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION DETAIL
// ══════════════════════════════════════════════════════════════

function MissionDetail({ mission, onRefresh }: { mission: MissionType; onRefresh: () => void }) {
  const cols = [
    { label: "Status", value: mission.status, color: STATUS_COLORS[mission.status] },
    { label: "Priority", value: mission.priority },
    { label: "Mode", value: mission.execution_mode },
    { label: "Created", value: new Date(mission.created_at).toLocaleString() },
  ];
  if (mission.deadline) cols.push({ label: "Deadline", value: new Date(mission.deadline).toLocaleDateString() });
  if (mission.completed_at) cols.push({ label: "Completed", value: new Date(mission.completed_at).toLocaleString() });

  const taskCount = mission.plan?.task_count ?? 0;
  const completed = mission.plan?.tasks?.filter((t) => t.status === "completed").length ?? 0;
  const failed = mission.plan?.tasks?.filter((t) => t.status === "failed").length ?? 0;
  const progress = taskCount > 0 ? Math.round((completed / taskCount) * 100) : 0;

  return (
    <Panel
      title={mission.title}
      subtitle={mission.description || "(no description)"}
      actions={
        <button className="pill bg-surface/60 text-faint hover:text-text" onClick={onRefresh} title="Refresh">
          <RefreshCw size={12} />
        </button>
      }
    >
      {(mission.status === "executing" || mission.status === "paused") && taskCount > 0 && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-faint">Progress</span>
            <span className="text-[11px] font-medium tabular-nums">
              {completed}/{taskCount} tasks · {progress}%
              {failed > 0 && <span className="text-danger ml-2">{failed} failed</span>}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface/50">
            <div className="h-full rounded-full bg-accent/60 transition-all duration-500"
              style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}
      {mission.plan && (
        <div className="mb-4 text-[11px] text-faint flex items-center gap-3">
          <span>⏱ ~{mission.plan.estimated_total_minutes}m estimated</span>
          <span className="capitalize">· {mission.plan.complexity} complexity</span>
          <span className="capitalize">· {mission.plan.risk_level} risk</span>
        </div>
      )}
      <div className="grid grid-cols-4 gap-2 mb-4">
        {cols.map((c) => (
          <div key={c.label} className="glass rounded-xl px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-faint">{c.label}</div>
            <div className="mt-0.5 text-sm font-medium" style={c.color ? { color: c.color } : {}}>{c.value}</div>
          </div>
        ))}
      </div>
      {mission.objectives.length > 0 && (
        <Section title="Objectives">
          {mission.objectives.map((o, i) => (
            <li key={i} className="text-sm text-muted flex items-start gap-2">
              <span className="text-accent mt-0.5">◆</span> {o}
            </li>
          ))}
        </Section>
      )}
      {mission.deliverables.length > 0 && (
        <Section title="Deliverables">
          {mission.deliverables.map((d, i) => (
            <li key={i} className="text-sm text-muted flex items-start gap-2">
              <span className="text-accent mt-0.5">◇</span> {d}
            </li>
          ))}
        </Section>
      )}
      {mission.prompt && (
        <Section title="Prompt">
          <pre className="text-xs text-muted whitespace-pre-wrap bg-surface/40 rounded-lg p-3 max-h-24 overflow-y-auto">
            {mission.prompt}
          </pre>
        </Section>
      )}
      {mission.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {mission.tags.map((t) => <Badge key={t} tone="info">{t}</Badge>)}
        </div>
      )}
      {mission.attachments.length > 0 && (
        <Section title={`Attachments (${mission.attachments.length})`}>
          {mission.attachments.map((a) => (
            <div key={a.id} className="text-xs text-muted flex items-center gap-2 rounded-lg bg-surface/30 px-2 py-1.5">
              <FileText size={12} className="text-accent shrink-0" />
              <span className="flex-1 truncate">{a.filename}</span>
              <span className="text-[10px] text-faint shrink-0">({(a.size_bytes / 1024).toFixed(0)} KB)</span>
              <span className="text-[10px] text-faint italic truncate">{a.description || a.mime_type}</span>
            </div>
          ))}
        </Section>
      )}
      {mission.error && (
        <div className="mt-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
          <AlertCircle size={12} className="inline mr-1" />{mission.error}
        </div>
      )}
    </Panel>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <div className="text-[10px] uppercase tracking-wider text-faint mb-1.5">{title}</div>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  EXECUTION TIMELINE — parallel agent visual
// ══════════════════════════════════════════════════════════════

function ExecutionTimeline({ plan }: { plan: MissionPlanType | null }) {
  if (!plan) {
    return (
      <Panel title="Execution Timeline" subtitle="No plan available" className="h-full">
        <Empty title="No execution data" hint="The mission has not been planned yet." />
      </Panel>
    );
  }

  const completed = plan.tasks.filter((t) => t.status === "completed").length;
  const running = plan.tasks.filter((t) => t.status === "running").length;
  const progress = plan.task_count > 0 ? Math.round((completed / plan.task_count) * 100) : 0;

  // Group tasks by assigned provider for the parallel swimlane visual
  const byProvider: Record<string, MissionTaskType[]> = {};
  for (const t of plan.tasks) {
    const key = t.assigned_provider || "unassigned";
    if (!byProvider[key]) byProvider[key] = [];
    byProvider[key].push(t);
  }

  return (
    <Panel
      title="Execution Timeline"
      subtitle={`${completed} done · ${running} running · ${progress}%`}
      className="h-full"
    >
      {/* Overall progress */}
      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-surface/50">
        <div className="h-full rounded-full bg-accent/60 transition-all duration-500" style={{ width: `${progress}%` }} />
      </div>

      {/* Agent swimlanes */}
      <div className="space-y-3">
        {Object.entries(byProvider).map(([provider, tasks]) => {
          const agentInfo = AGENT_PROVIDERS.find((a) => a.id === provider);
          return (
            <div key={provider}>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: agentInfo?.color ?? "#6b7280" }} />
                <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: agentInfo?.color }}>
                  {agentInfo?.label ?? provider}
                </span>
              </div>
              <div className="relative ml-3 pl-3 border-l border-border/30 space-y-1">
                {tasks.map((task, idx) => (
                  <div key={task.id} className="flex items-center gap-2">
                    {/* Timeline dot */}
                    <div className="absolute left-[-5px] w-2 h-2 rounded-full bg-surface/50"
                      style={{ backgroundColor: TASK_COLORS[task.status] ?? "#6b7280" }} />
                    {/* Task chip */}
                    <span className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                      task.status === "running" ? "border-accent/50 bg-accent/10 text-accent" :
                      task.status === "completed" ? "border-ok/30 bg-ok/10 text-ok" :
                      task.status === "failed" ? "border-danger/30 bg-danger/10 text-danger" :
                      "border-border/30 text-faint"
                    }`}>
                      {task.title}
                    </span>
                    <span className="text-[9px] text-faint ml-auto tabular-nums">~{task.estimated_minutes}m</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center gap-4 text-[9px] text-faint">
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#22c55e]" /> Running</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#6b7280]" /> Pending</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#ef4444]" /> Failed</span>
        <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[#6366f1]" /> Planned</span>
      </div>
    </Panel>
  );
}

// ══════════════════════════════════════════════════════════════
//  SHARED MEMORY PANEL
// ══════════════════════════════════════════════════════════════

function SharedMemoryPanel() {
  const memory = useStore((s) => s.memory);
  const agents = useStore((s) => s.agents);

  const missionMemory = memory.filter((m) => m.scope === "project" || m.scope === "shared");
  const globalMemory = memory.filter((m) => m.scope === "conversation" || m.scope === "long_term");

  return (
    <Panel
      title="Shared Memory"
      subtitle={`${memory.length} items · ${Object.keys(agents).length} agents`}
      className="h-full"
    >
      {/* Memory by scope */}
      {missionMemory.length > 0 && (
        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-faint mb-1.5">Mission Context</div>
          <div className="space-y-1.5">
            {missionMemory.slice(0, 20).map((item) => (
              <div key={item.id} className="glass rounded-xl px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium text-accent truncate">{item.key}</span>
                  {item.agent_id && (
                    <span className="text-[9px] text-faint shrink-0">by {item.agent_id}</span>
                  )}
                </div>
                <p className="text-xs text-muted mt-0.5 line-clamp-2">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {globalMemory.length > 0 && (
        <div>
          <div className="text-[10px] uppercase tracking-wider text-faint mb-1.5">Global Context</div>
          <div className="space-y-1.5">
            {globalMemory.slice(0, 10).map((item) => (
              <div key={item.id} className="glass rounded-xl px-3 py-2">
                <div className="text-[11px] font-medium truncate">{item.key}</div>
                <p className="text-xs text-muted mt-0.5 line-clamp-1">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {memory.length === 0 && (
        <Empty title="No shared memory" hint="Memory items will appear here as agents store context." />
      )}

      <div className="mt-3 text-[9px] text-center text-faint">
        Prevents agents from repeatedly asking for the same information
      </div>
    </Panel>
  );
}

// ══════════════════════════════════════════════════════════════
//  INTER-AGENT COMMUNICATION LOG
// ══════════════════════════════════════════════════════════════

function AgentCommsLog({ missionId }: { missionId: string }) {
  const events = useStore((s) => s.events);

  const commsEvents = useMemo(() =>
    events.filter((e) => e.topic.includes("task.") || e.topic.includes("agent.") || e.topic.includes("approval.")),
  [events]);

  return (
    <Panel
      title="Inter-Agent Communication"
      subtitle={`${commsEvents.length} events via EventBus`}
      className="h-full"
    >
      {commsEvents.length === 0 ? (
        <Empty title="No agent communication yet" hint="Events will appear as agents coordinate via the EventBus." />
      ) : (
        <div className="space-y-1.5 max-h-[400px] overflow-y-auto">
          {commsEvents.slice(0, 80).map((e) => {
            const p = e.payload as Record<string, any>;
            const source = String(p?.source ?? p?.agent_id ?? p?.provider ?? "system");
            const target = String(p?.target ?? p?.assigned_provider ?? "");
            return (
              <div key={e.id} className="glass rounded-xl px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-mono text-faint">
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded ${
                    e.topic.includes("completed") ? "bg-ok/10 text-ok" :
                    e.topic.includes("failed") || e.topic === "approval.decided" ? "bg-danger/10 text-danger" :
                    e.topic.includes("dispatched") || e.topic === "approval.requested" ? "bg-warn/10 text-warn" :
                    "bg-accent/10 text-accent"
                  }`}>
                    {e.topic}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-muted">
                  <span className="font-medium">{source}</span>
                  {target && (
                    <>
                      <span className="text-faint">→</span>
                      <span className="font-medium text-accent">{target}</span>
                    </>
                  )}
                </div>
                <div className="mt-0.5 text-faint text-[10px] line-clamp-1">
                  {JSON.stringify(p).slice(0, 120)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-3 text-[9px] text-center text-faint">
        Everything is event-driven · agents communicate through the EventBus
      </div>
    </Panel>
  );
}

// ══════════════════════════════════════════════════════════════
//  RESULT MERGE & VALIDATION PIPELINE
// ══════════════════════════════════════════════════════════════

function MergePipelinePanel() {
  const completed = useStore((s) => s.missionUpdates) > 0;

  // Simulated stage states — in production these come from EventBus events
  const [stageStates, setStageStates] = useState<Record<string, "pending" | "running" | "passed" | "failed">>({});
  const [pulse, setPulse] = useState(false);

  // Animate through stages when a mission completes
  useEffect(() => {
    if (completed) {
      setPulse(true);
      const timer = setTimeout(() => setPulse(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [completed]);

  return (
    <Panel
      title="Merge & Validate"
      subtitle="Results collected, merged, and validated"
      className="h-full"
    >
      <div className="grid grid-cols-4 gap-2 mb-4">
        {MERGE_STAGES.map((stage) => {
          const state = stageStates[stage.id] ?? "pending";
          return (
            <motion.div
              key={stage.id}
              className={`glass rounded-xl p-3 text-center transition-colors ${
                state === "running" ? "ring-1 ring-accent/40" :
                state === "passed" ? "ring-1 ring-ok/40" :
                state === "failed" ? "ring-1 ring-danger/40" : ""
              }`}
              animate={pulse ? { scale: [1, 1.02, 1] } : {}}
              transition={{ duration: 1.5, repeat: pulse ? Infinity : 0 }}
            >
              <stage.icon size={20} className={`mx-auto mb-1 ${
                state === "passed" ? "text-ok" :
                state === "failed" ? "text-danger" :
                state === "running" ? "text-accent" : "text-faint"
              }`} />
              <div className="text-[10px] font-medium">{stage.label}</div>
              <div className="mt-0.5 flex items-center justify-center gap-1">
                {state === "pending" && <span className="text-[9px] text-faint">Waiting</span>}
                {state === "running" && <Loader2 size={10} className="animate-spin text-accent" />}
                {state === "passed" && <CheckCircle2 size={10} className="text-ok" />}
                {state === "failed" && <XCircle size={10} className="text-danger" />}
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Process description */}
      <div className="glass rounded-xl p-3 text-[11px] text-muted space-y-1">
        <p>After all agents complete their work, the Result Merger automatically:</p>
        <ul className="space-y-0.5 pl-4 list-disc">
          <li>Detects and resolves merge conflicts</li>
          <li>Merges compatible changes from all agents</li>
          <li>Runs code formatting and linting across merged code</li>
          <li>Runs automated tests to verify correctness</li>
          <li>Performs security scans on new/modified code</li>
          <li>Runs regression tests to ensure nothing broke</li>
          <li>Generates documentation for new/changed features</li>
          <li>Produces one unified, validated result</li>
        </ul>
      </div>

      <div className="mt-2 text-[9px] text-center text-faint">
        Final validation gate: all tasks finished, tests passed, no conflicts, no regressions, security OK
      </div>
    </Panel>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION PLAN VIEW (existing, enhanced)
// ══════════════════════════════════════════════════════════════

function MissionPlanView({ plan, mission }: { plan: MissionPlanType; mission: MissionType }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const isActive = mission.status === "executing" || mission.status === "paused";

  return (
    <Panel
      title="Execution Plan"
      subtitle={`${plan.complexity} complexity · ${plan.risk_level} risk · ~${plan.estimated_total_minutes}m total · ${plan.task_count} tasks`}
      className="h-full"
    >
      <div className="mb-3 text-xs text-muted">{plan.summary}</div>

      <div className="space-y-2">
        {plan.tasks.map((task, idx) => (
          <div key={task.id}>
            <motion.div
              layout
              className={`glass rounded-xl p-3 cursor-pointer hover:border-border/40 border transition-colors ${
                expanded === task.id ? "border-accent/30" : "border-transparent"
              } ${task.status === "running" ? "ring-1 ring-accent/30" : ""}`}
              onClick={() => setExpanded(expanded === task.id ? null : task.id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] text-faint font-mono shrink-0">{idx + 1}.</span>
                  <StatusDot status={task.status === "running" ? "running" : task.status === "completed" ? "healthy" : task.status === "failed" ? "failed" : "idle"} pulse={task.status === "running"} />
                  <span className="text-sm truncate">{task.title}</span>
                  <span className="text-[10px] text-faint">~{task.estimated_minutes}m</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {task.assigned_role && <Badge tone="info">{task.assigned_role.replace(/_/g, " ")}</Badge>}
                  {task.assigned_provider && (
                    <span className="text-[10px] text-accent bg-accent/10 px-1.5 py-0.5 rounded">{task.assigned_provider}</span>
                  )}
                  {expanded === task.id ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </div>
              </div>

              <AnimatePresence>
                {expanded === task.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-2 pt-2 border-t border-border/40 text-xs text-muted space-y-2">
                      <p>{task.description}</p>
                      {task.dependencies.length > 0 && (
                        <p className="text-faint">Depends on: {task.dependencies.map((d) => d.slice(0, 8)).join(", ")}</p>
                      )}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px]" style={{ color: TASK_COLORS[task.status] ?? "#6b7280" }}>● {task.status}</span>
                        {task.assigned_provider && (
                          <span className="text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded">{task.assigned_provider}</span>
                        )}
                      </div>

                      {isActive && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          <TaskActionButton label={task.status === "failed" ? "Retry" : "Restart"} icon={<RotateCcw size={10} />}
                            onClick={async () => { /* TODO: api.restartTask(task.id) */ }} />
                          <TaskActionButton label="Reassign" icon={<UserPlus size={10} />}
                            onClick={async () => { /* TODO: api.reassignTask(task.id) */ }} />
                          {task.output && (
                            <span className="text-[10px] text-ok flex items-center gap-1"><Download size={10} /> Output</span>
                          )}
                        </div>
                      )}

                      {task.output && (
                        <div className="mt-1">
                          <div className="text-[10px] uppercase tracking-wider text-faint mb-0.5">Output</div>
                          <pre className="text-[10px] whitespace-pre-wrap bg-surface/40 rounded p-2 max-h-20 overflow-y-auto">
                            {task.output.slice(0, 300)}{task.output.length > 300 ? "..." : ""}
                          </pre>
                        </div>
                      )}
                      {task.error && (
                        <div className="text-[10px] text-danger flex items-center gap-1"><AlertCircle size={10} /> {task.error}</div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {idx < plan.tasks.length - 1 && (
              <div className="flex justify-center py-0.5"><div className="w-px h-3 bg-border/30" /></div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function TaskActionButton({ label, icon, onClick }: {
  label: string; icon: React.ReactNode; onClick: () => void;
}) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-1 rounded-md border border-border/40 px-2 py-1 text-[10px] text-faint hover:text-text hover:border-border transition-colors">
      {icon} {label}
    </button>
  );
}

// ══════════════════════════════════════════════════════════════
//  FINAL VALIDATION — all quality gates before mission complete
// ══════════════════════════════════════════════════════════════

function FinalValidationPanel({ mission }: { mission: MissionType }) {
  const gates = useMemo(() => {
    const plan = mission.plan;
    const tasksDone = plan?.tasks.every((t) => t.status === "completed") ?? false;
    const testsPassed = plan?.tasks.filter((t) => t.status === "completed").length === plan?.task_count;
    const noConflicts = !mission.error?.includes("merge") && !mission.error?.includes("conflict");
    const hasDocs = plan?.tasks.some((t) => t.title.toLowerCase().includes("document")) ?? false;
    const secPassed = !mission.error?.includes("security");
    return [
      { id: "tasks", label: "All Tasks Finished", met: tasksDone,
        desc: `${plan?.tasks.filter((t) => t.status === "completed").length ?? 0}/${plan?.task_count ?? 0} completed` },
      { id: "tests", label: "All Tests Passed", met: testsPassed && !mission.error?.includes("test"),
        desc: mission.error?.includes("test") ? "Test failures detected" : "No test failures" },
      { id: "conflicts", label: "No Merge Conflicts", met: noConflicts,
        desc: noConflicts ? "Clean merge" : "Conflicts detected" },
      { id: "regression", label: "No Regressions", met: !mission.error?.includes("regression"),
        desc: mission.error?.includes("regression") ? "Regressions found" : "Clean" },
      { id: "docs", label: "Documentation Updated", met: hasDocs,
        desc: hasDocs ? "Documentation generated" : "No documentation task in plan" },
      { id: "security", label: "Security Checks Passed", met: secPassed,
        desc: secPassed ? "No vulnerabilities" : "Security issues detected" },
    ];
  }, [mission]);

  const passed = gates.filter((g) => g.met).length;
  const total = gates.length;
  const ready = passed === total;

  return (
    <Panel title="Final Validation" subtitle={`${passed}/${total} gates passed`} className="h-full">
      <div className={`mb-4 rounded-xl p-3 text-center text-sm font-medium transition-colors ${
        ready ? "bg-ok/10 text-ok" : "bg-warn/10 text-warn"
      }`}>
        {ready ? "✅ All gates passed — mission ready to complete" : `⏳ ${total - passed} gate(s) not satisfied`}
      </div>
      <div className="space-y-1.5">
        {gates.map((gate) => (
          <div key={gate.id}
            className={`flex items-center gap-3 rounded-xl px-3 py-2 transition-colors ${gate.met ? "bg-ok/5" : "bg-warn/5"}`}
          >
            <div className={`shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
              gate.met ? "bg-ok/20 text-ok" : "bg-warn/20 text-warn"
            }`}>
              {gate.met ? <Check size={12} /> : <Clock size={12} />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium">{gate.label}</div>
              <div className="text-[10px] text-faint">{gate.desc}</div>
            </div>
            <span className={`text-[9px] tabular-nums ${gate.met ? "text-ok" : "text-warn"}`}>
              {gate.met ? "PASS" : "PENDING"}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ── OmniRoute Planner ──
function RoutingPlanner({ mission }: { mission: MissionType }) {
  const [selectedStrategy, setSelectedStrategy] = useState<GatewayStrategy>("balanced");
  const [routePlan, setRoutePlan] = useState<MissionRoutePlanType | null>(null);
  const [loading, setLoading] = useState(false);

  const compareRoute = useCallback(async () => {
    setLoading(true);
    try {
      const results = await api.compareStrategies(mission.id);
      const plan = results[selectedStrategy];
      if (plan) setRoutePlan(plan);
    } catch {
      setRoutePlan(null);
    } finally {
      setLoading(false);
    }
  }, [mission.id, selectedStrategy]);

  const currentStrategy = ROUTING_STRATEGIES.find((s) => s.id === selectedStrategy);
  const stratSummary = routePlan
    ? `$${routePlan.total_estimated_cost.toFixed(2)} · ${routePlan.average_composite_score.toFixed(2)} score · ${routePlan.assignments.length} tasks`
    : null;

  return (
    <Panel
      title={`Routing — ${currentStrategy?.label ?? selectedStrategy}`}
      subtitle={stratSummary ?? "Select a strategy and compare"}
      actions={
        <button
          className={`pill ${loading ? "opacity-50 pointer-events-none" : "bg-accent/15 text-accent hover:bg-accent/25"}`}
          onClick={compareRoute}
          disabled={loading}
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {loading ? " Comparing…" : " Compare"}
        </button>
      }
      className="h-full"
    >
      {/* Strategy selector grid */}
      <div className="mb-4 grid grid-cols-3 gap-1.5">
        {ROUTING_STRATEGIES.map((s) => (
          <button
            key={s.id}
            onClick={() => { setSelectedStrategy(s.id); setRoutePlan(null); }}
            className={`rounded-xl p-2.5 text-left transition-all ${
              selectedStrategy === s.id
                ? "bg-accent/15 ring-1 ring-accent/40"
                : "bg-surface/30 hover:bg-surface/50"
            }`}
          >
            <div className="text-sm">{s.icon} {s.label}</div>
            <div className="text-[10px] text-faint mt-0.5">{s.desc}</div>
          </button>
        ))}
      </div>

      {/* Route plan display */}
      {routePlan ? (
        <div className="space-y-3">
          {/* Summary stats */}
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Est. Cost", value: `$${routePlan.total_estimated_cost.toFixed(2)}` },
              { label: "Duration", value: `${(routePlan.total_estimated_duration_ms / 1000).toFixed(1)}s` },
              { label: "Avg Score", value: routePlan.average_composite_score.toFixed(3) },
              { label: "Providers", value: Object.keys(routePlan.provider_usage).length.toString() },
            ].map((s) => (
              <div key={s.label} className="glass rounded-xl px-2.5 py-2 text-center">
                <div className="text-[9px] uppercase tracking-wider text-faint">{s.label}</div>
                <div className="mt-0.5 text-sm font-medium tabular-nums">{s.value}</div>
              </div>
            ))}
          </div>

          {/* Provider usage breakdown */}
          {Object.keys(routePlan.provider_usage).length > 0 && (
            <div>
              <div className="text-[11px] font-medium text-faint mb-1.5">Provider Usage</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(routePlan.provider_usage).map(([provider, count]) => (
                  <Badge key={provider}>
                    {provider} ×{count}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Task assignments */}
          <div>
            <div className="text-[11px] font-medium text-faint mb-1.5">Task Assignments ({routePlan.assignments.length})</div>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {routePlan.assignments.map((a) => (
                <div key={a.task_id}
                  className="flex items-center gap-2 rounded-lg bg-surface/20 px-2.5 py-1.5 text-xs"
                >
                  <StatusDot status={a.status as any} />
                  <span className="flex-1 truncate">{a.task_title}</span>
                  <span className="text-faint text-[10px] tabular-nums">
                    {a.assigned_agent_name}
                  </span>
                  <span className="text-faint text-[10px] tabular-nums">
                    ${a.estimated_cost.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <Empty
          title="No route plan"
          hint="Select a strategy above and click Compare to generate a route plan."
        />
      )}
    </Panel>
  );
}
