"use client";

/**
 * AI Brain — Neural Intelligence Visualization
 * A full-page 3D holographic brain scene with glass-morphism overlay panels
 * References: Dark theme, central glowing brain, blue/cyan holographic aesthetic
 */

import React, { useRef, useMemo, useEffect, useState } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { EffectComposer, Bloom, ChromaticAberration } from '@react-three/postprocessing';
import { useStore } from '@/lib/store';

// ─── Types ───────────────────────────────────────────────────────────────────
interface TelemetryPoint { hour: string; value: number }

// ─── Constants ────────────────────────────────────────────────────────────────
const COLORS = {
  primary: '#4488ff',
  primaryDim: '#2255cc',
  accent: '#66ccff',
  accentGreen: '#44ffaa',
  textPrimary: '#e0e8ff',
  textDim: '#8899bb',
  panelBg: 'rgba(10, 20, 40, 0.45)',
  panelBorder: 'rgba(68, 136, 255, 0.25)',
  glow: '#4488ff',
  brainSurface: '#2266dd',
  brainGlow: '#4488ff',
  active: '#44ffaa',
  idle: '#4488ff',
  warning: '#ff8844',
};

// ─── 3D Brain Components ─────────────────────────────────────────────────────

function HolographicBrain({ position, scale = 1, color = COLORS.brainSurface, pulseSpeed = 1, isCentral = false }: {
  position: [number, number, number];
  scale?: number;
  color?: string;
  pulseSpeed?: number;
  isCentral?: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null!);
  const glowRef = useRef<THREE.Mesh>(null!);
  const coreRef = useRef<THREE.Mesh>(null!);
  
  // Brain geometry: left + right hemispheres using SphereGeometry with displacement
  const leftHemiGeom = useMemo(() => {
    const geo = new THREE.SphereGeometry(0.8 * scale, 48, 48);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      // Displace the left hemisphere
      if (x < 0) {
        const noise = Math.sin(y * 8) * 0.04 + Math.cos(z * 6 + x * 3) * 0.03 + Math.sin((x + y + z) * 5) * 0.02;
        const len = Math.sqrt(x*x + y*y + z*z);
        const nx = x / len, ny = y / len, nz = z / len;
        const r = 0.8 + noise;
        pos.setXYZ(i, nx * r * scale, ny * r * scale, nz * r * scale);
      }
    }
    geo.computeVertexNormals();
    return geo;
  }, [scale]);

  const rightHemiGeom = useMemo(() => {
    const geo = new THREE.SphereGeometry(0.8 * scale, 48, 48);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      if (x > 0) {
        const noise = Math.sin(y * 8) * 0.04 + Math.cos(z * 6 - x * 3) * 0.03 + Math.sin((x + y + z) * 5) * 0.02;
        const len = Math.sqrt(x*x + y*y + z*z);
        const nx = x / len, ny = y / len, nz = z / len;
        const r = 0.8 + noise;
        pos.setXYZ(i, nx * r * scale, ny * r * scale, nz * r * scale);
      }
    }
    geo.computeVertexNormals();
    return geo;
  }, [scale]);

  const cerebellumGeom = useMemo(() => {
    return new THREE.SphereGeometry(0.35 * scale, 24, 24);
  }, [scale]);

  const stemGeom = useMemo(() => {
    return new THREE.CylinderGeometry(0.12 * scale, 0.2 * scale, 0.4 * scale, 12);
  }, [scale]);

  // Pulse animation
  useFrame((state) => {
    const t = state.clock.elapsedTime * pulseSpeed;
    if (groupRef.current) {
      groupRef.current.rotation.y = Math.sin(t * 0.15) * 0.3;
      groupRef.current.position.y = position[1] + Math.sin(t * 0.5) * 0.05 * scale;
    }
    if (glowRef.current) {
      const intensity = 0.4 + Math.sin(t * 0.8) * 0.2 * pulseSpeed;
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity = Math.min(intensity, 0.8);
      glowRef.current.scale.setScalar(1 + Math.sin(t * 0.6) * 0.03);
    }
    if (coreRef.current) {
      (coreRef.current.material as THREE.MeshStandardMaterial).emissiveIntensity = 0.3 + Math.sin(t * 0.5) * 0.15 * pulseSpeed;
    }
  });

  return (
    <group ref={groupRef} position={position}>
      {/* Outer glow sphere */}
      <mesh ref={glowRef} scale={1.3}>
        <sphereGeometry args={[scale, 32, 32]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={0.08}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* Corpus callosum bridge */}
      <mesh position={[0, 0.1 * scale, 0]} scale={[0.4 * scale, 0.05 * scale, 0.15 * scale]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color={COLORS.glow} transparent opacity={0.3} blending={THREE.AdditiveBlending} />
      </mesh>

      {/* Left hemisphere */}
      <mesh geometry={leftHemiGeom} position={[-0.05 * scale, 0.05 * scale, 0]}>
        <meshPhysicalMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.3}
          metalness={0.1}
          roughness={0.3}
          transparent
          opacity={0.75}
          wireframe={false}
          clearcoat={0.2}
          clearcoatRoughness={0.4}
        />
      </mesh>
      {/* Left hemisphere wireframe overlay */}
      <mesh geometry={leftHemiGeom} position={[-0.05 * scale, 0.05 * scale, 0]}>
        <meshBasicMaterial color={COLORS.glow} wireframe transparent opacity={0.08} />
      </mesh>

      {/* Right hemisphere */}
      <mesh geometry={rightHemiGeom} position={[0.05 * scale, 0.05 * scale, 0]}>
        <meshPhysicalMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.3}
          metalness={0.1}
          roughness={0.3}
          transparent
          opacity={0.75}
          wireframe={false}
          clearcoat={0.2}
          clearcoatRoughness={0.4}
        />
      </mesh>
      {/* Right hemisphere wireframe overlay */}
      <mesh geometry={rightHemiGeom} position={[0.05 * scale, 0.05 * scale, 0]}>
        <meshBasicMaterial color={COLORS.glow} wireframe transparent opacity={0.08} />
      </mesh>

      {/* Cerebellum */}
      <mesh geometry={cerebellumGeom} position={[0, -0.55 * scale, 0.25 * scale]}>
        <meshPhysicalMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.15}
          metalness={0.05}
          roughness={0.4}
          transparent
          opacity={0.6}
        />
      </mesh>

      {/* Brainstem */}
      <mesh geometry={stemGeom} position={[0, -0.9 * scale, 0.1 * scale]} rotation={[0.1, 0, 0]}>
        <meshPhysicalMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.1}
          metalness={0.05}
          roughness={0.5}
          transparent
          opacity={0.5}
        />
      </mesh>

      {/* Core glow */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.3 * scale, 16, 16]} />
        <meshBasicMaterial
          color={COLORS.accent}
          transparent
          opacity={0.15}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* Orbital rings */}
      <OrbitalRing radius={1.2 * scale} color={COLORS.glow} speed={0.3 * pulseSpeed} rot={[Math.PI / 2, 0, 0]} />
      <OrbitalRing radius={1.4 * scale} color={COLORS.accent} speed={0.2 * pulseSpeed} rot={[Math.PI / 3, 0.5, 0]} />
      {isCentral && (
        <OrbitalRing radius={1.6 * scale} color={COLORS.accentGreen} speed={0.15 * pulseSpeed} rot={[Math.PI / 4, 1, 0]} />
      )}
    </group>
  );
}

function OrbitalRing({ radius, color, speed, rot }: { radius: number; color: string; speed: number; rot: [number, number, number] }) {
  const ref = useRef<THREE.Line>(null!);
  const points = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= 64; i++) {
      const theta = (i / 64) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(theta) * radius, Math.sin(theta) * radius, 0));
    }
    return pts;
  }, [radius]);

  const lineObj = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.3,
    });
    return new THREE.Line(geometry, material);
  }, [points, color]);

  useFrame((state) => {
    if (ref.current) {
      ref.current.rotation.x = rot[0];
      ref.current.rotation.y = rot[1] + state.clock.elapsedTime * speed;
      ref.current.rotation.z = rot[2];
    }
  });

  return <primitive ref={ref} object={lineObj} />;
}

// ─── Background ────────────────────────────────────────────────────────────────

function Background({ stars = 800 }: { stars?: number }) {
  const pointsObj = useMemo(() => {
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(stars * 3);
    for (let i = 0; i < stars * 3; i++) {
      positions[i] = (Math.random() - 0.5) * 200;
    }
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: '#8899bb',
      size: 0.15,
      transparent: true,
      opacity: 0.6,
      sizeAttenuation: true,
    });
    return new THREE.Points(geometry, material);
  }, [stars]);

  return <primitive object={pointsObj} />;
}

// ─── Grid Floor ──────────────────────────────────────────────────────────────

function HolographicGrid() {
  const gridRef = useRef<THREE.GridHelper>(null!);
  useFrame((state) => {
    if (gridRef.current) {
      gridRef.current.position.y = -2.5 + Math.sin(state.clock.elapsedTime * 0.1) * 0.02;
    }
  });
  return (
    <gridHelper ref={gridRef} args={[20, 40, COLORS.primaryDim, COLORS.primaryDim]} position={[0, -2.5, 0]}>
      <primitive object={new THREE.LineBasicMaterial({ transparent: true, opacity: 0.15 })} />
    </gridHelper>
  );
}

// ─── Main 3D Scene ──────────────────────────────────────────────────────────

function NeuralScene() {
  const { agents, telemetry, tasks } = useStore();
  
  // Get active providers from agents
  const providers = useMemo(() => {
    const pMap = new Map<string, { name: string; model: string; status: string; health?: number }>();
    const agentList = agents ? Object.values(agents) : [];
    agentList.forEach(a => {
      if (a.provider && !pMap.has(a.provider)) {
        pMap.set(a.provider, {
          name: a.provider,
          model: a.role, // use role as model identifier
          status: a.status || 'idle',
          health: a.health === 'healthy' ? 95 : a.health === 'degraded' ? 60 : 30,
        });
      }
    });
    return Array.from(pMap.values());
  }, [agents]);

  const activeTaskCount = Object.values(tasks || {}).filter((t: any) => t.status === 'running' || t.status === 'pending').length;

  return (
    <Canvas camera={{ position: [0, 1, 6], fov: 45 }} dpr={[1, 2]}>
      <color attach="background" args={['#050a18']} />
      <fog attach="fog" args={['#050a18', 15, 30]} />

      <ambientLight intensity={0.2} />
      <directionalLight position={[5, 10, 5]} intensity={0.3} color={COLORS.primary} />
      <pointLight position={[0, 0, 3]} intensity={0.5} color={COLORS.accent} />

      <OrbitControls enableZoom={false} enablePan={false} autoRotate autoRotateSpeed={0.5} />

      <Background />

      {/* Central brain */}
      <HolographicBrain position={[0, 0.2, 0]} scale={1} isCentral pulseSpeed={1} />

      {/* Provider brains positioned in a semi-circle */}
      {providers.slice(0, 6).map((p, i) => {
        const angle = (i / Math.max(providers.length - 1, 1)) * Math.PI - Math.PI / 2;
        const radius = 3.2;
        const x = Math.cos(angle) * radius;
        const z = Math.sin(angle) * radius;
        return (
          <HolographicBrain
            key={p.name}
            position={[x, -0.3 + Math.sin(i * 1.5) * 0.3, z - 0.5]}
            scale={0.45}
            color={p.status === 'running' || p.status === 'active' ? COLORS.accentGreen : COLORS.primaryDim}
            pulseSpeed={p.status === 'running' || p.status === 'active' ? 1.5 : 0.5}
          />
        );
      })}

      {/* Neural links from center to providers */}
      {providers.slice(0, 6).map((p, i) => {
        const angle = (i / Math.max(providers.length - 1, 1)) * Math.PI - Math.PI / 2;
        const radius = 3.2;
        const x = Math.cos(angle) * radius;
        const z = Math.sin(angle) * radius;
        return (
          <NeuralLink
            key={`link-${p.name}`}
            start={[0, 0.2, 0]}
            end={[x, -0.3 + Math.sin(i * 1.5) * 0.3, z - 0.5]}
            color={p.status === 'running' || p.status === 'active' ? COLORS.accentGreen : COLORS.primaryDim}
          />
        );
      })}

      <HolographicGrid />

      <EffectComposer>
        <Bloom luminanceThreshold={0.2} luminanceSmoothing={0.9} intensity={0.6} />
        <ChromaticAberration offset={[0.002, 0.002]} />
      </EffectComposer>
    </Canvas>
  );
}

function NeuralLink({ start, end, color }: { start: [number, number, number]; end: [number, number, number]; color: string }) {
  const ref = useRef<THREE.Line>(null!);
  const points = useMemo(() => {
    const mid = new THREE.Vector3(
      (start[0] + end[0]) / 2,
      (start[1] + end[1]) / 2 - 0.5,
      (start[2] + end[2]) / 2
    );
    const curve = new THREE.QuadraticBezierCurve3(
      new THREE.Vector3(...start),
      mid,
      new THREE.Vector3(...end)
    );
    return curve.getPoints(30);
  }, [start, end]);

  const lineObj = useMemo(() => {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.2,
    });
    return new THREE.Line(geometry, material);
  }, [points, color]);

  useFrame((state) => {
    if (ref.current) {
      const mat = ref.current.material as THREE.LineBasicMaterial;
      mat.opacity = 0.15 + Math.sin(state.clock.elapsedTime * 0.5 + start[0]) * 0.1;
    }
  });

  return <primitive ref={ref} object={lineObj} />;
}

// ─── Dashboard Overlay Components ────────────────────────────────────────────

function MetricCard({ title, value, unit, icon, trend }: {
  title: string; value: string | number; unit?: string; icon?: string; trend?: 'up' | 'down' | 'stable';
}) {
  return (
    <div className="ai-brain-card">
      <div className="ai-brain-card-header">
        <span className="ai-brain-card-icon">{icon || '◈'}</span>
        <span className="ai-brain-card-title">{title}</span>
        {trend && (
          <span className={`ai-brain-trend ${trend}`}>
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
          </span>
        )}
      </div>
      <div className="ai-brain-card-value">
        {value}<span className="ai-brain-card-unit">{unit}</span>
      </div>
    </div>
  );
}

function ProviderMiniCard({ name, model, status, health }: {
  name: string; model: string; status: string; health?: number;
}) {
  const statusColor = 
    status === 'running' || status === 'active' ? COLORS.accentGreen :
    status === 'idle' ? COLORS.primaryDim :
    status === 'offline' ? '#555' :
    COLORS.warning;

  return (
    <div className="ai-brain-provider-card" style={{ borderLeftColor: statusColor }}>
      <div className="ai-brain-provider-name">{name}</div>
      <div className="ai-brain-provider-meta">
        <span className="ai-brain-provider-model">{model}</span>
        <span className="ai-brain-provider-status" style={{ color: statusColor }}>● {status}</span>
      </div>
      {health !== undefined && (
        <div className="ai-brain-provider-health">
          <div className="ai-brain-health-bar" style={{ width: `${health}%`, background: health > 60 ? COLORS.accentGreen : COLORS.warning }} />
        </div>
      )}
    </div>
  );
}

// ─── Main View ──────────────────────────────────────────────────────────────

export default function AIBrain() {
  const { agents, tasks, events } = useStore();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const providers = useMemo(() => {
    const pMap = new Map<string, { name: string; model: string; status: string; health?: number }>();
    const agentList = agents ? Object.values(agents) : [];
    agentList.forEach(a => {
      if (a.provider && !pMap.has(a.provider)) {
        pMap.set(a.provider, {
          name: a.provider,
          model: a.role, // use role as model identifier
          status: a.status || 'idle',
          health: a.health === 'healthy' ? 95 : a.health === 'degraded' ? 60 : 30,
        });
      }
    });
    return Array.from(pMap.values());
  }, [agents]);

  const activeTasks = Object.values(tasks || {}).filter((t: any) => t.status === 'running' || t.status === 'pending').length;
  const recentEvents = (events || []).slice(-6).reverse();

  return (
    <div className="ai-brain-page">
      {/* 3D Scene - full background */}
      <div className="ai-brain-scene">
        <NeuralScene />
      </div>

      {/* Overlay UI */}
      <div className="ai-brain-overlay">
        {/* Top bar */}
        <div className="ai-brain-topbar">
          <div className="ai-brain-title">
            <span className="ai-brain-logo">🧠</span>
            <div>
              <h1>Neural Intelligence Core</h1>
              <div className="ai-brain-subtitle">Mission Control • Real-time Consciousness Engine</div>
            </div>
          </div>
          <div className="ai-brain-time">
            <div className="ai-brain-clock">{time.toLocaleTimeString()}</div>
            <div className="ai-brain-date">{time.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</div>
          </div>
        </div>

        {/* Main content: Left = metrics, Right = providers */}
        <div className="ai-brain-content">
          {/* Left column - Metrics */}
          <div className="ai-brain-metrics">
            <MetricCard title="Active Providers" value={providers.length} icon="⊞" />
            <MetricCard title="Running Tasks" value={activeTasks} icon="⚡" trend={activeTasks > 0 ? 'up' : 'stable'} />
            <MetricCard title="Neural Links" value={providers.length * 2} icon="◈" />
            <MetricCard title="System Health" value={providers.reduce((s, p) => s + (p.health || 85), 0) / Math.max(providers.length, 1)} unit="%" trend={providers.length > 0 ? 'up' : 'stable'} />
          </div>

          {/* Center - Provider Fleet */}
          <div className="ai-brain-providers">
            <div className="ai-brain-panel-header">
              <h2>Provider Fleet</h2>
              <span className="ai-brain-panel-count">{providers.length} connected</span>
            </div>
            <div className="ai-brain-provider-grid">
              {providers.length === 0 && (
                <div className="ai-brain-empty">Awaiting provider connections...</div>
              )}
              {providers.map(p => (
                <ProviderMiniCard key={p.name} {...p} />
              ))}
            </div>
          </div>

          {/* Right column - Events */}
          <div className="ai-brain-events">
            <div className="ai-brain-panel-header">
              <h2>Neural Activity</h2>
              <span className="ai-brain-panel-count">{recentEvents.length} recent</span>
            </div>
            <div className="ai-brain-event-stream">
              {recentEvents.length === 0 && (
                <div className="ai-brain-empty">No recent events</div>
              )}
              {recentEvents.map((e: any, i: number) => (
                <div key={i} className="ai-brain-event-item">
                  <span className="ai-brain-event-icon">⟡</span>
                  <div className="ai-brain-event-content">
                    <div className="ai-brain-event-text">{e.message || e.type || 'Event'}</div>
                    <div className="ai-brain-event-time">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom status bar */}
        <div className="ai-brain-bottombar">
          <div className="ai-brain-status-item">
            <span className="ai-brain-status-dot active" />
            System Online
          </div>
          <div className="ai-brain-status-item">
            <span className="ai-brain-status-dot" style={{ background: providers.length > 0 ? COLORS.accentGreen : '#555' }} />
            {providers.length} Providers
          </div>
          <div className="ai-brain-status-item">
            <span className="ai-brain-status-dot" style={{ background: activeTasks > 0 ? COLORS.accentGreen : '#555' }} />
            {activeTasks} Active Tasks
          </div>
          <div className="ai-brain-status-item">
            <span className="ai-brain-status-dot" style={{ background: '#4488ff' }} />
            v1.0.0-rc1
          </div>
        </div>
      </div>

      <style jsx>{`
        .ai-brain-page {
          position: relative;
          width: 100%;
          height: 100%;
          overflow: hidden;
          background: #050a18;
          color: ${COLORS.textPrimary};
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .ai-brain-scene {
          position: absolute;
          inset: 0;
          z-index: 0;
        }
        .ai-brain-overlay {
          position: relative;
          z-index: 1;
          display: flex;
          flex-direction: column;
          height: 100%;
          pointer-events: none;
        }
        .ai-brain-overlay > * {
          pointer-events: auto;
        }
        .ai-brain-topbar {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          padding: 16px 24px;
          background: linear-gradient(180deg, ${COLORS.panelBg} 0%, transparent 100%);
          border-bottom: 1px solid ${COLORS.panelBorder};
          backdrop-filter: blur(12px);
        }
        .ai-brain-title {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .ai-brain-logo {
          font-size: 32px;
          line-height: 1;
        }
        .ai-brain-title h1 {
          font-size: 18px;
          font-weight: 600;
          margin: 0;
          color: ${COLORS.textPrimary};
          letter-spacing: 0.5px;
        }
        .ai-brain-subtitle {
          font-size: 11px;
          color: ${COLORS.textDim};
          letter-spacing: 1px;
          text-transform: uppercase;
        }
        .ai-brain-time {
          text-align: right;
        }
        .ai-brain-clock {
          font-size: 24px;
          font-weight: 300;
          color: ${COLORS.textPrimary};
          letter-spacing: 2px;
        }
        .ai-brain-date {
          font-size: 11px;
          color: ${COLORS.textDim};
        }
        .ai-brain-content {
          flex: 1;
          display: grid;
          grid-template-columns: 240px 1fr 240px;
          gap: 16px;
          padding: 16px 24px;
          overflow: auto;
        }
        .ai-brain-metrics {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .ai-brain-card {
          background: ${COLORS.panelBg};
          border: 1px solid ${COLORS.panelBorder};
          border-radius: 8px;
          padding: 12px 16px;
          backdrop-filter: blur(8px);
        }
        .ai-brain-card-header {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 10px;
          color: ${COLORS.textDim};
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        .ai-brain-card-icon {
          font-size: 12px;
        }
        .ai-brain-card-value {
          font-size: 28px;
          font-weight: 300;
          color: ${COLORS.textPrimary};
          margin-top: 4px;
          letter-spacing: 1px;
        }
        .ai-brain-card-unit {
          font-size: 12px;
          color: ${COLORS.textDim};
          margin-left: 4px;
        }
        .ai-brain-trend {
          margin-left: auto;
          font-size: 10px;
        }
        .ai-brain-trend.up { color: ${COLORS.accentGreen}; }
        .ai-brain-trend.down { color: ${COLORS.warning}; }
        .ai-brain-providers {
          display: flex;
          flex-direction: column;
        }
        .ai-brain-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }
        .ai-brain-panel-header h2 {
          font-size: 12px;
          font-weight: 600;
          margin: 0;
          color: ${COLORS.textPrimary};
          text-transform: uppercase;
          letter-spacing: 1px;
        }
        .ai-brain-panel-count {
          font-size: 10px;
          color: ${COLORS.textDim};
        }
        .ai-brain-provider-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 8px;
        }
        .ai-brain-provider-card {
          background: ${COLORS.panelBg};
          border: 1px solid ${COLORS.panelBorder};
          border-left: 3px solid ${COLORS.primaryDim};
          border-radius: 6px;
          padding: 10px 14px;
          backdrop-filter: blur(8px);
        }
        .ai-brain-provider-name {
          font-size: 13px;
          font-weight: 600;
          color: ${COLORS.textPrimary};
        }
        .ai-brain-provider-meta {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-top: 4px;
          font-size: 10px;
        }
        .ai-brain-provider-model {
          color: ${COLORS.textDim};
        }
        .ai-brain-provider-status {
          font-size: 9px;
        }
        .ai-brain-provider-health {
          margin-top: 6px;
          height: 2px;
          background: rgba(255,255,255,0.05);
          border-radius: 2px;
          overflow: hidden;
        }
        .ai-brain-health-bar {
          height: 100%;
          border-radius: 2px;
          transition: width 0.5s ease;
        }
        .ai-brain-events {
          display: flex;
          flex-direction: column;
        }
        .ai-brain-event-stream {
          display: flex;
          flex-direction: column;
          gap: 4px;
          overflow: auto;
          flex: 1;
        }
        .ai-brain-event-item {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          background: ${COLORS.panelBg};
          border: 1px solid ${COLORS.panelBorder};
          border-radius: 6px;
          padding: 8px 12px;
          font-size: 11px;
        }
        .ai-brain-event-icon {
          color: ${COLORS.accent};
          font-size: 10px;
          margin-top: 1px;
        }
        .ai-brain-event-content {
          flex: 1;
          min-width: 0;
        }
        .ai-brain-event-text {
          color: ${COLORS.textPrimary};
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .ai-brain-event-time {
          font-size: 9px;
          color: ${COLORS.textDim};
          margin-top: 2px;
        }
        .ai-brain-empty {
          color: ${COLORS.textDim};
          font-size: 11px;
          text-align: center;
          padding: 20px;
        }
        .ai-brain-bottombar {
          display: flex;
          align-items: center;
          gap: 20px;
          padding: 8px 24px;
          background: ${COLORS.panelBg};
          border-top: 1px solid ${COLORS.panelBorder};
          backdrop-filter: blur(12px);
          font-size: 10px;
          color: ${COLORS.textDim};
        }
        .ai-brain-status-item {
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .ai-brain-status-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #555;
        }
        .ai-brain-status-dot.active {
          background: ${COLORS.accentGreen};
          box-shadow: 0 0 6px ${COLORS.accentGreen};
        }
      `}</style>
    </div>
  );
}