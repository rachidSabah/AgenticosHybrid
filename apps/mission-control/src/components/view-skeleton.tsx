"use client";

import { useState, useEffect } from "react";
import { Panel, Empty, Stat } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { getStartupDiagnostics, parseBackendLog, getStartupStage } from "@/lib/diagnostics";

interface Props {
  title: string;
  subtitle?: string;
}

export function ViewSkeleton({ title, subtitle }: Props) {
  const connected = useStore((s) => s.connected);
  const connect = useStore((s) => s.connect);
  const [delayed, setDelayed] = useState(false);
  const [backendLog, setBackendLog] = useState<string[]>([]);
  const [startupError, setStartupError] = useState<string | null>(null);
  const [diagnosticsLoaded, setDiagnosticsLoaded] = useState(false);

  useEffect(() => {
    if (connected) {
      setDelayed(false);
      return;
    }
    const timer = setTimeout(() => {
      if (!connected) {
        setDelayed(true);
        // Load diagnostics from Tauri backend
        loadDiagnostics();
      }
    }, 6000);
    return () => clearTimeout(timer);
  }, [connected]);

  async function loadDiagnostics() {
    try {
      const report = await getStartupDiagnostics();
      if (report) {
        const lines = parseBackendLog(report);
        setBackendLog(lines);
        const { stage, error } = getStartupStage(report.startup_log + "\n" + report.backend_log);
        if (stage === "failed" || stage === "timeout") {
          setStartupError(error || "Backend failed to start");
        }
        setDiagnosticsLoaded(true);
      }
    } catch {
      // Not in Tauri environment
    }
  }

  return (
    <Panel title={title} subtitle={subtitle} className="h-full">
      <div className="h-full flex flex-col items-center justify-center space-y-4 p-6">
        {!delayed ? (
          <Empty
            title={connected ? "Loading view..." : "Connecting to AgenticOS Backend..."}
            hint={connected ? "Processing live EventBus envelopes" : "Initializing local EventBus & Runtime Discovery"}
          />
        ) : (
          <div className="flex flex-col items-center space-y-4 max-w-md text-center animate-fade-in">
            <div className={`rounded-full p-3 ${startupError ? "bg-danger/10 text-danger" : "bg-warn/10 text-warn"}`}>
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-text">
                {startupError ? "Backend Startup Failed" : "Backend Connection Delay"}
              </h3>
              <p className="text-xs text-muted">
                {startupError
                  ? `The embedded Desktop Runtime backend encountered an error: ${startupError}`
                  : "The embedded Desktop Runtime backend (127.0.0.1:8000) is taking longer than expected to start up or respond."}
              </p>
            </div>

            {backendLog.length > 0 && (
              <div className="w-full max-w-lg mt-2">
                <div className="text-[10px] font-mono text-left text-faint bg-surface/30 rounded-lg p-3 max-h-32 overflow-y-auto border border-border/40">
                  {backendLog.map((line, i) => {
                    const isError = line.includes("✗") || line.includes("FAILED");
                    const isOk = line.includes("✓");
                    return (
                      <div key={i} className={`${isError ? "text-danger" : isOk ? "text-ok" : "text-muted"} truncate`}>
                        {line}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => connect()}
                className="rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent/80 transition"
              >
                Retry Connection
              </button>
              {diagnosticsLoaded && (
                <button
                  onClick={loadDiagnostics}
                  className="rounded-lg border border-border/60 px-4 py-1.5 text-xs font-medium text-muted hover:bg-surface/20 transition"
                >
                  Refresh Diagnostics
                </button>
              )}
              <a
                href="#desktop-diagnostics"
                onClick={(e) => {
                  e.preventDefault();
                  window.dispatchEvent(new CustomEvent("nav-view", { detail: "desktop-diagnostics" }));
                }}
                className="rounded-lg border border-border/60 px-4 py-1.5 text-xs font-medium text-muted hover:bg-surface/20 transition"
              >
                Open Diagnostics
              </a>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}

export function ViewSkeletonMinimal({ title }: { title: string }) {
  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="animate-pulse space-y-3 w-3/4">
        <div className="h-4 bg-surface/50 rounded w-1/3" />
        <div className="h-4 bg-surface/50 rounded w-1/4" />
        <div className="h-32 bg-surface/50 rounded-xl" />
        <div className="h-32 bg-surface/50 rounded-xl" />
        <div className="h-32 bg-surface/50 rounded-xl" />
      </div>
    </div>
  );
}