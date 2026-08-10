"use client";

import { useMemo, useState } from "react";
import { Panel, Stat, Badge, StatusDot } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Orbit, Users, Send, GitMerge, Vote } from "lucide-react";
import type { AgentNode, TaskNode } from "@/lib/types";

// Collaboration topics published by the backend orchestrator / agents.
const COLLAB_TOPICS = new Set([
  "collaboration.delegate",
  "collaboration.review",
  "collaboration.vote",
  "collaboration.handshake",
  "task.dispatched",
  "task.completed",
  "agent.completed",
]);

export function LiveCollaboration() {
  const connected = useStore((s) => s.connected);
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const events = useStore((s) => s.events);

  const [delegating, setDelegating] = useState(false);
  const [actionResult, setActionResult] = useState<string | null>(null);

  const agentList = useMemo(() => Object.values(agents) as AgentNode[], [agents]);
  const activeAgents = agentList.filter((a) => a.status === "running" || a.status === "completed" || a.status === "recovering");
  const taskList = useMemo(() => Object.values(tasks) as TaskNode[], [tasks]);
  const activeTasks = taskList.filter((t) => t.status !== "completed" && t.status !== "failed" && t.status !== "pending");

  const collabEvents = useMemo(
    () => events.filter((e) => COLLAB_TOPICS.has(e.topic) || COLLAB_TOPICS.has(e.type)).slice(0, 30),
    [events],
  );

  // Delegate the first in-flight task to the first available (non-busy) agent.
  const handleDelegate = async () => {
    const source = activeAgents[0];
    const target = activeAgents.find((a) => a.id !== source?.id && a.status === "idle") ?? activeAgents[1];
    const task = activeTasks[0];
    if (!source || !target || !task) {
      setActionResult("Not enough real agents/tasks to delegate — no operation performed.");
      return;
    }
    setDelegating(true);
    setActionResult(null);
    try {
      const r = await api.collaborationDelegate({
        from_agent: source.id,
        to_agent: target.id,
        task_id: task.id,
        reason: "manual delegation from Live Collaboration",
      });
      setActionResult(
        r.delegated ? `Delegated task "${task.title}" from ${r.from} to ${r.to}.` : "Delegation API did not confirm.",
      );
    } catch (e) {
      setActionResult(`Delegation failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setDelegating(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Orbit size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">AGENT COLLABORATION</h1>
            <p className="text-[11px] text-faint">Real agent delegation, reviews & votes flowing through the orchestrator</p>
          </div>
        </div>
        <Badge tone={connected ? "ok" : "warn"}>{connected ? "Live Session Active" : "Standalone Session"}</Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Active Agents" value={activeAgents.length} tone="accent" />
        <Stat label="In-Flight Tasks" value={activeTasks.length} tone="ok" />
        <Stat label="Collab Events" value={collabEvents.length} tone="default" />
        <Stat label="Connection" value={connected ? "Connected" : "Local"} tone={connected ? "ok" : "default"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Active Agents" subtitle={`${agentList.length} known · ${activeAgents.length} busy`}>
          {agentList.length === 0 ? (
            <div className="p-6 text-center text-[11px] text-faint">
              No agents discovered yet — bind local AI agents first.
            </div>
          ) : (
            <div className="space-y-2">
              {agentList.slice(0, 20).map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3 text-xs">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <StatusDot status={a.health} />
                    <div className="min-w-0">
                      <div className="font-semibold text-text truncate">{a.id}</div>
                      <div className="text-[10px] text-faint truncate">
                        {a.role}{a.provider ? ` · ${a.provider}` : ""}
                        {a.capabilities?.length ? ` · ${a.capabilities.join(", ")}` : ""}
                      </div>
                    </div>
                  </div>
                  <Badge tone={a.status === "running" ? "warn" : a.status === "completed" ? "ok" : a.status === "failed" ? "danger" : "default"}>
                    {a.status}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Collaboration Activity" subtitle={`${collabEvents.length} recent orchestration events`}>
          {collabEvents.length === 0 ? (
            <div className="p-6 text-center text-[11px] text-faint">
              No collaboration events yet. Delegation, reviews, and votes will appear here as the orchestrator runs.
            </div>
          ) : (
            <div className="space-y-1.5 max-h-96 overflow-y-auto pr-1">
              {collabEvents.map((e) => (
                <div key={e.id} className="flex items-start gap-2 rounded-lg border border-border/40 px-3 py-2 text-[11px]">
                  <span className="font-mono text-muted shrink-0">{e.topic || e.type}</span>
                  <span className="text-faint truncate">
                    {typeof e.payload?.message === "string"
                      ? e.payload.message
                      : `from ${e.source || "?"}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Collaboration Actions" subtitle="Real calls to the orchestrator">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleDelegate}
            disabled={delegating}
            className="flex items-center gap-1.5 rounded-lg bg-accent/15 border border-accent/40 px-3 py-2 text-xs font-semibold text-accent hover:bg-accent/25 transition disabled:opacity-50"
          >
            <Send size={13} />
            {delegating ? "Delegating…" : "Delegate Task"}
          </button>
          <div className="flex items-center gap-1.5 rounded-lg border border-border/60 px-3 py-2 text-[11px] text-faint">
            <GitMerge size={13} />
            Reviews & votes are emitted by agents during real orchestrator runs.
          </div>
          {actionResult && (
            <span className={`text-[11px] ${actionResult.startsWith("Delegation failed") ? "text-danger" : "text-ok"}`}>
              {actionResult}
            </span>
          )}
        </div>
        <div className="mt-3 text-[11px] text-faint">
          <span className="inline-flex items-center gap-1"><Users size={12} /> {activeAgents.length} agent(s) available for delegation</span>
          <span className="mx-2">·</span>
          <span className="inline-flex items-center gap-1"><Vote size={12} /> quorum resolution is handled by the orchestrator</span>
        </div>
      </Panel>
    </div>
  );
}
