"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { RefreshCw, Download, HardDrive } from "lucide-react";

// Shape mirrors the backend BackupResult.to_dict() payload — only real fields.
type BackupRow = {
  success?: boolean;
  backup_path?: string;
  size_bytes?: number;
  scope?: string;
  started_at?: string;
  completed_at?: string | null;
  duration_seconds?: number;
  file_count?: number;
  error?: string | null;
};

const formatAge = (iso?: string): string => {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};

const formatSize = (bytes?: number): string => {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes <= 0) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export function DisasterRecovery() {
  const [backups, setBackups] = useState<BackupRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadBackups = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listBackups();
      setBackups(Array.isArray(res) ? (res as BackupRow[]) : []);
      setError(null);
    } catch {
      setBackups([]);
      setError("Failed to load backups from backend");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBackups();
  }, [loadBackups]);

  const handleCreateBackup = async () => {
    setCreating(true);
    try {
      await api.createBackup();
      await loadBackups();
      setError(null);
    } catch {
      setError("Backup creation failed: backend request error");
    } finally {
      setCreating(false);
    }
  };

  const latestBackup = backups.reduce<BackupRow | null>((acc, b) => {
    const t = b.started_at ? new Date(b.started_at).getTime() : 0;
    if (!t) return acc;
    const accT = acc?.started_at ? new Date(acc.started_at).getTime() : 0;
    return !acc || t > accT ? b : acc;
  }, null);

  return (
    <div className="flex h-full flex-col overflow-y-auto bg-background text-text p-4 space-y-4">
      <div className="flex items-center justify-between border-b border-border/40 bg-surface/30 px-5 py-3 rounded-2xl backdrop-blur-xl">
        <div className="flex items-center gap-3">
          <RefreshCw size={20} className="text-accent animate-pulse" />
          <div>
            <h1 className="text-sm font-bold tracking-wider uppercase">BACKUP &amp; DISASTER RECOVERY CENTER</h1>
            <p className="text-[11px] text-faint">One-click backups, restore snapshots, versioning &amp; automated rollback engine</p>
          </div>
        </div>
        <button
          onClick={handleCreateBackup}
          disabled={creating}
          className="flex items-center gap-1.5 rounded-xl bg-accent px-4 py-2 text-xs font-semibold text-white hover:bg-accent/80 transition disabled:opacity-50"
        >
          <Download size={14} />
          {creating ? "Creating Snapshot…" : "One-Click Backup"}
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Total Snapshots" value={backups.length} tone="accent" />
        <Stat label="Latest Backup" value={latestBackup ? formatAge(latestBackup.started_at) : "—"} />
        <Stat label="Auto-Backup Status" value="—" />
        <Stat label="Disaster Recovery" value="—" />
      </div>

      {error && (
        <div className="rounded-xl border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
          {error}
        </div>
      )}

      <Panel title="System Snapshots & Backups" subtitle="Full system restore & configuration rollback points">
        {loading ? (
          <div className="py-8 text-center text-xs text-faint">Loading backups…</div>
        ) : backups.length === 0 ? (
          <div className="py-8 text-center text-xs text-faint">No backups recorded</div>
        ) : (
          <div className="space-y-2">
            {backups.map((b, idx) => (
              <div key={b.backup_path || `backup-${idx}`} className="flex items-center justify-between rounded-xl border border-border/40 bg-surface/20 p-3.5 text-xs">
                <div className="space-y-1">
                  <div className="flex items-center gap-2 font-semibold text-text">
                    <HardDrive size={14} className="text-accent" />
                    {b.scope || "backup"} <span className="text-[10px] text-faint font-mono">({b.started_at ? new Date(b.started_at).toLocaleString() : "—"})</span>
                  </div>
                  <div className="text-[11px] text-faint font-mono">
                    Size: {formatSize(b.size_bytes)} · Files: {typeof b.file_count === "number" ? b.file_count : "—"} · Duration: {typeof b.duration_seconds === "number" ? `${b.duration_seconds.toFixed(1)}s` : "—"}
                  </div>
                  {b.error && (
                    <div className="text-[11px] text-danger font-mono">{b.error}</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={b.success === false ? "danger" : b.success === true ? "ok" : "default"}>
                    {b.success === false ? "Failed" : b.success === true ? "Completed" : "Unknown"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
