"use client";

/**
 * Agent Constellation 2.0 — Living Neural Intelligence Visualization
 *
 * A cinematic 3D holographic command center where:
 *   - The central brain = Mission Control orchestrator
 *   - Every discovered provider = an orbiting holographic brain
 *   - Neural links (mesh) = real communication channels
 *   - Task packets = animated pulses traveling along active routes
 *   - Everything driven by live store/WebSocket data
 *
 * Architecture: React Three Fiber + post-processing + force layout
 * Visual DNA: JARVIS / NASA Mission Control / Apple Vision Pro / TRON
 */

import {
  useEffect, useMemo, useRef, useState, useCallback, memo,
} from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Text,
  Html,
  Line,
  MeshDistortMaterial,
  Billboard,
} from "@react-three/drei";
import {
  EffectComposer,
  Bloom,
  ChromaticAberration,
  Noise,
} from "@react-three/postprocessing";
import * as THREE from "three";
import { useStore } from "@/lib/store";
import type { AgentNode, ProviderHealthRecord, TaskNode } from "@/lib/types";

// ─────────────────────────────────────────────
//  DESIGN TOKENS
// ─────────────────────────────────────────────

const PALETTE = {
  central: "#818cf8",   // indigo-400 — Mission Control brain
  provider: "#6366f1",  // indigo-500 — provider brains
  healthy: "#22c55e",
  busy: "#f97316",
  reasoning: "#a855f7",
  idle: "#64748b",
  error: "#ef4444",
  offline: "#374151",
  link: "#4f6cff",
  linkActive: "#818cf8",
  linkDim: "#1f2633",
  bg: "#080a10",
};

const BRAIN_COLORS: Record<string, string> = {
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

const CENTRAL_BRAIN_RADIUS = 1.6;
const PROVIDER_ORBIT_RADIUS = 8;
const STAR_COUNT = 1500;
const MAX_TASK_PACKETS = 40;

// ─────────────────────────────────────────────
//  UTILITY
// ─────────────────────────────────────────────

/** Fibonacci sphere for even 3D distribution */
function fibSphere(
  count: number,
  radius = PROVIDER_ORBIT_RADIUS,
): [number, number, number][] {
  if (count === 0) return [];
  const phi = Math.PI * (3 - Math.sqrt(5));
  const out: [number, number, number][] = [];
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    out.push([Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius]);
  }
  return out;
}

/** Create a brain hemisphere geometry with gyri/sulci displacement */
function createHemisphereGeometry(
  segments = 28,
  radius = 1,
  side: "left" | "right",
  complexity = 1,
) {
  const geo = new THREE.SphereGeometry(radius, segments, segments, 0, Math.PI, 0, Math.PI / 2);
  const pos = geo.attributes.position.array as Float32Array;
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2];
    // Squash top for brain-like shape
    const squash = y > 0 ? 1 - y * 0.35 * complexity : 1;
    pos[i] = x * squash;
    pos[i + 2] = z * squash;
    // Gyri bumps
    const noise =
      Math.sin(x * 8) * Math.cos(z * 7) * 0.07 * complexity +
      Math.sin((x + z) * 6) * 0.04 * complexity +
      Math.cos(x * 5 + z * 5) * 0.03 * complexity;
    pos[i] += x * noise;
    pos[i + 1] += y * noise * 0.4;
    pos[i + 2] += z * noise;
    // Clip to hemisphere
    if (side === "left" && x > 0) pos[i] = -pos[i];
    if (side === "right" && x < 0) pos[i] = -pos[i];
  }
  geo.computeVertexNormals();
  return geo;
}

/** Blend hex color strings */
function hexBlend(a: string, b: string, t: number): string {
  const ah = parseInt(a.replace("#", ""), 16);
  const bh = parseInt(b.replace("#", ""), 16);
  const rr = Math.round(((ah >> 16) & 0xff) * (1 - t) + ((bh >> 16) & 0xff) * t);
  const gg = Math.round(((ah >> 8) & 0xff) * (1 - t) + ((bh >> 8) & 0xff) * t);
  const bb = Math.round((ah & 0xff) * (1 - t) + (bh & 0xff) * t);
  return `#${((1 << 24) | (rr << 16) | (gg << 8) | bb).toString(16).slice(1)}`;
}

// ─────────────────────────────────────────────
//  BACKGROUND — Star field + hex grid
// ─────────────────────────────────────────────

function StarField() {
  const ref = useRef<THREE.Points>(null!);
  const [geo] = useState(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(STAR_COUNT * 3);
    const col = new Float32Array(STAR_COUNT * 3);
    for (let i = 0; i < STAR_COUNT; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 5 + Math.random() * 40;
      pos[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
      pos[i * 3 + 1] = Math.sin(phi) * Math.sin(theta) * r;
      pos[i * 3 + 2] = Math.cos(phi) * r;
      const c = 0.15 + Math.random() * 0.3;
      col[i * 3] = c * 0.8;
      col[i * 3 + 1] = c * 0.85;
      col[i * 3 + 2] = c;
    }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    return g;
  });

  useFrame((_, delta) => {
    ref.current.rotation.y += delta * 0.003;
    ref.current.rotation.x += delta * 0.001;
  });

  return (
    <points ref={ref} geometry={geo}>
      <pointsMaterial
        size={0.06}
        vertexColors
        transparent
        opacity={0.6}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function HexGrid({ y = -6 }: { y?: number }) {
  return (
    <group position={[0, y, 0]}>
      <gridHelper args={[30, 30, "#1a1e30", "#0f1220"]} />
    </group>
  );
}

// ─────────────────────────────────────────────
//  HOLOGRAPHIC BRAIN (shared by central + provider)
// ─────────────────────────────────────────────

interface BrainProps {
  position?: [number, number, number];
  scale?: number;
  color?: string;
  pulseSpeed?: number;
  pulseIntensity?: number;
  activity?: "idle" | "thinking" | "reasoning" | "busy" | "offline";
  isCentral?: boolean;
}

const BrainGeometry = memo(function BrainGeometry({
  hemisphere,
  color,
  emissiveIntensity = 0.4,
}: {
  hemisphere: "left" | "right";
  color: string;
  emissiveIntensity?: number;
}) {
  const [geo] = useState(() =>
    createHemisphereGeometry(28, 1, hemisphere, 1),
  );
  return (
    <mesh geometry={geo} position={hemisphere === "left" ? [-0.04, 0.08, 0] : [0.04, 0.08, 0]}>
      <meshPhysicalMaterial
        color="#141438"
        emissive={color}
        emissiveIntensity={emissiveIntensity}
        metalness={0.3}
        roughness={0.4}
        clearcoat={0.4}
        transparent
        opacity={0.92}
      />
    </mesh>
  );
});

function HolographicBrain({
  position = [0, 0, 0],
  scale = 1,
  color = PALETTE.provider,
  pulseSpeed = 1,
  pulseIntensity = 0.5,
  activity = "idle",
  isCentral = false,
}: BrainProps) {
  const groupRef = useRef<THREE.Group>(null!);
  const glowRef = useRef<THREE.Mesh>(null!);
  const leftRef = useRef<THREE.Mesh>(null!);
  const rightRef = useRef<THREE.Mesh>(null!);
  const emitRef = useRef<THREE.Points>(null!);

  // Activity → animation params
  const activityParams = useMemo(() => {
    switch (activity) {
      case "thinking":
        return { breatheRate: 0.6, pulseAmp: 0.6, rotSpeed: 0.06, glow: 0.4, emitSpeed: 0.8 };
      case "reasoning":
        return { breatheRate: 0.9, pulseAmp: 0.8, rotSpeed: 0.1, glow: 0.55, emitSpeed: 1.2 };
      case "busy":
        return { breatheRate: 1.3, pulseAmp: 1, rotSpeed: 0.15, glow: 0.7, emitSpeed: 1.8 };
      case "offline":
        return { breatheRate: 0.2, pulseAmp: 0.05, rotSpeed: 0.01, glow: 0.05, emitSpeed: 0 };
      default:
        return { breatheRate: 0.4, pulseAmp: 0.3, rotSpeed: 0.03, glow: 0.15, emitSpeed: 0.3 };
    }
  }, [activity]);

  // Emission particle geometry
  const emitGeo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(120 * 3);
    for (let i = 0; i < 120; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.1 + Math.random() * 2.5;
      pos[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
      pos[i * 3 + 1] = Math.cos(phi) * r * 0.6;
      pos[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * r;
    }
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);

  useFrame((state, delta) => {
    if (!groupRef.current) return;
    const p = activityParams;
    const t = state.clock.elapsedTime;

    // Overall rotation
    groupRef.current.rotation.y += delta * p.rotSpeed;
    if (isCentral) groupRef.current.rotation.x += delta * p.rotSpeed * 0.3;

    // Breathing
    if (leftRef.current && rightRef.current) {
      const breathe = 1 + Math.sin(t * p.breatheRate) * 0.025 * (activity === "offline" ? 0.1 : 1);
      leftRef.current.scale.setScalar(breathe);
      rightRef.current.scale.setScalar(breathe);
      const em = 0.2 + (Math.sin(t * p.breatheRate * 1.8) * 0.5 + 0.5) * p.pulseAmp * pulseIntensity;
      (leftRef.current.material as THREE.MeshPhysicalMaterial).emissiveIntensity = em;
      (rightRef.current.material as THREE.MeshPhysicalMaterial).emissiveIntensity = em;
    }

    // Glow pulse
    if (glowRef.current) {
      const gl = 0.06 + (Math.sin(t * p.breatheRate * 1.2) * 0.5 + 0.5) * p.glow * pulseIntensity;
      glowRef.current.scale.setScalar(1 + gl * 0.6);
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity = gl;
    }

    // Emitted particles
    if (emitRef.current && activity !== "offline") {
      const pos = emitRef.current.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < 120; i++) {
        const idx = i * 3;
        const len = Math.sqrt(pos[idx] ** 2 + pos[idx + 1] ** 2 + pos[idx + 2] ** 2);
        if (len > 4) {
          const a = Math.random() * Math.PI * 2;
          const b = Math.acos(2 * Math.random() - 1);
          pos[idx] = Math.sin(b) * Math.cos(a) * 1.2;
          pos[idx + 1] = Math.cos(b) * 0.7;
          pos[idx + 2] = Math.sin(b) * Math.sin(a) * 1.2;
        } else {
          const speed = (0.2 + Math.random() * 0.4) * p.emitSpeed * delta;
          pos[idx] += (pos[idx] / Math.max(len, 0.1)) * speed;
          pos[idx + 1] += (pos[idx + 1] / Math.max(len, 0.1)) * speed;
          pos[idx + 2] += (pos[idx + 2] / Math.max(len, 0.1)) * speed;
        }
      }
      emitRef.current.geometry.attributes.position.needsUpdate = true;
    }
  });

  const s = scale;
  const emIntensity = activity === "offline" ? 0.02 : 0.4;

  return (
    <group ref={groupRef} position={position} scale={[s, s, s]}>
      {/* Outer aura */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[1.7, 32, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} />
      </mesh>

      {/* Inner glow */}
      <mesh>
        <sphereGeometry args={[1.35, 32, 32]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} blending={THREE.AdditiveBlending} />
      </mesh>

      {/* Hemispheres */}
      <BrainGeometry hemisphere="left" color={color} emissiveIntensity={emIntensity} />
      <BrainGeometry hemisphere="right" color={color} emissiveIntensity={emIntensity} />

      {/* Corpus callosum glow */}
      <mesh>
        <boxGeometry args={[0.1, 0.4, 0.7]} />
        <meshBasicMaterial color={color} transparent opacity={0.25} />
      </mesh>

      {/* Cerebellum */}
      <mesh position={[0, -0.65, 0.08]}>
        <sphereGeometry args={[0.4, 12, 12]} />
        <meshPhysicalMaterial
          color="#141438"
          emissive={color}
          emissiveIntensity={emIntensity * 0.7}
          metalness={0.2}
          roughness={0.5}
          transparent
          opacity={0.85}
        />
      </mesh>

      {/* Brainstem */}
      <mesh position={[0, -1.05, 0]}>
        <cylinderGeometry args={[0.12, 0.1, 0.4, 8]} />
        <meshPhysicalMaterial color="#141438" emissive={color} emissiveIntensity={emIntensity * 0.5} transparent opacity={0.6} />
      </mesh>

      {/* Orbital rings (more for central) */}
      {(isCentral
        ? [
            { r: 1.7, rot: [Math.PI / 2, 0, 0] as [number, number, number] },
            { r: 1.9, rot: [Math.PI / 3.5, Math.PI / 4, 0] as [number, number, number] },
            { r: 2.1, rot: [Math.PI / 1.4, -Math.PI / 3, 0] as [number, number, number] },
            { r: 2.3, rot: [Math.PI / 2.5, Math.PI / 2, 0] as [number, number, number] },
          ]
        : [
            { r: 1.5, rot: [Math.PI / 2, 0, 0] as [number, number, number] },
            { r: 1.7, rot: [Math.PI / 3, Math.PI / 4, 0] as [number, number, number] },
          ]
      ).map(({ r, rot }) => (
        <mesh key={r} rotation={rot}>
          <ringGeometry args={[r - 0.015, r, 48]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.1}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* Emitted particles */}
      {activity !== "offline" && (
        <points ref={emitRef} geometry={emitGeo}>
          <pointsMaterial
            size={0.035}
            color={color}
            transparent
            opacity={0.5}
            sizeAttenuation
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </points>
      )}
    </group>
  );
}

// ─────────────────────────────────────────────
//  BRAIN HUD — floating info ring around a brain
// ─────────────────────────────────────────────

function BrainHUD({
  name,
  version,
  status,
  latency,
  model,
  tasks,
  position,
}: {
  name: string;
  version?: string;
  status: string;
  latency?: number;
  model?: string;
  tasks?: number;
  position: [number, number, number];
}) {
  const color = BRAIN_COLORS[status] ?? PALETTE.idle;
  return (
    <Html position={[position[0], position[1] - 1.8, position[2]]} center distanceFactor={8}>
      <div
        className="rounded-xl px-3 py-2 text-[10px] font-mono leading-tight whitespace-nowrap min-w-[100px]"
        style={{
          background: "rgba(8,10,16,0.85)",
          border: `1px solid ${color}30`,
          backdropFilter: "blur(12px)",
        }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
          <span className="text-[11px] font-semibold text-white/90">{name}</span>
        </div>
        {version && <div className="text-faint">v{version}</div>}
        {model && <div className="text-muted truncate max-w-[120px]">{model}</div>}
        {latency !== undefined && (
          <div className="text-muted">{latency < 1000 ? `${latency}ms` : `${(latency / 1000).toFixed(1)}s`}</div>
        )}
        {tasks !== undefined && <div className="text-accent">{tasks} tasks</div>}
      </div>
    </Html>
  );
}

// ─────────────────────────────────────────────
//  NEURAL LINK
// ─────────────────────────────────────────────

const NeuralLink = memo(function NeuralLink({
  from, to, active, intensity = 1,
}: {
  from: [number, number, number];
  to: [number, number, number];
  active?: boolean;
  intensity?: number;
}) {
  const points = useMemo(() => {
    const f = new THREE.Vector3(from[0], from[1], from[2]);
    const t = new THREE.Vector3(to[0], to[1], to[2]);
    const mid = f.clone().add(t).multiplyScalar(0.5);
    mid.y += 0.8 + Math.random() * 0.4; // slight upward arc
    const curve = new THREE.QuadraticBezierCurve3(f, mid, t);
    return curve.getPoints(28);
  }, [from, to]);

  const color = active ? PALETTE.linkActive : PALETTE.linkDim;
  const opacity = active ? 0.3 + 0.3 * intensity : 0.12;

  return (
    <Line
      points={points}
      color={color}
      lineWidth={active ? 1.5 : 0.5}
      transparent
      opacity={opacity}
    />
  );
});

// ─────────────────────────────────────────────
//  TASK PACKET — animated traveling particle
// ─────────────────────────────────────────────

function TaskPacket({
  from, to, progress, color = PALETTE.linkActive, size = 0.08,
}: {
  from: [number, number, number];
  to: [number, number, number];
  progress: number;
  color?: string;
  size?: number;
}) {
  const point = useMemo(() => {
    const t = Math.max(0.001, Math.min(0.999, progress));
    const f = new THREE.Vector3(from[0], from[1], from[2]);
    const tt = new THREE.Vector3(to[0], to[1], to[2]);
    const mid = f.clone().add(tt).multiplyScalar(0.5);
    mid.y += 0.8;
    const curve = new THREE.QuadraticBezierCurve3(f, mid, tt);
    return curve.getPoint(t);
  }, [from, to, progress]);

  const isArriving = progress > 0.9;
  const s = isArriving ? size * (1 + (progress - 0.9) * 2) : size;

  return (
    <mesh position={[point.x, point.y, point.z]} scale={[s, s, s]}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color={isArriving ? "#22c55e" : color} transparent opacity={0.9} />
    </mesh>
  );
}

// ─────────────────────────────────────────────
//  DETAIL PANEL (HTML overlay)
// ─────────────────────────────────────────────

function DetailPanel({
  provider,
  tasks,
  onClose,
}: {
  provider: AgentNode;
  tasks: TaskNode[];
  onClose: () => void;
}) {
  const color = BRAIN_COLORS[provider.status] ?? PALETTE.idle;
  const providerTasks = tasks.filter((t) => t.role === provider.role);

  return (
    <div className="absolute right-4 top-4 z-20 w-72 rounded-2xl border border-border/40 bg-surface/90 p-4 text-[11px] shadow-2xl backdrop-blur-xl">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: color }} />
          <span className="font-semibold text-sm text-white/90">{provider.role}</span>
        </div>
        <button onClick={onClose} className="text-faint hover:text-white text-sm">✕</button>
      </div>

      <div className="space-y-1.5 text-muted">
        <div className="flex justify-between">
          <span>Status</span>
          <span className="text-white/80 capitalize">{provider.status}</span>
        </div>
        <div className="flex justify-between">
          <span>Health</span>
          <span className="text-white/80 capitalize">{provider.health}</span>
        </div>
        {provider.provider && (
          <div className="flex justify-between">
            <span>Provider</span>
            <span className="text-white/80">{provider.provider}</span>
          </div>
        )}
        {provider.current_task && (
          <div className="flex justify-between">
            <span>Current Task</span>
            <span className="text-white/80 truncate max-w-[120px]">{provider.current_task}</span>
          </div>
        )}
        {provider.capabilities.length > 0 && (
          <div className="pt-1">
            <div className="text-faint mb-1">Capabilities</div>
            <div className="flex flex-wrap gap-1">
              {provider.capabilities.map((c) => (
                <span
                  key={c}
                  className="rounded-full border border-accent/20 bg-accent/5 px-1.5 py-0.5 text-[9px] text-accent"
                >
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}
        {providerTasks.length > 0 && (
          <div className="pt-1">
            <div className="text-faint mb-1">Tasks ({providerTasks.length})</div>
            <div className="max-h-24 overflow-y-auto space-y-0.5">
              {providerTasks.map((t) => (
                <div key={t.id} className="flex items-center justify-between">
                  <span className="truncate max-w-[140px] text-white/70">{t.title || t.id.slice(0, 8)}</span>
                  <span className="text-faint text-[9px] capitalize">{t.status}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
//  SCENE
// ─────────────────────────────────────────────

function ConstellationScene({ pulseIntensity }: { pulseIntensity: number }) {
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const telemetry = useStore((s) => s.telemetry);
  const events = useStore((s) => s.events);

  const [selectedAgent, setSelectedAgent] = useState<AgentNode | null>(null);
  const [packetProgress, setPacketProgress] = useState(0);

  // Derive provider list from agents (unique providers)
  const providerList = useMemo(() => {
    const map = new Map<string, AgentNode>();
    Object.values(agents).forEach((a) => {
      const key = a.provider ?? a.role;
      if (!map.has(key)) map.set(key, a);
    });
    return Array.from(map.values());
  }, [agents]);

  const positions = useMemo(
    () => fibSphere(providerList.length),
    [providerList.length],
  );

  // Animated packet progress
  useEffect(() => {
    if (providerList.length === 0) return;
    let frame: number;
    const start = performance.now();
    const animate = () => {
      const elapsed = (performance.now() - start) / 1000;
      setPacketProgress((elapsed % 3) / 3);
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [providerList.length]);

  // Task packet routes — from center to active providers
  const packets = useMemo(() => {
    if (providerList.length === 0) return [];
    const active = providerList.filter((a) => a.status === "running" || a.status === "recovered");
    const count = Math.min(5, active.length);
    const result: {
      from: [number, number, number];
      to: [number, number, number];
      progress: number;
      color: string;
      size: number;
    }[] = [];
    for (let i = 0; i < count; i++) {
      const idx = providerList.indexOf(active[i % active.length]);
      const pos = positions[idx];
      if (!pos) continue;
      const offset = i * 0.15;
      const prog = ((packetProgress + offset) % 1);
      result.push({
        from: [0, 0, 0],
        to: pos,
        progress: prog,
        color: prog > 0.85 ? "#22c55e" : PALETTE.linkActive,
        size: 0.06 + prog * 0.04,
      });
    }
    return result;
  }, [providerList, positions, packetProgress]);

  // Running agent count for link activity
  const runningSet = useMemo(
    () => new Set(providerList.filter((a) => a.status === "running").map((a) => a.id)),
    [providerList],
  );

  // Brain metrics
  const metrics = useMemo(
    () => ({
      agents: providerList.length,
      tasks: Object.keys(tasks).length,
      running: Object.values(tasks).filter((t) => t.status === "dispatched" || t.status === "assigned").length,
      errors: telemetry.errors,
      runningAgents: providerList.filter((a) => a.status === "running").length,
    }),
    [providerList, tasks, telemetry],
  );

  return (
    <>
      <color attach="background" args={[PALETTE.bg]} />
      <fog attach="fog" args={[PALETTE.bg, 18, 35]} />

      <ambientLight intensity={0.15} />
      <directionalLight position={[3, 5, 3]} intensity={0.3} color={PALETTE.central} />
      <directionalLight position={[-3, -2, -3]} intensity={0.15} color={PALETTE.reasoning} />
      <pointLight position={[0, 0, 0]} intensity={0.3} color={PALETTE.central} distance={15} />

      <StarField />
      <HexGrid y={-6.5} />

      {/* Central Mission Control Brain */}
      <HolographicBrain
        scale={1.3}
        color={PALETTE.central}
        pulseSpeed={0.5}
        pulseIntensity={pulseIntensity}
        activity={providerList.some((a) => a.status === "running") ? "busy" : "idle"}
        isCentral
      />

      {/* Central brain label */}
      <Html position={[0, 3.2, 0]} center distanceFactor={8}>
        <div className="text-center">
          <div className="text-xs font-bold text-white/90 tracking-widest uppercase">Mission Control</div>
          <div className="text-[9px] text-faint mt-0.5 font-mono">
            {metrics.agents} agents · {metrics.tasks} tasks · {metrics.runningAgents} active
          </div>
        </div>
      </Html>

      {/* Provider brains */}
      {providerList.map((agent, i) => {
        const pos = positions[i];
        if (!pos) return null;
        const isRunning = agent.status === "running";
        const activity =
          agent.status === "failed" ? "offline"
          : agent.status === "running" ? "busy"
          : agent.status === "recovered" ? "reasoning"
          : "idle";
        return (
          <group key={agent.id}>
            <HolographicBrain
              position={pos}
              scale={0.6}
              color={BRAIN_COLORS[agent.status] ?? PALETTE.provider}
              pulseSpeed={isRunning ? 1.2 : 0.5}
              pulseIntensity={isRunning ? 0.8 : 0.3}
              activity={activity as BrainProps["activity"]}
            />

            <BrainHUD
              name={agent.role}
              status={agent.status}
              position={pos}
              tasks={Object.values(tasks).filter((t) => t.role === agent.role).length}
            />

            {/* Neural link center → provider */}
            <NeuralLink from={[0, 0, 0]} to={pos} active={isRunning} />

            {/* Clickable interaction area */}
            <mesh
              position={pos}
              onClick={(e: any) => {
                e.stopPropagation();
                setSelectedAgent((prev) => (prev?.id === agent.id ? null : agent));
              }}
            >
              <sphereGeometry args={[1, 8, 8]} />
              <meshBasicMaterial transparent opacity={0} />
            </mesh>
          </group>
        );
      })}

      {/* Mesh connections between providers (for active providers) */}
      {providerList.map((a, i) => {
        if (a.status !== "running") return null;
        const posA = positions[i];
        if (!posA) return null;
        // Connect to 1-2 other active providers
        const others = providerList.filter((p, j) => p.status === "running" && j !== i);
        const connections = others.slice(0, 2);
        return connections.map((b) => {
          const idxB = providerList.indexOf(b);
          const posB = positions[idxB];
          if (!posB) return null;
          return (
            <NeuralLink
              key={`mesh-${a.id}-${b.id}`}
              from={posA}
              to={posB}
              active
              intensity={0.6}
            />
          );
        });
      })}

      {/* Task packets */}
      {packets.map((pkt, i) => (
        <TaskPacket key={`pkt-${i}`} {...pkt} />
      ))}

      {/* Orbit controls */}
      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        minDistance={4}
        maxDistance={35}
        autoRotate
        autoRotateSpeed={0.25}
        dampingFactor={0.08}
        target={[0, 0, 0]}
      />
    </>
  );
}

// ─────────────────────────────────────────────
//  EXPORTED VIEW
// ─────────────────────────────────────────────

export function AgentConstellation() {
  const agents = useStore((s) => s.agents);
  const events = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);
  const [mounted, setMounted] = useState(false);
  const [pulseIntensity, setPulseIntensity] = useState(0.4);

  // Pulse brain on new events
  useEffect(() => {
    if (events.length > 0) {
      setPulseIntensity(1);
      const t = setTimeout(() => setPulseIntensity(0.4), 500);
      return () => clearTimeout(t);
    }
  }, [events.length]);

  useEffect(() => setMounted(true), []);

  const agentCount = Object.keys(agents).length;

  return (
    <div className="scroll-page p-4 no-hscroll">
      {/* Metrics bar */}
      <div className="mb-3 flex flex-wrap items-center gap-3 text-[11px]">
        <div className="flex items-center gap-1.5 rounded-lg border border-accent/20 bg-accent/5 px-3 py-1.5">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
          <span className="text-accent font-mono font-medium">{agentCount} providers</span>
        </div>
        <div className="flex items-center gap-1.5 rounded-lg border border-border/30 bg-surface/20 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-[#22c55e]" />
          <span className="text-muted font-mono">{telemetry.tasks} tasks</span>
        </div>
        <div className="flex items-center gap-1.5 rounded-lg border border-border/30 bg-surface/20 px-3 py-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-[#f59e0b]" />
          <span className="text-muted font-mono">{telemetry.pipelines} pipelines</span>
        </div>
        {telemetry.errors > 0 && (
          <div className="flex items-center gap-1.5 rounded-lg border border-danger/30 bg-danger/10 px-3 py-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-danger animate-pulse" />
            <span className="text-danger font-mono">{telemetry.errors} errors</span>
          </div>
        )}
        <div className="flex items-center gap-1.5 rounded-lg border border-border/30 bg-surface/20 px-3 py-1.5 ml-auto">
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-[#22c55e]" : "bg-[#ef4444]"}`} />
          <span className="text-muted font-mono">{connected ? "WS live" : "WS offline"}</span>
        </div>
      </div>

      {/* 3D Neural Scene */}
      <div className="relative h-[calc(100vh-8rem)] min-h-[550px] w-full overflow-hidden rounded-2xl border border-border/40 bg-[#080a10] shadow-xl">
        {mounted && (
          <Canvas
            dpr={[1, 2]}
            gl={{
              antialias: true,
              alpha: false,
              powerPreference: "high-performance",
              stencil: false,
              depth: true,
            }}
            camera={{ position: [14, 5, 14], fov: 40, near: 0.1, far: 50 }}
          >
            <ConstellationScene pulseIntensity={pulseIntensity} />

            <EffectComposer multisampling={0}>
              <Bloom
                luminanceThreshold={0.12}
                luminanceSmoothing={0.9}
                intensity={0.85}
                mipmapBlur
              />
              <ChromaticAberration offset={new THREE.Vector2(0.0015, 0.0015)} />
              <Noise opacity={0.02} />
            </EffectComposer>
          </Canvas>
        )}

        {/* Empty state */}
        {agentCount === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#080a10]/80 backdrop-blur-sm">
            <div className="text-center max-w-sm">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-accent/20">
                <span className="text-2xl text-accent/50">🧠</span>
              </div>
              <p className="text-sm font-medium text-muted">Neural Constellation Empty</p>
              <p className="mt-1 text-xs text-faint">
                Connect providers and dispatch agents to populate the living neural intelligence.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-faint">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#818cf8]" /> Mission Control</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#f97316]" /> Running</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#64748b]" /> Idle</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#a855f7]" /> Reasoning</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-[#ef4444]" /> Error</span>
        <span className="flex items-center gap-1.5 ml-auto">Drag to orbit · Scroll to zoom · Click a brain</span>
      </div>
    </div>
  );
}
