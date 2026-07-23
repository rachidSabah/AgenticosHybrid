"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, StatusDot } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Shield, Lock, FileText, CheckCircle2, AlertTriangle, ShieldCheck, UserCheck } from "lucide-react";

export function GovernanceCenter() {
  const [policies, setPolicies] = useState([
    { id: "pol-1", name: "Strict Data Loss Prevention (DLP)", type: "Prompt Guardrail", target: "All Models", status: "Active", risk: "Low" },
    { id: "pol-2", name: "EU AI Act Compliance & Audit Logging", type: "Compliance Rule", target: "Production Pipelines", status: "Active", risk: "Low" },
    { id: "pol-3", name: "High-Cost Model Approval Gate (> $1.00)", type: "Approval Workflow", target: "Claude 3.7 / GPT-4o", status: "Active", risk: "Medium" },
    { id: "pol-4", name: "Local Data Residency Lock (US-East)", type: "Data Residency", target: "Ollama / Hermes", status: "Active", risk: "Low" },
  ]);

  const connected = useStore((s) => s.connected);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Shield size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">ENTERPRISE AI GOVERNANCE & COMPLIANCE</h1>
            <p className="text-[11px] text-faint">Usage policies, approval gates, prompt guardrails & compliance controls</p>
          </div>
        </div>
        <Badge tone={connected ? "ok" : "warn"}>{connected ? "Policies Enforced" : "Local Policy Engine"}</Badge>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Active Policies" value={policies.length} tone="accent" />
        <Stat label="Guardrail Interceptions" value={42} tone="ok" />
        <Stat label="Pending Approvals" value={0} tone="ok" />
        <Stat label="Compliance Score" value="99.4%" tone="ok" />
      </div>

      <Panel title="Configured Enterprise Policies" subtitle="Active guardrails & compliance rules">
        <div className="space-y-2">
          {policies.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
              <div className="space-y-1">
                <div className="flex items-center gap-2 font-semibold text-text">
                  <ShieldCheck size={14} className="text-accent" />
                  {p.name}
                </div>
                <div className="text-[11px] text-faint">
                  Type: <span className="text-muted">{p.type}</span> · Scope: <span className="text-purple-300">{p.target}</span>
                </div>
              </div>
              <Badge tone="ok">{p.status}</Badge>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
