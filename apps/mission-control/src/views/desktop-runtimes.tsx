"use client";

import { useCallback, useEffect, useState } from "react";
import { Panel, Stat, Badge, StatusDot, Empty } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { RuntimeInfo, RuntimeDiscoveryResult } from "@/lib/desktop-types";

export default function DesktopRuntimes() {
  const [runtimes, setRuntimes] = useState<RuntimeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryResult, setDiscoveryResult] = useState<RuntimeDiscoveryResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.runtimes();
      setRuntimes(data ?? []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoveryResult(null);
    try {
      const result = await api.discoverRuntimes();
      setDiscoveryResult(result);
      setRuntimes(result.runtimes ?? []);
    } catch (err) {
      setError(`Discovery failed: ${err}`);
    } finally {
      setDiscovering(false);
    }
  };

  if (loading) return <div className="flex items-center justify-center h-full text-xs text-faint">Loading…</div>;
  if (error && runtimes.length === 0) return <div className="flex items-center justify-center h-full text-xs text-danger">{error}</div>;

  const verifiedCount = runtimes.filter((r) => r.verified).length;

  return (
    <div className="flex h-full flex-col gap-4 overflow-auto p-4">
      <div className="flex flex-wrap items-center gap-3">
        <Stat label="Total Runtimes" value={runtimes.length} />
        <Stat label="Verified" value={verifiedCount} tone="ok" />
        <Stat label="Unverified" value={runtimes.length - verifiedCount} tone={runtimes.length - verifiedCount > 0 ? "warn" : "ok"} />
        {discoveryResult && (
          <Stat label="Last Discovery" value={`${discoveryResult.duration_seconds.toFixed(1)}s`} />
        )}
        <button
          onClick={handleDiscover}
          disabled={discovering}
          className="ml-auto rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white transition hover:bg-accent/80 disabled:opacity-50"
        >
          {discovering ? "Discovering…" : "Discover Runtimes"}
        </button>
      </div>

      {discoveryResult && discoveryResult.errors.length > 0 && (
        <div className="rounded-lg border border-warn/40 bg-warn/5 px-4 py-2 text-xs text-warn">
          {discoveryResult.errors.join("; ")}
        </div>
      )}

      <Panel title="Runtimes" subtitle={`${runtimes.length} discovered${discoveryResult ? ` (${discoveryResult.total_discovered} total in scan)` : ""}`} className="min-h-0 flex-1">
        {runtimes.length === 0 ? (
          <Empty title="No runtimes found" hint="Click 'Discover Runtimes' to scan for available runtimes." />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {runtimes.map((rt, i) => (
              <div key={`${rt.name}-${i}`} className="rounded-xl border border-border/60 bg-surface/20 p-4">
                <div className="flex items-center gap-3">
                  <StatusDot status={rt.verified ? "healthy" : "unknown"} pulse={rt.verified} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{rt.name}</span>
                      <Badge tone={rt.verified ? "ok" : "warn"}>{rt.verified ? "Verified" : "Unverified"}</Badge>
                      <Badge>{rt.runtime_type}</Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-faint">
                      <span>v{rt.version}</span>
                      <span className="truncate max-w-[200px]">{rt.path}</span>
                      <span>{rt.source}</span>
                    </div>
                    {rt.executable && (
                      <div className="text-[11px] text-faint">Executable: {rt.executable}</div>
                    )}
                    {rt.capabilities && rt.capabilities.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {rt.capabilities.map((cap) => (
                          <span key={cap} className="rounded-md bg-accent/10 px-2 py-0.5 text-[10px] text-accent">
                            {cap}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
