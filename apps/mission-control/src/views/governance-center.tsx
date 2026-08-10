"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Shield, ShieldCheck, FileText, AlertTriangle, ScrollText } from "lucide-react";

interface ExecutivePolicy {
  type: string;
  params: Record<string, unknown>;
  updated_at: string;
}

interface ToolPermRow {
  name: string;
  requires_approval: boolean;
}

interface AuditEvent {
  timestamp: string;
  topic: string;
  source: string;
  payload: Record<string, unknown>;
}

export function GovernanceCenter() {
  const connected = useStore((s) => s.connected);

  const [policy, setPolicy] = useState<ExecutivePolicy | null>(null);
  const [policyHistory, setPolicyHistory] = useState<Array<Record<string, unknown>>>([]);
  const [tools, setTools] = useState<ToolPermRow[]>([]);
  const [auditTrail, setAuditTrail] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, tp, trail] = await Promise.all([
        api.executivePolicies().catch(() => null),
        api.toolPermissions().catch(() => null),
        api.securityAuditTrail(100).catch(() => null),
      ]);

      if (p?.policy) setPolicy(p.policy);
      if (Array.isArray(p?.history)) setPolicyHistory(p.history);
      if (tp) {
        // Build a real row list from whatever the backend returned.
        const rows: ToolPermRow[] = [];
        const permMap = tp.permissions ?? {};
        for (const [name, v] of Object.entries(permMap)) {
          const requiresApproval =
            typeof v === "object" && v !== null && "requires_approval" in v
              ? Boolean((v as { requires_approval?: boolean }).requires_approval)
              : false;
          rows.push({ name, requires_approval: requiresApproval });
        }
        for (const name of tp.requires_approval ?? []) {
          if (!rows.some((r) => r.name === name)) rows.push({ name, requires_approval: true });
        }
        for (const name of tp.auto_approved ?? []) {
          if (!rows.some((r) => r.name === name)) rows.push({ name, requires_approval: false });
        }
        setTools(rows);
      }
      if (Array.isArray(trail)) setAuditTrail(trail);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, connected]);

  // Derived, real stats only.
  const approvalRequired = tools.filter((t) => t.requires_approval).length;
  const autoApproved = tools.filter((t) => !t.requires_approval).length;
  const interceptions = auditTrail.filter((e) => e.topic === "tool.denied").length;
  const pendingApprovals = auditTrail.filter((e) => e.topic === "approval.requested").length;

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Shield size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">ENTERPRISE AI GOVERNANCE & COMPLIANCE</h1>
            <p className="text-[11px] text-faint">Executive policy, tool approval gates & security audit trail</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={connected ? "ok" : "warn"}>{connected ? "Connected" : "Offline"}</Badge>
          <button
            onClick={load}
            disabled={loading}
            className="rounded-lg border border-border/60 px-3 py-1.5 text-xs text-faint transition hover:bg-surface/20 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Policy Type" value={policy?.type ?? "—"} tone="accent" />
        <Stat label="Tool Denials" value={interceptions} tone={interceptions > 0 ? "warn" : "default"} />
        <Stat label="Approval Requests" value={pendingApprovals} tone={pendingApprovals > 0 ? "warn" : "default"} />
        <Stat label="Security Events" value={auditTrail.length} tone="default" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Executive Policy" subtitle={policy ? `updated ${new Date(policy.updated_at).toLocaleString()}` : "No policy returned by backend"}>
          {!policy ? (
            <div className="p-6 text-center text-[11px] text-faint">
              ExecutiveController unavailable — backend returned no policy.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2 rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
                <ShieldCheck size={14} className="text-accent" />
                <div>
                  <div className="font-semibold text-text">Active: {policy.type}</div>
                  <div className="text-[11px] text-faint mt-0.5">
                    {Object.entries(policy.params ?? {}).map(([k, v]) => `${k}=${String(v)}`).join(" · ") || "no params"}
                  </div>
                </div>
              </div>
              {policyHistory.length > 0 && (
                <div>
                  <div className="mb-1 text-xs font-medium text-faint">Policy History</div>
                  {policyHistory.slice(0, 5).map((h, i) => (
                    <div key={i} className="rounded-lg border border-border/40 px-3 py-2 text-[11px] text-faint flex justify-between">
                      <span>{String(h.type ?? "—")}</span>
                      <span className="text-muted">{String(h.updated_at ?? "—")}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Panel>

        <Panel title="Tool Approval Gates" subtitle={`${tools.length} tools known`}>
          {tools.length === 0 ? (
            <div className="p-6 text-center text-[11px] text-faint">
              Backend returned no tool permission configuration.
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {tools.map((t) => (
                <div key={t.name} className="flex items-center justify-between rounded-lg border border-border/40 px-3 py-2 text-xs">
                  <span className="text-muted">{t.name}</span>
                  <Badge tone={t.requires_approval ? "warn" : "ok"}>
                    {t.requires_approval ? "approval required" : "auto-approved"}
                  </Badge>
                </div>
              ))}
              <div className="flex items-center gap-2 pt-1 text-[11px] text-faint">
                <span>{approvalRequired} require approval</span>
                <span>·</span>
                <span>{autoApproved} auto-approved</span>
              </div>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Security Audit Trail" subtitle={`${auditTrail.length} recent security events`}>
        {auditTrail.length === 0 ? (
          <div className="p-6 text-center text-[11px] text-faint flex flex-col items-center gap-2">
            <ScrollText size={20} className="text-faint/60" />
            No security events recorded yet.
          </div>
        ) : (
          <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
            {auditTrail.slice(0, 30).map((e, i) => (
              <div key={i} className="flex items-start gap-2 rounded-lg border border-border/40 px-3 py-2 text-[11px]">
                <AlertTriangle size={12} className={`shrink-0 mt-0.5 ${e.topic === "tool.denied" ? "text-danger" : e.topic === "mission.failed" ? "text-warn" : "text-faint"}`} />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-muted">{e.topic}</span>
                    <span className="text-faint/60">{e.timestamp}</span>
                  </div>
                  <div className="text-faint truncate">source: {e.source || "—"}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {error && (
        <div className="text-xs text-danger/80 bg-danger/5 rounded-lg px-3 py-2">
          API error: {error}
        </div>
      )}
    </div>
  );
}
