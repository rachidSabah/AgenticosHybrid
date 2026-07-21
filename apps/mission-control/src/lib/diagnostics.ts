"use client";

// Bridge to Tauri diagnostics commands.
// These let the frontend surface embedded-backend startup failures directly.

export interface BackendStatus {
  connected: boolean;
  details: string;
  log_path: string;
  startup_log_path: string;
}

export interface DiagnosticReport {
  startup_log: string;
  backend_log: string;
  status: BackendStatus;
}

interface TauriInvoke {
  (cmd: string, args?: Record<string, unknown>): Promise<unknown>;
}

function getInvoke(): TauriInvoke | null {
  try {
    // Tauri v2 injects invoke at runtime (detect via __TAURI__ or __TAURI_INTERNALS__)
    const win = window as unknown as Record<string, unknown>;
    if (typeof window !== "undefined" && win.__TAURI_INTERNALS__) {
      const internals = win.__TAURI_INTERNALS__ as Record<string, unknown>;
      if (typeof internals.invoke === "function") return internals.invoke as TauriInvoke;
    }
    // Fallback: Tauri v1 compat via window.__TAURI__
    if (typeof window !== "undefined" && win.__TAURI__) {
      const tauri = win.__TAURI__ as Record<string, unknown>;
      const core = tauri.core as Record<string, unknown> | undefined;
      if (core && typeof core.invoke === "function") return core.invoke as TauriInvoke;
    }
  } catch {
    // Not running inside Tauri
  }
  return null;
}

export async function getBackendStatus(): Promise<BackendStatus | null> {
  const invoke = getInvoke();
  if (!invoke) return null;
  try {
    return (await invoke("get_backend_status")) as BackendStatus;
  } catch {
    return null;
  }
}

export async function getStartupDiagnostics(): Promise<DiagnosticReport | null> {
  const invoke = getInvoke();
  if (!invoke) return null;
  try {
    return (await invoke("get_startup_diagnostics")) as DiagnosticReport;
  } catch {
    return null;
  }
}

export function parseBackendLog(report: DiagnosticReport): string[] {
  const lines: string[] = [];

  // Parse startup log for [AgenticOS-Startup] markers
  for (const log of [report.startup_log, report.backend_log]) {
    for (const line of log.split("\n")) {
      if (line.includes("[AgentICOS-Startup]") || line.includes("AgenticOS-Startup") || line.includes("[AgenticOS-Startup]") || line.includes("✗") || line.includes("✓") || line.includes("⚠")) {
        lines.push(line.trim());
      }
    }
  }

  return lines;
}

export function getStartupStage(statusLog: string): { stage: string; error: string | null } {
  if (statusLog.includes("DESKTOP_READY") || statusLog.includes("Backend health check passed")) {
    return { stage: "ready", error: null };
  }
  if (statusLog.includes("✗") || statusLog.includes("FAILED") || statusLog.includes("exited prematurely")) {
    // Find the last error
    const lines = statusLog.split("\n").filter((l) => l.includes("✗") || l.includes("FAILED"));
    return { stage: "failed", error: lines[lines.length - 1] || "Unknown startup error" };
  }
  if (statusLog.includes("timed out")) {
    return { stage: "timeout", error: "Backend health check timed out" };
  }
  if (statusLog.includes("port 8000 is not yet open")) {
    return { stage: "starting", error: null };
  }
  return { stage: "unknown", error: null };
}
