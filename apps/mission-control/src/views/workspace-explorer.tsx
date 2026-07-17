"use client";

import { useState } from "react";
import { Panel, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";

// Workspace Explorer. Resolves the sandbox path granted to an agent via the
// security framework's workspace isolation. Real lookup against the control plane.
export function WorkspaceExplorer() {
  const [agentId, setAgentId] = useState("");
  const [workspace, setWorkspace] = useState("");
  const [err, setErr] = useState("");

  async function resolve() {
    if (!agentId) return;
    setErr("");
    setWorkspace("");
    try {
      const r = await api.workspaceFor(agentId);
      setWorkspace(r.workspace);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="h-full p-4">
      <Panel title="Workspace Explorer" subtitle="Agent sandbox isolation" className="h-full">
        <div className="flex max-w-md gap-2">
          <input
            className="flex-1 rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
            placeholder="agent id"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && resolve()}
          />
          <button className="pill bg-accent/20 text-accent hover:bg-accent/30" onClick={resolve}>
            Resolve
          </button>
        </div>
        {workspace && (
          <div className="mt-4 rounded-xl border border-border/60 bg-surface/40 px-4 py-3 font-mono text-sm">
            {workspace}
          </div>
        )}
        {err && <div className="mt-3 text-sm text-danger">{err}</div>}
        {!workspace && !err && (
          <div className="mt-6">
            <Empty title="Enter an agent id" hint="The security framework returns the agent's isolated workspace." />
          </div>
        )}
      </Panel>
    </div>
  );
}
