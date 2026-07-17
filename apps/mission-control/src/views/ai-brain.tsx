"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { AgentSpec, CapabilityInfo } from "@/lib/types";

// The AI Brain centerpiece. Every ring, pulse, and orbiting node is driven by
// REAL EventBus pulses from the live telemetry ring — no synthetic animation.
export function AIBrain() {
  const pulses = useStore((s) => s.telemetry.pulses);
  const metrics = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);
  const agents = useStore((s) => s.agents);
  const providers = useStore((s) => s.providers);

  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [compose, setCompose] = useState(false);
  const [spec, setSpec] = useState<Partial<AgentSpec>>({ name: "", capabilities: [], provider: "", model: "" });
  const [result, setResult] = useState<string>("");

  useEffect(() => {
    api.capabilities().then(setCaps).catch(() => {});
  }, []);

  // A pulse is "fresh" within the last 1.2s; the brain lights up accordingly.
  const now = Date.now();
  const recentPulses = pulses.filter((p) => now - p.at < 1200);
  const idle = recentPulses.length === 0;
  const intensity = Math.min(1, recentPulses.length / 6);

  const orbit = useMemo(() => {
    const entries = Object.values(agents);
    return entries.map((a, i) => ({
      id: a.id,
      role: a.role,
      status: a.status,
      angle: (i / Math.max(1, entries.length)) * Math.PI * 2,
    }));
  }, [agents]);

  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      <div className="col-span-7 relative flex items-center justify-center">
        <div className="relative aspect-square w-full max-w-[520px]">
          {/* Ambient glow reacts to event intensity */}
          <motion.div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                "radial-gradient(circle at center, rgba(99,102,241,0.35), rgba(99,102,241,0.04) 60%, transparent 72%)",
            }}
            animate={{ opacity: idle ? 0.25 : 0.35 + intensity * 0.6, scale: idle ? 0.96 : 1 + intensity * 0.06 }}
            transition={{ duration: 0.4 }}
          />
          {/* Core */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
            <motion.div
              className="grid h-40 w-40 place-items-center rounded-full glass-strong shadow-glow"
              animate={{ scale: idle ? 1 : 1 + intensity * 0.05 }}
              transition={{ type: "spring", stiffness: 120, damping: 14 }}
            >
              <div className="text-center">
                <div className="text-[11px] uppercase tracking-widest text-faint">AI Brain</div>
                <div className="mt-1 text-2xl font-semibold tabular-nums">
                  {recentPulses.length > 0 ? recentPulses.length : "idle"}
                </div>
                <div className="text-[11px] text-faint">{connected ? "live" : "offline"}</div>
              </div>
            </motion.div>
            {/* Pulse rings emitted on real events */}
            <AnimatePresence>
              {recentPulses.slice(0, 3).map((p, i) => (
                <motion.div
                  key={p.at + "-" + i}
                  className="absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent/40"
                  initial={{ scale: 1, opacity: 0.6 }}
                  animate={{ scale: 2.4, opacity: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 1.1, delay: i * 0.12 }}
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Orbiting live agents */}
          {orbit.map((o) => {
            const x = Math.cos(o.angle) * 200;
            const y = Math.sin(o.angle) * 200;
            return (
              <motion.div
                key={o.id}
                className="absolute left-1/2 top-1/2"
                style={{ x, y }}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 90, damping: 16 }}
              >
                <div className="-translate-x-1/2 -translate-y-1/2 rounded-full border border-border/60 bg-surface/80 px-2.5 py-1 text-[11px] backdrop-blur">
                  <StatusDot status={o.status} pulse={o.status === "running"} />
                  <span className="ml-1.5">{o.role}</span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>

      <div className="col-span-5 flex flex-col gap-4">
        <Panel title="Brain Telemetry" subtitle="Derived from EventBus pulses" className="flex-1">
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Tasks" value={metrics.tasks} />
            <Metric label="Agents" value={metrics.agents} />
            <Metric label="Providers" value={metrics.providers} />
            <Metric label="Errors" value={metrics.errors} danger={metrics.errors > 0} />
          </div>
          <div className="mt-4">
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-faint">Providers</div>
            <div className="space-y-1.5">
              {Object.values(providers).map((p) => (
                <div key={p.provider} className="flex items-center gap-2 text-sm">
                  <StatusDot status={p.status} pulse={p.status === "healthy"} />
                  <span className="flex-1 truncate">{p.provider}</span>
                  <span className="text-xs text-faint">{p.latency_ms.toFixed(0)}ms</span>
                </div>
              ))}
              {Object.keys(providers).length === 0 && <Empty title="No providers" />}
            </div>
          </div>
        </Panel>

        <Panel
          title="Compose Agent"
          subtitle="Routed through the Capability Engine"
          actions={
            <button className="pill bg-accent/15 text-accent hover:bg-accent/25" onClick={() => setCompose((v) => !v)}>
              {compose ? "Close" : "New"}
            </button>
          }
        >
          {compose ? (
            <div className="space-y-3">
              <input
                className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
                placeholder="Name (e.g. planner)"
                value={spec.name}
                onChange={(e) => setSpec({ ...spec, name: e.target.value })}
              />
              <div className="flex flex-wrap gap-1.5">
                {caps.map((c) => {
                  const on = spec.capabilities?.includes(c.name);
                  return (
                    <button
                      key={c.name}
                      onClick={() =>
                        setSpec((s) => ({
                          ...s,
                          capabilities: on
                            ? (s.capabilities ?? []).filter((x) => x !== c.name)
                            : [...(s.capabilities ?? []), c.name],
                        }))
                      }
                      className={on ? "pill bg-accent/20 text-accent" : "pill bg-surface/60 text-muted"}
                    >
                      {c.name}
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
                  placeholder="Provider (optional)"
                  value={spec.provider}
                  onChange={(e) => setSpec({ ...spec, provider: e.target.value })}
                />
                <button
                  className="pill bg-accent/20 text-accent hover:bg-accent/30"
                  onClick={async () => {
                    try {
                      const r = await api.composeAgent(spec as AgentSpec);
                      setResult(`Composed ${r.name} (${r.id})`);
                    } catch (e) {
                      setResult("Failed: " + (e as Error).message);
                    }
                  }}
                >
                  Compose
                </button>
              </div>
              {result && <div className="text-xs text-muted">{result}</div>}
            </div>
          ) : (
            <div className="text-sm text-faint">
              Compose a new agent from registered capabilities. The request is validated and routed by the
              backend Capability Engine and emits a real <Badge tone="info">agent.composed</Badge> event.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Metric({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className="glass rounded-xl px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${danger ? "text-danger" : "text-text"}`}>{value}</div>
    </div>
  );
}
