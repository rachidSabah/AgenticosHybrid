"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore, selectMetrics } from "@/lib/store";
import { useShallow } from "zustand/react/shallow";
import { api } from "@/lib/api";
import type { ProviderHealthRecord, CapabilityInfo, AuditEntry } from "@/lib/types";

export function MissionOverview() {
  const m = useStore(useShallow(selectMetrics));
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const providers = useStore((s) => s.providers);
  const events = useStore((s) => s.events);

  const [providersData, setProvidersData] = useState<ProviderHealthRecord[]>([]);
  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.providerHealth().then(setProvidersData).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.capabilities().then(setCaps).catch((err) => { console.error("API error:", err); setError(String(err)); });
    api.audit().then(setAudit).catch((err) => { console.error("API error:", err); setError(String(err)); });
  }, []);

  const healthy = Object.values(providers).filter((p) => p.status === "healthy").length;
  const running = Object.values(agents).filter((a) => a.status === "running").length;

  return (
    <div className="scroll-page space-y-4 p-4 no-hscroll">
      <div className="flex flex-wrap gap-3">
        <Stat label="Agents" value={m.agents} delta={`${running} running`} tone="accent" />
        <Stat label="Tasks" value={m.tasks} delta={`${Object.keys(tasks).length} tracked`} />
        <Stat label="Providers" value={m.providers} delta={`${healthy} healthy`} tone="ok" />
        <Stat label="Pipelines" value={m.pipelines} />
        <Stat label="Cost" value={`$${m.cost.toFixed(4)}`} tone="warn" />
        <Stat label="Errors" value={m.errors} tone={m.errors ? "danger" : "ok"} />
        <Stat label="Events" value={events.length} delta="live stream" />
      </div>

      <Panel title="Live Activity" subtitle="Real-time EventBus pulses">
        <ActivityStream />
      </Panel>

      <Panel title="Provider Health" subtitle="From provider control center">
        {providersData.length === 0 && providers && Object.keys(providers).length === 0 ? (
          <Empty title="No provider telemetry yet" hint="Run a task or register a provider." />
        ) : (
          <div className="space-y-2">
            {providersData.map((p) => (
              <div key={p.provider} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2">
                <StatusDot status={p.status} pulse={p.status === "healthy"} />
                <span className="flex-1 text-sm">{p.provider}</span>
                <span className="text-xs text-faint">{p.latency_ms.toFixed(0)}ms</span>
              </div>
            ))}
            {Object.values(providers).map((p) =>
              providersData.find((d) => d.provider === p.provider) ? null : (
                <div key={p.provider} className="flex items-center gap-3 rounded-xl border border-border/60 px-3 py-2">
                  <StatusDot status={p.status} pulse={p.status === "healthy"} />
                  <span className="flex-1 text-sm">{p.provider}</span>
                  <span className="text-xs text-faint">{p.latency_ms.toFixed(0)}ms</span>
                </div>
              ),
            )}
          </div>
        )}
      </Panel>

      <Panel title="Capabilities" subtitle={`${caps.length} registered`}>
        <div className="flex flex-wrap gap-1.5">
          {caps.map((c) => (
            <Badge key={c.name} tone={c.requires_approval ? "warn" : "default"}>
              {c.name}
            </Badge>
          ))}
          {caps.length === 0 && <Empty title="No capabilities" />}
        </div>
      </Panel>

      <Panel title="Agent Fleet" subtitle="Current live agents">
        <div className="flex flex-wrap gap-2">
          {Object.values(agents).map((a) => (
            <div key={a.id} className="flex items-center gap-2 rounded-xl border border-border/60 px-3 py-2">
              <StatusDot status={a.status} pulse={a.status === "running"} />
              <div className="leading-tight">
                <div className="text-sm">{a.role}</div>
                <div className="text-[11px] text-faint">{a.provider ?? "—"}</div>
              </div>
            </div>
          ))}
          {Object.keys(agents).length === 0 && <Empty title="No agents active" hint="Compose one from the AI Brain." />}
        </div>
      </Panel>

      <Panel title="Audit Trail" subtitle="Security-relevant actions" contentClassName="p-0">
        <div className="divide-y divide-border/50">
          {audit.slice(0, 12).map((e) => (
            <div key={e.id} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="w-28 shrink-0 truncate text-faint">{e.action}</span>
              <span className="flex-1 truncate">{e.target || e.principal}</span>
              <Badge tone={e.outcome === "deny" ? "danger" : e.outcome === "allow" ? "ok" : "default"}>
                {e.outcome}
              </Badge>
            </div>
          ))}
          {audit.length === 0 && <Empty title="No audit entries" />}
        </div>
      </Panel>
    </div>
  );
}

function ActivityStream() {
  const events = useStore((s) => s.events);
  return (
    <div className="space-y-1.5">
      {events.slice(0, 40).map((e, i) => (
        <motion.div
          key={e.id}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.2 }}
          className="flex items-center gap-3 rounded-lg px-2 py-1.5 text-xs hover:bg-surface/40"
          style={{ opacity: Math.max(0.35, 1 - i * 0.02) }}
        >
          <StatusDot status={e.topic.includes("fail") || e.topic.includes("denied") ? "danger" : "healthy"} />
          <span className="w-36 shrink-0 truncate font-mono text-faint">{e.topic}</span>
          <span className="flex-1 truncate text-muted">{e.source}</span>
          <span className="text-faint">{new Date(e.timestamp).toLocaleTimeString()}</span>
        </motion.div>
      ))}
      {events.length === 0 && <Empty title="Awaiting events…" hint="Live EventBus traffic appears here." />}
    </div>
  );
}
