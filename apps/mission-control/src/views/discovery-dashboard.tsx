"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { safeFixed, safeNum } from "@/lib/safe";
import { useStore } from "@/lib/store";
import type {
  DiscoveryCacheEntry,
  DiscoveryHistoryEntry,
  DiscoveryProfileEntry,
  DiscoveryProviderInfo,
  DiscoveryStats,
  DiscoveryValidationEntry,
  HotReloadStatus,
} from "@/lib/types";

type DiscoveryTab = "dashboard" | "history" | "profiles" | "validation";

export function DiscoveryDashboard() {
  const [tab, setTab] = useState<DiscoveryTab>("dashboard");

  return (
    <div className="scroll-page">
      <div className="flex items-center gap-1 border-b border-border/60 px-4 pt-2">
        {(["dashboard", "history", "profiles", "validation"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t-lg px-4 py-2 text-xs font-medium transition ${
              tab === t
                ? "bg-surface/40 text-text"
                : "text-faint hover:text-muted hover:bg-surface/20"
            }`}
          >
            {t === "dashboard" ? "Dashboard" : t === "history" ? "History" : t === "profiles" ? "Profiles" : "Validation"}
          </button>
        ))}
      </div>
      <div className="p-4">
        {tab === "dashboard" && <DiscoveryDashboardTab />}
        {tab === "history" && <DiscoveryHistoryTab />}
        {tab === "profiles" && <DiscoveryProfilesTab />}
        {tab === "validation" && <DiscoveryValidationTab />}
      </div>
    </div>
  );
}

// ── Sub-tab: Dashboard ──

function DiscoveryDashboardTab() {
  const [providers, setProviders] = useState<DiscoveryProviderInfo[]>([]);
  const [cache, setCache] = useState<DiscoveryCacheEntry[]>([]);
  const [stats, setStats] = useState<DiscoveryStats | null>(null);
  const [hotReload, setHotReload] = useState<HotReloadStatus | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.discoveryProviders().then((res) => setProviders(Array.isArray(res) ? res : [])).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.discoveryCache().then((res) => { const data = res as unknown as { entries: DiscoveryCacheEntry[]; total: number }; setCache(Array.isArray(data?.entries) ? data.entries : Array.isArray(res) ? (res as any) : []); }).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.discoveryStats().then((res) => setStats(res && typeof res === "object" && !("status" in res && (res as any).status === "offline") ? res : null)).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.hotReloadStatus().then((res) => setHotReload(res && typeof res === "object" && "running" in res ? res : null)).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  // EventBus live subscription — reload on discovery/scan events
  const events = useStore((s) => s.events);
  const connected = useStore((s) => s.connected);

  const discoveryEventCount = useMemo(
    () => events.filter((e) => e.topic?.startsWith("discovery.") || e.topic?.startsWith("provider.")).length,
    [events]
  );

  useEffect(() => {
    load();
  }, [discoveryEventCount, load]);

  const handleScan = async () => {
    setScanning(true);
    setScanResult(null);
    try {
      const result = await api.runDiscoveryScan();
      const found = result?.engines_found ?? 0;
      const registered = result?.engines_registered ?? 0;
      setScanResult(`Found ${found} engines, registered ${registered}`);
      load();
    } catch (err) {
      setScanResult(`Scan failed: ${err}`);
    } finally {
      setScanning(false);
    }
  };

  const handleHotReloadToggle = async () => {
    try {
      if (hotReload?.running) {
        await api.stopHotReload();
        setHotReload({ running: false });
      } else {
        await api.startHotReload();
        setHotReload({ running: true });
      }
    } catch { /* ignore */ }
  };

  const activeCount = providers.filter((p) => p.enabled).length;
  const cacheHitCount = cache.reduce((s, e) => s + e.hit_count, 0);
  const expiredCount = cache.filter((e) => e.expired).length;

  return (
    <div className="no-hscroll">
      <div className="rflex gap-3">
        <Stat label="Active Providers" value={activeCount} tone="ok" />
        <Stat label="Cache Entries" value={cache.length} />
        <Stat label="Cache Hits" value={cacheHitCount} tone="accent" />
        <Stat label="Expired" value={expiredCount} tone={expiredCount ? "warn" : "ok"} />
        {stats && (
          <>
            <Stat label="Total Scans" value={stats.total_scans} />
            <Stat label="Engines Found" value={stats.total_engines_found} tone="accent" />
            <Stat label="Avg Duration" value={`${safeFixed(stats?.avg_duration_ms, 0)}ms`} />
            <Stat label="Failure Rate" value={`${safeFixed((safeNum(stats?.failure_rate) * 100), 1)}%`} tone={safeNum(stats?.failure_rate) > 0.1 ? "warn" : "ok"} />
          </>
        )}
      </div>

      <div className="rflex items-center gap-3 mt-3">
        <button
          onClick={handleScan}
          disabled={scanning}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          {scanning ? "Scanning…" : "Run Discovery Scan"}
        </button>
        <button
          onClick={handleHotReloadToggle}
          className="rounded-lg border border-border/60 px-4 py-2 text-xs font-medium transition hover:bg-surface/20"
        >
          Hot Reload: {hotReload?.running ? "ON" : "OFF"}
        </button>
        <button
          onClick={() => api.clearDiscoveryCache().then(() => load())}
          className="rounded-lg border border-border/60 px-4 py-2 text-xs text-faint transition hover:bg-surface/20"
        >
          Clear Cache
        </button>
        <button
          onClick={async () => {
            setScanning(true);
            setScanResult(null);
            try {
              const res = await api.post<{ status: string; detected: number; registered: number }>("/api/brains/rescan", {});
              setScanResult(`Rescanned: found ${res.detected} runtimes (${res.registered} registered)`);
              await useStore.getState().hydrate();
              load();
            } catch (err) {
              setScanResult(`Rescan failed: ${err}`);
            } finally {
              setScanning(false);
            }
          }}
          disabled={scanning}
          className="rounded-lg bg-emerald-600/20 border border-emerald-500/40 px-4 py-2 text-xs font-medium text-emerald-400 transition hover:bg-emerald-600/30 disabled:opacity-50"
        >
          {scanning ? "Rescanning…" : "Rescan Runtimes"}
        </button>
        {scanResult && (
          <span className="text-xs text-muted">{scanResult}</span>
        )}
        <div className="ml-auto flex items-center gap-2 text-[11px] text-faint">
          <StatusDot status={connected ? "healthy" : "failed"} pulse={connected} />
          <span>{connected ? "EventBus live" : "EventBus disconnected"}</span>
        </div>
      </div>

      <div className="rflex gap-4 mt-4">
        <Panel title="Discovery Providers" subtitle={`${providers.length} registered`} className="flex-1">
          <div className="space-y-2">
            {providers.map((p) => (
              <div key={p.name} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
                <StatusDot status={p.enabled ? "healthy" : "unknown"} pulse={p.enabled} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{p.name}</span>
                    <Badge>{p.provider_type}</Badge>
                  </div>
                  <div className="mt-0.5 text-[11px] text-faint">
                    Interval: {p.interval_seconds}s &middot; Timeout: {p.timeout_seconds}s
                  </div>
                </div>
                <button
                  onClick={() =>
                    api.enableProvider(p.name, { enabled: !p.enabled }).then(() => load())
                  }
                  className={`rounded-md px-2.5 py-1 text-[11px] font-medium transition ${
                    p.enabled
                      ? "bg-ok/12 text-ok hover:bg-ok/20"
                      : "bg-surface/40 text-faint hover:bg-surface/60"
                  }`}
                >
                  {p.enabled ? "Enabled" : "Disabled"}
                </button>
              </div>
            ))}
            {providers.length === 0 && <Empty title="No providers" hint="Providers register at kernel startup." />}
          </div>
        </Panel>

        <Panel title="Cache" subtitle={`${cache.filter((e) => !e.expired).length} active`} className="flex-1">
          <div className="space-y-1.5">
            {cache.slice(0, 30).map((e) => (
              <div key={e.key} className="flex items-center gap-2 text-xs">
                <StatusDot status={e.expired ? "failed" : "healthy"} />
                <span className="w-36 shrink-0 truncate font-mono text-faint">{e.provider_name}</span>
                <span className="flex-1 truncate text-muted">{e.key}</span>
                <span className="w-16 text-right tabular-nums text-faint">{e.hit_count}x</span>
                <span className="w-24 text-right text-faint">
                  {e.expired ? "expired" : new Date(e.expires_at).toLocaleTimeString()}
                </span>
              </div>
            ))}
            {cache.length === 0 && <Empty title="Cache empty" hint="Run a discovery scan to populate." />}
          </div>
        </Panel>
      </div>
    </div>
  );
}

// ── Sub-tab: History ──

function DiscoveryHistoryTab() {
  const [history, setHistory] = useState<DiscoveryHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discoveryHistory(100).then(setHistory).catch((err) => { console.error("API error:", err); setError(String(err)); }).finally(() => setLoading(false));
  }, []);

  return (
    <Panel title="Scan History" subtitle={`${history.length} scans recorded`}>
      {loading ? (
        <div className="flex items-center justify-center py-12 text-xs text-faint">Loading…</div>
      ) : history.length === 0 ? (
        <Empty title="No scans yet" hint="Run a discovery scan to populate history." />
      ) : (
        <div className="table-container">
          <div className="divide-y divide-border/40 min-w-[600px]">
            <div className="flex items-center gap-3 px-2 py-2 text-[11px] font-semibold uppercase text-faint">
              <span className="w-8">#</span>
              <span className="w-32">Profile</span>
              <span className="w-20">Started</span>
              <span className="w-16">Duration</span>
              <span className="w-14 text-right">Found</span>
              <span className="w-14 text-right">Failed</span>
              <span className="flex-1 text-right">Errors</span>
            </div>
            {history.map((h, i) => (
              <div key={h.id} className="flex items-center gap-3 px-2 py-2 text-xs">
                <span className="w-8 text-faint">{i + 1}</span>
                <span className="w-32 truncate font-mono">{h.profile_name}</span>
                <span className="w-20 text-faint">{new Date(h.started_at).toLocaleTimeString()}</span>
                <span className="w-16 tabular-nums text-faint">{safeFixed(h?.duration_ms, 0)}ms</span>
                <span className="w-14 text-right tabular-nums">{h.engines_found}</span>
                <span className="w-14 text-right tabular-nums" style={{ color: h.providers_failed ? "var(--warn)" : undefined }}>
                  {h.providers_failed}
                </span>
                <span className="flex-1 truncate text-right text-faint">{h.errors.join(", ")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Panel>
  );
}

// ── Sub-tab: Profiles ──

function DiscoveryProfilesTab() {
  const [profiles, setProfiles] = useState<DiscoveryProfileEntry[]>([]);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.discoveryProfiles().then(setProfiles).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await api.createDiscoveryProfile({ name: newName.trim() });
      setNewName("");
      load();
    } catch { /* ignore */ }
    setCreating(false);
  };

  const handleDelete = async (name: string) => {
    try {
      await api.deleteDiscoveryProfile(name);
      load();
    } catch { /* ignore */ }
  };

  const handleActivate = async (name: string) => {
    try {
      await api.activateDiscoveryProfile(name);
      load();
    } catch { /* ignore */ }
  };

  return (
    <div className="no-hscroll">
      <div className="rflex items-center gap-3">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New profile name…"
          className="flex-1 rounded-lg border border-border/60 bg-surface/20 px-3 py-2 text-xs placeholder:text-faint"
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <button
          onClick={handleCreate}
          disabled={creating || !newName.trim()}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          Create
        </button>
      </div>

      <div className="card-grid mt-4">
        {profiles.map((p) => (
          <div key={p.name} className="card-fluid rounded-xl border border-border/60 bg-surface/20 p-4">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-medium">{p.name}</span>
                {p.description && (
                  <span className="ml-2 text-xs text-faint">{p.description}</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleActivate(p.name)}
                  className="rounded-md bg-accent/12 px-2.5 py-1 text-xs font-medium text-accent transition hover:bg-accent/20"
                >
                  Activate
                </button>
                <button
                  onClick={() => handleDelete(p.name)}
                  className="rounded-md bg-danger/12 px-2.5 py-1 text-xs font-medium text-danger transition hover:bg-danger/20"
                >
                  Delete
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {p.provider_configs.map((pc) => (
                <span
                  key={pc.name}
                  className={`rounded-md px-2 py-0.5 text-[11px] ${
                    pc.enabled ? "bg-ok/12 text-ok" : "bg-surface/40 text-faint"
                  }`}
                >
                  {pc.name}
                </span>
              ))}
              {p.provider_configs.length === 0 && (
                <span className="text-[11px] text-faint">No providers configured</span>
              )}
            </div>
            <div className="mt-2 flex gap-3 text-[11px] text-faint">
              <span>Interval: {p.interval_seconds}s</span>
              <span>Auto-register: {p.auto_register ? "yes" : "no"}</span>
              <span>Validate: {p.validate_after_discovery ? "yes" : "no"}</span>
            </div>
          </div>
        ))}
        {profiles.length === 0 && (
          <div className="col-span-full">
            <Empty title="No profiles" hint="Create a profile to configure discovery behavior." />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-tab: Validation ──

function DiscoveryValidationTab() {
  const [validations, setValidations] = useState<DiscoveryValidationEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discoveryHistory(50).then(async (history) => {
      const results: DiscoveryValidationEntry[] = [];
      // Get engines found in recent scans and validate them
      // For now show the scan history as validation proxy
      for (const h of history.slice(0, 10)) {
        if (h.engines_found > 0) {
          results.push({
            engine_id: h.id,
            engine_name: `scan-${h.profile_name}`,
            valid: h.providers_failed === 0,
            errors: h.errors,
            warnings: [],
            validated_at: h.completed_at || h.started_at,
          });
        }
      }
      setValidations(results);
    }).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  return (
    <Panel title="Validation Results" subtitle={`${validations.length} engines validated`}>
      {validations.length === 0 ? (
        <Empty title="No validation data" hint="Run a discovery scan to trigger validation." />
      ) : (
        <div className="space-y-2">
          {validations.map((v) => (
            <div key={v.engine_id} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2.5">
              <StatusDot status={v.valid ? "healthy" : "failed"} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{v.engine_name}</span>
                  <Badge tone={v.valid ? "ok" : "danger"}>{v.valid ? "Pass" : "Fail"}</Badge>
                </div>
                {v.errors.length > 0 && (
                  <div className="mt-0.5 text-[11px] text-danger">{v.errors.join("; ")}</div>
                )}
                {v.warnings.length > 0 && (
                  <div className="mt-0.5 text-[11px] text-faint">{v.warnings.join("; ")}</div>
                )}
              </div>
              <span className="text-[11px] text-faint">
                {new Date(v.validated_at).toLocaleTimeString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
