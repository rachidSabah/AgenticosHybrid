"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type {
  DesktopDiagnosticsInfo,
  IntegrityCheckResult,
  SelfDiagnosticsReport,
  MemoryLeakReport,
  ThreadReport,
  ResourceUsageSummary,
  CleanupResult,
  RepairResult,
} from "@/lib/desktop-types";

export default function DesktopDiagnostics() {
  const [diagnostics, setDiagnostics] = useState<DesktopDiagnosticsInfo | null>(null);
  const [integrity, setIntegrity] = useState<IntegrityCheckResult | null>(null);
  const [selfReport, setSelfReport] = useState<SelfDiagnosticsReport | null>(null);
  const [memoryReport, setMemoryReport] = useState<MemoryLeakReport | null>(null);
  const [threadReport, setThreadReport] = useState<ThreadReport | null>(null);
  const [resources, setResources] = useState<ResourceUsageSummary | null>(null);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [repairResult, setRepairResult] = useState<RepairResult | null>(null);
  const [recoveryMode, setRecoveryMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [d, res] = await Promise.all([
        api.diagnostics().catch(() => null),
        api.resourceUsage().catch(() => null),
      ]);
      setDiagnostics(d);
      setResources(res);
      try {
        const rec = await api.recoveryStatus();
        setRecoveryMode(rec.in_recovery);
      } catch { /* ignore */ }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleIntegrity = async () => {
    try {
      const result = await api.integrityCheck();
      setIntegrity(result);
    } catch (err) { setError(String(err)); }
  };

  const handleDiagnostics = async () => {
    try {
      const result = await api.runDiagnostics();
      setSelfReport(result);
    } catch (err) { setError(String(err)); }
  };

  const handleMemory = async () => {
    try {
      const result = await api.checkMemory();
      setMemoryReport(result);
    } catch (err) { setError(String(err)); }
  };

  const handleThreads = async () => {
    try {
      const result = await api.checkThreads();
      setThreadReport(result);
    } catch (err) { setError(String(err)); }
  };

  const handleCleanup = async () => {
    try {
      const result = await api.cleanupResources();
      setCleanupResult(result);
    } catch (err) { setError(String(err)); }
  };

  const handleRepair = async () => {
    try {
      const result = await api.repairSystem();
      setRepairResult(result);
    } catch (err) { setError(String(err)); }
  };

  const toggleRecovery = async () => {
    try {
      if (recoveryMode) {
        await api.exitRecovery();
      } else {
        await api.enterRecovery();
      }
      setRecoveryMode(!recoveryMode);
    } catch (err) { setError(String(err)); }
  };

  if (loading) return <div role="status" aria-live="polite" className="flex items-center justify-center h-full text-xs text-faint">Loading…</div>;

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4" role="region" aria-label="Desktop Diagnostics">
      {error && (
        <div role="alert" className="col-span-12 rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">{error}</div>
      )}

      <div className="col-span-12 flex flex-wrap items-center gap-3" aria-live="polite">
        <Stat label="System Info" value={diagnostics ? `${diagnostics.os_name} ${diagnostics.os_version}` : "—"} />
        {diagnostics && (
          <>
            <Stat label="Python" value={diagnostics.python_version} />
            <Stat label="Hostname" value={diagnostics.hostname} />
            <Stat label="Display" value={`${diagnostics.display_resolution} (${diagnostics.display_count})`} />
          </>
        )}
        {resources && (
          <>
            <Stat label="CPU" value={`${resources.cpu_percent.toFixed(1)}%`} tone={resources.cpu_percent > 80 ? "danger" : resources.cpu_percent > 60 ? "warn" : "default"} />
            <Stat label="Memory" value={`${resources.memory_mb.toFixed(0)} MB`} />
            <Stat label="Threads" value={resources.thread_count} />
          </>
        )}
      </div>

      <Panel title="Integrity Check" subtitle={integrity ? `Last: ${new Date(integrity.checked_at).toLocaleTimeString()}` : "Not yet checked"} className="col-span-6 row-span-2">
        <div className="space-y-3">
          <button
            onClick={handleIntegrity}
            aria-label="Run Integrity Check"
            className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80"
          >
            Run Integrity Check
          </button>
          {integrity && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span role="status"><Badge tone={integrity.status === "passed" ? "ok" : "danger"}>{integrity.status}</Badge></span>
                <span className="text-[11px] text-faint">{integrity.duration_seconds.toFixed(1)}s</span>
              </div>
              {integrity.checks.length > 0 && (
                <div className="divide-y divide-border/30">
                  {integrity.checks.map((c, i) => (
                    <div key={i} className="flex items-center gap-2 py-1.5 text-xs">
                      <StatusDot status={c.status === "passed" ? "healthy" : "failed"} />
                      <span className="flex-1 text-muted">{c.name}</span>
                      <Badge tone={c.status === "passed" ? "ok" : "danger"}>{c.status}</Badge>
                    </div>
                  ))}
                </div>
              )}
              {integrity.warnings.length > 0 && (
                <div className="text-[11px] text-warn">Warnings: {integrity.warnings.join("; ")}</div>
              )}
              {integrity.errors.length > 0 && (
                <div className="text-[11px] text-danger">Errors: {integrity.errors.join("; ")}</div>
              )}
            </div>
          )}
          {!integrity && <Empty title="Press the button to run" />}
        </div>
      </Panel>

      <Panel title="Self-Diagnostics" subtitle="Services health report" className="col-span-6 row-span-2">
        <div className="space-y-3">
          <button
            onClick={handleDiagnostics}
            aria-label="Run Diagnostics"
            className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80"
          >
            Run Diagnostics
          </button>
          {selfReport && (
            <div className="space-y-2">
              <span role="status"><Badge tone={selfReport.status === "healthy" ? "ok" : selfReport.status === "degraded" ? "warn" : "danger"}>{selfReport.status}</Badge></span>
              <div className="divide-y divide-border/30">
                {selfReport.services.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 py-1.5 text-xs">
                    <StatusDot status={s.status === "healthy" ? "healthy" : s.status === "degraded" ? "degraded" : "failed"} />
                    <span className="flex-1 text-muted">{s.name}</span>
                    <Badge tone={s.status === "healthy" ? "ok" : s.status === "degraded" ? "warn" : "danger"}>{s.status}</Badge>
                  </div>
                ))}
              </div>
              {selfReport.recommendations.length > 0 && (
                <div className="rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-[11px] text-accent">
                  {selfReport.recommendations.map((r, i) => (
                    <div key={i}>{r}</div>
                  ))}
                </div>
              )}
              {selfReport.errors.length > 0 && (
                <div className="text-[11px] text-danger">{selfReport.errors.join("; ")}</div>
              )}
            </div>
          )}
          {!selfReport && <Empty title="Press the button to run" />}
        </div>
      </Panel>

      <Panel title="Memory Leak Detection" subtitle={memoryReport ? `${memoryReport.current_memory_mb.toFixed(0)} MB current` : "Not checked"} className="col-span-4 row-span-2">
        <div className="space-y-3">
          <button
            onClick={handleMemory}
            aria-label="Check Memory"
            className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
          >
            Check Memory
          </button>
          {memoryReport && (
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <StatusDot status={memoryReport.detected ? "failed" : "healthy"} pulse={memoryReport.detected} />
                <span className={memoryReport.detected ? "text-danger" : "text-ok"}>{memoryReport.detected ? "Leak detected" : "No leak detected"}</span>
              </div>
              <div className="text-faint">Baseline: {memoryReport.baseline_memory_mb.toFixed(0)} MB</div>
              <div className="text-faint">Growth: {memoryReport.growth_rate_mb_per_minute.toFixed(1)} MB/min</div>
              {memoryReport.recommendations.length > 0 && (
                <div className="mt-2 text-[11px] text-warn">{memoryReport.recommendations.join("; ")}</div>
              )}
            </div>
          )}
          {!memoryReport && <Empty title="Press to check" />}
        </div>
      </Panel>

      <Panel title="Thread Monitoring" subtitle={threadReport ? `${threadReport.total_threads} total threads` : "Not checked"} className="col-span-4 row-span-2">
        <div className="space-y-3">
          <button
            onClick={handleThreads}
            aria-label="Check Threads"
            className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
          >
            Check Threads
          </button>
          {threadReport && (
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <StatusDot status={threadReport.threshold_exceeded ? "failed" : "healthy"} pulse={threadReport.threshold_exceeded} />
                <span className={threadReport.threshold_exceeded ? "text-danger" : "text-ok"}>{threadReport.threshold_exceeded ? "Threshold exceeded" : "Normal"}</span>
              </div>
              <div className="text-faint">Active: {threadReport.active_threads} / Total: {threadReport.total_threads}</div>
              <div className="text-faint">Threshold: {threadReport.threshold}</div>
            </div>
          )}
          {!threadReport && <Empty title="Press to check" />}
        </div>
      </Panel>

      <Panel title="Resource Usage" subtitle="Current utilization" className="col-span-4 row-span-2" aria-live="polite">
        {resources ? (
          <div className="space-y-2 text-xs">
            <div className="flex justify-between"><span className="text-faint">CPU</span><span className="font-mono">{resources.cpu_percent.toFixed(1)}%</span></div>
            <div className="flex justify-between"><span className="text-faint">Memory</span><span className="font-mono">{resources.memory_mb.toFixed(0)} MB</span></div>
            <div className="flex justify-between"><span className="text-faint">Threads</span><span className="font-mono">{resources.thread_count}</span></div>
            <div className="flex justify-between"><span className="text-faint">Open Handles</span><span className="font-mono">{resources.open_handles}</span></div>
            <div className="flex justify-between"><span className="text-faint">Network Connections</span><span className="font-mono">{resources.network_connections}</span></div>
            <div className="flex justify-between"><span className="text-faint">Disk I/O</span><span className="font-mono">{(resources.disk_io_bytes_per_sec / 1024).toFixed(1)} KB/s</span></div>
          </div>
        ) : (
          <Empty title="No resource data" />
        )}
      </Panel>

      <Panel title="Cleanup & Repair" className="col-span-6 row-span-1">
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleCleanup}
            aria-label="Cleanup Resources"
            className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
          >
            Cleanup Resources
          </button>
          <button
            onClick={handleRepair}
            aria-label="Repair System"
            className="rounded-lg border border-warn/40 px-4 py-2 text-xs font-medium text-warn transition hover:bg-warn/10"
          >
            Repair System
          </button>
          {cleanupResult && (
            <div className="w-full text-xs text-ok">{cleanupResult.items_cleaned} items cleaned ({cleanupResult.duration_seconds.toFixed(1)}s)</div>
          )}
          {repairResult && (
            <div className="w-full text-xs">
              <span className="text-ok">{repairResult.repaired.length} repaired</span>
              {repairResult.failed.length > 0 && <span className="ml-2 text-danger">{repairResult.failed.length} failed</span>}
            </div>
          )}
        </div>
      </Panel>

      <Panel title="Recovery Mode" subtitle={recoveryMode ? "Currently active" : "Inactive"} className="col-span-6 row-span-1">
        <div className="flex items-center gap-4">
          <StatusDot status={recoveryMode ? "running" : "idle"} pulse={recoveryMode} />
          <span className="text-xs text-muted">{recoveryMode ? "Recovery mode is enabled" : "Recovery mode is disabled"}</span>
          <button
            onClick={toggleRecovery}
            aria-label={recoveryMode ? "Exit Recovery" : "Enter Recovery"}
            className={`ml-auto rounded-lg px-4 py-2 text-xs font-medium transition ${
              recoveryMode
                ? "border border-border/60 text-muted hover:bg-surface/20"
                : "bg-warn/12 text-warn hover:bg-warn/20"
            }`}
          >
            {recoveryMode ? "Exit Recovery" : "Enter Recovery"}
          </button>
        </div>
      </Panel>
    </div>
  );
}
