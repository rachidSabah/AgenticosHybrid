"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { MissionType, MissionPlanType, MissionTaskType } from "@/lib/types";
import { Plus, X, Play, Pause, Trash2, FileText, Target, ListTodo, Tag, Clock, ChevronDown, ChevronUp } from "lucide-react";

const PRIORITIES = ["low", "medium", "high", "critical"];
const MODES = ["sequential", "parallel", "hybrid"];

const STATUS_COLORS: Record<string, string> = {
  draft: "#6b7280",
  planning: "#f59e0b",
  planned: "#6366f1",
  executing: "#22c55e",
  paused: "#f59e0b",
  completed: "#22c55e",
  failed: "#ef4444",
  cancelled: "#6b7280",
};

const TASK_STATUS_COLORS: Record<string, string> = {
  pending: "#6b7280",
  planned: "#6366f1",
  assigned: "#8b5cf6",
  running: "#22c55e",
  completed: "#22c55e",
  failed: "#ef4444",
  blocked: "#ef4444",
  skipped: "#6b7280",
};

// ── Main Component ──

export function MissionOrchestrator() {
  const [missions, setMissions] = useState<MissionType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedMission, setSelectedMission] = useState<MissionType | null>(null);
  const [planning, setPlanning] = useState<string | null>(null);

  const loadMissions = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.missions();
      setMissions(data);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadMissions(); }, [loadMissions]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      {/* Left panel — mission list */}
      <div className="col-span-4 flex flex-col gap-4">
        <Panel
          title="Missions"
          subtitle={`${missions.length} total`}
          actions={
            <button
              className="pill bg-accent/20 text-accent hover:bg-accent/30"
              onClick={() => setShowCreate(!showCreate)}
            >
              {showCreate ? <X size={14} /> : <Plus size={14} />}
              {showCreate ? "Close" : "New"}
            </button>
          }
          className="flex-1"
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
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 glass rounded-xl animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="text-sm text-danger p-3 glass rounded-xl">{error}</div>
          ) : missions.length === 0 ? (
            <Empty title="No missions yet" hint="Click 'New' to create your first mission." />
          ) : (
            <div className="space-y-2">
              {missions.map((m) => (
                <MissionCard
                  key={m.id}
                  mission={m}
                  selected={selectedMission?.id === m.id}
                  onClick={() => setSelectedMission(m)}
                  onPlan={async () => {
                    setPlanning(m.id);
                    try {
                      await api.planMission(m.id);
                      await loadMissions();
                    } finally {
                      setPlanning(null);
                    }
                  }}
                  onStart={async () => {
                    await api.startMission(m.id);
                    loadMissions();
                  }}
                  onPause={async () => {
                    await api.pauseMission(m.id);
                    loadMissions();
                  }}
                  onCancel={async () => {
                    await api.cancelMission(m.id);
                    loadMissions();
                  }}
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

      {/* Right panel — mission detail / plan */}
      <div className="col-span-8 flex flex-col gap-4">
        {selectedMission ? (
          <>
            <MissionDetail mission={selectedMission} />
            {selectedMission.plan && <MissionPlanView plan={selectedMission.plan} />}
          </>
        ) : (
          <Panel title="Mission Detail" subtitle="Select a mission to view" className="flex-1">
            <Empty title="No mission selected" hint="Select a mission from the left panel." />
          </Panel>
        )}
      </div>
    </div>
  );
}

// ── Mission Card (compact) ──

function MissionCard({
  mission,
  selected,
  onClick,
  onPlan,
  onStart,
  onPause,
  onCancel,
  onDelete,
  planning,
}: {
  mission: MissionType;
  selected: boolean;
  onClick: () => void;
  onPlan: () => void;
  onStart: () => void;
  onPause: () => void;
  onCancel: () => void;
  onDelete: () => void;
  planning: boolean;
}) {
  const statusColor = STATUS_COLORS[mission.status] ?? "#6b7280";
  const taskCount = mission.plan?.task_count ?? 0;

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
            {mission.deadline && <span>Due {new Date(mission.deadline).toLocaleDateString()}</span>}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {mission.status === "planned" && (
            <button
              className="pill bg-green-500/15 text-green-400 hover:bg-green-500/25 text-[10px]"
              onClick={(e) => { e.stopPropagation(); onStart(); }}
              title="Start"
            >
              <Play size={12} />
            </button>
          )}
          {mission.status === "executing" && (
            <button
              className="pill bg-yellow-500/15 text-yellow-400 hover:bg-yellow-500/25 text-[10px]"
              onClick={(e) => { e.stopPropagation(); onPause(); }}
              title="Pause"
            >
              <Pause size={12} />
            </button>
          )}
          {mission.status === "draft" && (
            <button
              className="pill bg-accent/15 text-accent hover:bg-accent/25 text-[10px]"
              onClick={(e) => { e.stopPropagation(); onPlan(); }}
              disabled={planning}
              title="Plan"
            >
              {planning ? "..." : <FileText size={12} />}
            </button>
          )}
          {(mission.status === "draft" || mission.status === "planned" || mission.status === "paused") && (
            <button
              className="pill bg-surface/80 text-faint hover:text-danger text-[10px]"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              title="Delete"
            >
              <Trash2 size={12} />
            </button>
          )}
          {(mission.status === "executing" || mission.status === "paused") && (
            <button
              className="pill bg-red-500/15 text-red-400 hover:bg-red-500/25 text-[10px]"
              onClick={(e) => { e.stopPropagation(); onCancel(); }}
              title="Cancel"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// ── Mission Creation Form ──

function MissionForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (data: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    title: "",
    description: "",
    prompt: "",
    objectives: [""],
    deliverables: [""],
    priority: "medium",
    execution_mode: "hybrid",
    constraints: [] as string[],
    deadline: "",
    tags: [] as string[],
  });
  const [submitting, setSubmitting] = useState(false);

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
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <input
        className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
        placeholder="Mission title *"
        value={form.title}
        onChange={(e) => update("title", e.target.value)}
      />
      <textarea
        className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60 resize-none"
        placeholder="Mission description"
        rows={2}
        value={form.description}
        onChange={(e) => update("description", e.target.value)}
      />
      <textarea
        className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60 resize-none font-mono text-[11px]"
        placeholder="Prompt (full instruction for AI agents)"
        rows={4}
        value={form.prompt}
        onChange={(e) => update("prompt", e.target.value)}
      />

      <div className="grid grid-cols-2 gap-2">
        <select
          className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none"
          value={form.priority}
          onChange={(e) => update("priority", e.target.value)}
        >
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <select
          className="rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none"
          value={form.execution_mode}
          onChange={(e) => update("execution_mode", e.target.value)}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      <ArrayInput
        label="Objectives"
        values={form.objectives}
        onChange={(v) => update("objectives", v)}
        placeholder="e.g. Implement update mechanism"
        icon={<Target size={12} />}
      />
      <ArrayInput
        label="Deliverables"
        values={form.deliverables}
        onChange={(v) => update("deliverables", v)}
        placeholder="e.g. Design document"
        icon={<ListTodo size={12} />}
      />

      <div className="grid grid-cols-2 gap-2">
        <input
          className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-xs outline-none focus:border-accent/60"
          placeholder="Tags (comma-separated)"
          value={form.tags.join(", ")}
          onChange={(e) => update("tags", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))}
        />
        <input
          type="date"
          className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-xs outline-none focus:border-accent/60"
          value={form.deadline}
          onChange={(e) => update("deadline", e.target.value)}
        />
      </div>

      <div className="flex gap-2 pt-1">
        <button
          className="flex-1 pill bg-accent/20 text-accent hover:bg-accent/30 disabled:opacity-40"
          onClick={handleSubmit}
          disabled={!form.title.trim() || submitting}
        >
          {submitting ? "Creating..." : "Create Mission"}
        </button>
        <button
          className="pill bg-surface/60 text-muted hover:bg-surface"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Array Input (objectives, deliverables) ──

function ArrayInput({
  label,
  values,
  onChange,
  placeholder,
  icon,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  icon: React.ReactNode;
}) {
  const add = () => onChange([...values, ""]);
  const set = (i: number, v: string) => {
    const next = [...values];
    next[i] = v;
    onChange(next);
  };
  const remove = (i: number) => onChange(values.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label className="text-[10px] uppercase tracking-wider text-faint flex items-center gap-1">
          {icon} {label}
        </label>
        <button className="text-[10px] text-accent hover:text-accent/80" onClick={add}>+ Add</button>
      </div>
      {values.map((v, i) => (
        <div key={i} className="flex gap-1">
          <input
            className="flex-1 rounded-lg border border-border/60 bg-surface/50 px-2 py-1.5 text-xs outline-none focus:border-accent/60"
            placeholder={placeholder}
            value={v}
            onChange={(e) => set(i, e.target.value)}
          />
          <button className="text-faint hover:text-danger p-1" onClick={() => remove(i)}>
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}

// ── Mission Detail Panel ──

function MissionDetail({ mission }: { mission: MissionType }) {
  const cols = [
    { label: "Status", value: mission.status, color: STATUS_COLORS[mission.status] },
    { label: "Priority", value: mission.priority },
    { label: "Mode", value: mission.execution_mode },
    { label: "Created", value: new Date(mission.created_at).toLocaleString() },
  ];
  if (mission.deadline) cols.push({ label: "Deadline", value: new Date(mission.deadline).toLocaleDateString() });

  return (
    <Panel title={mission.title} subtitle={mission.description || "(no description)"}>
      <div className="grid grid-cols-4 gap-2 mb-4">
        {cols.map((c) => (
          <div key={c.label} className="glass rounded-xl px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-faint">{c.label}</div>
            <div className="mt-0.5 text-sm font-medium" style={c.color ? { color: c.color } : {}}>
              {c.value}
            </div>
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
          <pre className="text-xs text-muted whitespace-pre-wrap bg-surface/40 rounded-lg p-3 max-h-32 overflow-y-auto">
            {mission.prompt}
          </pre>
        </Section>
      )}

      {mission.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {mission.tags.map((t) => (
            <Badge key={t} tone="info">{t}</Badge>
          ))}
        </div>
      )}

      {mission.attachments.length > 0 && (
        <Section title={`Attachments (${mission.attachments.length})`}>
          {mission.attachments.map((a) => (
            <div key={a.id} className="text-sm text-muted flex items-center gap-2">
              <FileText size={12} className="text-accent" />
              <span>{a.filename}</span>
              <span className="text-[10px] text-faint">({(a.size_bytes / 1024).toFixed(0)} KB)</span>
            </div>
          ))}
        </Section>
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

// ── Mission Plan View ──

function MissionPlanView({ plan }: { plan: MissionPlanType }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <Panel
      title="Execution Plan"
      subtitle={`${plan.complexity} complexity · ${plan.risk_level} risk · ~${plan.estimated_total_minutes}m total`}
    >
      <div className="mb-3 text-xs text-muted">{plan.summary}</div>

      <div className="space-y-2">
        {plan.tasks.map((task, idx) => (
          <div key={task.id}>
            <motion.div
              layout
              className="glass rounded-xl p-3 cursor-pointer hover:border-border/40 border border-transparent transition-colors"
              onClick={() => setExpanded(expanded === task.id ? null : task.id)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-[10px] text-faint font-mono shrink-0">{idx + 1}.</span>
                  <StatusDot status={task.status} pulse={task.status === "running"} />
                  <span className="text-sm truncate">{task.title}</span>
                  <span className="text-[10px] text-faint">~{task.estimated_minutes}m</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {task.assigned_role && (
                    <Badge tone="info">{task.assigned_role.replace(/_/g, " ")}</Badge>
                  )}
                  {task.assigned_provider && (
                    <span className="text-[10px] text-accent">{task.assigned_provider}</span>
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
                    <div className="mt-2 pt-2 border-t border-border/40 text-xs text-muted space-y-1">
                      <p>{task.description}</p>
                      {task.dependencies.length > 0 && (
                        <p className="text-faint">
                          Depends on: {task.dependencies.map((d) => d.slice(0, 8)).join(", ")}
                        </p>
                      )}
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px]" style={{ color: TASK_STATUS_COLORS[task.status] ?? "#6b7280" }}>
                          ● {task.status}
                        </span>
                        {task.assigned_provider && (
                          <span className="text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded">
                            {task.assigned_provider}
                          </span>
                        )}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>

            {/* Dependency arrow */}
            {idx < plan.tasks.length - 1 && (
              <div className="flex justify-center py-0.5">
                <div className="w-px h-3 bg-border/30" />
              </div>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
