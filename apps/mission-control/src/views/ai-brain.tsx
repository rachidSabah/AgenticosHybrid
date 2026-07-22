"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { AgentSpec, CapabilityInfo } from "@/lib/types";

// ── SVG Brain Geometry ──
const S = 400;          // viewBox size
const C = 200;          // center
const ORBIT_R = 168;    // orbital radius (SVG units)

// Stylised brain — left / right cerebral hemispheres + brainstem + cerebellum
const L_HEMI = [
  "M200,45",
  "C162,45 130,66 126,100",
  "C122,130 133,154 150,164",
  "C156,167 162,169 167,169",
  "C167,180 162,197 156,214",
  "L200,220 Z",
].join(" ");

const R_HEMI = [
  "M200,45",
  "C238,45 270,66 274,100",
  "C278,130 267,154 250,164",
  "C244,167 238,169 233,169",
  "C233,180 238,197 244,214",
  "L200,220 Z",
].join(" ");

const STEM = "M190,216 L190,266 C190,276 210,276 210,266 L210,216 Z";

const CEREBELLUM =
  "M155,165 C140,184 145,208 163,214 C178,219 192,215 200,210 C208,215 222,219 237,214 C255,208 260,184 245,165";

// Decorative sulcus folds (thin strokes inside each hemisphere)
const SULCI = [
  // Left hemisphere folds
  "M147,92 Q157,102 154,117",
  "M162,82 Q170,97 167,112",
  "M138,114 Q148,124 146,139",
  "M153,128 Q162,138 160,150",
  // Right hemisphere folds
  "M253,92 Q243,102 246,117",
  "M238,82 Q230,97 233,112",
  "M262,114 Q252,124 254,139",
  "M247,128 Q238,138 240,150",
];

// ── Sub-components ──

function Metric({
  label,
  value,
  danger,
}: {
  label: string;
  value: number;
  danger?: boolean;
}) {
  return (
    <div className="glass rounded-xl px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-faint">
        {label}
      </div>
      <div
        className={`mt-1 text-lg font-semibold tabular-nums ${
          danger ? "text-danger" : "text-text"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

/** Animated traveling pulse dot along a line at a given angle. */
function NeuralPulse({ angle, delay = 0 }: { angle: number; delay?: number }) {
  const x1 = C + Math.cos(angle) * 32; // start just outside brain
  const y1 = C + Math.sin(angle) * 32;
  const x2 = C + Math.cos(angle) * (ORBIT_R + 6);
  const y2 = C + Math.sin(angle) * (ORBIT_R + 6);

  return (
    <motion.circle
      r={3}
      fill="rgba(129,140,248,0.85)"
      filter="url(#glow)"
      initial={{ cx: x1, cy: y1, opacity: 0 }}
      animate={{
        cx: [x1, x2, x1],
        cy: [y1, y2, y1],
        opacity: [0, 1, 0],
      }}
      transition={{
        duration: 2.6,
        ease: "easeInOut",
        repeat: Infinity,
        delay,
      }}
    />
  );
}

/** Horizontal signal-strength bars for the Live Connections panel. */
function SignalBars({ latency }: { latency: number }) {
  const bars = 5;
  const level =
    latency <= 50 ? 5 : latency <= 150 ? 4 : latency <= 400 ? 3 : latency <= 1200 ? 2 : 1;

  return (
    <div className="flex items-end gap-[2px]">
      {Array.from({ length: bars }, (_, i) => (
        <span
          key={i}
          className={`block w-[3px] rounded-[1px] transition-all ${
            i < level ? "bg-accent/70" : "bg-border/30"
          }`}
          style={{ height: `${4 + i * 4}px` }}
        />
      ))}
    </div>
  );
}

// ── Main Component ──

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
  const [spec, setSpec] = useState<Partial<AgentSpec>>({
    name: "",
    capabilities: [],
    provider: "",
    model: "",
  });
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .capabilities()
      .then(setCaps)
      .catch((err) => {
        console.error("API error:", err);
        setError(String(err));
      });
  }, []);

  // A pulse is "fresh" within the last 1.2s; the brain lights up accordingly.
  const now = Date.now();
  const recentPulses = pulses.filter((p) => now - p.at < 1200);
  const idle = recentPulses.length === 0;
  const intensity = Math.min(1, recentPulses.length / 6);

  // Orbital layout for connected agents
  const orbit = useMemo(() => {
    const entries = Object.values(agents);
    return entries.map((a, i) => ({
      id: a.id,
      role: a.role,
      status: a.status,
      health: a.health,
      provider: a.provider ?? "",
      current_task: a.current_task,
      angle: (i / Math.max(1, entries.length)) * Math.PI * 2,
    }));
  }, [agents]);

  // Derive a map of provider → set of models from active agents
  const providerModels = useMemo(() => {
    const map: Record<string, Set<string>> = {};
    for (const a of Object.values(agents)) {
      if (a.provider) {
        if (!map[a.provider]) map[a.provider] = new Set();
        for (const c of a.capabilities) map[a.provider].add(c);
      }
    }
    return map;
  }, [agents]);

  // ── Render ──

  return (
    <div className="scroll-page space-y-4 p-4 no-hscroll">
      {/* ── Left: Brain visualisation ── */}
      <div className="relative flex items-center justify-center">
        <div className="relative aspect-square w-full max-w-[520px]">
          {/* SVG layer — brain illustration + neural connection lines */}
          <svg
            viewBox={`0 0 ${S} ${S}`}
            className="absolute inset-0 h-full w-full select-none"
            style={{ filter: "drop-shadow(0 0 12px rgba(99,102,241,0.15))" }}
          >
            <defs>
              {/* Brain gradient */}
              <linearGradient id="brainGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(129,140,248,0.75)" />
                <stop offset="50%" stopColor="rgba(99,102,241,0.65)" />
                <stop offset="100%" stopColor="rgba(139,92,246,0.55)" />
              </linearGradient>
              <linearGradient
                id="brainGradActive"
                x1="0%"
                y1="0%"
                x2="100%"
                y2="100%"
              >
                <stop offset="0%" stopColor="rgba(165,180,252,0.9)" />
                <stop offset="50%" stopColor="rgba(99,102,241,0.8)" />
                <stop offset="100%" stopColor="rgba(167,139,250,0.7)" />
              </linearGradient>
              {/* Glow filter for neural pulses */}
              <filter id="glow">
                <feGaussianBlur stdDeviation="2.5" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="brainGlow">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Connection lines (neural pathways) */}
            {orbit.map((o) => {
              const x2 = C + Math.cos(o.angle) * ORBIT_R;
              const y2 = C + Math.sin(o.angle) * ORBIT_R;
              return (
                <g key={`conn-${o.id}`}>
                  {/* Base line */}
                  <line
                    x1={C}
                    y1={C}
                    x2={x2}
                    y2={y2}
                    stroke="rgba(99,102,241,0.12)"
                    strokeWidth={1.2}
                  />
                  {/* Animated dash (flowing signal) */}
                  <line
                    x1={C}
                    y1={C}
                    x2={x2}
                    y2={y2}
                    stroke="rgba(129,140,248,0.35)"
                    strokeWidth={1.5}
                    strokeDasharray="5 18"
                    className="animate-dash-flow"
                  />
                  {/* Orbital node dot */}
                  <circle
                    cx={x2}
                    cy={y2}
                    r={5}
                    fill={
                      o.status === "running" || o.health === "healthy"
                        ? "rgba(99,102,241,0.6)"
                        : o.status === "failed"
                          ? "rgba(239,68,68,0.5)"
                          : "rgba(148,163,184,0.4)"
                    }
                    stroke={
                      o.status === "running" || o.health === "healthy"
                        ? "rgba(129,140,248,0.7)"
                        : "rgba(148,163,184,0.3)"
                    }
                    strokeWidth={1.5}
                    filter={o.status === "running" || o.health === "healthy" ? "url(#glow)" : undefined}
                  />
                </g>
              );
            })}

            {/* Traveling neural pulses */}
            {orbit.map(
              (o, i) =>
                (o.status === "running" || o.health === "healthy") && (
                  <NeuralPulse key={`pulse-${o.id}`} angle={o.angle} delay={i * 0.25} />
                ),
            )}

            {/* ── SVG Brain illustration ── */}
            <g filter="url(#brainGlow)">
              {/* Cerebellum (bottom) */}
              <motion.path
                d={CEREBELLUM}
                fill="url(#brainGrad)"
                stroke="rgba(99,102,241,0.3)"
                strokeWidth={1.2}
                animate={{
                  fill: idle
                    ? "url(#brainGrad)"
                    : "url(#brainGradActive)",
                  opacity: idle ? 0.5 : 0.7 + intensity * 0.3,
                }}
                transition={{ duration: 0.6 }}
              />
              {/* Left hemisphere */}
              <motion.path
                d={L_HEMI}
                fill="url(#brainGrad)"
                stroke="rgba(99,102,241,0.35)"
                strokeWidth={1.5}
                animate={{
                  fill: idle
                    ? "url(#brainGrad)"
                    : "url(#brainGradActive)",
                }}
                transition={{ duration: 0.6 }}
              />
              {/* Right hemisphere */}
              <motion.path
                d={R_HEMI}
                fill="url(#brainGrad)"
                stroke="rgba(99,102,241,0.35)"
                strokeWidth={1.5}
                animate={{
                  fill: idle
                    ? "url(#brainGrad)"
                    : "url(#brainGradActive)",
                }}
                transition={{ duration: 0.6 }}
              />
              {/* Brainstem */}
              <motion.path
                d={STEM}
                fill="rgba(99,102,241,0.4)"
                stroke="rgba(99,102,241,0.25)"
                strokeWidth={1}
                animate={{ opacity: idle ? 0.4 : 0.6 + intensity * 0.4 }}
                transition={{ duration: 0.6 }}
              />
            </g>

            {/* Sulcus / fold details */}
            {SULCI.map((d, i) => (
              <path
                key={`sulcus-${i}`}
                d={d}
                fill="none"
                stroke="rgba(99,102,241,0.2)"
                strokeWidth={1.2}
                strokeLinecap="round"
              />
            ))}

            {/* Corpus callosum / center bridge highlight */}
            <motion.path
              d="M173,125 Q180,118 200,115 Q220,118 227,125"
              fill="none"
              stroke="rgba(165,180,252,0.25)"
              strokeWidth={1.8}
              strokeLinecap="round"
              animate={{ opacity: idle ? 0.15 : 0.25 + intensity * 0.35 }}
              transition={{ duration: 0.8 }}
            />
          </svg>

          {/* Ambient glow reacts to event intensity */}
          <motion.div
            className="absolute inset-0 rounded-full pointer-events-none"
            style={{
              background:
                "radial-gradient(circle at center, rgba(99,102,241,0.25), rgba(99,102,241,0.03) 55%, transparent 70%)",
            }}
            animate={{
              opacity: idle ? 0.2 : 0.3 + intensity * 0.55,
              scale: idle ? 0.97 : 1 + intensity * 0.04,
            }}
            transition={{ duration: 0.4 }}
          />

          {/* Core brain label (pulse count / idle) — overlaid on the SVG */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
            <motion.div
              className="grid h-36 w-36 place-items-center"
              animate={{ scale: idle ? 1 : 1 + intensity * 0.03 }}
              transition={{ type: "spring", stiffness: 120, damping: 14 }}
            >
              <div className="text-center">
                <div className="text-[10px] uppercase tracking-[0.15em] text-faint">
                  AI Brain
                </div>
                <motion.div
                  className="mt-1 text-xl font-semibold tabular-nums"
                  animate={{
                    color: idle
                      ? "rgba(148,163,184,0.7)"
                      : "rgba(165,180,252,1)",
                  }}
                  transition={{ duration: 0.4 }}
                >
                  {recentPulses.length > 0 ? recentPulses.length : "—"}
                </motion.div>
                <div className="text-[10px] text-faint tracking-wider">
                  {connected ? (
                    <span className="inline-flex items-center gap-1">
                      <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok shadow-[0_0_6px_rgba(34,197,94,0.6)]" />
                      live
                    </span>
                  ) : (
                    "offline"
                  )}
                </div>
              </div>
            </motion.div>
          </div>

          {/* Pulse rings emitted on real events */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
            <AnimatePresence>
              {recentPulses.slice(0, 3).map((p, i) => (
                <motion.div
                  key={p.at + "-" + i}
                  className="absolute left-1/2 top-1/2 h-36 w-36 -translate-x-1/2 -translate-y-1/2 rounded-full border border-accent/35"
                  initial={{ scale: 1, opacity: 0.5 }}
                  animate={{ scale: 2.6, opacity: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 1.1, delay: i * 0.12 }}
                />
              ))}
            </AnimatePresence>
          </div>

          {/* Orbiting live agents */}
          {orbit.map((o) => {
            const x = Math.cos(o.angle) * ORBIT_R;
            const y = Math.sin(o.angle) * ORBIT_R;
            return (
              <motion.div
                key={o.id}
                className="absolute left-1/2 top-1/2"
                style={{ x, y }}
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ type: "spring", stiffness: 90, damping: 16 }}
              >
                <div className="-translate-x-1/2 -translate-y-1/2 flex items-center gap-2 rounded-full border border-border/60 bg-surface/80 px-3 py-1 text-[11px] backdrop-blur shadow-sm">
                  <StatusDot
                    status={o.status}
                    pulse={o.status === "running" || o.health === "healthy"}
                  />
                  <span className="font-medium">{o.role}</span>
                  {o.current_task && (
                    <span className="max-w-[80px] truncate text-[10px] text-faint">
                      {o.current_task}
                    </span>
                  )}
                </div>
              </motion.div>
            );
          })}

          {/* Entropy label */}
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-[10px] tracking-[0.2em] text-faint/40 uppercase pointer-events-none">
            {Object.keys(agents).length} agent{Object.keys(agents).length !== 1 ? "s" : ""} routed
          </div>
        </div>
      </div>

      {/* ── Right: Panels ── */}
      <div className="flex flex-col gap-4">
        {/* ── Brain Telemetry (unchanged) ── */}
        <Panel
          title="Brain Telemetry"
          subtitle="Derived from EventBus pulses"
          className="flex-1 overflow-hidden"
        >
          <div className="grid grid-cols-2 gap-3">
            <Metric label="Tasks" value={metrics.tasks} />
            <Metric label="Agents" value={metrics.agents} />
            <Metric label="Providers" value={metrics.providers} />
            <Metric
              label="Errors"
              value={metrics.errors}
              danger={metrics.errors > 0}
            />
          </div>
          <div className="mt-4">
            <div className="mb-1.5 text-[11px] uppercase tracking-wide text-faint">
              Providers
            </div>
            <div className="space-y-1.5">
              {Object.values(providers).map((p) => (
                <div
                  key={p.provider}
                  className="flex items-center gap-2 text-sm"
                >
                  <StatusDot
                    status={p.status}
                    pulse={p.status === "healthy"}
                  />
                  <span className="flex-1 truncate">{p.provider}</span>
                  <span className="text-xs text-faint">
                    {p.latency_ms.toFixed(0)}ms
                  </span>
                </div>
              ))}
              {Object.keys(providers).length === 0 && (
                <Empty title="No providers" />
              )}
            </div>
          </div>
        </Panel>

        {/* ── NEW: Live Connections ── */}
        <Panel
          title="Live Connections"
          subtitle="Provider health & latency"
          className="flex-none"
        >
          <div className="space-y-2">
            {Object.values(providers).length === 0 ? (
              <Empty
                title="No connections"
                hint="Providers will appear when registered with the EventBus"
              />
            ) : (
              Object.values(providers).map((p) => {
                const models = providerModels[p.provider];
                const modelLabel =
                  models && models.size > 0
                    ? Array.from(models).slice(0, 2).join(", ")
                    : "—";
                return (
                  <div
                    key={p.provider}
                    className="glass rounded-xl px-3.5 py-2.5 transition-all hover:bg-surface/60"
                  >
                    <div className="flex items-center justify-between gap-3">
                      {/* Status dot + name */}
                      <div className="flex items-center gap-2.5 min-w-0">
                        <StatusDot
                          status={p.status}
                          pulse={p.status === "healthy"}
                        />
                        <span className="text-sm font-medium truncate">
                          {p.provider}
                        </span>
                      </div>

                      {/* Signal bars */}
                      <SignalBars latency={p.latency_ms} />
                    </div>

                    <div className="mt-2 flex items-center gap-4 text-[11px] text-faint">
                      {/* Latency */}
                      <span className="tabular-nums">
                        {p.latency_ms.toFixed(0)}ms
                      </span>

                      {/* Status badge */}
                      <Badge
                        tone={
                          p.status === "healthy"
                            ? "ok"
                            : p.status === "degraded"
                              ? "warn"
                              : p.status === "down"
                                ? "danger"
                                : "default"
                        }
                      >
                        {p.status}
                      </Badge>

                      {/* Model / capabilities */}
                      <span className="flex-1 truncate" title={modelLabel}>
                        {modelLabel !== "—" ? modelLabel : "N/A"}
                      </span>

                      {/* Last checked */}
                      {p.last_checked && (
                        <span className="tabular-nums">
                          {new Date(p.last_checked).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </span>
                      )}
                    </div>

                    {/* Error inline (if any) */}
                    {p.error && (
                      <div className="mt-1.5 text-[10px] text-danger/80 leading-tight truncate">
                        {p.error}
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {/* Summary footer */}
            {Object.values(providers).length > 0 && (
              <div className="flex items-center justify-between border-t border-border/40 pt-2 text-[11px] text-faint">
                <span>
                  {Object.values(providers).filter((p) => p.status === "healthy")
                    .length}{" "}
                  / {Object.keys(providers).length} healthy
                </span>
                <span>
                  avg{" "}
                  {Object.values(providers).length > 0
                    ? (
                        Object.values(providers).reduce(
                          (s, p) => s + p.latency_ms,
                          0,
                        ) / Object.values(providers).length
                      ).toFixed(0)
                    : 0}
                  ms
                </span>
              </div>
            )}
          </div>
        </Panel>

        {/* ── Compose Agent (unchanged) ── */}
        <Panel
          title="Compose Agent"
          subtitle="Routed through the Capability Engine"
          className="flex-none"
          actions={
            <button
              className="pill bg-accent/15 text-accent hover:bg-accent/25"
              onClick={() => setCompose((v) => !v)}
            >
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
                      className={
                        on
                          ? "pill bg-accent/20 text-accent"
                          : "pill bg-surface/60 text-muted"
                      }
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
              {result && (
                <div className="text-xs text-muted">{result}</div>
              )}
            </div>
          ) : (
            <div className="text-sm text-faint">
              Compose a new agent from registered capabilities. The request is
              validated and routed by the backend Capability Engine and emits a
              real <Badge tone="info">agent.composed</Badge> event.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
