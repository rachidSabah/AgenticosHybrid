"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { Orbit, Users, MessageSquare, ShieldCheck, Share2 } from "lucide-react";

export function LiveCollaboration() {
  const [activeUsers, setActiveUsers] = useState([
    { id: "u-1", name: "Lead Architect", role: "Admin", mission: "Mission Orchestrator Refactor", status: "Active", avatar: "LA" },
    { id: "u-2", name: "Security Auditor", role: "Auditor", mission: "Governance & DLP Policy Check", status: "Active", avatar: "SA" },
    { id: "u-3", name: "AI Engineer", role: "Developer", mission: "OmniRoute Pipeline Optimization", status: "Active", avatar: "AE" },
  ]);

  const connected = useStore((s) => s.connected);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Orbit size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">LIVE COLLABORATION & MULTI-USER WORKSPACE</h1>
            <p className="text-[11px] text-faint">Shared missions, team workspaces, presence & role-based access control</p>
          </div>
        </div>
        <Badge tone={connected ? "ok" : "warn"}>{connected ? "Live Session Active" : "Standalone Session"}</Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Active Teammates" value={activeUsers.length} tone="accent" />
        <Stat label="Shared Missions" value={4} tone="ok" />
        <Stat label="Live Workspaces" value={2} tone="default" />
        <Stat label="RBAC Status" value="Enforced" tone="ok" />
      </div>

      <Panel title="Active Teammates & Workspaces" subtitle="Real-time multi-agent presence & shared prompt editing">
        <div className="space-y-2">
          {activeUsers.map((u) => (
            <div key={u.id} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-full bg-accent/20 text-accent font-bold text-xs border border-accent/40">
                  {u.avatar}
                </div>
                <div>
                  <div className="font-semibold text-text">{u.name} <span className="text-[10px] text-purple-300 font-mono">({u.role})</span></div>
                  <div className="text-[11px] text-faint">Active in: <span className="text-muted">{u.mission}</span></div>
                </div>
              </div>
              <Badge tone="ok">{u.status}</Badge>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
