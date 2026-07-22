"use client";

/**
 * AI Brain 2.0 — Neural Intelligence Dashboard
 *
 * A living digital consciousness view combining:
 *   - Mini 3D neural scene showing all provider brains
 *   - Real-time telemetry panels derived from EventBus data
 *   - Provider health, event stream, and system metrics
 *
 * Architecture: React Three Fiber embedded scene + HTML overlay panels
 * Data: All from Zustand store (WebSocket-fed EventBus)
 */

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Line,
  Html,
  MeshDistortMaterial,
  Text as DreiText,
} from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import * as THREE from "three";
import { motion, AnimatePresence } from "framer-motion";
import { useStore, selectMetrics } from "@/lib/store";
import type { AgentNode, EventEnvelope } from "@/lib/types";
import { Panel } from "@/components/ui/responsive";

// ─────────────────────────────────────────────
//  DESIGN CONSTANTS
// ─────────────────────────────────────────────

const PALETTE = {
  central: "#818cf8",
  reasoning: "#a855f7",
  busy: "#f97316",
  healthy: "#22c55e",
  idle: "#64748b",
  error: "#ef4444",
  offline: "#374151",
  bg: "#080a10",
};

const STATUS_COLORS: Record<string, string> = {
  running: PALETTE.busy,
  healthy: PALETTE.healthy,
  completed: PALETTE.healthy,
  failed: PALETTE.error,
  recovered: PALETTE.reasoning,
  idle: PALETTE.idle,
  degraded: "#f59e0b",
  down: PALETTE.offline,
  unknown: PALETTE.idle,
};

// ─────────────────────────────────────────────
//  MINI BRAIN — simplified 3D brain for scene
// ─────────────────────────────────────────────

function MiniBrain({
  position = [0, 0, 0],
  scale = 1,
  color = PALETTE.central,
  activity = "idle",
}: {
  position?: [number, number, number];
  scale?: number;
  color?: string;
  activity?: string;
}) {
  const groupRef = useRef<THREE.Group>(null!);
  const meshRef = useRef<THREE.Mesh>(null!);

  const p = useMemo(() => {
    switch (activity) {
      case "busy":
        return { rate: 1.4, amp: 0.9, rot: 0.12, glow: 0.6 };
      case "reasoning":
        return { rate: 0.8, amp: 0.7, rot: 0.08, glow: 0.45 };
      case "offline":
        return { rate: 0.1, amp: 0.02, rot: 0.01, glow: 0.02 };
      default:
        return { rate: 0.3, amp: 0.2, rot: 0.02, glow: 0.1 };
    }
  }, [activity]);

  useFrame((state) => {
    if (!groupRef.current) return;
    groupRef.current.rotation.y += 0.01 * p.rot;
    if (meshRef.current) {
      const breathe = 1 + Math.sin(state.clock.elapsedTime * p.rate) * 0.02 * p.amp;
      meshRef.current.scale.setScalar(breathe);
      (meshRef.current.material as THREE.MeshPhysicalMaterial).emissiveIntensity =
        0.1 + (Math.sin(state.clock.elapsedTime * p.rate * 1.5) * 0.5 + 0.5) * p.glow;
    }
  });

  return (
    <group ref={groupRef} position={position} scale={[scale, scale, scale]}>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[0.8, 1]} />
        <meshPhysicalMaterial
          color="#141438"
          emissive={color}
          emissiveIntensity={0.2}
          metalness={0.4}
          roughness={0.3}
          clearcoat={0.3}
          transparent
          opacity={0.9}
        />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.85, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.06} />
      </mesh>
    </group>
  );
}

// ─────────────────────────────────────────────
//  MINI NEURAL LINK
// ─────────────────────────────────────────────

function MiniLink({
  from, to, active,
}: {
  from: [number, number, number];
  to: [number, number, number];
  active?: boolean;
}) {
  const points = useMemo(() => {
    const f = new THREE.Vector3(...from);
    const t = new THREE.Vector3(...to);
    const mid = f.clone().add(t).multiplyScalar(0.5);
    mid.y += 0.3;
    const curve = new THREE.QuadraticBezierCurve3(f, mid, t);
    return curve.getPoints(16);
  }, [from, to]);

  return (
    <Line
      points={points}
      color={active ? PALETTE.central : "#1f2633"}
      lineWidth={active ? 1 : 0.3}
      transparent
      opacity={active ? 0.4 : 0.08}
    />
  );
}

// ─────────────────────────────────────────────
//  MINI SCENE
// ─────────────────────────────────────────────

function MiniConstellation() {
  const agents = useStore((s) => s.agents);
  const events = useStore((s) => s.events);

  const providerList = useMemo(() => Object.values(agents), [agents]);
  const positions = useMemo(() => {
    const count = providerList.length;
    if (count === 0) return [];
    const phi = Math.PI * (3 - Math.sqrt(5));
    return providerList.map((_, i) => {
      const y = 1 - (i / (count - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const theta = phi * i;
      return [Math.cos(theta) * r * 2.8, y * 2.8, Math.sin(theta) * r * 2.8] as [number, number, number];
    });
  }, [providerList]);

  const [pulseIntensity, setPulseIntensity] = useState(0.3);
  useEffect(() => {
    if (events.length > 0) {
      setPulseIntensity(1);
      const t = setTimeout(() => setPulseIntensity(0.3), 400);
      return () => clearTimeout(t);
    }
  }, [events.length]);

  return (
    <>
      <color attach="background" args={[PALETTE.bg]} />
      <ambientLight intensity={0.2} />
      <directionalLight position={[2, 3, 2]} intensity={0.3} color={PALETTE.central} />

      {/* Central brain */}
      <MiniBrain color={PALETTE.central} scale={0.6} activity={providerList.some(a => a.status === "running") ? "busy" : "idle"} />

      {/* Provider brains */}
      {providerList.map((a, i) => {
        const pos = positions[i];
        if (!pos) return null;
        const activity = a.status === "running" ? "busy" : a.status === "failed" ? "offline" : "idle";
        return (
          <group key={a.id}>
            <MiniBrain
              position={pos}
              scale={0.3}
              color={STATUS_COLORS[a.status] ?? PALETTE.idle}
              activity={activity}
            />
            <MiniLink from={[0, 0, 0]} to={pos} active={a.status === "running"} />
          </group>
        );
      })}

      {/* Orbit controls - disabled auto-rotate in this mini view */}
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        enableRotate={false}
        autoRotate
        autoRotateSpeed={0.2}
      />
    </>
  );
}

// ─────────────────────────────────────────────
//  METRIC CARD
// ─────────────────────────────────────────────

function MetricCard({
  label, value, danger, icon, trend,
}: {
  label: string;
  value: string | number;
  danger?: boolean;
  icon?: string;
  trend?: "up" | "down" | "stable";
}) {
  return (
    <motion.div
      className="rounded-xl border border-border/30 bg-surface/30 p-3.5 backdrop-blur-sm"
      whileHover={{ scale: 1.02 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="text-[10px] uppercase tracking-wider text-faint/70">{label}</div>
        {icon && <span className="text-[14px] opacity-50">{icon}</span>}
      </div>
      <div className={`text-xl font-semibold tabular-nums tracking-tight ${danger ? "text-danger" : "text-white/90"}`}>
        {value}
      </div>
      {trend && (
        <div className={`text-[9px] mt-0.5 ${trend === "up" ? "text-[#22c55e]" : trend === "down" ? "text-danger" : "text-faint"}`}>
          {trend === "up" ? "↑" : trend === "down" ? "↓" : "→"} {trend}
        </div>
      )}
    </motion.div>
  );
}

// ─────────────────────────────────────────────
//  EVENT STREAM
// ─────────────────────────────────────────────

function EventStream({ events }: { events: EventEnvelope[] }) {
  const recent = events.slice(0, 12);
  return (
    <div className="h-48 space-y-0.5 overflow-y-auto text-[10px] font-mono">
      {recent.length === 0 && (
        <div className="text-faint/50 italic p-2">No events yet</div>
      )}
      {recent.map((e) => (
        <div
          key={e.id}
          className="flex items-center gap-2 rounded px-2 py-1 hover:bg-surface/30 transition-colors"
        >
          <span className="h-1 w-1 shrink-0 rounded-full bg-accent/40" />
          <span className="shrink-0 text-faint/60">
            {new Date(e.timestamp || Date.now()).toLocaleTimeString()}
          </span>
          <span className="shrink-0 text-accent/80">{e.topic}</span>
          <span className="truncate text-faint/50">
            {JSON.stringify(e.payload).slice(0, 40)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
//  PROVIDER HEALTH LIST
// ─────────────────────────────────────────────

function ProviderHealthList({ agents }: { agents: Record<string, AgentNode> }) {
  const list = Object.values(agents);
  return (
    <div className="space-y-1.5">
      {list.length === 0 && (
        <div className="text-faint/50 italic text-[11px] p-2">No providers</div>
      )}
      {list.map((a) => {
        const color = STATUS_COLORS[a.status] ?? PALETTE.idle;
        return (
          <div
            key={a.id}
            className="flex items-center justify-between rounded-lg border border-border/20 bg-surface/20 px-3 py-2 text-[11px]"
          >
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              <span className="font-medium text-white/80">{a.role}</span>
              {a.provider && (
                <span className="text-faint">@{a.provider}</span>
              )}
            </div>
            <div className="flex items-center gap-3">
              {a.current_task && (
                <span className="max-w-[100px] truncate text-faint">{a.current_task}</span>
              )}
              <span className="capitalize text-faint/80">{a.status}</span>
              {a.health && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full border ${
                  a.health === "healthy" ? "border-[#22c55e]/30 text-[#22c55e]" :
                  a.health === "degraded" ? "border-[#f59e0b]/30 text-[#f59e0b]" :
                  "border-danger/30 text-danger"
                }`}>
                  {a.health}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────
//  ACTIVITY METER
// ─────────────────────────────────────────────

function ActivityMeter({ pulses }: { pulses: { topic: string; at: number }[] }) {
  const now = Date.now();
  const recent = pulses.filter((p) => now - p.at < 5000).length;

  // 5 bars representing last 5 seconds
  const bars = useMemo(() => {
    const b = [0, 0, 0, 0, 0];
    pulses.forEach((p) => {
      const diff = now - p.at;
      if (diff < 1000) b[0]++;
      else if (diff < 2000) b[1]++;
      else if (diff < 3000) b[2]++;
      else if (diff < 4000) b[3]++;
      else if (diff < 5000) b[4]++;
    });
    return b;
  }, [pulses, now]);

  const max = Math.max(...bars, 1);

  return (
    <div className="flex items-end gap-1.5 h-12">
      {bars.map((v, i) => (
        <div
          key={i}
          className="w-3 rounded-t-sm transition-all bg-gradient-to-t from-accent/40 to-accent/80"
          style={{
            height: `${(v / max) * 100}%`,
            opacity: 0.3 + (v / Math.max(max, 1)) * 0.7,
          }}
        />
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────
//  MAIN COMPONENT
// ─────────────────────────────────────────────

export function AIBrain() {
  const agents = useStore((s) => s.agents);
  const events = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const agentCount = Object.keys(agents).length;
  const eventCount = events.length;

  // Recent pulses for activity meter
  const now = Date.now();
  const recentPulses = telemetry.pulses.filter((p) => now - p.at < 1200);
  const isBraveActive = recentPulses.length > 0;
  const brainIntensity = Math.min(1, recentPulses.length / 6);

  return (
    <div className="scroll-page space-y-4 p-4 no-hscroll">

      {/* ── Top: 3D Neural Mini-Scene ── */}
      <div className="relative h-[240px] w-full overflow-hidden rounded-2xl border border-border/40 bg-[#080a10]">
        {mounted && (
          <Canvas
            dpr={[1, 1.5]}
            gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
            camera={{ position: [5, 3, 5], fov: 50, near: 0.1, far: 15 }}
          >
            <MiniConstellation />
            <EffectComposer multisampling={0}>
              <Bloom luminanceThreshold={0.15} luminanceSmoothing={0.9} intensity={0.6} mipmapBlur />
              <ChromaticAberration offset={new THREE.Vector2(0.001, 0.001)} />
            </EffectComposer>
          </Canvas>
        )}

        {/* Overlay live status badge */}
        <div className="absolute top-3 left-3 flex items-center gap-2 rounded-lg bg-surface/60 backdrop-blur-md px-3 py-1.5 border border-border/30">
          <span className={`h-2 w-2 rounded-full ${connected ? "bg-[#22c55e] shadow-[0_0_8px_rgba(34,197,94,0.6)]" : "bg-[#ef4444]"}`} />
          <span className="text-[11px] font-mono text-white/80">
            {connected ? "Consciousness Online" : "Offline"}
          </span>
        </div>

        {/* Brain intensity indicator */}
        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          <span className="text-[9px] text-faint font-mono">Brain Activity</span>
          <div className="flex gap-0.5">
            {[0, 1, 2, 3].map((i) => (
              <motion.span
                key={i}
                className="block h-3 w-1 rounded-sm"
                animate={{
                  background: i < Math.ceil(brainIntensity * 4)
                    ? "rgba(129,140,248,0.8)"
                    : "rgba(129,140,248,0.15)",
                  scale: i < Math.ceil(brainIntensity * 4) ? [1, 1.2, 1] : 1,
                }}
                transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 1: Key Metrics ── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Providers" value={agentCount} icon="🧠" trend={agentCount > 0 ? "stable" : undefined} />
        <MetricCard label="Active Tasks" value={telemetry.tasks} icon="⚡" trend={telemetry.tasks > 0 ? "up" : "stable"} />
        <MetricCard label="Connected Providers" value={telemetry.providers} icon="🔗" />
        <MetricCard label="Errors" value={telemetry.errors} icon="⚠️" danger={telemetry.errors > 0} trend={telemetry.errors > 0 ? "down" : undefined} />
      </div>

      {/* ── Row 2: Telemetry + Activity ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Brain Telemetry */}
        <Panel
          title="Brain Telemetry"
          subtitle="Derived from EventBus pulses"
          className="lg:col-span-1"
        >
          <div className="grid grid-cols-2 gap-2 mb-3">
            <div className="rounded-lg bg-surface/20 p-2.5 text-center">
              <div className="text-[9px] uppercase tracking-wider text-faint">Pipelines</div>
              <div className="text-lg font-semibold text-white/90">{telemetry.pipelines}</div>
            </div>
            <div className="rounded-lg bg-surface/20 p-2.5 text-center">
              <div className="text-[9px] uppercase tracking-wider text-faint">Cost</div>
              <div className="text-lg font-semibold text-white/90">${telemetry.cost.toFixed(4)}</div>
            </div>
            <div className="rounded-lg bg-surface/20 p-2.5 text-center">
              <div className="text-[9px] uppercase tracking-wider text-faint">Latency</div>
              <div className="text-lg font-semibold text-white/90">{telemetry.latency.toFixed(1)}ms</div>
            </div>
            <div className="rounded-lg bg-surface/20 p-2.5 text-center">
              <div className="text-[9px] uppercase tracking-wider text-faint">Tokens</div>
              <div className="text-lg font-semibold text-white/90">{telemetry.tokens.toLocaleString()}</div>
            </div>
          </div>

          {/* Activity pulse meter */}
          <div className="border-t border-border/20 pt-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] uppercase tracking-wider text-faint">Recent Activity</span>
              <span className="text-[10px] font-mono text-accent">{recentPulses.length} pulses/sec</span>
            </div>
            <ActivityMeter pulses={telemetry.pulses} />
          </div>
        </Panel>

        {/* Event Stream */}
        <Panel
          title="Event Stream"
          subtitle="Live EventBus"
          className="lg:col-span-1"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[9px] text-faint">{events.length} total events</span>
            {connected && <span className="h-1.5 w-1.5 rounded-full bg-[#22c55e]" />}
          </div>
          <EventStream events={events} />
        </Panel>

        {/* Memory & Audit quick view */}
        <Panel
          title="System State"
          subtitle="Runtime metrics"
          className="lg:col-span-1"
        >
          <div className="space-y-2 text-[11px]">
            <div className="flex justify-between">
              <span className="text-faint">WebSocket</span>
              <span className={connected ? "text-[#22c55e]" : "text-danger"}>
                {connected ? "Connected" : "Disconnected"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-faint">Cache Size</span>
              <span className="text-white/80">{events.length} events</span>
            </div>
            <div className="flex justify-between">
              <span className="text-faint">Provider Count</span>
              <span className="text-white/80">{Object.keys(telemetry.providers).length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-faint">Memory Items</span>
              <span className="text-white/80">{telemetry.pipelines}</span>
            </div>
          </div>

          <div className="mt-4 border-t border-border/20 pt-3">
            <div className="text-[10px] uppercase tracking-wider text-faint mb-2">Provider Fleet</div>
            <ProviderHealthList agents={agents} />
          </div>
        </Panel>
      </div>

      {/* ── Provider Fleet (expanded) ── */}
      <Panel
        title="Provider Fleet"
        subtitle="All connected runtimes"
      >
        <ProviderHealthList agents={agents} />
      </Panel>

      {/* Footer status */}
      <div className="flex items-center justify-between text-[9px] text-faint/50 border-t border-border/10 pt-3">
        <span>AgenticOS v1.0.0-rc1 · Neural Intelligence Dashboard</span>
        <span>
          {connected ? "Live · " : "Offline · "}
          {eventCount > 0 ? `${eventCount} events since connect` : "awaiting events"}
        </span>
      </div>
    </div>
  );
}
