"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Panel, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import type { AgentSpec, CapabilityInfo } from "@/lib/types";
import { NeuralSupercomputer } from "@/components/neural/neural-supercomputer";


// ── SVG Brain Geometry (compact) ──
const BS = 140; // mini-brain viewBox
const BC = 70;  // mini-brain center
const L_HEMI = "M70,15 C52,15 40,28 38,45 C36,58 42,68 50,73 L70,76 Z";
const R_HEMI = "M70,15 C88,15 100,28 102,45 C104,58 98,68 90,73 L70,76 Z";
const STEM = "M66,75 L66,92 C66,96 74,96 74,92 L74,75 Z";
const CEREBELLUM = "M54,63 C48,72 52,80 62,82 C68,83 72,81 70,78 C68,81 72,83 78,82 C88,80 92,72 86,63";
const SULCI = [
  "M54,38 Q60,44 58,52",
  "M58,34 Q63,40 61,48",
  "M50,46 Q55,52 53,58",
  "M86,38 Q80,44 82,52",
  "M82,34 Q77,40 79,48",
  "M90,46 Q85,52 87,58",
];

// Agent identity colors
const AGENT_COLORS: Record<string, { primary: string; secondary: string; glow: string }> = {
  claude: { primary: "rgba(217,128,255,0.7)", secondary: "rgba(217,128,255,0.3)", glow: "drop-shadow(0 0 6px rgba(217,128,255,0.25))" },
  hermes: { primary: "rgba(99,102,241,0.7)", secondary: "rgba(99,102,241,0.3)", glow: "drop-shadow(0 0 6px rgba(99,102,241,0.25))" },
  opencode: { primary: "rgba(34,197,94,0.7)", secondary: "rgba(34,197,94,0.3)", glow: "drop-shadow(0 0 6px rgba(34,197,94,0.25))" },
  codex: { primary: "rgba(251,191,36,0.7)", secondary: "rgba(251,191,36,0.3)", glow: "drop-shadow(0 0 6px rgba(251,191,36,0.25))" },
  gemini: { primary: "rgba(56,189,248,0.7)", secondary: "rgba(56,189,248,0.3)", glow: "drop-shadow(0 0 6px rgba(56,189,248,0.25))" },
  ollama: { primary: "rgba(251,146,60,0.7)", secondary: "rgba(251,146,60,0.3)", glow: "drop-shadow(0 0 6px rgba(251,146,60,0.25))" },
};
function agentColor(provider: string): { primary: string; secondary: string; glow: string } {
  const key = Object.keys(AGENT_COLORS).find((k) => provider.toLowerCase().includes(k));
  return key ? AGENT_COLORS[key] : { primary: "rgba(129,140,248,0.6)", secondary: "rgba(129,140,248,0.25)", glow: "drop-shadow(0 0 4px rgba(129,140,248,0.15))" };
}

// Agent skills derived from capabilities
interface AgentSkill {
  name: string;
  level: number;
  health: "healthy" | "degraded" | "unknown";
  usage: number;
  experience: number;
  confidence: number;
  success_rate: number;
}
function deriveSkills(caps: string[], recentTasks: number): AgentSkill[] {
  const activeCaps = caps && caps.length > 0 ? caps : ["general_execution"];
  return activeCaps.map((cap) => {
    const formattedName = cap.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
    return {
      name: formattedName,
      level: 0.95,
      health: "healthy" as const,
      usage: Math.min(1, Math.max(0.1, recentTasks / 10)),
      experience: 0.9,
      confidence: 0.95,
      success_rate: 0.98,
    };
  });
}


function Metric({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  return (
    <div className="glass rounded-xl px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${danger ? "text-danger" : "text-text"}`}>
        {value}
      </div>
    </div>
  );
}

/** Horizontal signal-strength bars for the Live Connections panel. */
function SignalBars({ latency }: { latency: number }) {
  const level = latency <= 50 ? 5 : latency <= 150 ? 4 : latency <= 400 ? 3 : latency <= 1200 ? 2 : 1;
  return (
    <div className="flex items-end gap-[2px]">
      {Array.from({ length: 5 }, (_, i) => (
        <span key={i}
          className={`block w-[3px] rounded-[1px] transition-all ${i < level ? "bg-accent/70" : "bg-border/30"}`}
          style={{ height: `${4 + i * 4}px` }} />
      ))}
    </div>
  );
}

// ── MiniBrain SVG component ──
function MiniBrain({
  provider,
  status,
  intensity,
  size = 80,
  label,
  taskCount = 0,
  latency = 0,
  reasoningDepth = 0,
}: {
  provider: string;
  status: string;
  intensity: number;
  size?: number;
  label?: string;
  taskCount?: number;
  latency?: number;
  reasoningDepth?: number;
}) {
  const col = agentColor(provider);
  const active = status === "running" || status === "healthy" || status === "healthy";
  const idle = !active;

  // Neural particles: positions for firing between hemispheres
  const particles = useMemo(() => {
    if (!active) return [];
    const n = 3 + Math.floor(intensity * 4);
    return Array.from({ length: n }, (_, i) => ({
      id: i,
      delay: i * 0.4,
      duration: 1.2 + Math.random() * 0.8,
      startX: BC + (i % 2 === 0 ? -1 : 1) * (12 + Math.random() * 10),
      startY: 20 + Math.random() * 35,
    }));
  }, [active, intensity]);

  return (
    <div className="flex flex-col items-center gap-1" style={{ width: size }}>
      <svg
        viewBox={`0 0 ${BS} ${BS}`}
        className="select-none"
        style={{ width: size, height: size, filter: col.glow }}
      >
        <defs>
          <linearGradient id={`brainGrad-${provider.replace(/\s/g, "")}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={active ? col.primary : col.secondary} />
            <stop offset="100%" stopColor={active ? col.secondary : "rgba(148,163,184,0.25)"} />
          </linearGradient>
          <filter id={`glow-${provider.replace(/\s/g, "")}`}>
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* Cerebellum */}
        <motion.path
          d={CEREBELLUM}
          fill={`url(#brainGrad-${provider.replace(/\s/g, "")})`}
          stroke={col.primary}
          strokeWidth={0.8}
          animate={{ opacity: idle ? 0.4 : 0.6 + intensity * 0.4 }}
          transition={{ duration: 0.6 }}
        />
        {/* Left hemisphere */}
        <motion.path
          d={L_HEMI}
          fill={`url(#brainGrad-${provider.replace(/\s/g, "")})`}
          stroke={col.primary}
          strokeWidth={1}
          animate={{ opacity: idle ? 0.5 : 0.7 + intensity * 0.3 }}
          transition={{ duration: 0.6 }}
        />
        {/* Right hemisphere */}
        <motion.path
          d={R_HEMI}
          fill={`url(#brainGrad-${provider.replace(/\s/g, "")})`}
          stroke={col.primary}
          strokeWidth={1}
          animate={{ opacity: idle ? 0.5 : 0.7 + intensity * 0.3 }}
          transition={{ duration: 0.6 }}
        />
        {/* Brainstem */}
        <motion.path
          d={STEM}
          fill={col.secondary}
          stroke={col.primary}
          strokeWidth={0.6}
          animate={{ opacity: idle ? 0.3 : 0.5 + intensity * 0.5 }}
          transition={{ duration: 0.6 }}
        />
        {/* Sulci */}
        {SULCI.map((d, i) => (
          <path key={i} d={d} fill="none" stroke={col.primary} strokeWidth={0.6} opacity={idle ? 0.15 : 0.2 + intensity * 0.3}
            strokeLinecap="round" />
        ))}
        {/* Neural particles firing between hemispheres */}
        {active && particles.map((p) => (
          <motion.circle
            key={p.id}
            r={1.2 + intensity * 0.8}
            fill={col.primary}
            filter={`url(#glow-${provider.replace(/\s/g, "")})`}
            animate={{
              cx: [p.startX, BC * 2 - p.startX, p.startX],
              cy: [p.startY, p.startY + (Math.random() - 0.5) * 10, p.startY],
              opacity: [0, 0.9, 0],
              scale: [0.5, 1.5, 0.5],
            }}
            transition={{
              duration: p.duration,
              ease: "easeInOut",
              repeat: Infinity,
              delay: p.delay,
            }}
          />
        ))}
        {/* Synaptic glow burst wave */}
        {active && intensity > 0.3 && (
          <motion.circle
            cx={BC} cy={BC}
            r={0}
            fill="none"
            stroke={col.primary}
            strokeWidth={0.4}
            opacity={0}
            animate={{
              r: [0, BS * 0.6],
              opacity: [0.3, 0],
            }}
            transition={{
              duration: 2,
              ease: "easeOut",
              repeat: Infinity,
              delay: 0.5,
            }}
          />
        )}
        {/* Active glow ring */}
        {active && (
          <motion.circle
            cx={BC} cy={BC} r={BC - 4}
            fill="none"
            stroke={col.primary}
            strokeWidth={1.2}
            opacity={0.3}
            animate={{ scale: [1, 1.04, 1], opacity: [0.2, 0.4, 0.2] }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          />
        )}
      </svg>
      {label && (
        <span className="text-[10px] font-medium text-center truncate max-w-full">{label}</span>
      )}
      {/* Live per-brain metrics */}
      {active && (
        <div className="flex items-center gap-2 text-[8px] text-faint/70 tabular-nums">
          {taskCount > 0 && <span className="flex items-center gap-0.5"><span className="inline-block w-1 h-1 rounded-full bg-ok/60" />{taskCount}</span>}
          {latency > 0 && <span>{latency.toFixed(0)}ms</span>}
          {reasoningDepth > 0 && <span className="text-faint/50">d{reasoningDepth}</span>}
        </div>
      )}
    </div>
  );
}

/** Animated connection flow between two mini-brains */
function ConnectionFlow({
  x1, y1, x2, y2,
  color,
  active = true,
  delay = 0,
}: {
  x1: number; y1: number; x2: number; y2: number;
  color: string;
  active?: boolean;
  delay?: number;
}) {
  return (
    <g>
      {/* Base connection line */}
      <line x1={x1} y1={y1} x2={x2} y2={y2}
        stroke={color} strokeWidth={1.2} opacity={active ? 0.2 : 0.08} />
      {/* Wave propagation glow */}
      {active && (
        <line x1={x1} y1={y1} x2={x2} y2={y2}
          stroke={color} strokeWidth={2.5} opacity={0.08}
          className="animate-pulse-slow" />
      )}
      {/* Animated dash flow */}
      {active && (
        <>
          <line x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={color} strokeWidth={1.8} opacity={0.4}
            strokeDasharray="4 14" className="animate-dash-flow" />
          {/* Traveling pulse dots (wave propagation) */}
          {[0, 0.25, 0.5].map((phase) => (
            <motion.circle
              key={phase}
              r={2.5 - phase * 1}
              fill={color}
              filter={phase === 0 ? "url(#pulseGlow)" : undefined}
              animate={{
                cx: [x1, x2, x1],
                cy: [y1, y2, y1],
                opacity: [0, 0.9, 0],
                scale: phase === 0 ? [0.8, 1.2, 0.8] : [0.5, 0.8, 0.5],
              }}
              transition={{
                duration: 2.8,
                ease: "easeInOut",
                repeat: Infinity,
                delay: delay + phase * 0.8,
              }}
            />
          ))}
        </>
      )}
    </g>
  );
}

/** Compute layout positions for N nodes in a force-directed-like grid */
function computeLayout(n: number, width: number, height: number): { x: number; y: number }[] {
  if (n === 0) return [];
  if (n === 1) return [{ x: width / 2, y: height / 2 }];
  if (n === 2) return [{ x: width * 0.3, y: height / 2 }, { x: width * 0.7, y: height / 2 }];
  // >2: arrange in a circle
  const cx = width / 2;
  const cy = height / 2;
  const r = Math.min(width, height) * 0.38;
  return Array.from({ length: n }, (_, i) => ({
    x: cx + r * Math.cos((i / n) * Math.PI * 2 - Math.PI / 2),
    y: cy + r * Math.sin((i / n) * Math.PI * 2 - Math.PI / 2),
  }));
}

// ── Main Component ──
export function AIBrain() {
  const pulses = useStore((s) => s.telemetry.pulses);
  const metrics = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);
  const agents = useStore((s) => s.agents);
  const providers = useStore((s) => s.providers);
  const containerRef = useRef<HTMLDivElement>(null);

  const [caps, setCaps] = useState<CapabilityInfo[]>([]);
  const [compose, setCompose] = useState(false);
  const [spec, setSpec] = useState<Partial<AgentSpec>>({
    name: "", capabilities: [], provider: "", model: "",
  });
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [dims, setDims] = useState({ w: 520, h: 440 });

  useEffect(() => {
    api.capabilities().then(setCaps).catch((err) => {
      setError(String(err));
    });
  }, []);

  // Track container size for layout
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      if (width > 0 && height > 0) setDims({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // A pulse is "fresh" within the last 1.2s
  const now = Date.now();
  const recentPulses = pulses.filter((p) => now - p.at < 1200);
  const idle = recentPulses.length === 0;
  const intensity = Math.min(1, recentPulses.length / 6);

  // Derive provider -> model capabilities (declared before agentNodes uses it)
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

  // Build agent list with providers as nodes
  const agentNodes = useMemo(() => {
    const provList = Object.values(providers);
    // Count active tasks per provider
    const taskCounts: Record<string, number> = {};
    for (const a of Object.values(agents)) {
      if (a.provider) {
        taskCounts[a.provider] = (taskCounts[a.provider] || 0) + 1;
      }
    }
    return provList.map((p) => {
      const provCaps = providerModels[p.provider];
      const depth = provCaps?.has("reasoning") ? 3 : provCaps?.has("planning") ? 2 : 1;
      return {
        id: p.provider,
        label: p.provider,
        status: p.status,
        latency: p.latency_ms,
        color: agentColor(p.provider).primary,
        taskCount: taskCounts[p.provider] || 0,
        reasoningDepth: depth,
      };
    });
  }, [providers, agents, providerModels]);

  // Layout positions
  const positions = useMemo(() =>
    computeLayout(agentNodes.length, dims.w, dims.h),
    [agentNodes.length, dims.w, dims.h]
  );

  // Determine which agents are "bound" (connected) - all healthy providers are bound
  const bindings = useMemo(() => {
    const b: { from: number; to: number }[] = [];
    if (agentNodes.length < 2) return b;
    for (let i = 0; i < agentNodes.length; i++) {
      for (let j = i + 1; j < agentNodes.length; j++) {
        // Connect if both are healthy/running
        const active = agentNodes[i].status === "healthy" &&
                       agentNodes[j].status === "healthy";
        if (active) b.push({ from: i, to: j });
      }
    }
    // If no active pairs, connect nearest neighbors
    if (b.length === 0 && agentNodes.length >= 2) {
      for (let i = 0; i < agentNodes.length - 1; i++) {
        b.push({ from: i, to: i + 1 });
      }
      if (agentNodes.length > 2) b.push({ from: 0, to: agentNodes.length - 1 });
    }
    return b;
  }, [agentNodes]);

  // ── Render ──
  return (
    <div className="grid h-full grid-cols-12 gap-4 p-4">
      {/* ── Left: Dynamic 3D Neural Supercomputer ── */}
      <div className="col-span-7 relative h-full min-h-[450px]">
        <NeuralSupercomputer />
      </div>


      {/* ── Right: Panels (unchanged) ── */}
      <div className="col-span-5 flex flex-col gap-4 overflow-y-auto">
        {/* Brain Telemetry */}
        <Panel title="Brain Telemetry" subtitle="Derived from EventBus pulses" className="flex-1 overflow-hidden">
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

        {/* Live Connections */}
        <Panel title="Live Connections" subtitle="Provider health & latency" className="flex-none">
          <div className="space-y-2">
            {Object.values(providers).length === 0 ? (
              <Empty title="No connections" hint="Providers will appear when registered with the EventBus" />
            ) : (
              Object.values(providers).map((p) => {
                const models = providerModels[p.provider];
                const modelLabel = models && models.size > 0 ? Array.from(models).slice(0, 2).join(", ") : "—";
                const col = agentColor(p.provider);
                return (
                  <div key={p.provider} className="glass rounded-xl px-3.5 py-2.5 transition-all hover:bg-surface/60">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: col.primary }} />
                        <span className="text-sm font-medium truncate">{p.provider}</span>
                      </div>
                      <SignalBars latency={p.latency_ms} />
                    </div>
                    <div className="mt-2 flex items-center gap-4 text-[11px] text-faint">
                      <span className="tabular-nums">{p.latency_ms.toFixed(0)}ms</span>
                      <Badge tone={p.status === "healthy" ? "ok" : p.status === "degraded" ? "warn" : p.status === "down" ? "danger" : "default"}>{p.status}</Badge>
                      <span className="flex-1 truncate" title={modelLabel}>{modelLabel !== "—" ? modelLabel : "N/A"}</span>
                      {p.last_checked && (
                        <span className="tabular-nums">{new Date(p.last_checked).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
                      )}
                    </div>
                    {p.error && <div className="mt-1.5 text-[10px] text-danger/80 leading-tight truncate">{p.error}</div>}
                  </div>
                );
              })
            )}
            {Object.values(providers).length > 0 && (
              <div className="flex items-center justify-between border-t border-border/40 pt-2 text-[11px] text-faint">
                <span>{Object.values(providers).filter((p) => p.status === "healthy").length} / {Object.keys(providers).length} healthy</span>
                <span>avg {Object.values(providers).length > 0
                  ? (Object.values(providers).reduce((s, p) => s + p.latency_ms, 0) / Object.values(providers).length).toFixed(0)
                  : 0} ms</span>
              </div>
            )}
          </div>
        </Panel>

        {/* Agent Skills */}
        <Panel title="Agent Skills" subtitle="Capability-derived proficiency" className="flex-none">
          {Object.keys(agents).length === 0 ? (
            <Empty title="No agents" hint="Agents appear when they register with the EventBus" />
          ) : (
            <div className="space-y-3 max-h-[300px] overflow-y-auto">
              {Object.values(agents).map((agent) => {
                const skills = deriveSkills(agent.capabilities ?? [], 0);
                const color = agentColor(agent.provider ?? "");
                return (
                  <div key={agent.id} className="glass rounded-xl px-3 py-2.5">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color.primary, filter: color.glow }} />
                      <span className="text-xs font-medium">{agent.role ?? agent.id}</span>
                      {agent.provider && <span className="text-[10px] text-faint">via {agent.provider}</span>}
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                      {skills.slice(0, 4).map((sk) => (
                        <div key={sk.name} className="text-[10px]">
                          <div className="flex items-center justify-between mb-0.5">
                            <span className="text-faint">{sk.name}</span>
                            <span className="tabular-nums font-medium" style={{ color: color.primary }}>{(sk.level * 100).toFixed(0)}%</span>
                          </div>
                          <div className="h-[2px] rounded-full bg-border/30 overflow-hidden">
                            <motion.div className="h-full rounded-full" style={{ backgroundColor: color.primary }}
                              initial={{ width: 0 }} animate={{ width: `${sk.level * 100}%` }}
                              transition={{ duration: 0.8, ease: "easeOut" }} />
                          </div>
                          <div className="mt-0.5 flex gap-1.5 text-[8px] text-faint/60">
                            <span>H: {sk.health}</span>
                            <span>U: {(sk.usage * 100).toFixed(0)}%</span>
                            <span>SR: {(sk.success_rate * 100).toFixed(0)}%</span>
                            <span>E: {(sk.experience * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        {/* Compose Agent */}
        <Panel title="Compose Agent" subtitle="Routed through the Capability Engine" className="flex-none"
          actions={<button className="pill bg-accent/15 text-accent hover:bg-accent/25" onClick={() => setCompose((v) => !v)}>
            {compose ? "Close" : "New"}
          </button>}
        >
          {compose ? (
            <div className="space-y-3">
              <input className="w-full rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
                placeholder="Name (e.g. planner)" value={spec.name}
                onChange={(e) => setSpec({ ...spec, name: e.target.value })} />
              <div className="flex flex-wrap gap-1.5">
                {caps.map((c) => {
                  const on = spec.capabilities?.includes(c.name);
                  return (
                    <button key={c.name} onClick={() =>
                      setSpec((s) => ({ ...s, capabilities: on ? (s.capabilities ?? []).filter((x) => x !== c.name) : [...(s.capabilities ?? []), c.name] }))
                    } className={on ? "pill bg-accent/20 text-accent" : "pill bg-surface/60 text-muted"}>
                      {c.name}
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2">
                <input className="flex-1 rounded-lg border border-border/60 bg-surface/50 px-3 py-2 text-sm outline-none focus:border-accent/60"
                  placeholder="Provider (optional)" value={spec.provider}
                  onChange={(e) => setSpec({ ...spec, provider: e.target.value })} />
                <button className="pill bg-accent/20 text-accent hover:bg-accent/30"
                  onClick={async () => {
                    try {
                      const r = await api.composeAgent(spec as AgentSpec);
                      setResult(`Composed ${r.name} (${r.id})`);
                    } catch (e) { setResult("Failed: " + (e as Error).message); }
                  }}>
                  Compose
                </button>
              </div>
              {result && <div className="text-xs text-muted">{result}</div>}
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

export { AIBrain as AiBrain };
export default AIBrain;
