"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { Play, Pause, StepForward, RotateCcw, GitFork, Users, MessageSquare, ShieldAlert, Cpu } from "lucide-react";

type SwarmTab = "debugger" | "time-travel" | "team-assembly";

export function SwarmStudio() {
  const [tab, setTab] = useState<SwarmTab>("debugger");
  const [missionId, setMissionId] = useState("mission-live-01");
  const [stepIndex, setStepIndex] = useState(1);
  const [status, setStatus] = useState("idle");
  const [activeAgent, setActiveAgent] = useState<string | null>("agent-architect");
  const [teamRoles, setTeamRoles] = useState<any[]>([]);
  const [debateResult, setDebateResult] = useState<any | null>(null);
  const [taskPrompt, setTaskPrompt] = useState("Refactor auth system with zero-trust token validation");
  const [forkPrompt, setForkPrompt] = useState("Adjust architecture to use Rust high-performance submodules");

  const loadTeam = useCallback(async () => {
    try {
      const res = await api.post<any>("/api/swarm/team/compose", { task_description: taskPrompt });
      if (res && res.roles) setTeamRoles(res.roles);
    } catch { /* ignore */ }
  }, [taskPrompt]);

  useEffect(() => {
    void loadTeam();
  }, [loadTeam]);

  const handleStep = async () => {
    setStatus("stepping");
    try {
      const res = await api.post<any>(`/api/missions/${missionId}/step`, {});
      if (res) {
        setStepIndex((s) => s + 1);
        setStatus("stepping");
      }
    } finally {
      setTimeout(() => setStatus("paused"), 600);
    }
  };

  const handlePause = async () => {
    await api.post(`/api/missions/${missionId}/pause`, {});
    setStatus("paused");
  };

  const handleResume = async () => {
    await api.post(`/api/missions/${missionId}/resume`, {});
    setStatus("running");
  };

  const handleRewind = async (target: number) => {
    const res = await api.post<any>(`/api/missions/${missionId}/rewind`, { target_step: target });
    if (res) {
      setStepIndex(target);
      setStatus("paused");
    }
  };

  const handleFork = async () => {
    const res = await api.post<any>(`/api/missions/${missionId}/fork`, {
      target_step: stepIndex,
      adjusted_prompt: forkPrompt,
    });
    if (res && res.forked_mission_id) {
      setMissionId(res.forked_mission_id);
      setStatus("running");
    }
  };

  const handleDebate = async () => {
    const res = await api.post<any>("/api/swarm/team/debate", {
      topic: taskPrompt,
      proposed_change: "Implement cryptographic zero-trust validation boundary",
    });
    if (res) setDebateResult(res);
  };

  return (
    <div className="flex h-full flex-col bg-background text-text">
      {/* Sub-header Navigation */}
      <div className="flex items-center justify-between border-b border-border/60 px-4 pt-2 bg-surface/10">
        <div className="flex items-center gap-1 overflow-x-auto">
          {(["debugger", "time-travel", "team-assembly"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded-t-lg px-4 py-2 text-xs font-medium transition whitespace-nowrap ${
                tab === t ? "bg-surface/40 text-text border-b-2 border-accent" : "text-faint hover:text-muted hover:bg-surface/20"
              }`}
            >
              {t === "debugger" ? "Swarm DAG & Step-Debugger" : t === "time-travel" ? "Deterministic Time-Travel" : "Team Auto-Assembly & Debate"}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-xs pb-1">
          <Badge tone={status === "running" ? "ok" : status === "paused" ? "warn" : "default"}>{status.toUpperCase()}</Badge>
          <span className="font-mono text-faint">Step {stepIndex}</span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-4 space-y-4">
        {tab === "debugger" && (
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4">
            <Panel title="Interactive Swarm Execution DAG" subtitle="Node-level real-time inspection & step debugging">
              {/* Controls */}
              <div className="flex items-center gap-2 mb-4">
                <button onClick={handleStep} className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-white hover:bg-accent/80 transition">
                  <StepForward size={14} /> Step (F10)
                </button>
                <button onClick={status === "running" ? handlePause : handleResume} className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-surface/30 px-3 py-1.5 text-xs font-medium hover:bg-surface/60 transition">
                  {status === "running" ? <><Pause size={14} /> Pause</> : <><Play size={14} /> Resume</>}
                </button>
                <button onClick={() => handleRewind(Math.max(1, stepIndex - 1))} className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-surface/30 px-3 py-1.5 text-xs font-medium hover:bg-surface/60 transition">
                  <RotateCcw size={14} /> Rewind 1 Step
                </button>
              </div>

              {/* Swarm DAG Visualizer Nodes */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-4 rounded-xl border border-border/40 bg-surface/10">
                {[
                  { id: "agent-architect", name: "Principal Architect", status: "completed", tokens: 1420, mem: "12 keys", role: "Contract & Seams" },
                  { id: "agent-engineer", name: "Core Engineer", status: status === "running" ? "executing" : "waiting", tokens: 2850, mem: "24 keys", role: "Business Logic" },
                  { id: "agent-qa", name: "Resilience Auditor", status: "idle", tokens: 980, mem: "6 keys", role: "Adversarial TDD" },
                ].map((node) => (
                  <div
                    key={node.id}
                    onClick={() => setActiveAgent(node.id)}
                    className={`cursor-pointer rounded-xl border p-3.5 transition ${
                      activeAgent === node.id ? "border-accent bg-accent/10 shadow-lg shadow-accent/5" : "border-border/60 bg-surface/20 hover:border-border"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-xs">{node.name}</span>
                      <Badge tone={node.status === "completed" ? "ok" : node.status === "executing" ? "warn" : "default"}>{node.status}</Badge>
                    </div>
                    <div className="text-[11px] text-faint mb-2">{node.role}</div>
                    <div className="flex items-center justify-between text-[10px] text-faint font-mono pt-2 border-t border-border/30">
                      <span>Tokens: {node.tokens}</span>
                      <span>Memory: {node.mem}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Node Sandbox Inspector" subtitle={activeAgent ?? "Select a node"}>
              <div className="space-y-3 text-xs">
                <div className="rounded-lg border border-border/40 bg-surface/20 p-3">
                  <div className="font-semibold text-[11px] text-accent uppercase tracking-wider mb-1">Isolated Memory Scope</div>
                  <div className="font-mono text-[11px] text-faint space-y-1">
                    <div>• domain_models: [&quot;HexagonalKernel&quot;, &quot;EventBus&quot;]</div>
                    <div>• pending_tool_calls: [&quot;write_file&quot;, &quot;run_test&quot;]</div>
                    <div>• execution_lock: unlocked</div>
                  </div>
                </div>
                <div className="rounded-lg border border-border/40 bg-surface/20 p-3">
                  <div className="font-semibold text-[11px] text-emerald-400 uppercase tracking-wider mb-1">Active Prompt Context</div>
                  <p className="text-faint text-[11px] leading-relaxed">
                    You are the {activeAgent}. Maintain strict decoupled boundaries and ensure zero regressions across all verification suites.
                  </p>
                </div>
              </div>
            </Panel>
          </div>
        )}

        {tab === "time-travel" && (
          <div className="space-y-4">
            <Panel title="Deterministic Execution Timeline Scrubber" subtitle="Slide backward to inspect historical frames, diffs, and fork execution">
              <div className="space-y-4">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span>Step 1: Initial Architecture</span>
                  <span className="text-accent font-semibold">Current: Step {stepIndex}</span>
                  <span>Step 10: Final Certification</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={stepIndex}
                  onChange={(e) => handleRewind(parseInt(e.target.value))}
                  className="w-full h-2 rounded-lg bg-surface/60 accent-indigo-500 cursor-pointer"
                />
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                  <Stat label="Scrubbed Step" value={`Step ${stepIndex}`} />
                  <Stat label="Execution Status" value={status.toUpperCase()} tone={status === "running" ? "ok" : "warn"} />
                  <Stat label="Historical Frames" value="10 Captured" />
                </div>
              </div>
            </Panel>

            <Panel title="Checkpoint Fork Controller" subtitle="Branch execution from this historical step with modified prompts">
              <div className="space-y-3">
                <input
                  type="text"
                  value={forkPrompt}
                  onChange={(e) => setForkPrompt(e.target.value)}
                  className="w-full rounded-lg border border-border/60 bg-surface/30 px-3 py-2 text-xs text-text outline-none focus:border-accent"
                  placeholder="Enter adjusted prompt for the fork..."
                />
                <button onClick={handleFork} className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition">
                  <GitFork size={14} /> Fork Execution from Step {stepIndex}
                </button>
              </div>
            </Panel>
          </div>
        )}

        {tab === "team-assembly" && (
          <div className="space-y-4">
            <Panel title="Semantic Task Decomposition & Dynamic Agent Constellation" subtitle="Auto-generated specialized sub-agents based on prompt requirements">
              <div className="flex gap-2 mb-4">
                <input
                  type="text"
                  value={taskPrompt}
                  onChange={(e) => setTaskPrompt(e.target.value)}
                  className="flex-1 rounded-lg border border-border/60 bg-surface/30 px-3 py-2 text-xs text-text outline-none focus:border-accent"
                />
                <button onClick={loadTeam} className="rounded-lg bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/80 transition">
                  Decompose & Assemble
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {teamRoles.map((role) => (
                  <div key={role.role_id} className="rounded-xl border border-border/60 bg-surface/20 p-3.5">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-semibold text-xs">{role.name}</span>
                      <Badge tone="ok">{role.model_preference}</Badge>
                    </div>
                    <p className="text-faint text-[11px] mb-2">{role.system_prompt}</p>
                    <div className="flex flex-wrap gap-1">
                      {role.capabilities.map((c: string) => (
                        <span key={c} className="rounded bg-surface/60 px-2 py-0.5 text-[10px] text-faint font-mono">{c}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Pre-Commit Multi-Agent Consensus Debate" subtitle="Live voting and dialectic review before code commits">
              <button onClick={handleDebate} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition mb-3">
                <MessageSquare size={14} /> Initiate Consensus Debate
              </button>

              {debateResult && (
                <div className="space-y-3 rounded-xl border border-border/40 bg-surface/10 p-4">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-xs">Debate: {debateResult.topic}</span>
                    <Badge tone={debateResult.consensus_reached ? "ok" : "warn"}>
                      Consensus: {(debateResult.approval_rating * 100).toFixed(0)}% Approved
                    </Badge>
                  </div>
                  <div className="space-y-2">
                    {debateResult.contributions.map((c: any) => (
                      <div key={c.agent_id} className="rounded-lg border border-border/30 bg-surface/20 p-2.5 text-xs">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-accent">{c.role_name}</span>
                          <span className="text-[11px] text-emerald-400 font-semibold uppercase">✓ {c.vote}</span>
                        </div>
                        <p className="text-faint text-[11px]">{c.argument}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}