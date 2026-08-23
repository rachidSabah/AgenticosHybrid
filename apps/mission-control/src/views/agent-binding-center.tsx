"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import {
  Search, RefreshCw, Wrench, ShieldCheck, Link2, Unlink, Settings, Server,
  Terminal, Folder, Cpu, HardDrive, CheckCircle2, XCircle, AlertTriangle,
  Play, Plus, Upload, Download, Activity, Check, X, ShieldAlert,
  ChevronRight, Layers, FileCode, CornerDownRight, Radio, Filter, Zap,
} from "lucide-react";

// ── Types for Binding Center ──

export interface BoundAgent {
  id: string;
  name: string;
  vendor: string;
  version: string;
  executable_path: string;
  install_source: string; // PATH, Windows Registry, Cargo, npm, uv, etc.
  status: "healthy" | "degraded" | "unbound" | "validating" | "repairing";
  capabilities: string[];
  models: string[];
  arguments: string[];
  env: Record<string, string>;
  working_dir?: string;
  cpu_limit?: number;
  memory_limit_mb?: number;
  gpu_preference?: string;
  startup_mode?: "automatic" | "manual" | "on_demand";
  timeout_seconds?: number;
  last_validation?: string;
  last_heartbeat?: string;
  user_labels?: string[];
  notes?: string;
  logs?: string[];
  /** Last real result from POST /binding/validate — never fabricated. */
  validation?: {
    healthy: boolean;
    kind: string;
    streaming: boolean;
    tools: boolean;
    at: string;
  };
}

export interface ValidationCheck {
  id: string;
  label: string;
  command: string;
  status: "pending" | "running" | "passed" | "failed";
  output?: string;
  exit_code?: number;
  latency_ms?: number;
}

export interface DiscoveryLogEntry {
  id: string;
  timestamp: string;
  source: string;
  type: "info" | "warning" | "error" | "success";
  message: string;
}

export function AgentBindingCenter() {
  // Agents list is populated EXCLUSIVELY from live backend data
  // (/api/local-agents + /api/brains via the store). No hardcoded defaults.
  const [agents, setAgents] = useState<BoundAgent[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [scanningMode, setScanningMode] = useState<"idle" | "surface" | "deep">("idle");
  const [showManualWizard, setShowManualWizard] = useState(false);
  const [manualName, setManualName] = useState("");
  const [manualPath, setManualPath] = useState("");
  const [manualError, setManualError] = useState("");
  const [manualBinding, setManualBinding] = useState(false);
  const [logs, setLogs] = useState<DiscoveryLogEntry[]>([
    { id: "l1", timestamp: new Date().toLocaleTimeString(), source: "Discovery Engine", type: "info", message: "AI Agent Binding Center initialized" },
  ]);
  const [activeTab, setActiveTab] = useState<"details" | "validation" | "terminal" | "config">("details");

  const connected = useStore((s) => s.connected);
  const storeProviders = useStore((s) => s.providers);

  // Fetch live agents from the backend and transform them into BoundAgent
  // entries. This is the ONLY source of the binding list — no hardcoded
  // defaults. Re-runs when the store's provider map changes (which reflects
  // live discovery events via WebSocket).
  const refreshAgents = useCallback(async () => {
    try {
      const [localRes, brainsRes] = await Promise.allSettled([
        api.get<Array<Record<string, unknown>>>("/api/local-agents"),
        api.get<Array<Record<string, unknown>>>("/api/brains"),
      ]);
      const localAgents = localRes.status === "fulfilled" && Array.isArray(localRes.value) ? localRes.value : [];
      const brains = brainsRes.status === "fulfilled" && Array.isArray(brainsRes.value) ? brainsRes.value : [];

      const merged: BoundAgent[] = [];
      const seen = new Set<string>();
      // Dedupe by normalized display name so that the same logical agent
      // is never shown more than once (e.g. a path-discovered CLI and a
      // cli:/cloud-registered brain resolve to the same tool). When a name
      // collides we keep the entry with the better status and more info.
      const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
      const byName = new Map<string, BoundAgent>();
      const rank = (s: string) =>
        s === "healthy" ? 2 : s === "validating" || s === "repairing" ? 1 : 0;
      const upsert = (agent: BoundAgent) => {
        const key = norm(agent.name);
        const existing = byName.get(key);
        if (!existing) {
          byName.set(key, agent);
          merged.push(agent);
          return;
        }
        // Keep the richer / healthier entry; fold capabilities/models from both.
        const keep = rank(agent.status) >= rank(existing.status) ? agent : existing;
        const drop = keep === agent ? existing : agent;
        keep.capabilities = Array.from(new Set([...keep.capabilities, ...drop.capabilities]));
        keep.models = Array.from(new Set([...keep.models, ...drop.models]));
        keep.version = keep.version || drop.version;
        keep.executable_path = keep.executable_path || drop.executable_path;
        byName.set(key, keep);
        const idx = merged.indexOf(drop);
        if (idx !== -1) merged[idx] = keep;
      };

      // Local agents → BoundAgent
      for (const a of localAgents) {
        const id = String(a.id ?? a.name ?? "");
        if (!id || seen.has(id)) continue;
        seen.add(id);
        upsert({
          id,
          name: String(a.name ?? id),
          vendor: String(a.tool_type ?? "unknown"),
          version: String(a.version ?? ""),
          executable_path: String(a.executable_path ?? ""),
          install_source: String(a.tool_type ?? ""),
          status: a.status === "running" || a.status === "idle" || a.status === "busy" ? "healthy" : "degraded",
          capabilities: Array.isArray(a.capabilities) ? a.capabilities.map(String) : [],
          models: Array.isArray(a.supported_models) ? a.supported_models.map(String) : [],
          arguments: [],
          env: {},
          startup_mode: "automatic",
          timeout_seconds: 60,
          last_validation: String(a.last_seen ?? ""),
          last_heartbeat: String(a.last_seen ?? ""),
          user_labels: [],
          logs: [],
        });
      }

      // Brains not already in the list → BoundAgent.
      // Skip terminal/non-discoverable brains (e.g. status "removed") so that
      // uninstalled agents don't linger in the binding list as false "degraded"
      // rows. Only present brains the system can actually bind to.
      const BRAIN_EXCLUDE = new Set(["removed", "shutdown", "failed"]);
      for (const b of brains) {
        const bstatus = String(b.status ?? "");
        if (BRAIN_EXCLUDE.has(bstatus.toLowerCase())) continue;
        const id = String(b.id ?? b.display_name ?? "");
        if (!id || seen.has(id)) continue;
        seen.add(id);
        upsert({
          id,
          name: String(b.display_name ?? id),
          vendor: String(b.vendor ?? "unknown"),
          version: String(b.version ?? ""),
          executable_path: "",
          install_source: "brain_registry",
          status: Number(b.health) >= 50 ? "healthy" : "degraded",
          capabilities: Array.isArray(b.capabilities) ? b.capabilities.map(String) : [],
          models: Array.isArray(b.supported_models) ? b.supported_models.map(String) : [],
          arguments: [],
          env: {},
          startup_mode: "automatic",
          timeout_seconds: 60,
          last_validation: String(b.last_seen ?? ""),
          last_heartbeat: String(b.last_seen ?? ""),
          user_labels: [],
          logs: [],
        });
      }

      setAgents(merged);
      if (merged.length > 0) {
        setSelectedId((prev) => (merged.find((m) => m.id === prev) ? prev : merged[0].id));
      } else {
        setSelectedId("");
      }
    } catch {
      // Keep the list empty on error — no fake fallback.
    }
  }, []);

  // Initial fetch + periodic refresh + refresh on store provider changes
  useEffect(() => {
    refreshAgents();
    const interval = setInterval(refreshAgents, 15_000);
    return () => clearInterval(interval);
  }, [refreshAgents, storeProviders]);

  const selectedAgent = useMemo(() => {
    return agents.find((a) => a.id === selectedId) || agents[0];
  }, [agents, selectedId]);

  const addLog = useCallback((source: string, type: DiscoveryLogEntry["type"], message: string) => {
    setLogs((prev) => [
      { id: `log-${Date.now()}-${Math.random()}`, timestamp: new Date().toLocaleTimeString(), source, type, message },
      ...prev.slice(0, 100),
    ]);
  }, []);

  // ── Scans ──
  const runScan = async (mode: "surface" | "deep") => {
    setScanningMode(mode);
    addLog("Scan Engine", "info", `Starting ${mode.toUpperCase()} scan across system PATH, Registry, and Package Managers...`);
    try {
      const res =
        mode === "surface" ? await api.bindingDiscover("surface") : await api.bindingDeepScan();
      try { await api.post("/api/brains/rescan"); } catch { /* ignore if offline */ }
      try { await useStore.getState().hydrate(); } catch { /* ignore */ }
      await refreshAgents();
      setScanningMode("idle");
      const found = typeof res?.total_found === "number" ? res.total_found : 0;
      addLog(
        "Scan Engine",
        found > 0 ? "success" : "info",
        `${mode === "deep" ? "Deep" : "Surface"} scan complete: ${found} agent(s) registered on host.`,
      );
    } catch (err) {
      try { await useStore.getState().hydrate(); } catch { /* ignore */ }
      setScanningMode("idle");
      addLog(
        "Scan Engine",
        "error",
        `${mode.toUpperCase()} scan failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  // ── Actions ──
  const handleValidate = async (agent: BoundAgent) => {
    const id = agent.id;
    // Resolve the backend provider id: local agents expose tool_type
    // (e.g. "claude-code"); brains expose vendor (e.g. "claude_code").
    // The backend normalises these to the registered provider name.
    const providerId = agent.vendor || id;
    addLog("Validation Subsystem", "info", `Executing validation suite for provider [${providerId}]...`);
    setAgents((prev) => prev.map((a) => (a.id === id ? { ...a, status: "validating" } : a)));
    try {
      const res = await api.bindingValidate(providerId);
      const healthy = Boolean(res?.healthy);
      const bound = res?.bound !== false; // undefined (older responses) → treat as bound
      setAgents((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                // A discovered local tool that was never bound as a provider
                // (git, node, python, removed brains) reports bound:false —
                // keep its existing status instead of flipping to "degraded".
                status: bound ? (healthy ? "healthy" : "degraded") : a.status,
                last_validation: new Date().toISOString(),
                validation: {
                  healthy,
                  kind: String(res?.details?.kind ?? "unknown"),
                  streaming: Boolean(res?.details?.streaming),
                  tools: Boolean(res?.details?.tools),
                  at: new Date().toISOString(),
                },
                logs: [
                  ...(a.logs || []),
                  bound
                    ? `[VALIDATION ${healthy ? "PASS" : "FAIL"}] ${new Date().toLocaleTimeString()} -- kind=${res?.details?.kind ?? "unknown"} streaming=${res?.details?.streaming} tools=${res?.details?.tools}`
                    : `[VALIDATION SKIP] ${new Date().toLocaleTimeString()} -- ${providerId} is not a bound provider`,
                ],
              }
            : a
        )
      );
      addLog(
        "Validation Subsystem",
        healthy ? "success" : "warning",
        `Provider [${providerId}] validation ${healthy ? "passed" : "failed"} (streaming=${res?.details?.streaming}, tools=${res?.details?.tools}).`,
      );
    } catch (err) {
      setAgents((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                status: "degraded",
                logs: [...(a.logs || []), `[VALIDATION ERROR] ${new Date().toLocaleTimeString()} -- ${err instanceof Error ? err.message : String(err)}`],
              }
            : a
        )
      );
      addLog(
        "Validation Subsystem",
        "error",
        `Provider [${providerId}] validation failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleRepair = async (agent: BoundAgent) => {
    const id = agent.id;
    const providerId = agent.vendor || id;
    addLog("Repair Engine", "info", `Initiating auto-repair sequence for provider [${providerId}]...`);
    setAgents((prev) => prev.map((a) => (a.id === id ? { ...a, status: "repairing" } : a)));
    try {
      const res = await api.bindingRepair(providerId);
      const repaired = Boolean(res?.repaired);
      setAgents((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                status: repaired ? "healthy" : "degraded",
                logs: [
                  ...(a.logs || []),
                  `[REPAIR ${repaired ? "SUCCESS" : "FAILED"}] ${new Date().toLocaleTimeString()} -- ${res?.action_taken ?? "no action"}`,
                ],
              }
            : a
        )
      );
      addLog(
        "Repair Engine",
        repaired ? "success" : "warning",
        `Provider [${providerId}] ${repaired ? "repaired" : "not repaired"}: ${res?.action_taken ?? "no action taken"}`,
      );
    } catch (err) {
      setAgents((prev) =>
        prev.map((a) =>
          a.id === id
            ? {
                ...a,
                status: "degraded",
                logs: [...(a.logs || []), `[REPAIR ERROR] ${new Date().toLocaleTimeString()} -- ${err instanceof Error ? err.message : String(err)}`],
              }
            : a
        )
      );
      addLog(
        "Repair Engine",
        "error",
        `Provider [${providerId}] repair failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleUnbind = async (agent: BoundAgent) => {
    const id = agent.id;
    const providerId = agent.vendor || id;
    addLog("Binding Center", "warning", `Unbinding agent [${providerId}] from Mission Control (executable file untouched).`);
    try {
      const res = await api.bindingUnbind(providerId);
      if (res?.unbound) {
        setAgents((prev) => prev.filter((a) => a.id !== id));
        if (selectedId === id) setSelectedId(agents[0]?.id || "");
        addLog("Binding Center", "success", `Agent [${id}] unbound.`);
      } else {
        addLog("Binding Center", "warning", `Unbind reported success but no unbound flag for [${id}].`);
      }
    } catch (err) {
      addLog("Binding Center", "error", `Unbind failed for [${id}]: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleRebindAll = () => {
    addLog("Binding Center", "info", "Re-validating all registered agents...");
    agents.forEach((a) => handleValidate(a));
  };

  const handleManualBind = async () => {
    const provider = manualName.trim();
    const executable = manualPath.trim();
    if (!provider || !executable) {
      setManualError("Both an agent name and an executable path are required.");
      return;
    }
    setManualError("");
    setManualBinding(true);
    addLog("Manual Binder", "info", `Binding [${provider}] -> ${executable}...`);
    try {
      const res = await api.bindingManual({ provider, executable });
      if (res?.bound) {
        addLog("Manual Binder", "success", `Provider [${provider}] bound successfully by the backend.`);
        setShowManualWizard(false);
        setManualName("");
        setManualPath("");
        await refreshAgents();
      } else {
        setManualError("Backend did not confirm the bind (no bound flag).");
        addLog("Manual Binder", "warning", `Backend did not confirm bind for [${provider}].`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setManualError(msg);
      addLog("Manual Binder", "error", `Binding [${provider}] failed: ${msg}`);
    } finally {
      setManualBinding(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background text-text">
      {/* ── Top Toolbar ── */}
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-4 py-2.5 backdrop-blur-xl">
        <div className="flex items-center gap-2">
          <Server size={18} className="text-accent" />
          <h1 className="text-sm font-semibold tracking-wide">AI AGENT BINDING CENTER</h1>
          <Badge tone={connected ? "ok" : "warn"}>{connected ? "Runtime Live" : "Standalone"}</Badge>
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto">
          <button
            onClick={() => runScan("surface")}
            disabled={scanningMode !== "idle"}
            className="flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/15 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/25 transition disabled:opacity-50"
          >
            <RefreshCw size={13} className={scanningMode === "surface" ? "animate-spin" : ""} />
            Surface Scan
          </button>

          <button
            onClick={() => runScan("deep")}
            disabled={scanningMode !== "idle"}
            className="flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-500/15 px-3 py-1.5 text-xs font-medium text-purple-300 hover:bg-purple-500/25 transition disabled:opacity-50"
          >
            <Zap size={13} className={scanningMode === "deep" ? "animate-pulse" : ""} />
            Deep Scan
          </button>

          <button
            onClick={() => setShowManualWizard(true)}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-surface/40 px-3 py-1.5 text-xs font-medium hover:bg-surface/80 transition"
          >
            <Plus size={13} />
            Manual Bind
          </button>

          <div className="h-4 w-px bg-border/40 mx-1" />

          <button
            onClick={handleRebindAll}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-surface/40 px-2.5 py-1.5 text-xs font-medium text-muted hover:text-text hover:bg-surface/80 transition"
            title="Validate All"
          >
            <ShieldCheck size={13} />
            Validate All
          </button>

          <button
            onClick={() => {
              agents.forEach((a) => handleRepair(a));
            }}
            className="flex items-center gap-1.5 rounded-lg border border-border/60 bg-surface/40 px-2.5 py-1.5 text-xs font-medium text-muted hover:text-text hover:bg-surface/80 transition"
            title="Repair All"
          >
            <Wrench size={13} />
            Repair All
          </button>
        </div>
      </div>

      {/* ── Main Layout: 3 Columns ── */}
      <div className="grid flex-1 grid-cols-1 md:grid-cols-12 gap-3 overflow-hidden p-3 min-h-0">
        {/* Left Column: Discovered & Bound Agents (4 Cols) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-3 h-full min-h-0">
          <Panel
            title="Discovered & Bound Agents"
            subtitle={`${agents.length} agents active`}
            className="flex-1 flex flex-col min-h-0"
            contentClassName="flex-1 overflow-y-auto space-y-2 p-2"
          >
            {agents.map((agent) => {
              const isSelected = agent.id === selectedId;
              return (
                <div
                  key={agent.id}
                  onClick={() => setSelectedId(agent.id)}
                  className={`group relative flex cursor-pointer flex-col gap-1.5 rounded-xl border p-3 transition-all ${
                    isSelected
                      ? "border-accent/60 bg-accent/10 shadow-glow"
                      : "border-border/40 bg-surface/20 hover:border-border hover:bg-surface/30"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <StatusDot
                        status={
                          agent.status === "healthy"
                            ? "healthy"
                            : agent.status === "validating"
                            ? "running"
                            : agent.status === "repairing"
                            ? "planned"
                            : "failed"
                        }
                        pulse={agent.status === "healthy" || agent.status === "validating"}
                      />
                      <span className="text-xs font-semibold">{agent.name}</span>
                    </div>
                    <Badge tone={agent.status === "healthy" ? "ok" : "warn"}>
                      {agent.status}
                    </Badge>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-faint font-mono">
                    <span className="truncate max-w-[200px]">{agent.executable_path}</span>
                    <span>v{agent.version}</span>
                  </div>

                  <div className="mt-1 flex flex-wrap gap-1">
                    {agent.capabilities.slice(0, 3).map((cap) => (
                      <span key={cap} className="rounded bg-surface/50 px-1.5 py-0.5 text-[9px] text-muted">
                        {cap}
                      </span>
                    ))}
                    {agent.capabilities.length > 3 && (
                      <span className="rounded bg-surface/50 px-1 py-0.5 text-[9px] text-faint">
                        +{agent.capabilities.length - 3}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </Panel>
        </div>

        {/* Center & Right Column: Binding Details & Live Diagnostics (8 Cols) */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-3 h-full min-h-0">
          {selectedAgent ? (
            <div className="flex flex-1 flex-col gap-3 min-h-0">
              {/* Agent Detail Panel Header */}
              <Panel
                title={selectedAgent.name}
                subtitle={`${selectedAgent.vendor} · ${selectedAgent.install_source} · Bound to Mission Control`}
                actions={
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleValidate(selectedAgent)}
                      className="flex items-center gap-1 rounded-lg border border-ok/40 bg-ok/10 px-2.5 py-1 text-xs font-medium text-ok hover:bg-ok/20 transition"
                    >
                      <ShieldCheck size={12} />
                      Validate
                    </button>
                    <button
                      onClick={() => handleRepair(selectedAgent)}
                      className="flex items-center gap-1 rounded-lg border border-warn/40 bg-warn/10 px-2.5 py-1 text-xs font-medium text-warn hover:bg-warn/20 transition"
                    >
                      <Wrench size={12} />
                      Repair
                    </button>
                    <button
                      onClick={() => handleUnbind(selectedAgent)}
                      className="flex items-center gap-1 rounded-lg border border-danger/40 bg-danger/10 px-2.5 py-1 text-xs font-medium text-danger hover:bg-danger/20 transition"
                    >
                      <Unlink size={12} />
                      Unbind
                    </button>
                  </div>
                }
                className="shrink-0"
              >
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  <div>
                    <span className="text-[10px] text-faint block">Executable Path</span>
                    <span className="font-mono text-muted truncate block">{selectedAgent.executable_path}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-faint block">Install Source</span>
                    <span className="text-muted block">{selectedAgent.install_source}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-faint block">Startup Mode</span>
                    <span className="capitalize text-accent block">{selectedAgent.startup_mode}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-faint block">Last Validation</span>
                    <span className="text-muted block">{new Date(selectedAgent.last_validation || Date.now()).toLocaleTimeString()}</span>
                  </div>
                </div>
              </Panel>

              {/* Sub-tabs bar */}
              <div className="flex items-center gap-1 border-b border-border/40 pb-1">
                {[
                  { id: "details", label: "Binding Config", icon: Settings },
                  { id: "validation", label: "Validation Results", icon: ShieldCheck },
                  { id: "terminal", label: "Agent Output & Logs", icon: Terminal },
                ].map((t) => {
                  const Icon = t.icon;
                  const isActive = activeTab === t.id;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setActiveTab(t.id as any)}
                      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                        isActive
                          ? "bg-accent/20 text-accent border border-accent/30"
                          : "text-faint hover:text-text hover:bg-surface/30"
                      }`}
                    >
                      <Icon size={13} />
                      {t.label}
                    </button>
                  );
                })}
              </div>

              {/* Sub-tab content */}
              <div className="flex-1 overflow-y-auto min-h-0 glass rounded-xl p-4">
                {activeTab === "details" && (
                  <div className="space-y-4 text-xs">
                    <div>
                      <h3 className="font-semibold text-text mb-1">Supported Capabilities</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedAgent.capabilities.map((c) => (
                          <span key={c} className="rounded-lg border border-border/50 bg-surface/30 px-2.5 py-1 text-[11px] font-medium text-accent">
                            {c}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div>
                      <h3 className="font-semibold text-text mb-1">Available Models</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedAgent.models.map((m) => (
                          <span key={m} className="rounded-lg border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-[11px] font-mono text-purple-300">
                            {m}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <h3 className="font-semibold text-text mb-1">Environment Variables</h3>
                        <div className="rounded-lg bg-surface/40 p-2.5 font-mono text-[11px] space-y-1">
                          {Object.keys(selectedAgent.env).length === 0 ? (
                            <span className="text-faint">(None configured)</span>
                          ) : (
                            Object.entries(selectedAgent.env).map(([k, v]) => (
                              <div key={k} className="truncate">
                                <span className="text-accent">{k}</span>=<span className="text-muted">{v}</span>
                              </div>
                            ))
                          )}
                        </div>
                      </div>

                      <div>
                        <h3 className="font-semibold text-text mb-1">Default Arguments</h3>
                        <div className="rounded-lg bg-surface/40 p-2.5 font-mono text-[11px]">
                          {selectedAgent.arguments.length === 0 ? (
                            <span className="text-faint">(None)</span>
                          ) : (
                            selectedAgent.arguments.join(" ")
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === "validation" && (
                  <div className="space-y-3 text-xs">
                    <h3 className="font-semibold text-text">Provider Capability Report</h3>
                    {selectedAgent.validation ? (
                      <div className="space-y-2">
                        <div className="flex items-center justify-between rounded-xl border border-border/30 bg-surface/20 px-3 py-2">
                          <div className="flex items-center gap-2">
                            {selectedAgent.validation.healthy ? (
                              <CheckCircle2 size={14} className="text-ok" />
                            ) : (
                              <XCircle size={14} className="text-danger" />
                            )}
                            <div>
                              <span className="font-medium text-text">Provider Health</span>
                              <span className="block text-[10px] text-faint">
                                Reported by POST /binding/validate at {new Date(selectedAgent.validation.at).toLocaleTimeString()}
                              </span>
                            </div>
                          </div>
                          <span className={`font-mono text-[10px] ${selectedAgent.validation.healthy ? "text-ok" : "text-danger"}`}>
                            {selectedAgent.validation.healthy ? "healthy" : "degraded"}
                          </span>
                        </div>
                        {[
                          { label: "Provider Kind", value: selectedAgent.validation.kind },
                          { label: "Streaming Support", value: selectedAgent.validation.streaming ? "yes" : "no" },
                          { label: "Tool Support", value: selectedAgent.validation.tools ? "yes" : "no" },
                        ].map((row) => (
                          <div key={row.label} className="flex items-center justify-between rounded-xl border border-border/30 bg-surface/20 px-3 py-2">
                            <span className="font-medium text-text">{row.label}</span>
                            <span className="font-mono text-[10px] text-muted">{row.value}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-xl border border-border/30 bg-surface/20 px-3 py-3 text-[11px] text-faint">
                        No validation has run yet. Click <span className="text-accent">Validate</span> on this agent to fetch a real capability report from the backend.
                      </div>
                    )}
                  </div>
                )}

                {activeTab === "terminal" && (
                  <div className="h-full flex flex-col font-mono text-[11px] bg-black/60 rounded-lg p-3 text-green-400 overflow-y-auto">
                    {(selectedAgent.logs || []).map((l, i) => (
                      <div key={i} className="py-0.5">{l}</div>
                    ))}
                    {(selectedAgent.logs || []).length === 0 && (
                      <div className="text-faint mt-2">No output yet — run Validate or Repair to populate real logs.</div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <Empty title="No agent selected" hint="Select an agent from the left panel." />
          )}
        </div>
      </div>

      {/* ── Bottom Discovery Log & Event Output ── */}
      <div className="h-32 border-t border-border/40 bg-surface/20 p-2 overflow-y-auto font-mono text-[11px]">
        <div className="flex items-center justify-between border-b border-border/30 pb-1 mb-1 text-[10px] text-faint">
          <span className="flex items-center gap-1 font-sans font-semibold">
            <Activity size={12} className="text-accent" /> DISCOVERY & BINDING SYSTEM LOGS
          </span>
          <span>{logs.length} events logged</span>
        </div>
        <div className="space-y-1">
          {logs.map((log) => (
            <div key={log.id} className="flex items-start gap-2">
              <span className="text-faint shrink-0">{log.timestamp}</span>
              <span className={`shrink-0 font-bold ${
                log.type === "success" ? "text-ok" : log.type === "warning" ? "text-warn" : log.type === "error" ? "text-danger" : "text-accent"
              }`}>
                [{log.source}]
              </span>
              <span className="text-muted">{log.message}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Manual Bind Wizard Modal ── */}
      <AnimatePresence>
        {showManualWizard && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-md p-4"
          >
            <motion.div
              initial={{ scale: 0.95 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.95 }}
              className="w-full max-w-lg glass rounded-2xl p-5 border border-border/60 shadow-2xl space-y-4"
            >
              <div className="flex items-center justify-between border-b border-border/40 pb-3">
                <div className="flex items-center gap-2">
                  <Plus size={18} className="text-accent" />
                  <h2 className="text-sm font-semibold">Manual Agent Binding Wizard</h2>
                </div>
                <button onClick={() => setShowManualWizard(false)} className="text-faint hover:text-text">
                  <X size={16} />
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="text-faint block mb-1">Agent Name (provider id)</label>
                  <input
                    type="text"
                    value={manualName}
                    onChange={(e) => setManualName(e.target.value)}
                    placeholder="e.g. custom_coder"
                    className="w-full rounded-lg border border-border/60 bg-surface/40 px-3 py-2 outline-none focus:border-accent"
                  />
                </div>
                <div>
                  <label className="text-faint block mb-1">Executable Path</label>
                  <input
                    type="text"
                    value={manualPath}
                    onChange={(e) => setManualPath(e.target.value)}
                    placeholder="e.g. C:\Users\User\AppData\Local\Programs\OpenCode\opencode.exe"
                    className="w-full rounded-lg border border-border/60 bg-surface/40 px-3 py-2 outline-none focus:border-accent font-mono text-[11px]"
                  />
                </div>

                <div className="rounded-xl border border-border/30 bg-surface/20 p-3 text-[11px] text-faint">
                  Mission Control registers this provider with the backend via POST /binding/manual. The executable path is validated by the backend before binding.
                </div>
                {manualError && (
                  <div className="rounded-xl border border-danger/40 bg-danger/10 p-2.5 text-[11px] text-danger">
                    {manualError}
                  </div>
                )}
              </div>

              <div className="flex gap-2 pt-2 border-t border-border/40">
                <button
                  onClick={handleManualBind}
                  disabled={manualBinding}
                  className="flex-1 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/80 transition disabled:opacity-50"
                >
                  {manualBinding ? "Binding..." : "Validate & Bind Agent"}
                </button>
                <button
                  onClick={() => { setShowManualWizard(false); setManualError(""); }}
                  className="rounded-xl border border-border/60 px-4 py-2 text-xs font-medium text-muted hover:bg-surface"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
