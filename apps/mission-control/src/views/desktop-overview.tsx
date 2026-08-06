"use client";

import { useCallback, useEffect, useState } from "react";
import { safeFixed } from "@/lib/safe";
import { Panel, Badge, Empty } from "@/components/ui/primitives";
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

function KpiCard({ label, value, tone = "default" }: { label: string; value: string | number; tone?: "default" | "ok" | "warn" | "danger" | "accent" }) {
  const toneClass = { default: "text-text", ok: "text-ok", warn: "text-warn", danger: "text-danger", accent: "text-accent" }[tone];
  return (
    <div className="glass rounded-xl px-4 py-3 flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className={`text-2xl font-bold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}

function ProgressBar({ value, label, tone }: { value: number; label: string; tone?: "ok" | "warn" | "danger" | "accent" }) {
  const colorMap: Record<string, string> = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", accent: "bg-accent" };
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

  const activeWorkspace = Array.isArray(state.workspaces) ? state.workspaces.find((w) => w.id === state.active_workspace_id) : undefined;
  const windowsLength = Array.isArray(state.windows) ? state.windows.length : 0;
  const workspacesLength = Array.isArray(state.workspaces) ? state.workspaces.length : 0;

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold">Desktop Overview</h2>
          <Badge tone={statusTone(state.status)}>{state.status}</Badge>
        </div>
        <button onClick={load} className="rounded-lg border border-border/60 px-3 py-1.5 text-xs text-faint transition hover:bg-surface/30">Refresh</button>
      </div>

      {/* ── KPI Stats Row ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 shrink-0">
        <KpiCard label="Status" value={state.status} tone={statusTone(state.status)} />
        <KpiCard label="Uptime" value={formatUptime(state.uptime_seconds)} tone="accent" />
        <KpiCard label="Windows" value={windowsLength} tone="default" />
        <KpiCard label="Workspaces" value={workspacesLength} tone="default" />
      </div>

      {/* ── Two-column content ── */}
      <div className="grid flex-1 gap-3 min-h-0 grid-cols-1 lg:grid-cols-[1fr_1fr]">
        {/* Left: Performance */}
        <Panel title="Performance" subtitle="CPU, Memory & Disk usage">
          {state.performance ? (
            <div className="space-y-4">
              <ProgressBar value={state.performance.cpu_usage_percent} label="CPU" tone={state.performance.cpu_usage_percent > 80 ? "danger" : state.performance.cpu_usage_percent > 60 ? "warn" : "accent"} />
              <ProgressBar value={state.performance.memory_usage_percent} label="Memory" tone={state.performance.memory_usage_percent > 80 ? "danger" : state.performance.memory_usage_percent > 60 ? "warn" : "accent"} />
              <ProgressBar value={state.performance.disk_usage_percent} label="Disk" tone={state.performance.disk_usage_percent > 90 ? "danger" : state.performance.disk_usage_percent > 75 ? "warn" : "accent"} />
              <div className="pt-2 text-xs text-faint">
                {state.performance.process_count > 0 && `${state.performance.process_count} processes`}
                {state.performance.memory_total_mb > 0 && ` · ${safeFixed(state?.performance?.memory_used_mb, 0)} / ${safeFixed(state?.performance?.memory_total_mb, 0)} MB`}
                {state.performance.disk_total_gb > 0 && ` · ${safeFixed(state?.performance?.disk_free_gb, 1)} GB free`}
              </div>
            </div>
          ) : (
            <Empty title="No metrics yet" />
          )}
        </Panel>

        {/* Right: Windows */}
        <Panel title="Windows" subtitle={`${windowsLength} open`}>
          <div className="min-h-0 max-h-[300px] overflow-y-auto overflow-x-hidden no-scrollbar space-y-1.5">
            {windowsLength === 0 ? (
              <Empty title="No windows" hint="Open a window to see it here." />
            ) : (
              (state.windows ?? []).slice(0, 20).map((w) => (
                <div key={w.id} className="flex items-center gap-2 rounded-lg border border-border/40 px-3 py-2">
                  <span className={`h-2 w-2 rounded-full ${w.focused ? "bg-accent" : "bg-surface/60"}`} />
                  <span className="flex-1 truncate text-sm">{w.label}</span>
                  <Badge>{w.state}</Badge>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>

      {/* ── Workspaces row ── */}
      <Panel title="Workspaces" subtitle={`${workspacesLength} total`} className="shrink-0">
        <div className="flex flex-wrap gap-2">
          {(state.workspaces ?? []).map((ws) => (
            <div
              key={ws.id}
              tabIndex={0}
              role="button"
              className={`rounded-lg border px-3 py-2 text-xs transition cursor-pointer ${
                ws.id === state.active_workspace_id
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-border/60 text-muted hover:bg-surface/30"
              }`}
            >
              {ws.name}
              {ws.id === state.active_workspace_id && <span className="ml-1.5 text-[10px] text-accent">(active)</span>}
            </div>
          ))}
          {workspacesLength === 0 && <Empty title="No workspaces" />}
        </div>
      </Panel>

      {/* ── Version info ── */}
      {state.diagnostics && (
        <div className="flex items-center gap-3 text-[10px] text-faint shrink-0">
          <span>Version: {state.diagnostics.app_version}</span>
          <span>·</span>
          <span>Database: {state.database?.path ?? "—"}</span>
          <span>·</span>
          <span>Theme: {state.theme}</span>
          {activeWorkspace && (<><span>·</span><span>Active: {activeWorkspace.name}</span></>)}
        </div>
      )}
    </div>
  );
}
