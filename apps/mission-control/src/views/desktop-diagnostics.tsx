"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Stat, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import {
  Activity, ShieldCheck, Wrench, RefreshCw, Zap, Search, AlertTriangle,
  CheckCircle2, Terminal, Cpu, Database, Network, Server, Play, Check, X
} from "lucide-react";
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

interface DiagnosticProgress {
  phase: string;
  progress: number;
  active: boolean;
}

interface LogEntry {
  id: string;
  timestamp: string;
  level: "PASS" | "WARNING" | "ERROR" | "AUTO FIX" | "INFO";
  module: string;
  message: string;
}

interface RealErrorItem {
  id: string;
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  category: string;
  description: string;
  rootCause: string;
  module: string;
  suggestedFix: string;
}

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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live Diagnostic Engine state
  const [scanProgress, setScanProgress] = useState<DiagnosticProgress>({ phase: "Idle", progress: 0, active: false });
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: "1", timestamp: new Date().toLocaleTimeString(), level: "INFO", module: "Diagnostic Engine", message: "Desktop Health Center ready" },
  ]);
  const [activeErrors, setActiveErrors] = useState<RealErrorItem[]>([]);

  // ── Live WebSocket state from store ──
  const connected = useStore((s) => s.connected);
  const events = useStore((s) => s.events);
  const providers = useStore((s) => s.providers);

  const addLog = useCallback((level: LogEntry["level"], module: string, message: string) => {
    setLogs((prev) => [
      { id: `log-${Date.now()}-${Math.random()}`, timestamp: new Date().toLocaleTimeString(), level, module, message },
      ...prev.slice(0, 150),
    ]);
  }, []);

  const load = useCallback(async () => {
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
  }, []);

  useEffect(() => { load(); }, [load, connected]);

  // ── Mode 1: Quick Health Check ──
  const runQuickCheck = async () => {
    setScanProgress({ phase: "Quick Health Check", progress: 10, active: true });
    addLog("INFO", "Quick Check", "Requesting startup hardening validation from backend...");
    try {
      const res = await api.validateStartup();
      const checks = Array.isArray(res?.checks) ? res.checks : [];
      const passed = checks.filter((c) => c?.status === "ok" || c?.ok === true).length;
      addLog(
        passed === checks.length && checks.length > 0 ? "PASS" : "WARNING",
        "Startup Hardening",
        `Backend validated ${checks.length} startup check(s), ${passed} passed.`,
      );
    } catch (err) {
      addLog("ERROR", "Quick Check", `Startup validation failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    setScanProgress({ phase: "Quick Check Complete", progress: 100, active: false });
  };

  // ── Mode 2: Surface Scan ──
  const runSurfaceScan = async () => {
    setScanProgress({ phase: "Surface Scan", progress: 20, active: true });
    addLog("INFO", "Surface Scan", "Requesting surface provider discovery from backend...");
    try {
      const res = await api.bindingDiscover("surface");
      const found = typeof res?.total_found === "number" ? res.total_found : 0;
      addLog(
        found > 0 ? "PASS" : "INFO",
        "Surface Scan",
        `Backend discovery returned ${found} provider(s).`,
      );
    } catch (err) {
      addLog("ERROR", "Surface Scan", `Discovery failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    await load();
    setScanProgress({ phase: "Surface Scan Complete", progress: 100, active: false });
  };

  // ── Mode 3: Deep Scan ──
  const runDeepScan = async () => {
    setScanProgress({ phase: "Deep Scan", progress: 20, active: true });
    addLog("INFO", "Deep Scan Engine", "Requesting deep discovery + integrity + self-diagnostics from backend...");
    try {
      const deep = await api.bindingDeepScan();
      addLog("PASS", "Deep Scan", `Backend deep scan returned ${typeof deep?.total_found === "number" ? deep.total_found : 0} provider(s) across ${typeof deep?.sources_scanned === "number" ? deep.sources_scanned : 0} sources.`);
    } catch (err) {
      addLog("ERROR", "Deep Scan", `Deep discovery failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    try {
      const integ = await api.integrityCheck();
      setIntegrity(integ);
      addLog("INFO", "Integrity", `Integrity check returned status=${integ?.status ?? "n/a"}.`);
    } catch (err) {
      addLog("ERROR", "Integrity", `Integrity check failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    try {
      const diag = await api.runDiagnostics();
      setSelfReport(diag);
      addLog("INFO", "Self-Diagnostics", `Backend diagnostics report received (status=${diag?.status ?? "n/a"}).`);
    } catch (err) {
      addLog("ERROR", "Self-Diagnostics", `Diagnostics failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    setScanProgress({ phase: "Deep Scan Complete", progress: 100, active: false });
  };

  // ── Auto-Repair Engine ──
  const runRepairAll = async () => {
    setScanProgress({ phase: "Auto-Repairing", progress: 30, active: true });
    addLog("AUTO FIX", "Repair Engine", "Requesting backend repair + cleanup...");
    try {
      const res = await api.repairSystem();
      addLog(
        res?.success ? "PASS" : "WARNING",
        "Repair Engine",
        `Backend repair ${res?.success ? "completed" : "did not report success"} — repaired: ${res?.repaired?.length ?? 0}, failed: ${res?.failed?.length ?? 0}${res?.error ? ` (${res.error})` : ""}.`,
      );
    } catch (err) {
      addLog("ERROR", "Repair Engine", `Repair failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    try {
      const res = await api.cleanupResources();
      addLog("INFO", "Cleanup", `Backend cleanup returned space_freed_mb=${res?.space_freed_mb ?? "n/a"}, items_cleaned=${res?.items_cleaned ?? "n/a"}.`);
    } catch (err) {
      addLog("ERROR", "Cleanup", `Cleanup failed: ${err instanceof Error ? err.message : String(err)}`);
    }
    await load();
    setScanProgress({ phase: "Auto-Repair Complete", progress: 100, active: false });
  };

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      {/* ── Top Header Toolbar & Mode Triggers ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-border/50 bg-surface/30 px-5 py-3 backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <Activity size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">DESKTOP DIAGNOSTICS & SELF-HEALING</h1>
            <p className="text-[11px] text-faint">Real-time system health, pipeline validation, and auto-repair engine</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={runQuickCheck}
            disabled={scanProgress.active}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition disabled:opacity-50"
          >
            <Zap size={13} />
            Quick Check
          </button>

          <button
            onClick={runSurfaceScan}
            disabled={scanProgress.active}
            className="flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-500/10 px-3 py-1.5 text-xs font-semibold text-purple-300 hover:bg-purple-500/20 transition disabled:opacity-50"
          >
            <Search size={13} />
            Surface Scan
          </button>

          <button
            onClick={runDeepScan}
            disabled={scanProgress.active}
            className="flex items-center gap-1.5 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-1.5 text-xs font-semibold text-blue-300 hover:bg-blue-500/20 transition disabled:opacity-50"
          >
            <ShieldCheck size={13} />
            Deep Scan
          </button>

          <button
            onClick={runRepairAll}
            disabled={scanProgress.active}
            className="flex items-center gap-1.5 rounded-lg border border-ok/40 bg-ok/15 px-3.5 py-1.5 text-xs font-semibold text-ok hover:bg-ok/25 transition disabled:opacity-50 shadow-glow"
          >
            <Wrench size={13} />
            Repair All
          </button>
        </div>
      </div>

      {/* ── Live Progress Indicator ── */}
      {scanProgress.active && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-xl p-3 border border-accent/40 space-y-1.5">
          <div className="flex justify-between text-xs font-semibold">
            <span className="text-accent flex items-center gap-2">
              <RefreshCw size={12} className="animate-spin" /> {scanProgress.phase}
            </span>
            <span className="font-mono text-text">{scanProgress.progress}%</span>
          </div>
          <div className="h-2 w-full rounded-full bg-surface/50 overflow-hidden">
            <div className="h-full bg-accent transition-all duration-300 ease-out" style={{ width: `${scanProgress.progress}%` }} />
          </div>
        </motion.div>
      )}

      {/* ── System Resource Usage Overview (real backend values, "—" when unavailable) ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat
          label="CPU Load"
          value={resources?.cpu_percent != null ? `${resources.cpu_percent.toFixed(1)}%` : "—"}
          tone={resources?.cpu_percent != null ? "accent" : "default"}
        />
        <Stat
          label="Memory Usage"
          value={resources?.memory_mb != null ? `${resources.memory_mb.toFixed(0)} MB` : "—"}
          tone="default"
        />
        <Stat
          label="Active Threads"
          value={resources?.thread_count != null ? String(resources.thread_count) : "—"}
          tone="default"
        />
        <Stat
          label="EventBus Channel"
          value={connected ? "Connected" : "Local Bus"}
          tone={connected ? "ok" : "default"}
        />
      </div>

      {/* ── 2 Columns: Live Log Stream & Actionable Error Panel ── */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* Left Column: Live VS Code Style Log Stream (7 cols) */}
        <Panel title="Live Diagnostic Stream" subtitle="Real-time log telemetry" className="col-span-12 lg:col-span-7 flex flex-col min-h-0" contentClassName="flex-1 overflow-y-auto font-mono text-[11px] bg-black/60 rounded-xl p-3 space-y-1.5 text-green-400">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-2 leading-relaxed">
              <span className="text-faint shrink-0">{log.timestamp}</span>
              <span className={`shrink-0 font-bold ${
                log.level === "PASS" ? "text-ok" : log.level === "AUTO FIX" ? "text-accent" : log.level === "WARNING" ? "text-warn" : log.level === "ERROR" ? "text-danger" : "text-muted"
              }`}>
                [{log.level}]
              </span>
              <span className="text-purple-300 font-semibold shrink-0">[{log.module}]</span>
              <span className="text-text">{log.message}</span>
            </div>
          ))}
        </Panel>

        {/* Right Column: Actionable Error & Healing Console (5 cols) */}
        <Panel title="Health & Self-Healing Console" subtitle={`${activeErrors.length} unresolved issues`} className="col-span-12 lg:col-span-5 flex flex-col min-h-0" contentClassName="space-y-3 p-3 overflow-y-auto">
          {activeErrors.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-8 text-center glass rounded-xl space-y-2">
              <CheckCircle2 size={32} className="text-ok" />
              <div className="text-xs font-semibold text-text">
                {selfReport == null && integrity == null
                  ? "No diagnostics run yet"
                  : (selfReport?.status ?? integrity?.status) === "healthy"
                    ? "Backend reports healthy"
                    : `Backend reports "${selfReport?.status ?? integrity?.status ?? "unknown"}"`}
              </div>
              <div className="text-[11px] text-faint max-w-xs">
                {selfReport == null && integrity == null
                  ? "Run Quick Check, Surface Scan, or Deep Scan to assess system health."
                  : "No unresolved issues are recorded in this session."}
              </div>
            </div>
          ) : (
            activeErrors.map((err) => (
              <div key={err.id} className="rounded-xl border border-danger/40 bg-danger/10 p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-danger">{err.category}</span>
                  <Badge tone="danger">{err.severity}</Badge>
                </div>
                <div className="text-text font-medium">{err.description}</div>
                <div className="text-[11px] text-faint font-mono bg-black/40 p-2 rounded">
                  Root Cause: {err.rootCause}
                </div>
                <button
                  onClick={runRepairAll}
                  className="w-full rounded-lg bg-ok/20 border border-ok/40 py-1.5 text-xs font-semibold text-ok hover:bg-ok/30 transition"
                >
                  Auto-Fix Issue
                </button>
              </div>
            ))
          )}
        </Panel>
      </div>
    </div>
  );
}
