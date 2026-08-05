"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { safeFixed, safeNum, safeStr, safeArr, safeLen } from "@/lib/safe";
import type { ReleaseInfo, UpdateManifest, UpdateHistoryRecord } from "@/lib/desktop-types";

interface DevCommit {
  hash: string;
  short_hash: string;
  author: string;
  date: string;
  subject: string;
}

interface DevUpdateStatus {
  local_commit: string;
  local_short: string;
  branch: string;
  remote_commit: string;
  remote_short: string;
  behind: number;
  up_to_date: boolean;
  has_remote: boolean;
  error?: string;
}

export default function DesktopUpdates() {
  const [version, setVersion] = useState("");
  const [updateStatus, setUpdateStatus] = useState("");
  const [channel, setChannel] = useState("stable");
  const [channels, setChannels] = useState<string[]>([]);
  const [releases, setReleases] = useState<ReleaseInfo[]>([]);
  const [history, setHistory] = useState<UpdateHistoryRecord[]>([]);
  const [pending, setPending] = useState<UpdateManifest | null>(null);
  const [rollbackVersions, setRollbackVersions] = useState<string[]>([]);
  const [checking, setChecking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Dev-mode git update state
  const [devStatus, setDevStatus] = useState<DevUpdateStatus | null>(null);
  const [devCommits, setDevCommits] = useState<DevCommit[]>([]);
  const [devChecking, setDevChecking] = useState(false);
  const [devPulling, setDevPulling] = useState(false);
  const [devRestarting, setDevRestarting] = useState(false);
  const [devMessage, setDevMessage] = useState<string | null>(null);

  const loadDevStatus = useCallback(async () => {
    try {
      const s = await api.devUpdateStatus();
      setDevStatus(s);
      if (s && !s.up_to_date && s.has_remote) {
        const commits = await api.devUpdateCommits(50);
        setDevCommits(commits ?? []);
      } else {
        setDevCommits([]);
      }
    } catch {
      // Backend may not have the endpoint yet — silently ignore
    }
  }, []);

  const load = useCallback(async () => {
    try {
      const status = await api.updateStatus();
      setVersion(status.version);
      setUpdateStatus(status.status);
    } catch { /* ignore */ }
    try {
      const curChannel = await api.currentChannel();
      setChannel(curChannel.channel);
    } catch { /* ignore */ }
    try {
      const ch = await api.channels();
      setChannels(ch);
    } catch { /* ignore */ }
    try {
      const h = await api.updateHistory();
      setHistory(h ?? []);
    } catch { /* ignore */ }
    try {
      const p = await api.pendingUpdate();
      setPending(p);
    } catch { /* ignore */ }
    try {
      const rvs = await api.rollbackAvailable();
      setRollbackVersions(rvs ?? []);
    } catch { /* ignore */ }
    // Also load dev-mode git status
    void loadDevStatus();
  }, [loadDevStatus]);

  useEffect(() => { load(); }, [load]);

  const handleDevCheck = async () => {
    setDevChecking(true);
    setDevMessage(null);
    try {
      await loadDevStatus();
      if (devStatus && devStatus.up_to_date) {
        setDevMessage("Already up to date — local checkout matches origin/main.");
      }
    } finally {
      setDevChecking(false);
    }
  };

  const handleDevPull = async () => {
    setDevPulling(true);
    setDevMessage(null);
    try {
      const result = await api.devUpdatePull();
      if (result.success) {
        setDevMessage(`✓ Pulled latest. New HEAD: ${result.new_head || "?"}. Click "Restart Server" to apply.`);
        await loadDevStatus();
      } else {
        setDevMessage(`✗ Pull failed: ${result.error || result.stderr || "unknown error"}`);
      }
    } catch (err) {
      setDevMessage(`✗ Pull failed: ${String(err)}`);
    } finally {
      setDevPulling(false);
    }
  };

  const handleDevRestart = async () => {
    setDevRestarting(true);
    try {
      const result = await api.devUpdateRestart();
      if (result.scheduled) {
        setDevMessage("Restart scheduled — server will exit in 1s. Your process manager (npm/uvicorn) will auto-restart it. Refresh this page in ~5s.");
      }
    } catch (err) {
      setDevMessage(`✗ Restart failed: ${String(err)}`);
    } finally {
      setDevRestarting(false);
    }
  };

  const handleCheck = async () => {
    setChecking(true);
    setError(null);
    try {
      const r = await api.checkUpdates(channel);
      setReleases(r ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setChecking(false);
    }
  };

  const handleChannelChange = async (newChannel: string) => {
    try {
      await api.setChannel(newChannel);
      setChannel(newChannel);
    } catch (err) {
      setError(String(err));
    }
  };

  const handleDownload = async (manifest: UpdateManifest) => {
    setDownloading(true);
    try {
      await api.downloadUpdate(manifest);
      setPending(manifest);
    } catch (err) {
      setError(String(err));
    } finally {
      setDownloading(false);
    }
  };

  const handleInstall = async (manifest: UpdateManifest) => {
    setInstalling(true);
    try {
      await api.installUpdate(manifest);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setInstalling(false);
    }
  };

  const handleRollback = async () => {
    setRollingBack(true);
    try {
      await api.rollback();
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setRollingBack(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4" role="region" aria-label="Desktop Updates">
      {error && (
        <div role="alert" className="rounded-lg border border-danger/40 bg-danger/5 px-4 py-2 text-xs text-danger">{error}</div>
      )}

      {/* ── Development Updates (git pull from origin/main) ── */}
      {/* This panel works on localhost:3000 + any git checkout, even when
          the Tauri desktop update manager isn't available. It detects
          whether the local code is behind origin/main and offers to
          pull + restart. */}
      {devStatus && devStatus.has_remote && (
        <Panel
          title="Development Updates"
          subtitle={
            devStatus.up_to_date
              ? `Up to date on ${devStatus.branch}`
              : `${devStatus.behind} commit(s) behind origin/main`
          }
          className="col-span-12"
        >
          <div className="space-y-3">
            {/* Status row */}
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className="text-faint">Local:</span>
              <code className="rounded bg-surface/40 px-1.5 py-0.5 font-mono text-[11px] text-text">
                {devStatus.local_short || "unknown"}
              </code>
              <span className="text-faint">on</span>
              <code className="rounded bg-surface/40 px-1.5 py-0.5 font-mono text-[11px] text-text">
                {devStatus.branch || "unknown"}
              </code>
              <span className="text-faint">→</span>
              <span className="text-faint">Remote:</span>
              <code className="rounded bg-surface/40 px-1.5 py-0.5 font-mono text-[11px] text-text">
                {devStatus.remote_short || "unknown"}
              </code>
              {devStatus.up_to_date ? (
                <Badge tone="ok">Up to date</Badge>
              ) : (
                <Badge tone="warn">{devStatus.behind} behind</Badge>
              )}
              <button
                onClick={handleDevCheck}
                disabled={devChecking}
                aria-label="Check for new commits"
                className="ml-auto rounded-lg border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:bg-surface/20 disabled:opacity-50"
              >
                {devChecking ? "Checking…" : "Check for Updates"}
              </button>
            </div>

            {/* Message line */}
            {devMessage && (
              <div className="rounded-lg border border-border/40 bg-surface/20 px-3 py-2 text-xs text-text">
                {devMessage}
              </div>
            )}

            {/* New commits list */}
            {devCommits.length > 0 && (
              <div className="space-y-1.5">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-faint">
                  New commits available ({devCommits.length})
                </div>
                <div className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-border/40">
                  {devCommits.map((c) => (
                    <div key={c.hash} className="flex items-start gap-2 px-3 py-1.5 text-xs hover:bg-surface/20">
                      <code className="font-mono text-[10px] text-accent shrink-0">{c.short_hash}</code>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-text">{c.subject}</div>
                        <div className="text-[10px] text-faint">
                          {c.author} · {new Date(c.date).toLocaleString()}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            {!devStatus.up_to_date && (
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={handleDevPull}
                  disabled={devPulling}
                  aria-label="Pull latest commits"
                  className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
                >
                  {devPulling ? "Pulling…" : `Pull ${devStatus.behind} commit(s)`}
                </button>
                <button
                  onClick={handleDevRestart}
                  disabled={devRestarting}
                  aria-label="Restart server to apply"
                  className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20 disabled:opacity-50"
                >
                  {devRestarting ? "Restarting…" : "Restart Server"}
                </button>
              </div>
            )}
          </div>
        </Panel>
      )}

      <div className="flex flex-wrap items-center gap-3" aria-live="polite">
        <Stat label="Current Version" value={version || "—"} />
        <Stat label="Status" value={updateStatus} tone={updateStatus === "up-to-date" ? "ok" : updateStatus === "update-available" ? "warn" : "default"} />
        <div className="flex items-center gap-2 rounded-xl border border-border/60 px-3.5 py-3">
          <span className="text-[11px] uppercase tracking-wide text-faint">Channel</span>
          <select
            value={channel}
            onChange={(e) => handleChannelChange(e.target.value)}
            aria-label="Update Channel"
            className="rounded-lg border border-border/60 bg-surface/20 px-2 py-1 text-xs text-text"
          >
            {channels.map((ch) => (
              <option key={ch} value={ch}>{ch}</option>
            ))}
          </select>
        </div>
        <button
          onClick={handleCheck}
          disabled={checking}
          aria-label="Check for Updates"
          className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Check for Updates"}
        </button>
      </div>

      {pending && (
        <Panel title="Pending Update" subtitle={`${pending.version} (${pending.channel})`} className="col-span-12">
          <div className="flex items-center gap-4">
            <div className="flex-1 space-y-1">
              <div className="text-xs text-muted">
                Size: {safeFixed((safeNum(pending?.size_bytes) / 1024 / 1024), 1)} MB &middot; Released: {pending.release_date}
                {pending.mandatory && <span className="ml-2"><Badge tone="danger">Mandatory</Badge></span>}
              </div>
              {pending.changelog?.length > 0 && (
                <ul className="list-inside list-disc text-[11px] text-faint">
                  {pending.changelog.slice(0, 5).map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => handleDownload(pending)}
                disabled={downloading}
                aria-label="Download"
                className="rounded-lg border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:bg-surface/20 disabled:opacity-50"
              >
                {downloading ? "Downloading…" : "Download"}
              </button>
              <button
                onClick={() => handleInstall(pending)}
                disabled={installing}
                aria-label="Install"
                className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
              >
                {installing ? "Installing…" : "Install"}
              </button>
            </div>
          </div>
        </Panel>
      )}

      {releases.length > 0 && (
        <Panel title="Available Updates" subtitle={`${releases.length} release(s)`}>
          <div className="space-y-2">
            {releases.map((r, i) => {
              // Construct a minimal UpdateManifest from the ReleaseInfo
              // so we can reuse handleDownload / handleInstall.
              const manifest: UpdateManifest = {
                version: r.version,
                download_url: r.url,
                checksum_sha256: "",
                size_bytes: 0,
                release_date: r.published_at ?? "",
                min_version: "",
                changelog: r.release_notes ? r.release_notes.split("\n").filter(Boolean) : [],
                mandatory: false,
                channel: r.channel,
              };
              const isCurrent = r.version === version;
              return (
                <div key={r.tag || i} className="flex flex-wrap items-center gap-3 rounded-lg border border-border/40 px-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{r.version}</span>
                      <Badge tone={r.channel === "stable" ? "ok" : r.channel === "beta" ? "warn" : "accent"}>{r.channel}</Badge>
                      {r.prerelease && <Badge tone="info">Pre-release</Badge>}
                      {isCurrent && <Badge tone="default">Installed</Badge>}
                    </div>
                    {r.release_notes && (
                      <div className="mt-0.5 text-[11px] text-faint line-clamp-2">{r.release_notes}</div>
                    )}
                    {r.published_at && (
                      <div className="mt-0.5 text-[11px] text-faint">{new Date(r.published_at).toLocaleDateString()}</div>
                    )}
                  </div>
                  {!isCurrent && (
                    <div className="flex shrink-0 gap-2">
                      <button
                        onClick={() => handleDownload(manifest)}
                        disabled={downloading}
                        aria-label={`Download ${r.version}`}
                        className="rounded-lg border border-border/60 px-3 py-1.5 text-xs font-medium transition hover:bg-surface/20 disabled:opacity-50"
                      >
                        {downloading ? "Downloading…" : "Download"}
                      </button>
                      <button
                        onClick={() => handleInstall(manifest)}
                        disabled={installing}
                        aria-label={`Install ${r.version}`}
                        className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
                      >
                        {installing ? "Installing…" : "Install"}
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      <Panel title="Update History" subtitle={`${history.length} records`}>
        {history.length === 0 ? (
          <Empty title="No history" hint="Updates will appear here once installed." />
        ) : (
          <div className="divide-y divide-border/40">
            <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
              <span className="w-28">From</span>
              <span className="w-28">To</span>
              <span className="w-20">Channel</span>
              <span className="w-20">Status</span>
              <span className="w-28">Date</span>
            </div>
            {history.map((h) => (
              <div key={h.id} className="flex items-center gap-3 px-2 py-2 text-xs">
                <span className="w-28 font-mono text-faint">{h.from_version}</span>
                <span className="w-28 font-mono">{h.to_version}</span>
                <span className="w-20 text-muted">{h.channel}</span>
                <span className="w-20">
                  <Badge tone={h.status === "success" ? "ok" : h.status === "failed" ? "danger" : "warn"}>{h.status}</Badge>
                </span>
                <span className="w-28 text-faint">{new Date(h.installed_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Rollback" subtitle={`${rollbackVersions.length} version(s) available`}>
        <div className="space-y-3">
          {rollbackVersions.length === 0 ? (
            <Empty title="No rollback versions available" />
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {rollbackVersions.map((v) => (
                <span key={v} className="rounded-lg border border-border/60 px-3 py-1.5 text-xs font-mono">{v}</span>
              ))}
              <button
                onClick={handleRollback}
                disabled={rollingBack}
                aria-label="Rollback"
                className="ml-auto rounded-lg bg-warn/12 px-4 py-2 text-xs font-medium text-warn transition hover:bg-warn/20 disabled:opacity-50"
              >
                {rollingBack ? "Rolling back…" : "Rollback"}
              </button>
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}
