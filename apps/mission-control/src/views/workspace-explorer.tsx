"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import {
  Folder, Shield, HardDrive, RefreshCw, Search,
  Terminal, Cpu, CheckCircle2, ArrowRight, Layers, FileCode
} from "lucide-react";
import type { WorktreeEntry } from "@/lib/types";

export function WorkspaceExplorer() {
  const [agentId, setAgentId] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [worktrees, setWorktrees] = useState<WorktreeEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [err, setErr] = useState("");

  const agents = useStore((s) => s.agents);

  const loadWorktrees = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.worktreeList();
      setWorktrees(Array.isArray(list) ? list : []);
    } catch {
      setWorktrees([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorktrees();
  }, [loadWorktrees]);

  async function resolve(targetId?: string) {
    const idToResolve = targetId || agentId;
    if (!idToResolve) return;
    setResolving(true);
    setErr("");
    setWorkspace("");
    try {
      const r = await api.workspaceFor(idToResolve);
      setWorkspace(r.workspace);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setResolving(false);
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background/95 p-4 space-y-3">
      {/* ── Futuristic Control Deck Header ── */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-surface/40 via-cyan-950/20 to-surface/40 p-3.5 backdrop-blur-xl shadow-[0_0_20px_rgba(6,182,212,0.05)]">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.2)]">
            <HardDrive size={20} className="animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-semibold tracking-wide text-text">Workspace Explorer</h1>
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-mono tracking-wider text-cyan-400 uppercase">
                Sandbox Isolation
              </span>
            </div>
            <p className="text-xs text-faint">Inspect agent sandbox boundaries, git worktrees & security path enforcement</p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => loadWorktrees()}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-xl border border-cyan-500/40 bg-cyan-500/10 px-3.5 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-500/60 transition shadow-[0_0_12px_rgba(6,182,212,0.15)] disabled:opacity-50"
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            <span>Sync Worktrees</span>
          </button>
        </div>
      </div>

      {/* ── KPI Telemetry Row ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
        <Stat label="Active Worktrees" value={worktrees.length} tone="accent" />
        <Stat label="Active Agents" value={Object.keys(agents).length} tone="ok" />
        <Stat label="Isolation Level" value="Strict Sandbox" tone="accent" />
        <Stat label="Security Enforcement" value="Control Plane" />
      </div>

      {/* ── Main 2-Column Split Workspace ── */}
      <div className="grid flex-1 gap-4 min-h-0 grid-cols-1 lg:grid-cols-12 overflow-hidden">
        {/* Left Column: Agent Lookup Resolver */}
        <Panel
          title="Agent Sandbox Resolver"
          subtitle="Query agent workspace isolation path"
          className="col-span-12 lg:col-span-5 flex flex-col h-full overflow-hidden border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
        >
          <div className="flex flex-col space-y-3 p-1">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
                <input
                  className="w-full rounded-xl border border-cyan-500/30 bg-surface/50 py-2 pl-9 pr-3 text-xs text-text placeholder:text-faint outline-none focus:border-cyan-500/60 focus:shadow-[0_0_12px_rgba(6,182,212,0.15)] transition"
                  placeholder="Enter agent ID or select below..."
                  value={agentId}
                  onChange={(e) => setAgentId(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && resolve()}
                />
              </div>
              <button
                className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/80 transition shadow-[0_0_12px_rgba(6,182,212,0.2)] disabled:opacity-50 shrink-0"
                onClick={() => resolve()}
                disabled={resolving || !agentId.trim()}
              >
                {resolving ? "Resolving…" : "Resolve"}
              </button>
            </div>

            {/* Quick-pick Active Agents */}
            <div className="space-y-1.5">
              <div className="text-[10px] font-mono text-faint uppercase tracking-wider">Active Constellation Agents</div>
              <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto pr-1 custom-scrollbar">
                {Object.keys(agents).length === 0 ? (
                  <span className="text-xs text-faint italic">No active agents online</span>
                ) : (
                  Object.keys(agents).map((id) => (
                    <button
                      key={id}
                      onClick={() => {
                        setAgentId(id);
                        resolve(id);
                      }}
                      className={`rounded-lg border px-2.5 py-1 text-[11px] font-mono transition ${
                        agentId === id
                          ? "border-cyan-500/60 bg-cyan-500/20 text-cyan-300"
                          : "border-border/40 bg-surface/40 text-faint hover:text-text hover:border-cyan-500/30"
                      }`}
                    >
                      {id.slice(0, 12)}
                    </button>
                  ))
                )}
              </div>
            </div>

            {/* Resolution Output */}
            <div className="mt-2">
              {workspace && (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 space-y-1.5"
                >
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-400">
                    <CheckCircle2 size={14} />
                    <span>Isolated Workspace Path Resolved</span>
                  </div>
                  <div className="rounded-lg border border-emerald-500/20 bg-background/80 p-2.5 font-mono text-xs text-emerald-300 break-all">
                    {workspace}
                  </div>
                </motion.div>
              )}
              {err && (
                <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300">
                  {err}
                </div>
              )}
              {!workspace && !err && (
                <Empty title="Enter or select an agent ID" hint="The security framework returns the agent's isolated workspace." />
              )}
            </div>
          </div>
        </Panel>

        {/* Right Column: Active Git Worktrees List */}
        <Panel
          title="Active Git Worktrees"
          subtitle={`${worktrees.length} isolated branches`}
          className="col-span-12 lg:col-span-7 flex flex-col h-full overflow-hidden border border-cyan-500/15 bg-surface/30 backdrop-blur-md"
        >
          <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
            {worktrees.length === 0 ? (
              <Empty title="No active worktrees" hint="Agent worktrees will populate here when missions execute." />
            ) : (
              <AnimatePresence>
                {worktrees.map((wt) => (
                  <motion.div
                    key={wt.branch || wt.path}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: -10 }}
                    className="flex flex-col gap-2 rounded-xl border border-cyan-500/20 bg-surface/40 p-3 transition hover:border-cyan-500/50"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Folder size={15} className="text-cyan-400 shrink-0" />
                        <span className="text-xs font-semibold text-text font-mono truncate">{wt.branch}</span>
                      </div>
                      {wt.agent_id && (
                        <Badge tone="info">Agent: {wt.agent_id.slice(0, 8)}</Badge>
                      )}
                    </div>
                    <div className="rounded-lg bg-background/60 p-2 font-mono text-[11px] text-faint break-all">
                      {wt.path}
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-faint">
                      <span>Base: {wt.base_branch || "main"}</span>
                      {wt.task_id && <span>Task: {wt.task_id.slice(0, 8)}</span>}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

