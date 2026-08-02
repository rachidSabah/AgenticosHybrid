"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Cpu, Zap, Activity, Shield, Sparkles } from "lucide-react";
import { Panel, Stat, StatusDot, Badge } from "@/components/ui/primitives";
import { useStore } from "@/lib/store";

interface AnatomicalAIBrainProps {
  onSelectProvider?: (provider: string | null) => void;
}

export function AnatomicalAIBrain({ onSelectProvider }: AnatomicalAIBrainProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const providers = useStore((s) => s.providers);
  const agents = useStore((s) => s.agents);
  const events = useStore((s) => s.events);

  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const providerList = useMemo(() => Object.values(providers), [providers]);

  const activeProvider = useMemo(() => {
    if (!selected) return null;
    return providers[selected] || providerList.find((p) => p.provider === selected);
  }, [providers, providerList, selected]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 600;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x02040a);
    scene.fog = new THREE.FogExp2(0x02040a, 0.018);

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000);
    camera.position.set(0, 4, 22);

    // 3. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.4;
    container.appendChild(renderer.domElement);

    // 4. Orbit Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.04;
    controls.maxDistance = 50;
    controls.minDistance = 6;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.6;

    // 5. Post-Processing Bloom (Holographic Sci-Fi Glow)
    const renderPass = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), 2.2, 0.45, 0.12);
    const composer = new EffectComposer(renderer);
    composer.addPass(renderPass);
    composer.addPass(bloomPass);

    // 6. Generate 3D Anatomical Human Brain Point Cloud
    // Equations map left & right cerebral hemispheres, gyri/sulci folds, cerebellum, and brainstem.
    const brainGroup = new THREE.Group();
    scene.add(brainGroup);

    const particleCount = 3500;
    const positions: number[] = [];
    const colors: number[] = [];
    const sizes: number[] = [];

    const brainNodesPos: THREE.Vector3[] = [];

    // Color palette: Cyan, Electric Indigo, Magenta, Deep Sky Blue
    const colorOptions = [
      new THREE.Color(0x38bdf8), // Cyan / Sky Blue
      new THREE.Color(0x818cf8), // Electric Indigo
      new THREE.Color(0xc084fc), // Purple / Magenta
      new THREE.Color(0x34d399), // Emerald Teal
    ];

    for (let i = 0; i < particleCount; i++) {
      let x = 0, y = 0, z = 0;
      const isCerebellum = Math.random() < 0.18;
      const isBrainstem = !isCerebellum && Math.random() < 0.1;

      if (isBrainstem) {
        // Brainstem (cylinder-ish bottom center)
        const radius = 0.6 + Math.random() * 0.4;
        const angle = Math.random() * Math.PI * 2;
        x = Math.cos(angle) * radius;
        y = -4.5 + Math.random() * 3.0;
        z = -0.5 + Math.sin(angle) * radius;
      } else if (isCerebellum) {
        // Cerebellum (posterior bottom)
        const u = Math.random() * Math.PI;
        const v = Math.random() * Math.PI * 2;
        const r = 2.2 + Math.sin(u * 8) * 0.15;
        x = r * Math.sin(u) * Math.cos(v) * 1.2;
        y = -3.2 + r * Math.cos(u) * 0.7;
        z = -2.5 + r * Math.sin(u) * Math.sin(v) * 0.9;
      } else {
        // Main Cerebral Hemispheres (Left vs Right)
        const side = Math.random() < 0.5 ? -1 : 1; // Left/Right hemisphere split
        const u = (Math.random() - 0.5) * Math.PI;
        const v = Math.random() * Math.PI * 2;

        // Gyri and Sulci organic fold modulation
        const fold = Math.sin(u * 12) * Math.cos(v * 12) * 0.4;
        const rx = 3.6 + fold;
        const ry = 4.2 + fold * 0.8;
        const rz = 5.2 + fold * 0.9;

        x = (rx * Math.cos(u) * Math.cos(v)) * 0.9 + side * 0.45;
        y = (ry * Math.sin(u)) * 0.9;
        z = (rz * Math.cos(u) * Math.sin(v)) * 0.9;

        // Flatten inner medial longitudinal fissure
        if (Math.abs(x) < 0.5) {
          x *= 0.4;
        }
      }

      const vec = new THREE.Vector3(x, y, z);
      positions.push(x, y, z);
      brainNodesPos.push(vec);

      // Random color & size modulation
      const col = colorOptions[Math.floor(Math.random() * colorOptions.length)];
      colors.push(col.r, col.g, col.b);
      sizes.push(0.12 + Math.random() * 0.22);
    }

    const brainGeometry = new THREE.BufferGeometry();
    brainGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    brainGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));

    const brainMaterial = new THREE.PointsMaterial({
      size: 0.18,
      vertexColors: true,
      transparent: true,
      opacity: 0.85,
      blending: THREE.AdditiveBlending,
    });

    const brainPointCloud = new THREE.Points(brainGeometry, brainMaterial);
    brainGroup.add(brainPointCloud);

    // 7. Synaptic Connecting Lines (Neural Circuit Mesh)
    const linePositions: number[] = [];
    const lineColors: number[] = [];
    const maxConnectDistance = 1.4;

    // Connect close neighbor nodes with synaptic lines
    for (let i = 0; i < brainNodesPos.length; i += 6) {
      for (let j = i + 1; j < brainNodesPos.length; j += 6) {
        const dist = brainNodesPos[i].distanceTo(brainNodesPos[j]);
        if (dist < maxConnectDistance) {
          linePositions.push(
            brainNodesPos[i].x, brainNodesPos[i].y, brainNodesPos[i].z,
            brainNodesPos[j].x, brainNodesPos[j].y, brainNodesPos[j].z
          );

          const c1 = colors[i * 3];
          const c2 = colors[i * 3 + 1];
          const c3 = colors[i * 3 + 2];
          lineColors.push(c1, c2, c3, c1, c2, c3);
        }
      }
    }

    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
    lineGeo.setAttribute("color", new THREE.Float32BufferAttribute(lineColors, 3));

    const lineMat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.25,
      blending: THREE.AdditiveBlending,
    });

    const synapticMesh = new THREE.LineSegments(lineGeo, lineMat);
    brainGroup.add(synapticMesh);

    // 8. Glowing Inner Nucleus Core (Volumetric Core Lighting)
    const coreGeo = new THREE.SphereGeometry(2.2, 32, 32);
    const coreMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    brainGroup.add(coreMesh);

    // 9. Floating Holographic Tech Rings
    const ringGroup = new THREE.Group();
    scene.add(ringGroup);

    for (let r = 0; r < 3; r++) {
      const ringGeo = new THREE.RingGeometry(7 + r * 2.5, 7.1 + r * 2.5, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color: r === 0 ? 0x38bdf8 : r === 1 ? 0xc084fc : 0x34d399,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.3 - r * 0.08,
        blending: THREE.AdditiveBlending,
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.rotation.x = Math.PI / 2 + (r - 1) * 0.2;
      ringMesh.rotation.y = (r - 1) * 0.15;
      ringGroup.add(ringMesh);
    }

    // 10. Provider Brain Star Nodes orbiting the Holographic Brain
    const providerMeshes: THREE.Mesh[] = [];
    const count = providerList.length;

    providerList.forEach((prov, idx) => {
      const angle = (idx / Math.max(1, count)) * Math.PI * 2;
      const radius = 9.5;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(idx * 1.5) * 2;
      const z = Math.sin(angle) * radius;

      // Outer Glowing Provider Sphere
      const pGeo = new THREE.IcosahedronGeometry(0.85, 2);
      const isHealthy = prov.status === "healthy";
      const colorHex = isHealthy ? 0x38bdf8 : prov.status === "degraded" ? 0xfbbf24 : 0xef4444;
      const pColor = new THREE.Color(colorHex);

      const pMat = new THREE.MeshStandardMaterial({
        color: pColor,
        emissive: pColor,
        emissiveIntensity: 1.2,
        wireframe: true,
        transparent: true,
        opacity: 0.9,
      });

      const pMesh = new THREE.Mesh(pGeo, pMat);
      pMesh.position.set(x, y, z);
      pMesh.userData = { id: prov.provider, provider: prov };

      // Inner Solid Core
      const pCoreGeo = new THREE.SphereGeometry(0.4, 16, 16);
      const pCoreMat = new THREE.MeshBasicMaterial({ color: pColor });
      const pCoreMesh = new THREE.Mesh(pCoreGeo, pCoreMat);
      pMesh.add(pCoreMesh);

      // Light emission per provider node
      const pLight = new THREE.PointLight(pColor, 3, 12);
      pLight.position.copy(pMesh.position);

      scene.add(pMesh);
      scene.add(pLight);
      providerMeshes.push(pMesh);

      // Energy curve linking Provider node to Central AI Brain Core
      const curve = new THREE.CatmullRomCurve3([
        new THREE.Vector3(x, y, z),
        new THREE.Vector3(x * 0.5, y * 0.5 + 1.5, z * 0.5),
        new THREE.Vector3(0, 0, 0),
      ]);

      const cPoints = curve.getPoints(24);
      const cGeo = new THREE.BufferGeometry().setFromPoints(cPoints);
      const cMat = new THREE.LineBasicMaterial({
        color: pColor,
        transparent: true,
        opacity: 0.45,
        blending: THREE.AdditiveBlending,
      });
      const cLine = new THREE.Line(cGeo, cMat);
      scene.add(cLine);
    });

    // 11. Raycaster for Hover & Selection
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(providerMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        setHovered(hit.userData.id);
        container.style.cursor = "pointer";
      } else {
        setHovered(null);
        container.style.cursor = "default";
      }
    };

    const handleClick = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(providerMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const id = hit.userData.id;
        setSelected(id);
        onSelectProvider?.(id);
      } else {
        setSelected(null);
        onSelectProvider?.(null);
      }
    };

    renderer.domElement.addEventListener("mousemove", handleMouseMove);
    renderer.domElement.addEventListener("click", handleClick);

    // 12. Animation Loop
    let animationFrameId: number;
    const clock = new THREE.Clock();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      const elapsed = clock.getElapsedTime();

      // Rotate Main Brain
      brainGroup.rotation.y = elapsed * 0.12;

      // Pulse Central Nucleus Core
      const pulse = 1 + Math.sin(elapsed * 2.5) * 0.08;
      coreMesh.scale.set(pulse, pulse, pulse);

      // Rotate Tech Rings
      ringGroup.children.forEach((ring, idx) => {
        ring.rotation.z = elapsed * (0.08 * (idx % 2 === 0 ? 1 : -1));
      });

      // Animate Provider Star Nodes
      providerMeshes.forEach((mesh, idx) => {
        mesh.rotation.x = elapsed * 0.4;
        mesh.rotation.y = elapsed * 0.5 + idx;
        const bScale = 1 + Math.sin(elapsed * 3 + idx) * 0.06;
        mesh.scale.set(bScale, bScale, bScale);
      });

      controls.update();
      composer.render();
    };

    animate();

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
  }, [providerList, onSelectProvider]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-[#02040a] rounded-2xl border border-border/40">
      {/* 3D Anatomical AI Brain Canvas */}
      <div ref={mountRef} className="absolute inset-0 h-full w-full" />

      {/* Top HUD Controls */}
      <div className="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-3 glass px-4 py-2.5 rounded-xl pointer-events-auto border border-border/40 backdrop-blur-md">
          <Brain size={20} className="text-accent animate-pulse" />
          <div>
            <div className="text-xs font-bold tracking-wider uppercase text-text flex items-center gap-2">
              Holographic 3D AI Brain Core
              <span className="rounded bg-accent/20 px-2 py-0.5 text-[9px] text-accent font-mono">
                {providerList.length} Connected Engines
              </span>
            </div>
            <div className="text-[10px] text-faint">
              Anatomical Cerebral Synaptic Mesh · GPU WebGL Bloom Rendering
            </div>
          </div>
        </div>
      </div>

      {/* Hover Card */}
      {hovered && (
        <div className="absolute bottom-6 left-4 pointer-events-none glass px-4 py-3 rounded-2xl border border-accent/40 backdrop-blur-md max-w-xs space-y-1">
          <div className="flex items-center gap-2 text-xs font-bold uppercase text-text">
            <StatusDot status={providers[hovered]?.status || "healthy"} pulse />
            <span>{hovered} Provider Node</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px] text-faint pt-1 border-t border-border/30">
            <div>Latency: <span className="text-text font-mono">{providers[hovered]?.latency_ms?.toFixed(0) || 0}ms</span></div>
            <div>Status: <span className="text-accent font-mono">{providers[hovered]?.status || "healthy"}</span></div>
          </div>
        </div>
      )}

      {/* Selected Provider Inspector */}
      <AnimatePresence>
        {selected && activeProvider && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="absolute top-16 right-4 bottom-6 w-80 glass p-4 rounded-2xl border border-border/40 backdrop-blur-xl overflow-y-auto space-y-4 shadow-2xl pointer-events-auto"
          >
            <div className="flex items-center justify-between border-b border-border/40 pb-3">
              <div>
                <div className="text-sm font-bold text-text uppercase tracking-wider">{activeProvider.provider}</div>
                <div className="text-[10px] text-faint">Neural Provider Telemetry</div>
              </div>
              <button
                onClick={() => setSelected(null)}
                className="text-faint hover:text-text rounded-lg p-1 hover:bg-surface/30"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2">
              <Stat label="Health Status" value={activeProvider.status} tone={activeProvider.status === "healthy" ? "ok" : "warn"} />
              <Stat label="Synaptic Latency" value={`${activeProvider.latency_ms.toFixed(0)} ms`} />
            </div>

            <Panel title="Neural Capability Scores" className="text-xs space-y-2">
              {["System Architecture", "Code Generation", "Reasoning & Logic", "Verification"].map((sk) => (
                <div key={sk} className="flex items-center justify-between text-faint">
                  <span>{sk}</span>
                  <span className="text-accent font-mono font-bold">99%</span>
                </div>
              ))}
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
    </div>
  );
}

export default AnatomicalAIBrain;
