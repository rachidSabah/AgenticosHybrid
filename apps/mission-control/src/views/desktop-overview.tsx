"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { DesktopRuntimeState } from "@/lib/desktop-types";

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const parts: string[] = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  parts.push(`${s}s`);
  return parts.join(" ");
}

function statusTone(status: string): "ok" | "warn" | "danger" | "default" {
  if (status === "running") return "ok";
  if (status === "stopped") return "warn";
  if (status === "error") return "danger";
  return "default";
}

function ProgressBar({ value, label, tone }: { value: number; label: string; tone?: "ok" | "warn" | "danger" | "accent" }) {
  const colorMap: Record<string, string> = {
    ok: "bg-ok",
    warn: "bg-warn",
    danger: "bg-danger",
    accent: "bg-accent",
  };
  const barColor = colorMap[tone ?? "accent"] ?? "bg-accent";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-faint">{label}</span>
        <span className="font-mono tabular-nums text-muted">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-surface/50">
        <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  );
}

export default function DesktopOverview() {
  const [state, setState] = useState<DesktopRuntimeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.desktopState();
      setState(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center h-full text-xs text-faint">Loading…</div>;
  if (error) return <div className="flex items-center justify-center h-full text-xs text-danger">{error}</div>;
  if (!state) return <div className="flex items-center justify-center h-full text-xs text-faint">No data</div>;

  const activeWorkspace = state.workspaces.find((w) => w.id === state.active_workspace_id);

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4">
      <div className="col-span-12 flex flex-wrap items-start gap-3">
        <Stat label="Desktop Status" value={state.status} tone={statusTone(state.status)} />
        <Stat label="Uptime" value={formatUptime(state.uptime_seconds)} />
        <Stat label="Windows" value={state.windows.length} />
        <Stat label="Workspaces" value={state.workspaces.length} />
        {state.diagnostics && (
          <Stat label="Version" value={state.diagnostics.app_version} />
        )}
        {activeWorkspace && (
          <Stat label="Active Workspace" value={activeWorkspace.name} />
        )}
        <button
          onClick={load}
          className="ml-auto rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
        >
          Refresh
        </button>
      </div>

      <Panel title="Performance" subtitle="CPU, Memory & Disk usage" className="col-span-6 row-span-2">
        {state.performance ? (
          <div className="space-y-4">
            <ProgressBar value={state.performance.cpu_usage_percent} label="CPU" tone={state.performance.cpu_usage_percent > 80 ? "danger" : state.performance.cpu_usage_percent > 60 ? "warn" : "accent"} />
            <ProgressBar value={state.performance.memory_usage_percent} label="Memory" tone={state.performance.memory_usage_percent > 80 ? "danger" : state.performance.memory_usage_percent > 60 ? "warn" : "accent"} />
            <ProgressBar value={state.performance.disk_usage_percent} label="Disk" tone={state.performance.disk_usage_percent > 90 ? "danger" : state.performance.disk_usage_percent > 75 ? "warn" : "accent"} />
            {state.performance.process_count > 0 && (
              <div className="pt-2 text-xs text-faint">
                {state.performance.process_count} processes &middot; {state.performance.memory_total_mb > 0 && `${(state.performance.memory_used_mb).toFixed(0)} / ${(state.performance.memory_total_mb).toFixed(0)} MB`}
                {state.performance.disk_total_gb > 0 && state.performance.memory_total_mb > 0 && " &middot; "}
                {state.performance.disk_total_gb > 0 && `${state.performance.disk_free_gb.toFixed(1)} GB free`}
              </div>
            )}
          </div>
        ) : (
          <Empty title="No metrics yet" />
        )}
      </Panel>

      <Panel title="Windows" subtitle={`${state.windows.length} open`} className="col-span-6 row-span-2">
        <div className="space-y-1.5">
          {state.windows.length === 0 ? (
            <Empty title="No windows" hint="Open a window to see it here." />
          ) : (
            state.windows.slice(0, 20).map((w) => (
              <div key={w.id} className="flex items-center gap-2 rounded-lg border border-border/40 px-3 py-2">
                <span className={`h-2 w-2 rounded-full ${w.focused ? "bg-accent" : "bg-surface/60"}`} />
                <span className="flex-1 truncate text-sm">{w.label}</span>
                <Badge>{w.state}</Badge>
              </div>
            ))
          )}
        </div>
      </Panel>

      <Panel title="Workspaces" subtitle={`${state.workspaces.length} total`} className="col-span-12 row-span-1">
        <div className="flex flex-wrap gap-2">
          {state.workspaces.map((ws) => (
            <div
              key={ws.id}
              className={`rounded-lg border px-3 py-2 text-xs ${ws.id === state.active_workspace_id ? "border-accent bg-accent/10 text-accent" : "border-border/60 text-muted"}`}
            >
              {ws.name}
              {ws.id === state.active_workspace_id && <span className="ml-1.5 text-[10px] text-accent">(active)</span>}
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
