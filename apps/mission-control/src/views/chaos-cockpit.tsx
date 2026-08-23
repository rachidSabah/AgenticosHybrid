"use client";

import { useState, useEffect, useCallback } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { ShieldAlert, Zap, RefreshCw, RotateCcw, Activity, Terminal } from "lucide-react";

export function ChaosCockpit() {
  const [experiments, setExperiments] = useState<any[]>([]);
  const [canaries, setCanaries] = useState<any[]>([]);
  const [injecting, setInjecting] = useState(false);
  const [selectedFault, setSelectedFault] = useState("kill_agent_worker");

  const loadData = useCallback(async () => {
    try {
      const [exp, can] = await Promise.all([
        api.get<any[]>("/api/chaos/experiments").catch(() => []),
        api.get<any[]>("/api/healing/canary/list").catch(() => []),
      ]);
      if (exp) setExperiments(exp);
      if (can) setCanaries(can);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    void loadData();
    const id = setInterval(loadData, 5000);
    return () => clearInterval(id);
  }, [loadData]);

  const handleInjectFault = async () => {
    setInjecting(true);
    try {
      await api.post("/api/chaos/inject", {
        fault_type: selectedFault,
        target_component: "agent-worker-03",
      });
      await loadData();
    } finally {
      setInjecting(false);
    }
  };

  const handleDeployCanary = async () => {
    await api.post("/api/healing/canary/deploy", {
      incident_id: `INC-LIVE-${Math.floor(Math.random() * 900 + 100)}`,
      title: "Autonomous Exponential Backoff Canary Mitigation",
    });
    await loadData();
  };

  const handleRollbackCanary = async (id: string) => {
    await api.post("/api/healing/canary/rollback", { deployment_id: id });
    await loadData();
  };

  return (
    <div className="flex h-full flex-col bg-background text-text p-4 space-y-4 overflow-auto">
      {/* Top Telemetry Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Stat label="Resilience Score" value="99.4%" tone="ok" />
        <Stat label="Avg Recovery Time" value="42ms" tone="ok" />
        <Stat label="Chaos Experiments" value={experiments.length} />
        <Stat label="Canary Hotfixes" value={canaries.length} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        {/* Chaos Engineering Studio */}
        <Panel title="Autonomous Chaos & Resilience Testing Studio" subtitle="Inject live adversarial faults to verify self-healing isolation">
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <select
                value={selectedFault}
                onChange={(e) => setSelectedFault(e.target.value)}
                className="flex-1 rounded-lg border border-border/60 bg-surface/30 px-3 py-2 text-xs text-text outline-none focus:border-accent"
              >
                <option value="kill_agent_worker">Kill 3 Active Agent Workers</option>
                <option value="inject_network_latency">Inject 2000ms Synthetic Network Latency</option>
                <option value="corrupt_ast_payload">Corrupt Memory AST Payload</option>
                <option value="simulate_provider_outage">Simulate Anthropic Provider 503 Outage</option>
              </select>
              <button
                onClick={handleInjectFault}
                disabled={injecting}
                className="flex items-center gap-1.5 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-500 transition disabled:opacity-50"
              >
                <Zap size={14} className={injecting ? "animate-spin" : ""} />
                {injecting ? "Injecting Fault…" : "Inject Fault"}
              </button>
            </div>

            <div className="space-y-2">
              <div className="text-xs font-semibold text-faint">Fault Experiment Log</div>
              {experiments.length === 0 ? (
                <Empty title="No experiments run yet" hint="Select a fault above and click 'Inject Fault'." />
              ) : (
                experiments.map((exp) => (
                  <div key={exp.experiment_id} className="rounded-xl border border-border/40 bg-surface/15 p-3 text-xs">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-semibold text-accent">{exp.fault_type}</span>
                      <Badge tone="ok">{exp.status} in {exp.recovery_time_ms}ms</Badge>
                    </div>
                    <div className="space-y-1 font-mono text-[10px] text-faint bg-surface/40 p-2 rounded-lg">
                      {exp.logs.map((l: string, idx: number) => (
                        <div key={idx}>{l}</div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </Panel>

        {/* Canary Simulator & Automated Post-Mortem */}
        <Panel title="Autonomous SRE Canary Simulator" subtitle="Ephemeral worktree validation & 1-click canary rollback">
          <div className="space-y-4">
            <button
              onClick={handleDeployCanary}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition"
            >
              <Activity size={14} /> Simulate Autonomous Canary Patch
            </button>

            <div className="space-y-2">
              <div className="text-xs font-semibold text-faint">Canary Deployments</div>
              {canaries.length === 0 ? (
                <Empty title="No canary patches" hint="Click 'Simulate Canary Patch' to validate hotfixes." />
              ) : (
                canaries.map((can) => (
                  <div key={can.deployment_id} className="rounded-xl border border-border/40 bg-surface/15 p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-text">{can.remediation_title}</span>
                      <Badge tone={can.status === "applied" ? "ok" : "warn"}>{can.status}</Badge>
                    </div>
                    <div className="text-[11px] text-faint font-mono whitespace-pre-line bg-surface/40 p-2 rounded-lg">
                      {can.rca_postmortem}
                    </div>
                    {can.status === "applied" && (
                      <button
                        onClick={() => handleRollbackCanary(can.deployment_id)}
                        className="flex items-center gap-1 text-[11px] text-rose-400 hover:text-rose-300 font-semibold"
                      >
                        <RotateCcw size={12} /> 1-Click Canary Rollback
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}