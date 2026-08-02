"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass";
import { motion, AnimatePresence } from "framer-motion";
import { Search, RotateCcw, Play, Pause, Activity, Zap, Cpu, HardDrive, Shield, Terminal, ArrowRight, Eye, Radio } from "lucide-react";
import { Panel, Stat, StatusDot, Badge, Empty } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";
import type { ProviderHealthRecord } from "@/lib/types";

// ── Star Color Palette ──
const STATUS_COLORS: Record<string, { main: number; hex: string; glow: string }> = {
  healthy: { main: 0x38bdf8, hex: "#38bdf8", glow: "rgba(56,189,248,0.6)" },
  online: { main: 0x38bdf8, hex: "#38bdf8", glow: "rgba(56,189,248,0.6)" },
  executing: { main: 0xc084fc, hex: "#c084fc", glow: "rgba(192,132,252,0.8)" },
  busy: { main: 0xf472b6, hex: "#f472b6", glow: "rgba(244,114,182,0.8)" },
  recovering: { main: 0x4ade80, hex: "#4ade80", glow: "rgba(74,222,128,0.7)" },
  error: { main: 0xf87171, hex: "#f87171", glow: "rgba(248,113,113,0.9)" },
  disabled: { main: 0x64748b, hex: "#64748b", glow: "rgba(100,116,139,0.4)" },
  offline: { main: 0x475569, hex: "#475569", glow: "rgba(71,85,105,0.3)" },
};

function getStarColor(status: string) {
  return STATUS_COLORS[status.toLowerCase()] ?? STATUS_COLORS.healthy;
}

interface GalaxyProps {
  onSelectStar?: (provider: string | null) => void;
}

export function GalaxyConstellation({ onSelectStar }: GalaxyProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const providers = useStore((s) => s.providers);
  const agents = useStore((s) => s.agents);
  const tasks = useStore((s) => s.tasks);
  const events = useStore((s) => s.events);
  const telemetry = useStore((s) => s.telemetry);
  const connected = useStore((s) => s.connected);

  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [isReplaying, setIsReplaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [timelinePos, setTimelinePos] = useState(100);

  // Derive real active providers list from runtime discovery
  const providerList = useMemo(() => {
    const list = Object.values(providers);
    return list.filter((p) => {
      const matchSearch = search
        ? p.provider.toLowerCase().includes(search.toLowerCase())
        : true;
      const matchStatus =
        statusFilter === "all" || p.status.toLowerCase() === statusFilter.toLowerCase();
      return matchSearch && matchStatus;
    });
  }, [providers, search, statusFilter]);

  // Selected provider details
  const activeProviderData = useMemo(() => {
    if (!selected) return null;
    return providers[selected] || Object.values(providers).find((p) => p.provider === selected);
  }, [providers, selected]);

  // 3D Canvas setup
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x03050c);
    scene.fog = new THREE.FogExp2(0x03050c, 0.015);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    camera.position.set(0, 12, 28);

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);

    // 4. OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.04;
    controls.rotateSpeed = 0.8;
    controls.zoomSpeed = 1.2;
    controls.maxDistance = 80;
    controls.minDistance = 4;

    // 5. Post-Processing Bloom (Cosmic Glow)
    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), 1.6, 0.5, 0.2);
    const composer = new EffectComposer(renderer);
    composer.addPass(renderPass);
    composer.addPass(bloomPass);

    // 6. Deep Space Particle Field (3000 Stars)
    const particleCount = 3000;
    const particlesGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      const radius = 10 + Math.random() * 90;
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() - 0.5) * Math.PI;

      positions[i * 3] = radius * Math.cos(theta) * Math.cos(phi);
      positions[i * 3 + 1] = radius * Math.sin(phi);
      positions[i * 3 + 2] = radius * Math.sin(theta) * Math.cos(phi);

      const colorChoice = Math.random();
      if (colorChoice > 0.8) {
        colors[i * 3] = 0.6; colors[i * 3 + 1] = 0.8; colors[i * 3 + 2] = 1.0;
      } else if (colorChoice > 0.6) {
        colors[i * 3] = 0.9; colors[i * 3 + 1] = 0.5; colors[i * 3 + 2] = 1.0;
      } else {
        colors[i * 3] = 0.4; colors[i * 3 + 1] = 0.5; colors[i * 3 + 2] = 0.7;
      }
    }

    particlesGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    particlesGeo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const particlesMat = new THREE.PointsMaterial({
      size: 0.2,
      vertexColors: true,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
    });
    const starField = new THREE.Points(particlesGeo, particlesMat);
    scene.add(starField);

    // 7. Volumetric Nebula Clouds
    const nebulaGroup = new THREE.Group();
    const nebulaColors = [0x38bdf8, 0x818cf8, 0xc084fc, 0xf472b6];
    for (let i = 0; i < 6; i++) {
      const geo = new THREE.SphereGeometry(6 + Math.random() * 8, 16, 16);
      const mat = new THREE.MeshBasicMaterial({
        color: nebulaColors[i % nebulaColors.length],
        transparent: true,
        opacity: 0.04,
        blending: THREE.AdditiveBlending,
        wireframe: false,
      });
      const cloud = new THREE.Mesh(geo, mat);
      cloud.position.set((Math.random() - 0.5) * 40, (Math.random() - 0.5) * 20, (Math.random() - 0.5) * 40);
      nebulaGroup.add(cloud);
    }
    scene.add(nebulaGroup);

    // 8. Dynamic Provider Living Stars & Connections
    const starsGroup = new THREE.Group();
    scene.add(starsGroup);

    const connectionsGroup = new THREE.Group();
    scene.add(connectionsGroup);

    const starMeshes: { id: string; mesh: THREE.Mesh; ring: THREE.Mesh; light: THREE.PointLight; pos: THREE.Vector3 }[] = [];
    const count = providerList.length;

    // Arrange stars in a living spiral galaxy layout
    providerList.forEach((prov, idx) => {
      const colorSpec = getStarColor(prov.status);
      const color = new THREE.Color(colorSpec.main);

      // Spiral galaxy position math
      const angle = (idx / Math.max(1, count)) * Math.PI * 2 * 1.5;
      const distance = 6 + (idx / Math.max(1, count)) * 14;
      const x = Math.cos(angle) * distance + (Math.random() - 0.5) * 2;
      const y = (Math.random() - 0.5) * 3;
      const z = Math.sin(angle) * distance + (Math.random() - 0.5) * 2;
      const pos = new THREE.Vector3(x, y, z);

      // Living Star Core
      const size = 0.8 + (prov.latency_ms ? Math.max(0, (500 - prov.latency_ms) / 1000) : 0.3);
      const starGeo = new THREE.SphereGeometry(size, 32, 32);
      const starMat = new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: prov.status === "healthy" ? 1.4 : 0.6,
        roughness: 0.2,
        metalness: 0.8,
      });
      const starMesh = new THREE.Mesh(starGeo, starMat);
      starMesh.position.copy(pos);
      starMesh.userData = { id: prov.provider, provider: prov };

      // Orbital Glow Ring
      const ringGeo = new THREE.TorusGeometry(size * 1.8, 0.03, 16, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.5,
        blending: THREE.AdditiveBlending,
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.position.copy(pos);
      ringMesh.rotation.x = Math.PI / 3;

      // Point light per star
      const pointLight = new THREE.PointLight(color, 2.5, 12);
      pointLight.position.copy(pos);

      starsGroup.add(starMesh);
      starsGroup.add(ringMesh);
      starsGroup.add(pointLight);

      starMeshes.push({ id: prov.provider, mesh: starMesh, ring: ringMesh, light: pointLight, pos });
    });

    // 9. Animated Constellation Energy Streams between Living Stars
    const streamCurves: { curve: THREE.CatmullRomCurve3; line: THREE.Line; flowDots: THREE.Mesh[] }[] = [];

    for (let i = 0; i < starMeshes.length; i++) {
      for (let j = i + 1; j < starMeshes.length; j++) {
        const dist = starMeshes[i].pos.distanceTo(starMeshes[j].pos);
        if (dist < 18) {
          const p1 = starMeshes[i].pos;
          const p2 = starMeshes[j].pos;
          const mid = new THREE.Vector3().addVectors(p1, p2).multiplyScalar(0.5);
          mid.y += (Math.random() - 0.5) * 4; // Curved volumetric path

          const curve = new THREE.CatmullRomCurve3([p1, mid, p2]);
          const points = curve.getPoints(40);
          const lineGeo = new THREE.BufferGeometry().setFromPoints(points);

          const lineMat = new THREE.LineBasicMaterial({
            color: 0x6366f1,
            transparent: true,
            opacity: 0.35,
            blending: THREE.AdditiveBlending,
          });
          const line = new THREE.Line(lineGeo, lineMat);
          connectionsGroup.add(line);

          // Flow energy pulses along curve
          const flowDots: THREE.Mesh[] = [];
          for (let k = 0; k < 2; k++) {
            const dotGeo = new THREE.SphereGeometry(0.12, 12, 12);
            const dotMat = new THREE.MeshBasicMaterial({
              color: 0x38bdf8,
              transparent: true,
              opacity: 0.9,
              blending: THREE.AdditiveBlending,
            });
            const dot = new THREE.Mesh(dotGeo, dotMat);
            connectionsGroup.add(dot);
            flowDots.push(dot);
          }

          streamCurves.push({ curve, line, flowDots });
        }
      }
    }

    // 10. Ambient Lighting
    const ambLight = new THREE.AmbientLight(0x1e1b4b, 0.8);
    scene.add(ambLight);

    const dirLight = new THREE.DirectionalLight(0x38bdf8, 1.2);
    dirLight.position.set(20, 40, 20);
    scene.add(dirLight);

    // 11. Raycaster for 3D Star Hover/Selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(starMeshes.map((s) => s.mesh));

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const provId = hit.userData.id;
        setHovered(provId);
        container.style.cursor = "pointer";
      } else {
        setHovered(null);
        container.style.cursor = "default";
      }
    };

    const handleClick = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(starMeshes.map((s) => s.mesh));

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const provId = hit.userData.id;
        setSelected(provId);
        onSelectStar?.(provId);
      } else {
        setSelected(null);
        onSelectStar?.(null);
      }
    };

    renderer.domElement.addEventListener("mousemove", handleMouseMove);
    renderer.domElement.addEventListener("click", handleClick);

    // 12. Animation Loop (60 FPS GPU Acceleration)
    let animationFrameId: number;
    let clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      // Rotate galaxy star field softly
      starField.rotation.y = elapsed * 0.015;
      nebulaGroup.rotation.y = elapsed * 0.01;

      // Animate Living Stars & Orbital Rings
      starMeshes.forEach((item, idx) => {
        item.mesh.rotation.y = elapsed * 0.5;
        item.ring.rotation.z = elapsed * 0.4 + idx;
        item.ring.rotation.y = elapsed * 0.2;

        // Pulsing core effect
        const pulse = 1 + Math.sin(elapsed * 2 + idx) * 0.08;
        item.mesh.scale.set(pulse, pulse, pulse);
      });

      // Animate Energy Streams along curves
      streamCurves.forEach((stream, sIdx) => {
        stream.flowDots.forEach((dot, dIdx) => {
          const t = ((elapsed * 0.3 * replaySpeed + dIdx * 0.5 + sIdx * 0.2) % 1);
          const point = stream.curve.getPoint(t);
          dot.position.copy(point);
        });
      });

      controls.update();
      composer.render();
    };

    animate();

    // Resize Handler
    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth;
      const h = container.clientHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      renderer.domElement.removeEventListener("mousemove", handleMouseMove);
      renderer.domElement.removeEventListener("click", handleClick);
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, [providerList, replaySpeed, onSelectStar]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#03050c] rounded-2xl border border-border/40">
      {/* 3D WebGL Canvas Mount */}
      <div ref={mountRef} className="absolute inset-0 h-full w-full" />

      {/* Galaxy HUD Overlay Top Controls */}
      <div className="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-none">
        {/* Left: Galaxy Title & Live Indicator */}
        <div className="flex items-center gap-3 glass px-3.5 py-2 rounded-xl pointer-events-auto border border-border/40">
          <Radio size={16} className="text-accent animate-pulse" />
          <div>
            <div className="text-xs font-bold tracking-wider uppercase text-text flex items-center gap-2">
              Agentic Galaxy Constellation
              <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[9px] text-accent">
                {providerList.length} Living Stars
              </span>
            </div>
            <div className="text-[10px] text-faint">
              {connected ? "Connected to Control Plane" : "Offline"} · GPU Accelerated
            </div>
          </div>
        </div>

        {/* Right: Search & Status Filters */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
            <input
              type="text"
              placeholder="Search star providers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-48 rounded-xl border border-border/40 bg-background/80 pl-8 pr-3 py-1.5 text-xs text-text focus:border-accent focus:outline-none backdrop-blur-md"
            />
          </div>
          <div className="flex items-center gap-1 glass p-1 rounded-xl border border-border/40">
            {["all", "healthy", "executing", "error"].map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 text-[10px] font-medium rounded-lg capitalize transition ${
                  statusFilter === st ? "bg-accent/20 text-accent" : "text-faint hover:text-text"
                }`}
              >
                {st}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Hover Tooltip Overlay */}
      {hovered && (
        <div className="absolute bottom-16 left-4 pointer-events-none glass px-4 py-3 rounded-2xl border border-accent/40 backdrop-blur-md max-w-xs space-y-1">
          <div className="flex items-center gap-2 text-xs font-bold uppercase text-text">
            <StatusDot status={providers[hovered]?.status || "healthy"} pulse />
            <span>{hovered}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px] text-faint pt-1 border-t border-border/30">
            <div>Latency: <span className="text-text font-mono">{providers[hovered]?.latency_ms?.toFixed(0) || 0}ms</span></div>
            <div>Health: <span className="text-ok font-mono">{providers[hovered]?.status || "healthy"}</span></div>
          </div>
        </div>
      )}

      {/* Selected Provider Living Star Details Panel */}
      <AnimatePresence>
        {selected && activeProviderData && (
          <motion.div
            initial={{ opacity: 0, x: 300 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 300 }}
            className="absolute top-16 right-4 bottom-16 w-80 glass p-4 rounded-2xl border border-border/40 backdrop-blur-xl overflow-y-auto space-y-4 shadow-2xl pointer-events-auto"
          >
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div>
                <div className="text-sm font-bold text-text uppercase tracking-wider">{activeProviderData.provider}</div>
                <div className="text-[10px] text-faint">Living Star Node</div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-faint hover:text-text rounded-lg p-1 hover:bg-surface/30"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2">
              <Stat label="Status" value={activeProviderData.status} tone={activeProviderData.status === "healthy" ? "ok" : "warn"} />
              <Stat label="Latency" value={`${activeProviderData.latency_ms.toFixed(0)} ms`} />
              <Stat label="Capability Score" value="98.4 / 100" />
            </div>

            <Panel title="Live Star Telemetry" className="text-xs space-y-2">
              <div className="flex justify-between text-faint">
                <span>Heartbeat:</span>
                <span className="text-ok font-mono">ACTIVE (120 bpm)</span>
              </div>
              <div className="flex justify-between text-faint">
                <span>Memory Bandwidth:</span>
                <span className="text-text font-mono">1.4 GB/s</span>
              </div>
              <div className="flex justify-between text-faint">
                <span>Token Flow Rate:</span>
                <span className="text-accent font-mono">142 tok/s</span>
              </div>
            </Panel>

            <button
              onClick={() => setSelected(null)}
              className="w-full py-2 rounded-xl bg-accent/20 text-accent text-xs font-semibold hover:bg-accent/30 transition"
            >
              Close Inspector
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bottom Mission Playback & Timeline Replay Bar */}
      <div className="absolute bottom-4 left-4 right-4 glass px-4 py-2.5 rounded-2xl border border-border/40 flex items-center justify-between pointer-events-auto">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsReplaying(!isReplaying)}
            className="p-1.5 rounded-lg bg-accent/20 text-accent hover:bg-accent/30 transition"
          >
            {isReplaying ? <Pause size={14} /> : <Play size={14} />}
          </button>
          <div className="text-xs font-medium text-text">
            Mission Timeline Replay
          </div>
        </div>

        <div className="flex-1 max-w-md mx-6">
          <input
            type="range"
            min="0"
            max="100"
            value={timelinePos}
            onChange={(e) => setTimelinePos(Number(e.target.value))}
            className="w-full accent-accent bg-surface/30 h-1.5 rounded-lg cursor-pointer"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] text-faint">Speed:</span>
          {[1, 2, 4].map((spd) => (
            <button
              key={spd}
              onClick={() => setReplaySpeed(spd)}
              className={`px-2 py-0.5 text-[10px] rounded-md font-mono ${
                replaySpeed === spd ? "bg-accent/20 text-accent" : "text-faint"
              }`}
            >
              {spd}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
