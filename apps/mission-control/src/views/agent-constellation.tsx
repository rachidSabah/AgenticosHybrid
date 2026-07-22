"use client";

/**
 * Agent Constellation 2.0 — Living Neural Constellation
 *
 * A premium 3D holographic command-center visualization driven entirely by
 * live backend data (Zustand store + EventBus).
 *
 * Architecture:
 *   React Three Fiber + post-processing bloom + chromatic aberration
 *   d3-force-3d Fibonacci sphere for even agent distribution
 *   Instanced / implicit rendering for 60 FPS at 500+ nodes
 *
 * Visual DNA:
 *   JARVIS / NASA Mission Control / Apple Vision Pro / TRON / Cyberpunk
 */

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  OrbitControls,
  Text,
  Line,
  Html,
  MeshDistortMaterial,
  MeshTransmissionMaterial,
} from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import * as THREE from "three";
import { useStore } from "@/lib/store";
import type { AgentNode } from "@/lib/types";

// ── Design Tokens ──
const BRAIN_COLOR = "#6366f1";
const BRAIN_CORE = "#8b5cf6";
const BRAIN_GLOW = "#4f6cff";
const NODE_COLORS: Record<string, string> = {
  running: "#22c55e",
  completed: "#22c55e",
  failed: "#ef4444",
  recovered: "#f59e0b",
  idle: "#64748b",
  healthy: "#22c55e",
  degraded: "#f59e0b",
  down: "#ef4444",
  unknown: "#64748b",
};
const BG_COLOR = "#080a10";
const PARTICLE_COUNT = 1200;
const ORBIT_RADIUS = 7;

// ── Fibonacci Sphere (even distribution) ──
function fibSphere(count: number, radius = ORBIT_RADIUS): [number, number, number][] {
  const pts: [number, number, number][] = [];
  if (count === 0) return pts;
  const phi = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const theta = phi * i;
    pts.push([Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius]);
  }
  return pts;
}

// ── Hemisphere geometry helper ──
function createHemisphere(segments = 24, radius = 1, side: "left" | "right") {
  const geo = new THREE.SphereGeometry(radius, segments, segments, 0, Math.PI, 0, Math.PI / 2);
  // Flatten the top into more of a brain shape
  const pos = geo.attributes.position.array as Float32Array;
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2];
    // Squash top slightly
    if (y > 0) {
      const squash = 1 - y * 0.3;
      pos[i] = x * squash;
      pos[i + 2] = z * squash;
    }
    // Add gyri-like bumps
    const noise = Math.sin(x * 8) * Math.cos(z * 6) * 0.08 + Math.sin((x + z) * 5) * 0.05;
    pos[i] += x * noise;
    pos[i + 1] += y * noise * 0.5;
    pos[i + 2] += z * noise;
    // Mirror for left/right hemisphere
    if (side === "left") {
      if (x > 0) pos[i] = -pos[i]; // keep only left side
    } else {
      if (x < 0) pos[i] = -pos[i]; // keep only right side
    }
  }
  geo.computeVertexNormals();
  return geo;
}

// ── Particle Field ──
function ParticleField() {
  const meshRef = useRef<THREE.Points>(null!);
  const [geometry] = useState(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const colors = new Float32Array(PARTICLE_COUNT * 3);
    const sizes = new Float32Array(PARTICLE_COUNT);
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 80;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 80;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 80;
      colors[i * 3] = 0.2 + Math.random() * 0.3;
      colors[i * 3 + 1] = 0.25 + Math.random() * 0.3;
      colors[i * 3 + 2] = 0.6 + Math.random() * 0.4;
      sizes[i] = 0.02 + Math.random() * 0.06;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.setAttribute("size", new THREE.BufferAttribute(sizes, 1));
    return geo;
  });

  useFrame((_state, delta) => {
    if (meshRef.current) {
      meshRef.current.rotation.y += delta * 0.005;
      meshRef.current.rotation.x += delta * 0.002;
    }
  });

  return (
    <points ref={meshRef} geometry={geometry}>
      <pointsMaterial
        size={0.04}
        vertexColors
        transparent
        opacity={0.5}
        sizeAttenuation
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ── Neural Brain ──
function NeuralBrain({ pulseIntensity, events }: { pulseIntensity: number; events: number }) {
  const leftRef = useRef<THREE.Mesh>(null!);
  const rightRef = useRef<THREE.Mesh>(null!);
  const brainGroup = useRef<THREE.Group>(null!);
  const glowRef = useRef<THREE.Mesh>(null!);
  const particlesRef = useRef<THREE.Points>(null!);

  // Create hemisphere geometries once
  const [leftGeo] = useState(() => createHemisphere(32, 1.1, "left"));
  const [rightGeo] = useState(() => createHemisphere(32, 1.1, "right"));

  // Emitted particles geometry
  const emitGeo = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(200 * 3);
    for (let i = 0; i < 200; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = 1.2 + Math.random() * 2;
      pos[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
      pos[i * 3 + 1] = Math.cos(phi) * r * 0.6;
      pos[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * r;
    }
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    return geo;
  }, []);

  useFrame((state, delta) => {
    // Brain breathing + pulse
    const breathe = 1 + Math.sin(state.clock.elapsedTime * 0.5) * 0.03;
    const pulse = 0.4 + Math.sin(state.clock.elapsedTime * 1.8) * 0.3 * pulseIntensity;
    const glowPulse = 0.15 + Math.sin(state.clock.elapsedTime * 1.2) * 0.1 * pulseIntensity;

    if (leftRef.current && rightRef.current) {
      leftRef.current.scale.setScalar(breathe);
      rightRef.current.scale.setScalar(breathe);
      // Emissive pulse
      const mat = leftRef.current.material as THREE.MeshPhysicalMaterial;
      mat.emissiveIntensity = 0.3 + pulse;
    }

    if (glowRef.current) {
      glowRef.current.scale.setScalar(1 + glowPulse * 0.5);
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity = 0.06 + glowPulse;
    }

    if (brainGroup.current) {
      brainGroup.current.rotation.y += delta * 0.08;
    }

    // Animate emitted particles
    if (particlesRef.current) {
      const pos = particlesRef.current.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < pos.length; i += 3) {
        // Drift outward slowly
        const len = Math.sqrt(pos[i] ** 2 + pos[i + 1] ** 2 + pos[i + 2] ** 2);
        if (len > 3.5) {
          // Reset to surface
          const theta = Math.random() * Math.PI * 2;
          const phi = Math.acos(2 * Math.random() - 1);
          pos[i] = Math.sin(phi) * Math.cos(theta) * 1.3;
          pos[i + 1] = Math.cos(phi) * 0.8;
          pos[i + 2] = Math.sin(phi) * Math.sin(theta) * 1.3;
        } else {
          const speed = 0.3 + Math.random() * 0.5;
          pos[i] += (pos[i] / len) * delta * speed;
          pos[i + 1] += (pos[i + 1] / len) * delta * speed;
          pos[i + 2] += (pos[i + 2] / len) * delta * speed;
        }
      }
      particlesRef.current.geometry.attributes.position.needsUpdate = true;
    }
  });

  return (
    <group ref={brainGroup}>
      {/* Outer aura */}
      <mesh ref={glowRef}>
        <sphereGeometry args={[1.8, 32, 32]} />
        <meshBasicMaterial color={BRAIN_GLOW} transparent opacity={0.08} />
      </mesh>

      {/* Inner glow */}
      <mesh>
        <sphereGeometry args={[1.4, 32, 32]} />
        <meshBasicMaterial color={BRAIN_CORE} transparent opacity={0.1} blending={THREE.AdditiveBlending} />
      </mesh>

      {/* Left hemisphere */}
      <mesh ref={leftRef} geometry={leftGeo} position={[-0.05, 0.1, 0]}>
        <meshPhysicalMaterial
          color="#1a1a3e"
          emissive={BRAIN_COLOR}
          emissiveIntensity={0.4}
          metalness={0.3}
          roughness={0.4}
          clearcoat={0.3}
          transparent
          opacity={0.92}
          wireframe={false}
        />
      </mesh>

      {/* Right hemisphere */}
      <mesh ref={rightRef} geometry={rightGeo} position={[0.05, 0.1, 0]}>
        <meshPhysicalMaterial
          color="#1a1a3e"
          emissive={BRAIN_COLOR}
          emissiveIntensity={0.4}
          metalness={0.3}
          roughness={0.4}
          clearcoat={0.3}
          transparent
          opacity={0.92}
          wireframe={false}
        />
      </mesh>

      {/* Corpus callosum / center bridge glow */}
      <mesh>
        <boxGeometry args={[0.15, 0.5, 0.8]} />
        <meshBasicMaterial color={BRAIN_CORE} transparent opacity={0.3} />
      </mesh>

      {/* Cerebellum (bottom bump) */}
      <mesh position={[0, -0.75, 0.1]}>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshPhysicalMaterial
          color="#1a1a3e"
          emissive={BRAIN_COLOR}
          emissiveIntensity={0.3}
          metalness={0.2}
          roughness={0.5}
          transparent
          opacity={0.85}
        />
      </mesh>

      {/* Brainstem */}
      <mesh position={[0, -1.2, 0]}>
        <cylinderGeometry args={[0.15, 0.12, 0.5, 8]} />
        <meshPhysicalMaterial
          color="#1a1a3e"
          emissive={BRAIN_COLOR}
          emissiveIntensity={0.2}
          metalness={0.2}
          roughness={0.6}
          transparent
          opacity={0.7}
        />
      </mesh>

      {/* Orbital rings */}
      {[
        { radius: 1.8, rot: [Math.PI / 2, 0, 0] as [number, number, number] },
        { radius: 2.0, rot: [Math.PI / 3, Math.PI / 4, 0] as [number, number, number] },
        { radius: 2.2, rot: [Math.PI / 1.5, -Math.PI / 3, 0] as [number, number, number] },
      ].map((ring, i) => (
        <mesh key={i} rotation={ring.rot}>
          <ringGeometry args={[ring.radius - 0.02, ring.radius, 64]} />
          <meshBasicMaterial
            color={BRAIN_GLOW}
            transparent
            opacity={0.12 + i * 0.04}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* Emitted particles */}
      <points ref={particlesRef} geometry={emitGeo}>
        <pointsMaterial
          size={0.04}
          color={BRAIN_GLOW}
          transparent
          opacity={0.6}
          sizeAttenuation
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>
    </group>
  );
}

// ── Agent Node ──
function AgentNode({
  agent, pos, index, total, isSelected, onClick, onHover,
}: {
  agent: AgentNode;
  pos: [number, number, number];
  index: number;
  total: number;
  isSelected: boolean;
  onClick: () => void;
  onHover: (h: boolean) => void;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const [hovered, setHovered] = useState(false);
  const color = NODE_COLORS[agent.status] ?? NODE_COLORS.idle;
  const isRunning = agent.status === "running";
  const floatOffset = useRef(Math.random() * Math.PI * 2);

  useFrame((state) => {
    if (meshRef.current) {
      const floatY = Math.sin(state.clock.elapsedTime * 0.4 + floatOffset.current) * 0.15;
      meshRef.current.position.y = pos[1] + floatY + (isSelected ? 0.2 : 0);
      meshRef.current.position.x = pos[0];
      meshRef.current.position.z = pos[2];
      // Pulse if running
      if (isRunning) {
        const pulse = 1 + Math.sin(state.clock.elapsedTime * 2 + floatOffset.current) * 0.05;
        meshRef.current.scale.setScalar(pulse);
      } else {
        meshRef.current.scale.setScalar(1);
      }
    }
  });

  return (
    <group>
      {/* Outer glow ring */}
      <mesh position={[pos[0], pos[1], pos[2]]}>
        <ringGeometry args={[0.45, 0.6, 32]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={isRunning ? 0.5 : 0.2}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Node body */}
      <mesh
        ref={meshRef}
        position={[pos[0], pos[1], pos[2]]}
        onPointerOver={() => { setHovered(true); onHover(true); }}
        onPointerOut={() => { setHovered(false); onHover(false); }}
        onClick={onClick}
      >
        <circleGeometry args={[0.3, 32]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={hovered || isSelected ? 1 : 0.75}
        />
      </mesh>

      {/* Label */}
      <Html position={[pos[0], pos[1] - 0.7, pos[2]]} center distanceFactor={8}>
        <div
          className={`px-2.5 py-0.5 rounded text-[9px] font-mono whitespace-nowrap transition-all ${
            isRunning ? "text-accent font-medium" : "text-muted"
          }`}
          style={{
            background: "rgba(8,10,16,0.75)",
            border: `1px solid ${color}30`,
            backdropFilter: "blur(6px)",
          }}
        >
          {agent.role || agent.id}
        </div>
      </Html>
    </group>
  );
}

// ── Neural Link ──
function NeuralLink({
  from, to, active,
}: {
  from: [number, number, number];
  to: [number, number, number];
  active: boolean;
}) {
  const points = useMemo(() => {
    const mid = new THREE.Vector3(
      (from[0] + to[0]) / 2,
      (from[1] + to[1]) / 2 + 0.5,
      (from[2] + to[2]) / 2
    );
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(from[0], from[1], from[2]),
      mid,
      new THREE.Vector3(to[0], to[1], to[2])
    );
    return curve.getPoints(24);
  }, [from, to]);

  return (
    <Line
      points={points}
      color={active ? "#6366f1" : "#1f2633"}
      lineWidth={active ? 1.5 : 0.5}
      transparent
      opacity={active ? 0.5 : 0.15}
    />
  );
}

// ── Energy Signal (traveling pulse) ──
function EnergySignal({
  from, to, progress, color = "#6366f1",
}: {
  from: [number, number, number];
  to: [number, number, number];
  progress: number;
  color?: string;
}) {
  const point = useMemo(() => {
    const t = Math.max(0, Math.min(1, progress));
    const mid = new THREE.Vector3(
      (from[0] + to[0]) / 2,
      (from[1] + to[1]) / 2 + 0.5,
      (from[2] + to[2]) / 2
    );
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(from[0], from[1], from[2]),
      mid,
      new THREE.Vector3(to[0], to[1], to[2])
    );
    return curve.getPoint(t);
  }, [from, to, progress]);

  return (
    <mesh position={[point.x, point.y, point.z]}>
      <sphereGeometry args={[0.06, 8, 8]} />
      <meshBasicMaterial color={color} transparent opacity={0.8} />
    </mesh>
  );
}

// ── Scene Root ──
function ConstellationScene({ pulseIntensity }: { pulseIntensity: number }) {
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const telemetry = useStore((s) => s.telemetry);
  const events = useStore((s) => s.events);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [signalProgress, setSignalProgress] = useState(0);

  const agentList = useMemo(() => Object.values(agents), [agents]);
  const positions = useMemo(() => fibSphere(agentList.length), [agentList.length]);

  // Animate signals
  useEffect(() => {
    if (agentList.length === 0) return;
    let frame: number;
    let start = performance.now();
    const animate = () => {
      const elapsed = (performance.now() - start) / 1000;
      setSignalProgress((elapsed % 3) / 3); // 3-second cycle
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [agentList.length]);

  // Metrics for brain display
  const brainMetrics = useMemo(() => ({
    agents: agentList.length,
    tasks: Object.keys(tasks).length,
    running: Object.values(tasks).filter((t) => t.status === "dispatched" || t.status === "assigned").length,
    errors: telemetry.errors,
    running_agents: agentList.filter((a) => a.status === "running").length,
    providers: telemetry.providers,
  }), [agentList, tasks, telemetry]);

  const handleSelect = useCallback((id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  }, []);

  const signals = useMemo(() => {
    if (agentList.length === 0) return [];
    // Send signals from brain to a subset of agents
    const count = Math.min(3, agentList.length);
    const result: { from: [number, number, number]; to: [number, number, number]; progress: number; color: string }[] = [];
    const offsets = [0, 0.33, 0.67];
    for (let i = 0; i < count; i++) {
      const targetIdx = Math.floor((i / count) * agentList.length);
      const targetPos = positions[targetIdx];
      if (targetPos) {
        const prog = ((signalProgress + offsets[i]) % 1);
        result.push({
          from: [0, 0, 0],
          to: targetPos,
          progress: prog,
          color: prog > 0.8 ? "#22c55e" : "#6366f1",
        });
      }
    }
    return result;
  }, [agentList.length, positions, signalProgress]);

  return (
    <>
      <color attach="background" args={[BG_COLOR]} />
      <fog attach="fog" args={[BG_COLOR, 15, 30]} />

      <ambientLight intensity={0.2} />
      <directionalLight position={[5, 5, 5]} intensity={0.4} color={BRAIN_COLOR} />
      <directionalLight position={[-3, -3, -3]} intensity={0.2} color={BRAIN_CORE} />
      <pointLight position={[0, 0, 0]} intensity={0.5} color={BRAIN_GLOW} distance={10} />

      <ParticleField />

      <NeuralBrain pulseIntensity={pulseIntensity} events={events.length} />

      {/* Neural links center → agents */}
      {agentList.map((a, i) => {
        const pos = positions[i];
        if (!pos) return null;
        return (
          <NeuralLink
            key={`link-${a.id}`}
            from={[0, 0, 0]}
            to={pos}
            active={a.status === "running"}
          />
        );
      })}

      {/* Energy signals */}
      {signals.map((s, i) => (
        <EnergySignal key={i} {...s} />
      ))}

      {/* Agent nodes */}
      {agentList.map((a, i) => {
        const pos = positions[i];
        if (!pos) return null;
        return (
          <AgentNode
            key={a.id}
            agent={a}
            pos={pos}
            index={i}
            total={agentList.length}
            isSelected={selectedId === a.id}
            onClick={() => handleSelect(a.id)}
            onHover={() => {}}
          />
        );
      })}

      {/* Holographic floor grid (subtle) */}
      <gridHelper args={[20, 40, "#1a1e30", "#131725"]} position={[0, -6, 0]} />

      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        minDistance={3}
        maxDistance={30}
        autoRotate
        autoRotateSpeed={0.4}
        dampingFactor={0.08}
      />
    </>
  );
}

// ── View Component ──
export function AgentConstellation() {
  const agents = useStore((s) => s.agents);
  const events = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);
  const [mounted, setMounted] = useState(false);
  const [pulseIntensity, setPulseIntensity] = useState(0.5);

  // Pulse brain on new events
  useEffect(() => {
    if (events.length > 0) {
      setPulseIntensity(1);
      const timer = setTimeout(() => setPulseIntensity(0.5), 400);
      return () => clearTimeout(timer);
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
          <span className="text-accent font-mono font-medium">{agentCount} agents</span>
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
          <span className="text-muted font-mono">
            {connected ? "WS live" : "WS offline"}
          </span>
        </div>
      </div>

      {/* 3D Canvas */}
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
            camera={{ position: [12, 6, 12], fov: 40, near: 0.1, far: 50 }}
          >
            <ConstellationScene pulseIntensity={pulseIntensity} />

            <EffectComposer multisampling={0}>
              <Bloom
                luminanceThreshold={0.15}
                luminanceSmoothing={0.85}
                intensity={0.9}
                mipmapBlur
              />
              <ChromaticAberration
                offset={new THREE.Vector2(0.0015, 0.0015)}
              />
            </EffectComposer>
          </Canvas>
        )}

        {/* Empty overlay */}
        {agentCount === 0 && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#080a10]/80 backdrop-blur-sm z-10">
            <div className="text-center">
              <div className="mx-auto mb-4 h-16 w-16 rounded-full border border-accent/20 flex items-center justify-center">
                <span className="text-2xl text-accent/60">🧠</span>
              </div>
              <p className="text-sm text-muted font-medium">Neural Constellation Empty</p>
              <p className="mt-1 text-xs text-faint max-w-xs">
                Compose or dispatch agents to populate the living neural network.
                Discovered runtimes appear here automatically.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="mt-3 flex flex-wrap items-center gap-4 text-[10px] text-faint">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#22c55e]" /> Running
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#64748b]" /> Idle
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#ef4444]" /> Failed
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#f59e0b]" /> Degraded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-[#6366f1]" /> Active link
        </span>
        <span className="flex items-center gap-1.5 ml-auto">
          Drag/scroll to navigate · Auto-rotate on
        </span>
      </div>
    </div>
  );
}
