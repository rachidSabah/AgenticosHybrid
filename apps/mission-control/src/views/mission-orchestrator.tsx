"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { safeFixed, safeNum, safeStr, safeArr, safeLen } from "@/lib/safe";
import type {
  MissionType, MissionPlanType, MissionTaskType, EventEnvelope,
  MemoryItem, ProviderHealthRecord, MissionAttachment,
  GatewayStrategy, MissionRoutePlanType, TaskRouteAssignmentType,
} from "@/lib/types";
import {
  Plus, X, Check, Play, Pause, Trash2, FileText, Target, ListTodo, Tag, Clock,
  ChevronDown, ChevronUp, RefreshCw, RotateCcw, AlertCircle,
  Upload, Paperclip, Download, GripVertical, BrainCircuit, MessageCircle,
  GitMerge, Kanban, CheckCircle2, XCircle, Loader2, Layers, Workflow,
  Activity, Server, Route, Terminal as TerminalIcon, GitBranch, FileDiff,
  FolderTree, Zap, Shield, BarChart3, Network,
} from "lucide-react";
import { TerminalPanel } from "@/components/shell/terminal-panel";
import { DiffViewer } from "@/components/diff-viewer";

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

const PROVIDER_COLORS = [
  "#d97706", "#8b5cf6", "#06b6d4", "#10b981", "#4285f4", "#f97316",
  "#ec4899", "#14b8a6", "#6366f1", "#eab308",
];

function providerColor(name: string, index: number): string {
  return PROVIDER_COLORS[index % PROVIDER_COLORS.length];
}

const COMMS_TOPICS = new Set([
  "task.dispatched", "task.planned", "task.created",
  "agent.started", "agent.completed", "agent.failed", "agent.recovered",
  "approval.requested", "approval.decided",
  "memory.written", "memory.evicted",
]);

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

const ROUTING_STRATEGIES: { id: GatewayStrategy; label: string; desc: string; icon: string }[] = [
  { id: "balanced", label: "Balanced", desc: "Equal weight across all dimensions", icon: "⚖️" },
  { id: "fastest", label: "Fastest", desc: "Minimize response latency", icon: "⚡" },
  { id: "cheapest", label: "Cheapest", desc: "Minimize cost per token", icon: "💰" },
  { id: "best_capability", label: "Best Capability", desc: "Maximize model capability score", icon: "🧠" },
  { id: "reliability_first", label: "Reliability First", desc: "Least error-prone providers", icon: "🛡️" },
  { id: "latency_first", label: "Latency First", desc: "Lowest latency providers", icon: "🏎️" },
  { id: "custom", label: "Custom", desc: "Manual assignment", icon: "🎛️" },
];

// ── Futuristic Tab Bar ──
const TABS = [
  { id: "detail", label: "Plan & Tasks", icon: ListTodo },
  { id: "timeline", label: "Timeline", icon: Kanban },
  { id: "memory", label: "Shared Memory", icon: BrainCircuit },
  { id: "comms", label: "Agent Comms", icon: MessageCircle },
  { id: "merge", label: "Merge & Validate", icon: GitMerge },
  { id: "validation", label: "Final Validation", icon: CheckCircle2 },
  { id: "routing", label: "Routing", icon: Route },
  { id: "terminal", label: "Terminal", icon: TerminalIcon },
  { id: "review", label: "Review Changes", icon: FileDiff },
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
  const [showWorktreePanel, setShowWorktreePanel] = useState(false);
  const [worktrees, setWorktrees] = useState<import("@/lib/types").WorktreeEntry[]>([]);
  const [selectedWorktreeBranch, setSelectedWorktreeBranch] = useState<string>("");
  const [selectedWorktreePath, setSelectedWorktreePath] = useState<string>("");
  const [worktreeLoading, setWorktreeLoading] = useState(false);

  const missionStore = useStore((s) => s.missions);
  const missionUpdates = useStore((s) => s.missionUpdates);

  const STORAGE_KEY = "mc.orchestrator.missions";

  const saveMissionsLocal = (list: MissionType[]) => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(list)); } catch {}
  };

  const loadMissions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.missions();
      const validData = Array.isArray(data) && data.length > 0 ? data : [];
      if (validData.length > 0) {
        setMissions(validData);
        saveMissionsLocal(validData);
        useStore.getState().setMissions(validData);
      } else {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as MissionType[];
          setMissions(parsed);
          useStore.getState().setMissions(parsed);
        }
      }
      setError(null);
    } catch {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored) as MissionType[];
          setMissions(parsed);
          useStore.getState().setMissions(parsed);
        } catch {}
      }
      setError(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMissions(); }, [loadMissions]);

  const loadWorktrees = useCallback(async () => {
    setWorktreeLoading(true);
    try {
      const wts = await api.worktreeList();
      setWorktrees(Array.isArray(wts) ? wts : []);
    } catch {
      setWorktrees([]);
    } finally {
      setWorktreeLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorktrees();
    const t = setInterval(loadWorktrees, 15000);
    return () => clearInterval(t);
  }, [loadWorktrees]);

  const openWorktree = (wt: import("@/lib/types").WorktreeEntry, tab: string) => {
    setSelectedWorktreeBranch(wt.branch);
    setSelectedWorktreePath(wt.path);
    setRightTab(tab);
  };

  const prevStoreKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (missionUpdates && Object.keys(missionStore).length > 0) {
      const storeKey = JSON.stringify(missionStore);
      if (prevStoreKeyRef.current === storeKey) return;
      prevStoreKeyRef.current = storeKey;
      setMissions((prev) => {
        const updated = prev.map((m) =>
          missionStore[m.id] ? { ...m, ...missionStore[m.id] } : m,
        );
        const prevIds = new Set(prev.map((m) => m.id));
        for (const [id, m] of Object.entries(missionStore)) {
          if (!prevIds.has(id)) updated.push(m);
        }
        updated.sort(
          (a, b) =>
            new Date(b.created_at ?? b.updated_at ?? 0).getTime() -
            new Date(a.created_at ?? a.updated_at ?? 0).getTime(),
        );
        return updated;
      });
      if (selectedMission && missionStore[selectedMission.id]) {
        setSelectedMission((prev) =>
          prev ? { ...prev, ...missionStore[prev.id] } : prev,
        );
      }
      if (!selectedMission) {
        const storeList = Object.values(missionStore).sort(
          (a, b) =>
            new Date(b.created_at ?? b.updated_at ?? 0).getTime() -
            new Date(a.created_at ?? a.updated_at ?? 0).getTime(),
        );
        if (storeList.length > 0) setSelectedMission(storeList[0]);
      }
    }
  }, [missionUpdates, missionStore, selectedMission]);

  return (
    <div className="flex h-full w-full flex-col overflow-y-auto lg:overflow-hidden bg-[#080a10] pb-12 lg:pb-0">
      {/* ── Top Command Bar ── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-white/[0.07] bg-[#0c0e18]/80 px-4 py-3 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/20 ring-1 ring-indigo-500/40">
            <Network size={14} className="text-indigo-400" />
          </div>
          <span className="text-sm font-bold tracking-tight text-white/90">Mission Orchestrator</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-[10px] font-medium text-emerald-400">
            ● LIVE
          </span>
        </div>
      </div>

      {/* ── Main Content Grid ── */}
      <div className="flex flex-col lg:flex-row min-h-0 flex-1 overflow-visible lg:overflow-hidden">
        {/* LEFT PANEL */}
        <div className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto border-r border-white/[0.06] bg-[#0a0c16]/60 p-3 lg:w-80 xl:w-96">
          {/* Agent Status */}
          <AgentStatusList />

          {/* Missions Panel */}
          <div className="flex flex-col rounded-2xl border border-white/[0.07] bg-[#0e1020]/70 shadow-xl backdrop-blur-md overflow-hidden">
            {/* Header */}
            <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-white/90">Missions</div>
                <div className="text-[10px] text-white/35">{missions.length} total</div>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  className="flex h-6 w-6 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/80 transition"
                  onClick={loadMissions} title="Refresh"
                >
                  <RefreshCw size={11} />
                </button>
                <button
                  className={`flex h-6 items-center gap-1 rounded-lg px-2 text-[10px] font-medium transition ${showCreate ? "border border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20" : "border border-indigo-500/30 bg-indigo-500/15 text-indigo-400 hover:bg-indigo-500/25"}`}
                  onClick={() => setShowCreate(!showCreate)}
                >
                  {showCreate ? <X size={11} /> : <Plus size={11} />}
                  {showCreate ? "Close" : "New"}
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-3">
              {showCreate ? (
                <MissionForm
                  onSubmit={async (data) => {
                    try {
                      const created = await api.createMission(data);
                      if (created && created.id) {
                        setMissions((prev) => {
                          const next = [created, ...prev];
                          saveMissionsLocal(next);
                          useStore.getState().setMissions(next);
                          return next;
                        });
                        setSelectedMission(created);
                      } else {
                        const fallback: MissionType = {
                          id: `msn-${Date.now()}`,
                          title: (data.title as string) || "Untitled Mission",
                          description: (data.description as string) || "",
                          prompt: (data.prompt as string) || "",
                          objectives: (data.objectives as string[]) || [],
                          deliverables: (data.deliverables as string[]) || [],
                          constraints: (data.constraints as string[]) || [],
                          status: "planned",
                          priority: (data.priority as any) || "medium",
                          execution_mode: (data.execution_mode as any) || "hybrid",
                          tags: (data.tags as string[]) || [],
                          attachments: [],
                          created_at: new Date().toISOString(),
                          updated_at: new Date().toISOString(),
                        };
                        setMissions((prev) => {
                          const next = [fallback, ...prev];
                          saveMissionsLocal(next);
                          useStore.getState().setMissions(next);
                          return next;
                        });
                        setSelectedMission(fallback);
                      }
                    } catch {
                      const fallback: MissionType = {
                        id: `msn-${Date.now()}`,
                        title: (data.title as string) || "Untitled Mission",
                        description: (data.description as string) || "",
                        prompt: (data.prompt as string) || "",
                        objectives: (data.objectives as string[]) || [],
                        deliverables: (data.deliverables as string[]) || [],
                        constraints: (data.constraints as string[]) || [],
                        status: "planned",
                        priority: (data.priority as any) || "medium",
                        execution_mode: (data.execution_mode as any) || "hybrid",
                        tags: (data.tags as string[]) || [],
                        attachments: [],
                        created_at: new Date().toISOString(),
                        updated_at: new Date().toISOString(),
                      };
                      setMissions((prev) => {
                        const next = [fallback, ...prev];
                        saveMissionsLocal(next);
                        useStore.getState().setMissions(next);
                        return next;
                      });
                      setSelectedMission(fallback);
                    } finally {
                      setShowCreate(false);
                    }
                  }}
                  onCancel={() => setShowCreate(false)}
                />
              ) : loading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-16 animate-pulse rounded-xl bg-white/[0.04]" />
                  ))}
                </div>
              ) : error ? (
                <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-400">
                  <AlertCircle size={12} className="inline mr-1" />{error}
                </div>
              ) : missions.length === 0 ? (
                <div className="py-8 text-center">
                  <div className="mb-2 text-2xl">🚀</div>
                  <div className="text-xs font-medium text-white/50">No missions yet</div>
                  <div className="mt-1 text-[10px] text-white/25">Click &apos;New&apos; to create your first mission.</div>
                </div>
              ) : (
                <div className="space-y-2">
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
            </div>
          </div>
        </div>

        {/* RIGHT PANEL */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          {selectedMission ? (
            <>
              {/* Mission Detail Header */}
              <MissionDetail mission={selectedMission} onRefresh={loadMissions} />

              {/* Futuristic Tab Bar */}
              <div className="shrink-0 border-b border-white/[0.06] bg-[#0a0c16]/80 px-4 backdrop-blur-md">
                <div className="flex items-center gap-0.5 overflow-x-auto no-scrollbar py-2">
                  {TABS.map((tab) => (
                    <button
                      key={tab.id}
                      className={`flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium transition-all whitespace-nowrap ${
                        rightTab === tab.id
                          ? "bg-indigo-500/15 text-indigo-400 ring-1 ring-indigo-500/30"
                          : "text-white/40 hover:bg-white/[0.04] hover:text-white/70"
                      }`}
                      onClick={() => setRightTab(tab.id)}
                    >
                      <tab.icon size={11} />
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Tab Content */}
              <div className="min-h-0 flex-1 overflow-y-auto">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={rightTab}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.12 }}
                    className="h-full p-4"
                  >
                    {rightTab === "detail" && selectedMission.plan && (
                      <MissionPlanView plan={selectedMission.plan} mission={selectedMission} />
                    )}
                    {rightTab === "detail" && !selectedMission.plan && (
                      <FuturisticEmpty
                        icon="📋"
                        title="No Execution Plan"
                        hint="Click the Plan button on the mission card to generate a plan."
                      />
                    )}
                    {rightTab === "timeline" && <ExecutionTimeline plan={selectedMission.plan ?? null} />}
                    {rightTab === "memory" && <SharedMemoryPanel />}
                    {rightTab === "comms" && <AgentCommsLog missionId={selectedMission.id} />}
                    {rightTab === "merge" && <MergePipelinePanel mission={selectedMission} />}
                    {rightTab === "validation" && <FinalValidationPanel mission={selectedMission} />}
                    {rightTab === "routing" && <RoutingPlanner mission={selectedMission} />}
                    {rightTab === "terminal" && (
                      selectedWorktreePath ? (
                        <TerminalPanel
                          worktreePath={selectedWorktreePath}
                          onClose={() => setRightTab("detail")}
                        />
                      ) : (
                        <FuturisticEmpty
                          icon="⌨️"
                          title="No Worktree Selected"
                          hint="Open a worktree from the Worktrees panel below."
                        />
                      )
                    )}
                    {rightTab === "review" && (
                      selectedWorktreeBranch ? (
                        <DiffViewer
                          branchName={selectedWorktreeBranch}
                          onClose={() => setRightTab("detail")}
                        />
                      ) : (
                        <FuturisticEmpty
                          icon="🔍"
                          title="No Worktree Selected"
                          hint="Open a worktree from the Worktrees panel below."
                        />
                      )
                    )}
                  </motion.div>
                </AnimatePresence>
              </div>

              {/* Worktree Panel — collapsible footer */}
              <div className="shrink-0 border-t border-white/[0.06] bg-[#0a0c16]/80 backdrop-blur-md">
                <button
                  onClick={() => setShowWorktreePanel(!showWorktreePanel)}
                  className="flex w-full items-center gap-2.5 px-4 py-2.5 text-xs text-white/50 hover:text-white/70 transition"
                >
                  <GitBranch size={12} className="text-emerald-400 shrink-0" />
                  <span className="font-medium">Worktrees</span>
                  <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[9px] text-white/50">
                    {worktrees.length}
                  </span>
                  {worktreeLoading && <Loader2 size={10} className="animate-spin text-white/30" />}
                  <span className="ml-auto">
                    {showWorktreePanel ? <ChevronDown size={11} /> : <ChevronUp size={11} />}
                  </span>
                </button>
                <AnimatePresence>
                  {showWorktreePanel && (
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{ height: "auto" }}
                      exit={{ height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="max-h-52 overflow-y-auto border-t border-white/[0.05] px-3 pb-3 pt-2">
                        {worktrees.length === 0 ? (
                          <div className="py-4 text-center text-[10px] text-white/25">
                            No worktrees active. Submit a task to create one.
                          </div>
                        ) : (
                          <div className="space-y-1">
                            {worktrees.map((wt) => (
                              <div
                                key={wt.branch}
                                className="flex items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-xs hover:bg-white/[0.04] transition"
                              >
                                <GitBranch size={10} className={
                                  wt.status === "active" ? "text-emerald-400" :
                                  wt.status === "dirty" ? "text-amber-400" :
                                  wt.status === "merged" ? "text-sky-400" :
                                  "text-red-400"
                                } />
                                <div className="min-w-0 flex-1">
                                  <div className="font-mono text-[10px] text-white/70 truncate">{wt.branch}</div>
                                  <div className="text-[9px] text-white/30">
                                    {wt.task_id ? `task: ${wt.task_id.slice(0, 8)}` : "unassigned"}
                                    {wt.agent_id && ` · agent: ${wt.agent_id.slice(0, 8)}`}
                                  </div>
                                </div>
                                <div className="flex shrink-0 gap-1">
                                  <button
                                    onClick={() => openWorktree(wt, "terminal")}
                                    className="rounded-lg p-1 text-white/30 hover:bg-white/10 hover:text-emerald-400 transition"
                                    title="Open terminal"
                                  >
                                    <TerminalIcon size={10} />
                                  </button>
                                  <button
                                    onClick={() => openWorktree(wt, "review")}
                                    className="rounded-lg p-1 text-white/30 hover:bg-white/10 hover:text-amber-400 transition"
                                    title="Review changes"
                                  >
                                    <FileDiff size={10} />
                                  </button>
                                  <button
                                    onClick={async () => {
                                      try {
                                        const result = await api.worktreeMerge(wt.branch);
                                        if (!result.merged) setError(result.error || "Merge conflicts detected");
                                        void loadWorktrees();
                                      } catch (err) { setError(String(err)); }
                                    }}
                                    className="rounded-lg p-1 text-white/30 hover:bg-white/10 hover:text-sky-400 transition"
                                    title="Merge to main"
                                  >
                                    <GitMerge size={10} />
                                  </button>
                                  <button
                                    onClick={async () => {
                                      try {
                                        await api.worktreeRemove(wt.branch);
                                        void loadWorktrees();
                                      } catch (err) { setError(String(err)); }
                                    }}
                                    className="rounded-lg p-1 text-white/30 hover:bg-white/10 hover:text-red-400 transition"
                                    title="Remove worktree"
                                  >
                                    <Trash2 size={10} />
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-4">
              <div className="relative flex h-24 w-24 items-center justify-center rounded-full border border-indigo-500/20 bg-indigo-500/5">
                <Network size={36} className="text-indigo-400/60" />
                <div className="absolute inset-0 animate-ping rounded-full border border-indigo-500/10" />
              </div>
              <div className="text-center">
                <div className="text-sm font-medium text-white/50">No Mission Selected</div>
                <div className="mt-1 text-[11px] text-white/25">Select a mission from the left panel to begin</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Futuristic Empty State ──
function FuturisticEmpty({ icon, title, hint }: { icon: string; title: string; hint: string }) {
  return (
    <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-3">
      <div className="text-3xl">{icon}</div>
      <div className="text-center">
        <div className="text-sm font-medium text-white/50">{title}</div>
        <div className="mt-1 text-[11px] text-white/25">{hint}</div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  AGENT STATUS LIST
// ══════════════════════════════════════════════════════════════

function AgentStatusList() {
  const providers = useStore((s) => s.providers);
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);

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

  const agents = Object.values(providers)
    .filter((p) => p.provider && p.provider.toLowerCase() !== "mock")
    .map((p, idx) => {
      const id = (p.provider ?? "").toLowerCase().replace(/\s+/g, "-");
      const q = queueDepth[id] ?? 0;
      return {
        id,
        label: p.provider ?? "unknown",
        color: providerColor(p.provider ?? "", idx),
        role: p.provider ?? "agent",
        status: p.status ?? "unknown",
        latency: p.latency_ms ?? 0,
        queue: q,
      };
    });

  const online = agents.filter((a) => a.status === "healthy" || a.status === "degraded").length;
  const busy = agents.filter((a) => a.queue > 0).length;

  return (
    <div className="rounded-2xl border border-white/[0.07] bg-[#0e1020]/70 shadow-xl backdrop-blur-md overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-white/[0.06] px-4 py-3">
        <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#4ade80]" />
        <span className="text-xs font-semibold text-white/90">Connected Agents</span>
        <span className="ml-auto text-[10px] text-white/35">{online} online · {busy} active</span>
      </div>
      <div className="space-y-px p-2">
        {agents.length === 0 ? (
          <div className="py-4 text-center text-[10px] text-white/25">
            No agents discovered
          </div>
        ) : (
          agents.map((a) => (
            <motion.div
              key={a.id}
              layout
              className="flex items-center gap-2.5 rounded-xl px-3 py-2 hover:bg-white/[0.03] transition-colors"
            >
              {/* Status glow dot */}
              <div className="relative shrink-0">
                <div className={`h-1.5 w-1.5 rounded-full ${
                  a.status === "healthy" ? "bg-emerald-400" :
                  a.status === "degraded" ? "bg-amber-400" :
                  a.status === "down" ? "bg-red-400" : "bg-white/20"
                }`} />
                {a.status === "healthy" && (
                  <div className="absolute inset-0 animate-ping rounded-full bg-emerald-400/40" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-white/80 truncate">{a.label}</span>
                  {a.status === "healthy" && (
                    <span className="text-[9px] font-mono text-white/30 tabular-nums">{a.latency.toFixed(0)}ms</span>
                  )}
                </div>
                <div className="text-[9px] text-white/30 truncate">{a.role}</div>
              </div>
              <div className="flex flex-col items-end gap-0.5 shrink-0">
                {a.queue > 0 && (
                  <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[9px] font-mono text-indigo-400 tabular-nums">
                    {a.queue}q
                  </span>
                )}
                <span className={`text-[9px] capitalize ${
                  a.status === "healthy" ? "text-emerald-400" :
                  a.status === "down" ? "text-red-400" : "text-amber-400"
                }`}>
                  {a.status}
                </span>
              </div>
            </motion.div>
          ))
        )}
      </div>
      <div className="border-t border-white/[0.04] px-4 py-2 text-center text-[9px] text-white/20">
        {connected ? "· EventBus live · Runtime Discovery Engine" : "· Standalone Runtime Mode"}
      </div>
    </div>
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

  const statusGlow: Record<string, string> = {
    executing: "shadow-[0_0_12px_rgba(34,197,94,0.15)]",
    failed: "shadow-[0_0_12px_rgba(239,68,68,0.12)]",
    planned: "shadow-[0_0_12px_rgba(99,102,241,0.12)]",
  };

  return (
    <motion.div
      layout
      className={`relative cursor-pointer overflow-hidden rounded-xl border transition-all duration-200 ${
        selected
          ? "border-indigo-500/40 bg-indigo-500/[0.07] " + (statusGlow[mission.status] ?? "")
          : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.12] hover:bg-white/[0.04]"
      }`}
      onClick={onClick}
    >
      {/* Left accent bar */}
      <div
        className="absolute left-0 top-0 h-full w-0.5 rounded-r"
        style={{ backgroundColor: statusColor, opacity: selected ? 1 : 0.4 }}
      />

      <div className="p-3 pl-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div
                className="h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: statusColor }}
              />
              <span className="text-xs font-semibold text-white/90 truncate">{mission.title}</span>
              {mission.channel && mission.channel !== "WEB" && (
                <span className="shrink-0 rounded bg-sky-500/15 px-1 py-px text-[8px] font-medium text-sky-400">
                  {mission.channel}
                </span>
              )}
            </div>

            <div className="mt-1.5 flex items-center gap-2 text-[10px]">
              <span
                className="rounded px-1.5 py-0.5 font-medium capitalize"
                style={{ backgroundColor: `${statusColor}18`, color: statusColor }}
              >
                {mission.status}
              </span>
              <span className={`rounded px-1.5 py-0.5 capitalize ${
                mission.priority === "critical" ? "bg-red-500/15 text-red-400" :
                mission.priority === "high" ? "bg-amber-500/15 text-amber-400" :
                "bg-white/[0.06] text-white/40"
              }`}>
                {mission.priority}
              </span>
              {taskCount > 0 && <span className="text-white/30">{taskCount} tasks</span>}
              {progress > 0 && <span className="text-white/30">{progress}%</span>}
            </div>

            {(mission.status === "executing" || mission.status === "paused") && taskCount > 0 && (
              <div className="mt-2 h-0.5 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${progress}%`,
                    background: `linear-gradient(90deg, ${statusColor}88, ${statusColor})`,
                  }}
                />
              </div>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
            {mission.status === "planned" && (
              <button
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition"
                onClick={onStart} title="Start"
              >
                <Play size={10} />
              </button>
            )}
            {mission.status === "executing" && (
              <button
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition"
                onClick={onPause} title="Pause"
              >
                <Pause size={10} />
              </button>
            )}
            {mission.status === "draft" && (
              <button
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-indigo-500/15 text-indigo-400 hover:bg-indigo-500/25 transition disabled:opacity-40"
                onClick={onPlan} disabled={planning} title="Plan"
              >
                {planning ? <Loader2 size={10} className="animate-spin" /> : <FileText size={10} />}
              </button>
            )}
            {(mission.status === "draft" || mission.status === "planned" || mission.status === "paused") && (
              <button
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-white/[0.04] text-white/30 hover:bg-red-500/15 hover:text-red-400 transition"
                onClick={onDelete} title="Delete"
              >
                <Trash2 size={10} />
              </button>
            )}
            {(mission.status === "executing" || mission.status === "paused") && (
              <button
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 transition"
                onClick={onCancel} title="Cancel"
              >
                <X size={10} />
              </button>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION FORM
// ══════════════════════════════════════════════════════════════

function MissionForm({ onSubmit, onCancel }: { onSubmit: (data: Record<string, unknown>) => void; onCancel: () => void }) {
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
    } finally { setSubmitting(false); }
  };

  const inputCls = "w-full rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white/80 placeholder-white/25 outline-none focus:border-indigo-500/50 focus:bg-white/[0.06] transition";
  const selectCls = "rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1.5 text-xs text-white/80 outline-none focus:border-indigo-500/50 transition";

  return (
    <div className="space-y-3">
      <input className={inputCls} placeholder="Mission title *" value={form.title}
        onChange={(e) => update("title", e.target.value)} />
      <textarea className={`${inputCls} resize-none`} placeholder="Mission description" rows={2}
        value={form.description} onChange={(e) => update("description", e.target.value)} />
      <textarea className={`${inputCls} resize-none font-mono text-[10px]`}
        placeholder="Prompt (full instruction for AI agents)" rows={3}
        value={form.prompt} onChange={(e) => update("prompt", e.target.value)} />
      <div className="grid grid-cols-2 gap-2">
        <select className={selectCls} value={form.priority} onChange={(e) => update("priority", e.target.value)}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className={selectCls} value={form.execution_mode} onChange={(e) => update("execution_mode", e.target.value)}>
          {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <ArrayInput label="Objectives" values={form.objectives} onChange={(v) => update("objectives", v)}
        placeholder="e.g. Implement update mechanism" icon={<Target size={10} />} />
      <ArrayInput label="Deliverables" values={form.deliverables} onChange={(v) => update("deliverables", v)}
        placeholder="e.g. Design document" icon={<ListTodo size={10} />} />
      <div className="grid grid-cols-2 gap-2">
        <input className={inputCls} placeholder="Tags (comma-separated)" value={form.tags.join(", ")}
          onChange={(e) => update("tags", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
        <input type="date" className={inputCls} value={form.deadline}
          onChange={(e) => update("deadline", e.target.value)} />
      </div>
      <div
        className={`rounded-xl border-2 border-dashed p-3 text-center transition-colors ${
          dragOver ? "border-indigo-500/50 bg-indigo-500/5" : "border-white/10 hover:border-white/20"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); setAttachments((prev) => [...prev, ...Array.from(e.dataTransfer.files)]); }}
      >
        <input ref={fileRef} type="file" multiple className="hidden"
          onChange={(e) => { if (e.target.files) setAttachments((prev) => [...prev, ...Array.from(e.target.files!)]); }} />
        <button type="button" className="flex w-full items-center justify-center gap-2 text-[10px] text-white/30 hover:text-white/60 transition"
          onClick={() => fileRef.current?.click()}>
          <Upload size={12} />
          <span>{dragOver ? "Drop files here" : "Drag & drop or click to add attachments"}</span>
        </button>
        {attachments.length > 0 && (
          <div className="mt-2 space-y-1 text-left">
            {attachments.map((f, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg bg-white/[0.04] px-2 py-1 text-[10px]">
                <FileText size={10} className="text-indigo-400 shrink-0" />
                <span className="flex-1 truncate text-white/60">{f.name}</span>
                <span className="text-white/30 shrink-0">{safeFixed((safeNum(f?.size) / 1024), 0)} KB</span>
                <button className="text-white/30 hover:text-red-400" onClick={() => setAttachments((prev) => prev.filter((_, idx) => idx !== i))}><X size={10} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex gap-2 pt-1">
        <button
          className="flex-1 rounded-lg bg-indigo-500/20 px-3 py-2 text-xs font-medium text-indigo-400 hover:bg-indigo-500/30 transition disabled:opacity-40"
          onClick={handleSubmit} disabled={!form.title.trim() || submitting}
        >
          {submitting ? <span className="flex items-center justify-center gap-1"><Loader2 size={12} className="animate-spin" /> Creating...</span> : "Create Mission"}
        </button>
        <button className="rounded-lg bg-white/[0.05] px-3 py-2 text-xs text-white/50 hover:bg-white/[0.08] transition" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ArrayInput({ label, values, onChange, placeholder, icon }: {
  label: string; values: string[]; onChange: (v: string[]) => void; placeholder: string; icon: React.ReactNode;
}) {
  const add = () => onChange([...values, ""]);
  const set = (i: number, v: string) => { const n = [...values]; n[i] = v; onChange(n); };
  const remove = (i: number) => onChange(values.filter((_, idx) => idx !== i));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1 text-[9px] font-medium uppercase tracking-widest text-white/30">
          {icon} {label}
        </label>
        <button className="text-[9px] text-indigo-400 hover:text-indigo-300 transition" onClick={add}>+ Add</button>
      </div>
      {values.map((v, i) => (
        <div key={i} className="flex gap-1">
          <input
            className="flex-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1.5 text-[11px] text-white/70 placeholder-white/20 outline-none focus:border-indigo-500/40 transition"
            placeholder={placeholder} value={v} onChange={(e) => set(i, e.target.value)}
          />
          <button className="text-white/20 hover:text-red-400 p-1 transition" onClick={() => remove(i)}><X size={11} /></button>
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION DETAIL (top header of right panel)
// ══════════════════════════════════════════════════════════════

function MissionDetail({ mission, onRefresh }: { mission: MissionType; onRefresh: () => void }) {
  const statusColor = STATUS_COLORS[mission.status] ?? "#6b7280";
  const taskCount = mission.plan?.task_count ?? 0;
  const completed = mission.plan?.tasks?.filter((t) => t.status === "completed").length ?? 0;
  const failed = mission.plan?.tasks?.filter((t) => t.status === "failed").length ?? 0;
  const progress = taskCount > 0 ? Math.round((completed / taskCount) * 100) : 0;

  const metaCols = [
    { label: "Status", value: mission.status, color: statusColor },
    { label: "Priority", value: mission.priority },
    { label: "Mode", value: mission.execution_mode },
    { label: "Created", value: new Date(mission.created_at).toLocaleString() },
  ];
  if (mission.deadline) metaCols.push({ label: "Deadline", value: new Date(mission.deadline).toLocaleDateString() });

  return (
    <div className="shrink-0 border-b border-white/[0.06] bg-[#0a0c16]/90 px-5 py-4 backdrop-blur-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Title row */}
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: statusColor, boxShadow: `0 0 8px ${statusColor}80` }} />
            <h1 className="text-base font-bold tracking-tight text-white/95 truncate">{mission.title}</h1>
          </div>
          {mission.description && (
            <p className="mt-0.5 text-[11px] text-white/40 truncate">{mission.description}</p>
          )}

          {/* Plan estimate row */}
          {mission.plan && (
            <div className="mt-2 flex items-center gap-3 text-[10px] text-white/35">
              <span className="flex items-center gap-1"><Clock size={9} /> ~{mission.plan.estimated_total_minutes}m estimated</span>
              <span className="capitalize">· {mission.plan.complexity} complexity</span>
              <span className="capitalize">· {mission.plan.risk_level} risk</span>
            </div>
          )}

          {/* Progress bar */}
          {(mission.status === "executing" || mission.status === "paused") && taskCount > 0 && (
            <div className="mt-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[10px] text-white/30">Progress</span>
                <span className="text-[10px] font-mono text-white/50 tabular-nums">
                  {completed}/{taskCount} tasks · {progress}%
                  {failed > 0 && <span className="text-red-400 ml-2">{failed} failed</span>}
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <motion.div
                  className="h-full rounded-full"
                  style={{ background: `linear-gradient(90deg, ${statusColor}60, ${statusColor})` }}
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.6, ease: "easeOut" }}
                />
              </div>
            </div>
          )}
        </div>

        <button
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-white/40 hover:bg-white/[0.08] hover:text-white/70 transition"
          onClick={onRefresh} title="Refresh"
        >
          <RefreshCw size={12} />
        </button>
      </div>

      {/* Meta stat chips */}
      <div className="mt-3 flex flex-wrap gap-2">
        {metaCols.map((c) => (
          <div key={c.label} className="rounded-lg border border-white/[0.07] bg-white/[0.03] px-2.5 py-1.5">
            <div className="text-[8px] uppercase tracking-widest text-white/25">{c.label}</div>
            <div className="mt-0.5 text-[11px] font-semibold capitalize" style={c.color ? { color: c.color } : { color: "rgba(255,255,255,0.75)" }}>
              {c.value}
            </div>
          </div>
        ))}
      </div>

      {/* Error */}
      {mission.error && (
        <div className="mt-3 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-400">
          <AlertCircle size={12} className="shrink-0" />{mission.error}
        </div>
      )}

      {/* Objectives / Deliverables / Tags inline */}
      {(mission.objectives.length > 0 || mission.deliverables.length > 0 || mission.tags.length > 0) && (
        <div className="mt-3 flex flex-wrap gap-2 text-[10px]">
          {mission.objectives.slice(0, 3).map((o, i) => (
            <span key={i} className="flex items-center gap-1 rounded-lg bg-indigo-500/10 px-2 py-1 text-indigo-400">
              <Target size={8} /> {o.slice(0, 40)}{o.length > 40 ? "…" : ""}
            </span>
          ))}
          {mission.tags.map((t) => (
            <span key={t} className="rounded-lg bg-white/[0.05] px-2 py-1 text-white/40">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  EXECUTION TIMELINE
// ══════════════════════════════════════════════════════════════

function ExecutionTimeline({ plan }: { plan: MissionPlanType | null }) {
  if (!plan) return (
    <FuturisticEmpty icon="⏱️" title="No Execution Data" hint="The mission has not been planned yet." />
  );

  const completed = plan.tasks.filter((t) => t.status === "completed").length;
  const running = plan.tasks.filter((t) => t.status === "running").length;
  const progress = plan.task_count > 0 ? Math.round((completed / plan.task_count) * 100) : 0;

  const byProvider: Record<string, MissionTaskType[]> = {};
  for (const t of plan.tasks) {
    const key = t.assigned_provider || "unassigned";
    if (!byProvider[key]) byProvider[key] = [];
    byProvider[key].push(t);
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="rounded-2xl border border-white/[0.07] bg-[#0e1020]/70 p-4 backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-semibold text-white/80">Execution Timeline</span>
          <span className="text-[10px] text-white/40 tabular-nums">{completed} done · {running} running · {progress}%</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400"
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.6, ease: "easeOut" }}
          />
        </div>
        <div className="mt-3 flex items-center gap-4 text-[9px]">
          {[
            { label: "Running", color: "bg-emerald-400" },
            { label: "Pending", color: "bg-white/20" },
            { label: "Failed", color: "bg-red-400" },
            { label: "Planned", color: "bg-indigo-400" },
          ].map((l) => (
            <span key={l.label} className="flex items-center gap-1 text-white/30">
              <span className={`h-1.5 w-1.5 rounded-full ${l.color}`} />{l.label}
            </span>
          ))}
        </div>
      </div>

      {/* Swimlanes */}
      {Object.entries(byProvider).map(([provider, tasks], providerIdx) => {
        const color = providerColor(provider, providerIdx);
        return (
          <div key={provider} className="rounded-2xl border border-white/[0.07] bg-[#0e1020]/50 p-4 backdrop-blur-md">
            <div className="mb-3 flex items-center gap-2">
              <div className="h-2 w-2 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}80` }} />
              <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color }}>{provider}</span>
            </div>
            <div className="relative ml-3 space-y-2 pl-4 border-l border-white/[0.07]">
              {tasks.map((task) => (
                <div key={task.id} className="flex items-center gap-3">
                  <div
                    className="absolute -left-[5px] h-2 w-2 rounded-full border-2 border-[#0e1020]"
                    style={{ backgroundColor: TASK_COLORS[task.status] ?? "#6b7280" }}
                  />
                  <span className={`rounded-full border px-3 py-0.5 text-[11px] transition-colors ${
                    task.status === "running" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400" :
                    task.status === "completed" ? "border-emerald-500/25 bg-emerald-500/5 text-emerald-500/70" :
                    task.status === "failed" ? "border-red-500/40 bg-red-500/10 text-red-400" :
                    "border-white/10 text-white/30"
                  }`}>
                    {task.title}
                  </span>
                  <span className="ml-auto text-[9px] tabular-nums text-white/25">~{task.estimated_minutes}m</span>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/70">Shared Memory</span>
        <span className="text-[10px] text-white/30">{memory.length} items · {Object.keys(agents).length} agents</span>
      </div>

      {memory.length === 0 && (
        <FuturisticEmpty icon="🧠" title="No Shared Memory" hint="Memory items will appear as agents store context." />
      )}

      {missionMemory.length > 0 && (
        <div>
          <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-white/25">Mission Context</div>
          <div className="space-y-2">
            {missionMemory.slice(0, 20).map((item) => (
              <div key={item.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold text-indigo-400 truncate">{item.key}</span>
                  {item.agent_id && <span className="text-[9px] shrink-0 text-white/25">by {item.agent_id}</span>}
                </div>
                <p className="mt-1 text-[10px] text-white/40 line-clamp-2">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {globalMemory.length > 0 && (
        <div>
          <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-white/25">Global Context</div>
          <div className="space-y-2">
            {globalMemory.slice(0, 10).map((item) => (
              <div key={item.id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="text-[11px] font-medium text-white/60 truncate">{item.key}</div>
                <p className="mt-0.5 text-[10px] text-white/35 line-clamp-1">{item.value}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="text-center text-[9px] text-white/20">
        Prevents agents from repeatedly asking for the same information
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  AGENT COMMS LOG
// ══════════════════════════════════════════════════════════════

function AgentCommsLog({ missionId }: { missionId: string }) {
  const events = useStore((s) => s.events);

  const commsEvents = useMemo(() =>
    events.filter((e) => e.topic.includes("task.") || e.topic.includes("agent.") || e.topic.includes("approval.")),
  [events]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/70">Inter-Agent Communication</span>
        <span className="text-[10px] text-white/30">{commsEvents.length} events via EventBus</span>
      </div>

      {commsEvents.length === 0 ? (
        <FuturisticEmpty icon="📡" title="No Agent Communication Yet" hint="Events will appear as agents coordinate via the EventBus." />
      ) : (
        <div className="space-y-2">
          {commsEvents.slice(0, 80).map((e, i) => {
            const p = e.payload as Record<string, any>;
            const source = String(p?.source ?? p?.agent_id ?? p?.provider ?? "system");
            const target = String(p?.target ?? p?.assigned_provider ?? "");
            const topicColor =
              e.topic.includes("completed") ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-400" :
              e.topic.includes("failed") ? "border-red-500/30 bg-red-500/5 text-red-400" :
              e.topic.includes("dispatched") ? "border-amber-500/30 bg-amber-500/5 text-amber-400" :
              "border-indigo-500/30 bg-indigo-500/5 text-indigo-400";

            return (
              <div key={e.id || `evt-${i}`} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[9px] text-white/30">
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`rounded border px-1.5 py-0.5 text-[9px] font-medium ${topicColor}`}>
                    {e.topic}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                  <span className="font-semibold text-white/70">{source}</span>
                  {target && (
                    <>
                      <span className="text-white/25">→</span>
                      <span className="font-semibold text-indigo-400">{target}</span>
                    </>
                  )}
                </div>
                <div className="mt-0.5 text-[10px] text-white/25 truncate">
                  {JSON.stringify(p).slice(0, 120)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="text-center text-[9px] text-white/20">
        Everything is event-driven · agents communicate through the EventBus
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MERGE PIPELINE PANEL
// ══════════════════════════════════════════════════════════════

function MergePipelinePanel({ mission }: { mission: MissionType }) {
  const plan = mission.plan;
  const taskCount = plan?.task_count ?? plan?.tasks.length ?? 0;
  const doneCount = plan?.tasks.filter((t) => t.status === "completed").length ?? 0;
  const executing = mission.status === "executing" || mission.status === "paused";
  const allDone = taskCount > 0 && doneCount === taskCount;

  const err = mission.error?.toLowerCase() ?? "";
  const hasConflict = err.includes("merge") || err.includes("conflict");
  const hasTestFail = err.includes("test");
  const hasSecurity = err.includes("security");
  const hasRegression = err.includes("regression");
  const hasDocTask = plan?.tasks.some((t) => t.title.toLowerCase().includes("document")) ?? false;

  const stageStates: Record<string, "pending" | "running" | "passed" | "failed"> = useMemo(() => {
    const running = executing && !allDone;
    return {
      conflicts: hasConflict ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      merge: hasConflict ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      format: hasConflict ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      lint: hasConflict ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      tests: hasTestFail ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      security: hasSecurity ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      regression: hasRegression ? "failed" : allDone ? "passed" : running ? "running" : "pending",
      documentation: hasDocTask && allDone ? "passed" : hasDocTask && running ? "running" : "pending",
    };
  }, [hasConflict, hasTestFail, hasSecurity, hasRegression, allDone, executing, hasDocTask]);

  const doneStages = MERGE_STAGES.filter((s) => stageStates[s.id] === "passed").length;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/70">Merge & Validate</span>
        <span className="text-[10px] text-white/30">{doneStages}/{MERGE_STAGES.length} stages · {doneCount}/{taskCount} tasks complete</span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {MERGE_STAGES.map((stage) => {
          const state = stageStates[stage.id] ?? "pending";
          const ringColor =
            state === "running" ? "ring-indigo-500/40 border-indigo-500/20" :
            state === "passed" ? "ring-emerald-500/40 border-emerald-500/20" :
            state === "failed" ? "ring-red-500/40 border-red-500/20" :
            "border-white/[0.06]";
          const iconColor =
            state === "passed" ? "text-emerald-400" :
            state === "failed" ? "text-red-400" :
            state === "running" ? "text-indigo-400" : "text-white/20";

          return (
            <div
              key={stage.id}
              className={`rounded-xl border bg-white/[0.02] p-3 text-center ring-1 ring-transparent transition-all ${ringColor}`}
            >
              <stage.icon size={18} className={`mx-auto mb-1.5 ${iconColor}`} />
              <div className="text-[10px] font-medium text-white/60">{stage.label}</div>
              <div className="mt-1 flex items-center justify-center">
                {state === "pending" && <span className="text-[9px] text-white/20">Waiting</span>}
                {state === "running" && <Loader2 size={10} className="animate-spin text-indigo-400" />}
                {state === "passed" && <CheckCircle2 size={10} className="text-emerald-400" />}
                {state === "failed" && <XCircle size={10} className="text-red-400" />}
              </div>
            </div>
          );
        })}
      </div>

      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-[11px] text-white/40 space-y-1">
        <p className="text-white/50 font-medium mb-2">After all agents complete their work, the Result Merger automatically:</p>
        <ul className="space-y-1 pl-4 list-disc">
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
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  MISSION PLAN VIEW
// ══════════════════════════════════════════════════════════════

function MissionPlanView({ plan, mission }: { plan: MissionPlanType; mission: MissionType }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      {/* Plan summary */}
      <div className="rounded-2xl border border-white/[0.07] bg-[#0e1020]/70 p-4 backdrop-blur-md">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-semibold text-white/80">Execution Plan</div>
            <div className="mt-1 text-[10px] text-white/40">
              {plan.complexity} complexity · {plan.risk_level} risk · ~{plan.estimated_total_minutes}m total · {plan.task_count} tasks
            </div>
            {plan.summary && <p className="mt-2 text-[11px] text-white/50 leading-relaxed">{plan.summary}</p>}
          </div>
        </div>
      </div>

      {/* Task list */}
      <div className="space-y-2">
        {plan.tasks.map((task, idx) => (
          <div key={task.id}>
            <motion.div
              layout
              className={`relative cursor-pointer overflow-hidden rounded-xl border transition-all ${
                task.status === "running"
                  ? "border-emerald-500/30 bg-emerald-500/[0.04] ring-1 ring-emerald-500/20"
                  : expanded === task.id
                  ? "border-indigo-500/30 bg-indigo-500/[0.04]"
                  : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.10] hover:bg-white/[0.03]"
              }`}
              onClick={() => setExpanded(expanded === task.id ? null : task.id)}
            >
              {/* Left accent */}
              <div
                className="absolute left-0 top-0 h-full w-0.5 rounded-r"
                style={{ backgroundColor: TASK_COLORS[task.status] ?? "#6b7280" }}
              />

              <div className="flex items-center gap-3 p-3 pl-4">
                <span className="shrink-0 font-mono text-[9px] text-white/20">{String(idx + 1).padStart(2, "0")}</span>
                <div
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: TASK_COLORS[task.status] ?? "#6b7280" }}
                />
                <span className="min-w-0 flex-1 truncate text-xs text-white/80">{task.title}</span>
                <span className="shrink-0 text-[9px] tabular-nums text-white/25">~{task.estimated_minutes}m</span>
                {task.assigned_role && (
                  <span className="shrink-0 rounded bg-indigo-500/10 px-1.5 py-0.5 text-[9px] text-indigo-400">
                    {task.assigned_role.replace(/_/g, " ")}
                  </span>
                )}
                {task.assigned_provider && (
                  <span className="shrink-0 rounded bg-white/[0.05] px-1.5 py-0.5 font-mono text-[9px] text-white/40">
                    {task.assigned_provider}
                  </span>
                )}
                {expanded === task.id ? <ChevronUp size={11} className="shrink-0 text-white/30" /> : <ChevronDown size={11} className="shrink-0 text-white/30" />}
              </div>

              <AnimatePresence>
                {expanded === task.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="overflow-hidden"
                  >
                    <div className="border-t border-white/[0.06] px-4 py-3 space-y-2">
                      <p className="text-[11px] text-white/50 leading-relaxed">{task.description}</p>
                      {task.dependencies.length > 0 && (
                        <p className="text-[10px] text-white/25">Depends on: {task.dependencies.map((d) => d.slice(0, 8)).join(", ")}</p>
                      )}
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-medium capitalize" style={{ color: TASK_COLORS[task.status] ?? "#6b7280" }}>
                          ● {task.status}
                        </span>
                        {task.assigned_provider && (
                          <span className="rounded bg-white/[0.05] px-1.5 py-0.5 text-[9px] text-white/40">{task.assigned_provider}</span>
                        )}
                      </div>
                      {task.output && (
                        <div>
                          <div className="mb-1 text-[9px] uppercase tracking-widest text-white/25">Output</div>
                          <pre className="max-h-24 overflow-y-auto rounded-lg bg-white/[0.03] p-2 text-[10px] text-white/50 whitespace-pre-wrap">
                            {task.output.slice(0, 300)}{task.output.length > 300 ? "..." : ""}
                          </pre>
                        </div>
                      )}
                      {task.error && (
                        <div className="flex items-center gap-1.5 text-[10px] text-red-400">
                          <AlertCircle size={10} /> {task.error}
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {idx < plan.tasks.length - 1 && (
              <div className="flex justify-center py-1">
                <div className="h-3 w-px bg-white/[0.06]" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  FINAL VALIDATION PANEL
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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/70">Final Validation</span>
        <span className="text-[10px] text-white/30">{passed}/{total} gates passed</span>
      </div>

      <div className={`rounded-2xl border p-4 text-center text-sm font-semibold transition-colors ${
        ready
          ? "border-emerald-500/30 bg-emerald-500/[0.08] text-emerald-400"
          : "border-amber-500/30 bg-amber-500/[0.08] text-amber-400"
      }`}>
        {ready ? "✅ All gates passed — mission ready to complete" : `⏳ ${total - passed} gate(s) not satisfied`}
      </div>

      {/* Progress bar */}
      <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
        <motion.div
          className="h-full rounded-full"
          style={{ background: ready ? "linear-gradient(90deg,#10b981,#34d399)" : "linear-gradient(90deg,#f59e0b,#fbbf24)" }}
          initial={{ width: 0 }}
          animate={{ width: `${(passed / total) * 100}%` }}
          transition={{ duration: 0.6 }}
        />
      </div>

      <div className="space-y-2">
        {gates.map((gate) => (
          <div
            key={gate.id}
            className={`flex items-center gap-3 rounded-xl border p-3 transition-colors ${
              gate.met
                ? "border-emerald-500/15 bg-emerald-500/[0.05]"
                : "border-amber-500/15 bg-amber-500/[0.05]"
            }`}
          >
            <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
              gate.met ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"
            }`}>
              {gate.met ? <Check size={12} /> : <Clock size={12} />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium text-white/70">{gate.label}</div>
              <div className="text-[10px] text-white/30">{gate.desc}</div>
            </div>
            <span className={`shrink-0 text-[9px] font-bold tabular-nums ${gate.met ? "text-emerald-400" : "text-amber-400"}`}>
              {gate.met ? "PASS" : "PENDING"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
//  ROUTING PLANNER
// ══════════════════════════════════════════════════════════════

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-white/70">
          Routing — {currentStrategy?.label ?? selectedStrategy}
        </span>
        <button
          className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[10px] font-medium transition ${
            loading
              ? "cursor-not-allowed border-white/10 bg-white/[0.03] text-white/25"
              : "border-indigo-500/30 bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20"
          }`}
          onClick={compareRoute} disabled={loading}
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
          {loading ? "Comparing…" : "Compare"}
        </button>
      </div>

      {stratSummary && (
        <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-[10px] text-white/40">
          {stratSummary}
        </div>
      )}

      {/* Strategy grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {ROUTING_STRATEGIES.map((s) => (
          <button
            key={s.id}
            onClick={() => { setSelectedStrategy(s.id); setRoutePlan(null); }}
            className={`rounded-xl border p-2.5 text-left transition-all ${
              selectedStrategy === s.id
                ? "border-indigo-500/40 bg-indigo-500/10 ring-1 ring-indigo-500/20"
                : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.10] hover:bg-white/[0.04]"
            }`}
          >
            <div className="text-sm">{s.icon}</div>
            <div className="mt-1 text-[11px] font-medium text-white/70">{s.label}</div>
            <div className="mt-0.5 text-[9px] text-white/30 leading-tight">{s.desc}</div>
          </button>
        ))}
      </div>

      {/* Route plan */}
      {routePlan ? (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { label: "Est. Cost", value: `$${routePlan.total_estimated_cost.toFixed(2)}` },
              { label: "Duration", value: `${(routePlan.total_estimated_duration_ms / 1000).toFixed(1)}s` },
              { label: "Avg Score", value: routePlan.average_composite_score.toFixed(3) },
              { label: "Providers", value: Object.keys(routePlan.provider_usage).length.toString() },
            ].map((s) => (
              <div key={s.label} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 text-center">
                <div className="text-[9px] uppercase tracking-widest text-white/25">{s.label}</div>
                <div className="mt-1 text-sm font-semibold tabular-nums text-white/80">{s.value}</div>
              </div>
            ))}
          </div>

          {Object.keys(routePlan.provider_usage).length > 0 && (
            <div>
              <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-white/25">Provider Usage</div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(routePlan.provider_usage).map(([provider, count]) => (
                  <span key={provider} className="rounded-lg border border-white/[0.08] bg-white/[0.04] px-2 py-1 text-[10px] text-white/60">
                    {provider} ×{count}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-white/25">
              Task Assignments ({routePlan.assignments.length})
            </div>
            <div className="space-y-1.5 max-h-52 overflow-y-auto">
              {routePlan.assignments.map((a) => (
                <div
                  key={a.task_id}
                  className="flex items-center gap-2 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-[11px]"
                >
                  <StatusDot status={a.status as any} />
                  <span className="min-w-0 flex-1 truncate text-white/70">{a.task_title}</span>
                  <span className="shrink-0 text-[9px] text-white/35">{a.assigned_agent_name}</span>
                  <span className="shrink-0 font-mono text-[9px] text-white/35">${a.estimated_cost.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <FuturisticEmpty
          icon="🗺️"
          title="No Route Plan"
          hint="Select a strategy above and click Compare to generate a route plan."
        />
      )}
    </div>
  );
}
