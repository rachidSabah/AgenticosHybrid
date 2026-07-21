"use client";

import { useState, useCallback } from "react";
import { Panel, StatusDot } from "@/components/ui/primitives";
import { api } from "@/lib/api";

type ActionId =
  | "integrity"
  | "diagnostics"
  | "memory"
  | "threads"
  | "cleanup"
  | "repair"
  | "recovery"
  | "resources";

interface ActionState {
  running: boolean;
  result: string | null;
  error: string | null;
}

const initialState: Record<ActionId, ActionState> = {
  integrity:    { running: false, result: null, error: null },
  diagnostics:  { running: false, result: null, error: null },
  memory:       { running: false, result: null, error: null },
  threads:      { running: false, result: null, error: null },
  cleanup:      { running: false, result: null, error: null },
  repair:       { running: false, result: null, error: null },
  recovery:     { running: false, result: null, error: null },
  resources:    { running: false, result: null, error: null },
};

type SystemControlProps = {
  /** Optional className for embedding */
  className?: string;
  /** If true, only show the hardest actions (repair, recovery) */
  minimal?: boolean;
};

export function SystemControl({ className, minimal }: SystemControlProps) {
  const [states, setStates] = useState<Record<ActionId, ActionState>>(initialState);

  const run = useCallback(async (id: ActionId, fn: () => Promise<unknown>, label: string) => {
    setStates((prev) => ({ ...prev, [id]: { running: true, result: null, error: null } }));
    try {
      const res = await fn();
      const text = typeof res === "object" && res !== null
        ? JSON.stringify(res).slice(0, 120)
        : String(res);
      setStates((prev) => ({
        ...prev,
        [id]: { running: false, result: `${label}: ${text}`, error: null },
      }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setStates((prev) => ({
        ...prev,
        [id]: { running: false, result: null, error: msg },
      }));
    }
  }, []);

  const actions: { id: ActionId; label: string; fn: () => Promise<unknown> }[] = [
    { id: "integrity",   label: "Integrity Check", fn: () => api.integrityCheck() },
    { id: "diagnostics", label: "Run Diagnostics", fn: () => api.runDiagnostics() },
    { id: "memory",      label: "Memory Leak Check", fn: () => api.checkMemory() },
    { id: "threads",     label: "Thread Check",     fn: () => api.checkThreads() },
    { id: "cleanup",     label: "Cleanup Resources",fn: () => api.cleanupResources() },
    { id: "repair",      label: "Repair System",    fn: () => api.repairSystem() },
    { id: "resources",   label: "Resource Usage",   fn: () => api.resourceUsage() },
  ];

  const recoveryActions: { id: ActionId; label: string; fn: () => Promise<unknown> }[] = [
    { id: "recovery", label: "Toggle Recovery", fn: async () => {
      const status = await api.recoveryStatus();
      return status.in_recovery ? api.exitRecovery() : api.enterRecovery();
    }},
  ];

  const visible = minimal ? actions.slice(5) : actions;

  // Derive summary from results/errors
  const anyRunning = [...visible, ...recoveryActions].some((a) => states[a.id].running);
  const okCount = [...visible, ...recoveryActions].filter((a) => states[a.id].result && !states[a.id].error).length;
  const errCount = [...visible, ...recoveryActions].filter((a) => states[a.id].error).length;

  return (
    <Panel
      title="System Control"
      subtitle={
        anyRunning
          ? "Running…"
          : errCount
            ? `${okCount} ok · ${errCount} error`
            : "Hardening & diagnostics actions"
      }
      className={className}
    >
      <div className="flex flex-col gap-2">
        {visible.map((a) => (
          <ActionButton
            key={a.id}
            label={a.label}
            state={states[a.id]}
            onRun={() => run(a.id, a.fn, a.label)}
          />
        ))}

        {!minimal && (
          <>
            <hr className="my-1 border-border/40" />
            <div className="text-[10px] uppercase tracking-wide text-faint mb-1">
              Recovery
            </div>
            {recoveryActions.map((a) => (
              <ActionButton
                key={a.id}
                label={a.label}
                state={states[a.id]}
                onRun={() => run(a.id, a.fn, a.label)}
              />
            ))}
          </>
        )}
      </div>
    </Panel>
  );
}

// ── Single action row ──
function ActionButton({
  label,
  state,
  onRun,
}: {
  label: string;
  state: ActionState;
  onRun: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        onClick={onRun}
        disabled={state.running}
        className="shrink-0 rounded-lg border border-border/50 bg-surface/40 px-3 py-1.5 text-xs font-medium text-text hover:bg-surface/70 disabled:opacity-40 transition-colors"
      >
        {state.running ? "…" : label}
      </button>

      {state.result && (
        <span className="flex items-center gap-1.5 truncate text-[11px] text-ok">
          <StatusDot status="healthy" />
          <span className="truncate">{state.result}</span>
        </span>
      )}
      {state.error && (
        <span className="flex items-center gap-1.5 truncate text-[11px] text-danger">
          <StatusDot status="failed" />
          <span className="truncate">{state.error}</span>
        </span>
      )}
      {!state.result && !state.error && state.running && (
        <span className="text-[11px] text-faint animate-pulse">Running…</span>
      )}
    </div>
  );
}
