"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { OfflineEvent, BackupResult } from "@/lib/desktop-types";

function offlineTone(state: string): "ok" | "warn" | "danger" | "accent" | "default" {
  if (state === "online") return "ok";
  if (state === "synchronizing") return "accent";
  if (state === "reconnecting") return "warn";
  if (state === "offline") return "danger";
  return "default";
}

export default function DesktopOffline() {
  const [offlineState, setOfflineState] = useState("online");
  const [events, setEvents] = useState<OfflineEvent[]>([]);
  const [backups, setBackups] = useState<BackupResult[]>([]);
  const [restorePoints, setRestorePoints] = useState<{ points: Array<Record<string, unknown>> } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [creatingBackup, setCreatingBackup] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const st = await api.offlineState();
      setOfflineState(st.state);
    } catch { /* ignore */ }
    try {
      const ev = await api.offlineEvents();
      setEvents(ev ?? []);
    } catch { /* ignore */ }
    try {
      const bk = await api.listBackups();
      setBackups(bk ?? []);
    } catch { /* ignore */ }
    try {
      const rp = await api.restorePoints();
      setRestorePoints(rp);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleEnable = async () => {
    try {
      const result = await api.enableOffline();
      setOfflineState(result.state);
    } catch (err) { setError(String(err)); }
  };

  const handleDisable = async () => {
    try {
      const result = await api.disableOffline();
      setOfflineState(result.state);
    } catch (err) { setError(String(err)); }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await api.syncOffline();
      setEvents([]);
      load();
    } catch (err) { setError(String(err)); }
    setSyncing(false);
  };

  const handleCreateBackup = async () => {
    setCreatingBackup(true);
    try {
      const result = await api.createBackup();
      setBackups((prev) => [result, ...prev]);
    } catch (err) { setError(String(err)); }
    setCreatingBackup(false);
  };

  const queuedCount = events.filter((e) => !e.synced).length;

  return (
    <div className="grid h-full grid-cols-12 gap-4 overflow-auto p-4" role="region" aria-label="Offline Mode">
      {error && (
        <div role="alert" className="col-span-12 rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">{error}</div>
      )}

      <div className="col-span-12 flex flex-wrap items-center gap-3" aria-live="polite">
        <Stat label="Offline State" value={offlineState} tone={offlineTone(offlineState)} />
        <Stat label="Queued Events" value={queuedCount} tone={queuedCount > 0 ? "warn" : "ok"} />
        <Stat label="Total Backups" value={backups.length} />
        <div className="ml-auto flex gap-2">
          {offlineState === "online" && (
            <button
              onClick={handleEnable}
              aria-label="Enable Offline"
              className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80"
            >
              Enable Offline
            </button>
          )}
          {offlineState !== "online" && (
            <button
              onClick={handleDisable}
              aria-label="Disable Offline"
              className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
            >
              Disable Offline
            </button>
          )}
          <button
            onClick={handleSync}
            disabled={syncing || queuedCount === 0}
            aria-label="Sync Now"
            className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20 disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync Now"}
          </button>
        </div>
      </div>

      <Panel title="Queued Events" subtitle={`${queuedCount} pending`} className="col-span-6 row-span-2">
        {events.length === 0 ? (
          <Empty title="No queued events" hint="Events will appear here when offline mode queues them." />
        ) : (
          <div className="divide-y divide-border/40">
            <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
              <span className="w-6" />
              <span className="w-28">Type</span>
              <span className="flex-1">Queued At</span>
              <span className="w-20 text-right">Status</span>
            </div>
            {events.map((ev) => (
              <div key={ev.id} className="flex items-center gap-3 px-2 py-2 text-xs">
                <StatusDot status={ev.synced ? "healthy" : ev.error ? "failed" : "pending"} pulse={!ev.synced && !ev.error} />
                <span className="w-28 truncate text-muted">{ev.event_type}</span>
                <span className="flex-1 text-faint">{new Date(ev.queued_at).toLocaleString()}</span>
                <span className="w-20 text-right">
                  <span role="status"><Badge tone={ev.synced ? "ok" : ev.error ? "danger" : "warn"}>
                    {ev.synced ? "Synced" : ev.error ? "Error" : "Pending"}
                  </Badge></span>
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Backups" subtitle={`${backups.length} backup(s)`} className="col-span-6 row-span-2">
        <div className="space-y-3">
          <button
            onClick={handleCreateBackup}
            disabled={creatingBackup}
            aria-label="Create Backup"
            className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
          >
            {creatingBackup ? "Creating…" : "Create Backup"}
          </button>

          {backups.length > 0 && (
            <div className="divide-y divide-border/40">
              <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
                <span className="w-8" />
                <span className="flex-1">Path</span>
                <span className="w-20">Size</span>
                <span className="w-20 text-right">Scope</span>
              </div>
              {backups.map((bk, i) => (
                <div key={bk.backup_path || i} className="flex items-center gap-3 px-2 py-2 text-xs">
                  <StatusDot status={bk.success ? "healthy" : "failed"} />
                  <span className="flex-1 truncate text-muted">{bk.backup_path}</span>
                  <span className="w-20 font-mono text-faint">
                    {(bk.size_bytes / 1024 / 1024).toFixed(1)} MB
                  </span>
                  <span className="w-20 text-right text-faint">{bk.scope}</span>
                </div>
              ))}
            </div>
          )}
          {backups.length === 0 && <Empty title="No backups yet" hint="Create a backup to protect your data." />}
        </div>
      </Panel>

      <Panel title="Restore Points" subtitle={restorePoints ? `${restorePoints.points.length} available` : "Loading…"} className="col-span-12 row-span-1">
        {restorePoints && restorePoints.points.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {restorePoints.points.map((rp, i) => (
              <div key={i} className="rounded-lg border border-border/60 px-3 py-2 text-xs text-muted">
                {JSON.stringify(rp)}
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No restore points" hint="Restore points are created automatically before updates." />
        )}
      </Panel>
    </div>
  );
}
